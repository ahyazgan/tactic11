"""Real tus requests, crash recovery, owner boundaries and file integrity."""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import time

import pytest
from sqlalchemy import select

from app.db import models
from app.reports import review_media, review_upload
from tests.test_match_reports import environment as environment
from tests.test_match_reports import headers


def tus(**extra):
    return {**headers(), "Tus-Resumable": "1.0.0", **extra}


def create(client, length=12, name="match.mp4"):
    result = client.post("/match-reports/uploads", headers=tus(**{
        "Upload-Length": str(length), "Upload-Metadata": "filename " + base64.b64encode(name.encode()).decode(),
    }))
    assert result.status_code == 201, result.text
    return "/match-reports/" + result.headers["location"]


def patch(client, url, data, offset):
    return client.patch(url, headers=tus(**{"Upload-Offset": str(offset), "Content-Type": "application/offset+octet-stream"}), content=data)


def test_resume_persists_offset_and_verifies_all_bytes(environment, monkeypatch, session):
    client, users, _ = environment
    monkeypatch.setattr(review_media, "probe_video", lambda path: 30.0)
    url = create(client, name="../../maç.mp4")
    assert patch(client, url, b"hello ", 0).status_code == 204
    head = client.head(url, headers=tus())
    assert head.status_code == 200 and head.headers["Upload-Offset"] == "6"
    assert "no-store" in head.headers["cache-control"]
    assert "Upload-Expires" in head.headers
    # No in-memory upload state is used: a fresh reader sees the durable receipt.
    item = review_upload.pending(users[("alpha", "analyst")])[0]
    assert item["offset"] == 6
    assert client.get("/match-reports/videos", headers=headers()).json() == []
    assert patch(client, url, b"world!", 6).status_code == 204
    result = client.get(url, headers=headers()).json()
    assert result["video"]["filename"] == "maç.mp4"
    row = session.get(models.ReviewVideo, result["id"])
    assert row.sha256 == hashlib.sha256(b"hello world!").hexdigest()
    assert review_media.asset_path("alpha", row.id).read_bytes() == b"hello world!"
    assert client.head(url, headers=tus()).headers["Upload-Offset"] == "12"
    assert len(session.scalars(select(models.ReviewVideo)).all()) == 1
    assert client.get("/match-reports/uploads", headers=headers()).json() == []
    assert client.delete(url, headers=tus()).status_code == 409
    assert review_media.asset_path("alpha", row.id).is_file()


def test_offsets_and_owner_boundaries_cannot_overwrite(environment):
    client, _, _ = environment
    url = create(client)
    assert patch(client, url, b"abc", 0).status_code == 204
    assert patch(client, url, b"bad", 0).status_code == 409
    assert patch(client, url, b"x" * 12, 3).status_code == 413
    assert client.head(url, headers=tus()).headers["Upload-Offset"] == "3"
    for auth, status in [({}, 401), (headers("beta"), 404), (headers(role="coach"), 404), (headers(role="viewer"), 403)]:
        for method in ("head", "get", "delete"):
            assert getattr(client, method)(url, headers={**auth, "Tus-Resumable": "1.0.0"}).status_code == status
    assert client.get("/match-reports/uploads", headers=headers("beta")).json() == []


def test_tus_protocol_rejects_malformed_or_oversized_input(environment, monkeypatch):
    client, _, _ = environment
    assert client.options("/match-reports/uploads", headers=headers()).headers["Tus-Extension"] == "creation,expiration,termination"
    bad = client.post("/match-reports/uploads", headers=headers())
    assert bad.status_code == 412 and bad.headers["Tus-Version"] == "1.0.0"
    monkeypatch.setenv("REVIEW_MAX_UPLOAD_BYTES", "100")
    for length, code in [("101", 413), ("0", 413), ("-1", 400), ("1.5", 400)]:
        response = client.post("/match-reports/uploads", headers=tus(**{"Upload-Length": length}))
        assert response.status_code == code
    assert client.post("/match-reports/uploads", headers=tus(**{"Upload-Length": "12", "Upload-Metadata": "filename $$$"})).status_code == 400
    url = create(client)
    assert client.patch(url, headers=tus(**{"Upload-Offset": "0"}), content=b"a").status_code == 415
    monkeypatch.setattr(review_upload, "CHUNK_BYTES", 2)
    assert patch(client, url, b"abc", 0).status_code == 413
    assert client.head(url, headers=tus()).headers["Upload-Offset"] == "0"


