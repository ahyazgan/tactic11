"""Authenticated tus 1.0 core, creation, expiration and termination subset."""
from __future__ import annotations

import base64
import binascii
import uuid
from email.utils import formatdate
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.auth import get_current_tenant, require_role
from app.db import models
from app.db.session import get_session
from app.reports import review_upload

router = APIRouter(prefix="/match-reports/uploads", tags=["review-uploads"],
                   dependencies=[Depends(get_current_tenant)])
editor = require_role(["admin", "analyst", "coach"])
VERSION = "1.0.0"


def protocol(request: Request) -> None:
    if request.headers.get("Tus-Resumable") != VERSION:
        raise HTTPException(412, "Desteklenmeyen yükleme sürümü.", headers={"Tus-Version": VERSION})


def integer(request: Request, name: str) -> int:
    value = request.headers.get(name, "")
    if not value.isascii() or not value.isdecimal() or len(value) > 16:
        raise HTTPException(400, f"Geçersiz {name}.")
    return int(value)


def headers(item: review_upload.Receipt) -> dict[str, str]:
    return {"Tus-Resumable": VERSION, "Upload-Offset": str(item.offset), "Upload-Length": str(item.length),
            "Upload-Expires": formatdate(item.expires, usegmt=True), "Cache-Control": "private, no-store"}


@router.options("")
def options(user: models.User = Depends(editor)):
    return Response(status_code=204, headers={"Tus-Version": VERSION, "Tus-Resumable": VERSION,
                    "Tus-Extension": "creation,expiration,termination", "Tus-Max-Size": str(review_upload.limit())})


@router.get("")
def pending(user: models.User = Depends(editor)):
    return review_upload.pending(user)


@router.post("", dependencies=[Depends(protocol)])
def create(request: Request, user: models.User = Depends(editor)):
    length = integer(request, "Upload-Length")
    if length < 1 or length > review_upload.limit():
        raise HTTPException(413, "Video boyutu 0'dan büyük ve yükleme sınırı içinde olmalı.")
    metadata = request.headers.get("Upload-Metadata", "")
    if len(metadata) > 4096:
        raise HTTPException(400, "Yükleme bilgisi çok uzun.")
    values: dict[str, str] = {}
    try:
        for pair in metadata.split(","):
            key, encoded = pair.strip().split(" ", 1)
            if key in values:
                raise ValueError("duplicate metadata")
            values[key] = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(400, "Geçersiz yükleme bilgisi.") from exc
    filename = Path(values.get("filename", "video.mp4").replace("\\", "/")).name[:255]
    if Path(filename).suffix.lower() != ".mp4" or any(ord(c) < 32 for c in filename):
        raise HTTPException(422, "H.264 MP4 video seçin.")
    item = review_upload.create(user, filename, length)
    # Relative to the creation URL; works both directly and behind /api rewrites.
    return Response(status_code=201, headers={**headers(item), "Location": f"uploads/{item.id}"})


@router.head("/{upload_id}", dependencies=[Depends(protocol)])
def head(upload_id: uuid.UUID, user: models.User = Depends(editor), session: Session = Depends(get_session)):
    item, _ = review_upload.operate(user, str(upload_id), session)
    return Response(status_code=200, headers=headers(item))


@router.get("/{upload_id}")
def status(upload_id: uuid.UUID, user: models.User = Depends(editor), session: Session = Depends(get_session)):
    item, video = review_upload.operate(user, str(upload_id), session)
    return {**item.model_dump(), "video": video}


@router.patch("/{upload_id}", dependencies=[Depends(protocol)])
async def patch(upload_id: uuid.UUID, request: Request, user: models.User = Depends(editor),
                session: Session = Depends(get_session)):
    if request.headers.get("Content-Type") != "application/offset+octet-stream":
        raise HTTPException(415, "Geçersiz yükleme içerik türü.")
    offset = integer(request, "Upload-Offset")
    if "Content-Length" in request.headers and integer(request, "Content-Length") > review_upload.CHUNK_BYTES:
        raise HTTPException(413, "Yükleme parçası çok büyük.")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > review_upload.CHUNK_BYTES:
            raise HTTPException(413, "Yükleme parçası çok büyük.")
        data.extend(chunk)
    item, _ = await run_in_threadpool(review_upload.operate, user, str(upload_id), session,
                                      chunk=bytes(data), offset=offset)
    return Response(status_code=204, headers=headers(item))


@router.delete("/{upload_id}", dependencies=[Depends(protocol)])
def cancel(upload_id: uuid.UUID, user: models.User = Depends(editor), session: Session = Depends(get_session)):
    review_upload.operate(user, str(upload_id), session, cancel=True)
    return Response(status_code=204, headers={"Tus-Resumable": VERSION})
