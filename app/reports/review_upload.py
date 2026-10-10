"""Durable, bounded tus upload storage on the existing private media volume.

All operations on a receipt take the same OS lock (Windows and Linux). Bytes
are fsynced before the atomic receipt update; a crash before that update leaves
an unacknowledged tail which the next PATCH truncates. Completed source files
are never removed by receipt expiry/cancellation. This is a single shared local
volume backend, not a distributed object-storage implementation.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import portalocker
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.reports import review_media

CHUNK_BYTES = 4 * 1024 * 1024
TTL_SECONDS = 24 * 3600
MAX_PENDING = 3


class Receipt(BaseModel):
    id: str
    filename: str
    length: int
    offset: int = 0
    expires: float
    state: str = "uploading"


def limit() -> int:
    return int(os.environ.get("REVIEW_MAX_UPLOAD_BYTES", str(2 * 1024 ** 3)))


def directory(user: models.User) -> Path:
    folder = review_media.private_dir(user.tenant_id) / "uploads" / hashlib.sha256(user.id.encode()).hexdigest()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@contextmanager
def locked(path: Path) -> Iterator[None]:
    try:
        with portalocker.Lock(str(path.with_suffix(".lock")), mode="a+b", timeout=0):
            yield
    except portalocker.exceptions.LockException as exc:
        raise HTTPException(423, "Yükleme işleniyor; biraz sonra yeniden deneyin.", headers={"Retry-After": "1"}) from exc


def write(path: Path, receipt: Receipt) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(receipt.model_dump_json())
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def read(path: Path) -> Receipt:
    if not path.is_file():
        raise HTTPException(404, "Yükleme bulunamadı. Aynı hesapla aynı dosyayı seçin.")
    receipt = Receipt.model_validate_json(path.read_text(encoding="utf-8"))
    if receipt.expires <= time.time() or receipt.state == "failed":
        raise HTTPException(410, "Yükleme süresi doldu veya dosya geçersiz. Dosyayı yeniden seçin.")
    return receipt


def create(user: models.User, filename: str, length: int) -> Receipt:
    folder = directory(user)
    with locked(folder / "creation.json"):
        pending = 0
        for path in folder.glob("*.json"):
            # Receipts are created by this module only; no source footage here.
            try:
                with locked(path):
                    item = Receipt.model_validate_json(path.read_text(encoding="utf-8"))
                    if item.expires <= time.time() or item.state == "failed":
                        path.with_suffix(".part").unlink(missing_ok=True)
                        path.unlink(missing_ok=True)
                    elif item.state == "uploading":
                        pending += 1
            except HTTPException:
                pending += 1
            except FileNotFoundError:
                # A concurrent cancellation may remove a listed receipt before
                # this process acquires its lock.
                continue
        if pending >= MAX_PENDING:
            raise HTTPException(409, "Üç yarım yüklemeniz var. Yükleme listesinden tamamlayın veya iptal edin.")
        item = Receipt(id=str(uuid.uuid4()), filename=filename, length=length, expires=time.time() + TTL_SECONDS)
        write(folder / f"{item.id}.json", item)
        return item


def video_out(video: models.ReviewVideo) -> dict:
    return {"id": video.id, "filename": video.filename, "duration_seconds": video.duration_seconds,
            "size_bytes": video.size_bytes}


def complete(path: Path, item: Receipt, user: models.User, session: Session) -> dict | None:
    if item.offset != item.length:
        return None
    # Idempotent recovery after DB commit but before receipt commit/HTTP reply.
    video = session.scalars(select(models.ReviewVideo).where(
        models.ReviewVideo.id == item.id, models.ReviewVideo.tenant_id == user.tenant_id,
    )).first()
    if video is None:
        destination = review_media.asset_path(user.tenant_id, item.id)
        source = destination if destination.exists() else path.with_suffix(".part")
        if not source.is_file() or source.stat().st_size != item.length:
            raise HTTPException(409, "Yükleme dosyası eksik. Yüklemeyi iptal edip yeniden seçin.")
        try:
            duration = review_media.probe_video(source)
        except review_media.MediaError as exc:
            item.state = "failed"
            write(path, item)
            path.with_suffix(".part").unlink(missing_ok=True)
            raise HTTPException(422, str(exc)) from exc
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if source != destination:
            source.replace(destination)
        video = models.ReviewVideo(id=item.id, tenant_id=user.tenant_id, filename=item.filename,
                                   size_bytes=item.length, sha256=digest, duration_seconds=duration,
                                   created_at=datetime.now(UTC))
        session.add(video)
        session.commit()
    item.state = "done"
    write(path, item)
    return video_out(video)


def operate(user: models.User, upload_id: str, session: Session, *, chunk: bytes | None = None,
            offset: int | None = None, cancel: bool = False) -> tuple[Receipt, dict | None]:
    path = directory(user) / f"{uuid.UUID(upload_id)}.json"
    # Do not create lock files for arbitrary missing IDs.
    if not path.exists():
        raise HTTPException(404, "Yükleme bulunamadı.")
    with locked(path):
        if cancel:
            if not path.is_file():
                raise HTTPException(404, "Yükleme bulunamadı.")
            item = Receipt.model_validate_json(path.read_text(encoding="utf-8"))
            if review_media.asset_path(user.tenant_id, item.id).exists():
                raise HTTPException(409, "Video tamamlanmış; kaynak video iptal edilemez.")
            path.with_suffix(".part").unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            return item, None
        item = read(path)
        if chunk is not None:
            if offset != item.offset:
                raise HTTPException(409, "Yükleme konumu değişti.", headers={"Upload-Offset": str(item.offset)})
            if len(chunk) > CHUNK_BYTES or item.offset + len(chunk) > item.length:
                raise HTTPException(413, "Yükleme parçası sınırı aşıyor.")
            if item.state != "done":
                part = path.with_suffix(".part")
                if not part.exists() and item.offset:
                    # A crash after rename is recovered by complete(), never append to the source.
                    if item.offset == item.length and not chunk:
                        return item, complete(path, item, user, session)
                    raise HTTPException(409, "Yükleme dosyası eksik; iptal edip yeniden başlayın.")
                with part.open("r+b" if part.exists() else "w+b") as stream:
                    if os.fstat(stream.fileno()).st_size < item.offset:
                        raise HTTPException(409, "Yükleme dosyası eksik; iptal edip yeniden başlayın.")
                    stream.truncate(item.offset)
                    stream.seek(item.offset)
                    stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                item.offset += len(chunk)
                write(path, item)
        video = complete(path, item, user, session)
        return item, video


def pending(user: models.User) -> list[dict]:
    result = []
    for path in directory(user).glob("*.json"):
        try:
            with locked(path):
                item = read(path)
                if item.state == "uploading":
                    result.append(json.loads(item.model_dump_json()))
        except HTTPException:
            continue
    return result