def test_failed_media_is_never_published(environment, monkeypatch):
    client, users, _ = environment
    def invalid(path):
        raise review_media.MediaError("Geçersiz MP4.")
    monkeypatch.setattr(review_media, "probe_video", invalid)
    url = create(client, 3)
    assert patch(client, url, b"bad", 0).status_code == 422
    assert client.head(url, headers=tus()).status_code == 410
    assert client.get("/match-reports/videos", headers=headers()).json() == []
    assert not list(review_upload.directory(users[("alpha", "analyst")]).glob("*.part"))


def test_crash_tail_is_discarded_and_renamed_source_is_recovered(environment, monkeypatch, session):
    client, users, _ = environment
    user = users[("alpha", "analyst")]
    monkeypatch.setattr(review_media, "probe_video", lambda path: 30.0)
    url = create(client, 6)
    upload_id = url.rsplit("/", 1)[1]
    path = review_upload.directory(user) / f"{upload_id}.json"
    assert patch(client, url, b"abc", 0).status_code == 204
    # Process died after byte write, before recording the new offset.
    with path.with_suffix(".part").open("ab") as stream:
        stream.write(b"unacknowledged tail")
    real_commit = session.commit
    def crash():
        raise RuntimeError("simulated process loss after rename")
    monkeypatch.setattr(session, "commit", crash)
    with pytest.raises(RuntimeError):
        review_upload.operate(user, upload_id, session, chunk=b"def", offset=3)
    session.rollback()
    monkeypatch.setattr(session, "commit", real_commit)
    result = client.get(url, headers=headers())
    assert result.status_code == 200
    assert result.json()["video"]["size_bytes"] == 6
    assert review_media.asset_path("alpha", upload_id).read_bytes() == b"abcdef"
    assert client.head(url, headers=tus()).status_code == 200
    assert len(session.scalars(select(models.ReviewVideo)).all()) == 1


def test_pending_quota_expiry_and_cancel_only_remove_staging(environment):
    client, users, _ = environment
    urls = [create(client) for _ in range(3)]
    assert client.post("/match-reports/uploads", headers=tus(**{"Upload-Length": "12", "Upload-Metadata": "filename bWF0Y2gubXA0"})).status_code == 409
    assert patch(client, urls[0], b"abc", 0).status_code == 204
    assert client.delete(urls[0], headers=tus()).status_code == 204
    assert client.head(urls[0], headers=tus()).status_code == 404
    path = review_upload.directory(users[("alpha", "analyst")]) / (urls[1].rsplit("/", 1)[1] + ".json")
    value = json.loads(path.read_text())
    value["expires"] = time.time() - 1
    path.write_text(json.dumps(value))
    assert client.head(urls[1], headers=tus()).status_code == 410
    create(client)
    assert not path.exists()
    assert len(client.get("/match-reports/uploads", headers=headers()).json()) == 2


def test_real_other_process_lock_refuses_concurrent_patch(environment):
    client, users, tmp_path = environment
    url = create(client)
    path = review_upload.directory(users[("alpha", "analyst")]) / (url.rsplit("/", 1)[1] + ".lock")
    marker = tmp_path / "lock-ready"
    command = [sys.executable, "-c",
               "import portalocker,sys,time,pathlib; "
               "lock=portalocker.Lock(sys.argv[1],mode='a+b',timeout=0); lock.acquire(); "
               "pathlib.Path(sys.argv[2]).touch(); time.sleep(20)", str(path), str(marker)]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(.05)
        assert marker.exists()
        assert patch(client, url, b"abc", 0).status_code == 423
    finally:
        process.terminate()
        process.wait(timeout=5)
    assert patch(client, url, b"abc", 0).status_code == 204
