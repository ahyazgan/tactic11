"""Real auth, cross-club boundaries, approval lifecycle and delivery failure cases."""
from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.api import match_reports
from app.api.main import app
from app.auth.jwt_tokens import create_access_token
from app.db import models
from app.db.session import get_session
from app.reports import review_export, review_media


@pytest.fixture()
def environment(session, monkeypatch, tmp_path):
    monkeypatch.setenv("REVIEW_DATA_DIR", str(tmp_path))
    users = {}
    for club in ("alpha", "beta"):
        session.add(models.Tenant(id=club, slug=club, name=club, active=True,
                                  settings_json="{}", created_at=datetime.now(UTC)))
        for role in ("admin", "analyst", "coach", "viewer"):
            user = models.User(id=f"{club}-{role}", tenant_id=club, email=f"{role}@{club}.test",
                               password_hash="unused", role=role, active=True, created_at=datetime.now(UTC))
            users[(club, role)] = user
            session.add(user)
    session.commit()

    def session_override():
        yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        yield client, users, tmp_path
    app.dependency_overrides.clear()


def headers(club="alpha", role="analyst"):
    token = create_access_token(user_id=f"{club}-{role}", tenant_id=club, role=role)
    return {"Authorization": f"Bearer {token}"}


def upload(client, monkeypatch, club="alpha", data=b"original-source", name="match.mp4"):
    monkeypatch.setattr(review_media, "probe_video", lambda path: 30.0)
    response = client.post("/match-reports/videos", headers=headers(club),
                           files={"file": (name, data, "video/mp4")})
    assert response.status_code == 201, response.text
    return response.json()


def create(client, video):
    response = client.post("/match-reports", headers=headers(),
                           json={"video_id": video["id"], "title": "U17 - gerçek maç incelemesi"})
    assert response.status_code == 201, response.text
    return response.json()


def document():
    return {"club": "Örnek takım", "opponent": "Rakip", "match_date": "2026-10-10",
            "summary": "Seçilen bölümdeki gözlem; tam maç istatistiği değildir.",
            "strengths": "Görüntüde doğrulanan olumlu hareket.", "scope": "selected_segments",
            "training_focus": ["Destek oyuncusunun görevini netleştirme."],
            "findings": [{"id": str(uuid.uuid4()), "start": 1.0, "end": 3.0, "category": "transition",
                          "title": "Geri dönüş", "observation": "Destek gecikiyor.", "action": "Alan paylaşımı çalışması.",
                          "player": "", "next_check": "Sonraki maçta aynı görevi gözlemle."}]}


def save(client, report, content=None, **overrides):
    return client.put(f"/match-reports/{report['id']}", headers=headers(),
                      json={"version": report["version"], "title": report["title"],
                            "document": content or document(), **overrides})


def approve(client, report):
    response = client.post(f"/match-reports/{report['id']}/approve", headers=headers(),
                           json={"version": report["version"]})
    assert response.status_code == 200, response.text
    return response.json()


def test_private_upload_uses_distinct_ids_and_never_overwrites(environment, monkeypatch):
    client, _, _ = environment
    first = upload(client, monkeypatch, name="../../match.mp4")
    second = upload(client, monkeypatch, data=b"second", name="match.mp4")
    other = upload(client, monkeypatch, "beta")
    assert first["id"] != second["id"]
    assert first["filename"] == "match.mp4"
    assert review_media.asset_path("alpha", first["id"]).read_bytes() == b"original-source"
    listed = client.get("/match-reports/videos", headers=headers()).json()
    assert {v["id"] for v in listed} == {first["id"], second["id"]}
    assert client.get(f"/match-reports/videos/{other['id']}/content", headers=headers()).status_code == 404
    response = client.get(f"/match-reports/videos/{first['id']}/content", headers=headers(),
                          )
    assert response.content == b"original-source"
    assert response.headers["cache-control"] == "private, no-store"


def test_no_anonymous_access_and_viewer_cannot_mutate(environment, monkeypatch):
    client, _, _ = environment
    assert client.get("/match-reports").status_code == 401
    response = client.post("/match-reports/videos", headers=headers(role="viewer"),
                           files={"file": ("video.mp4", b"x", "video/mp4")})
    assert response.status_code == 403
    report = create(client, upload(client, monkeypatch))
    for method, path, payload in [
        ("put", f"/match-reports/{report['id']}", {"version": 1, "title": "x", "document": document()}),
        ("post", f"/match-reports/{report['id']}/approve", {"version": 1}),
        ("post", f"/match-reports/{report['id']}/exports", {"version": 1}),
    ]:
        assert getattr(client, method)(path, headers=headers(role="viewer"), json=payload).status_code == 403


def test_oversized_invalid_and_empty_uploads_leave_no_files(environment, monkeypatch):
    client, _, _ = environment
    monkeypatch.setenv("REVIEW_MAX_UPLOAD_BYTES", "4")
    assert client.post("/match-reports/videos", headers=headers(),
                       files={"file": ("x.mp4", b"12345")}).status_code == 413
    assert list(review_media.private_dir("alpha").iterdir()) == []
    assert client.post("/match-reports/videos", headers=headers(),
                       files={"file": ("x.html", b"x")}).status_code == 422
    monkeypatch.setattr(review_media, "probe_video", lambda path: (_ for _ in ()).throw(review_media.MediaError("invalid")))
    assert client.post("/match-reports/videos", headers=headers(),
                       files={"file": ("x.mp4", b"bad")}).status_code == 422
    assert list(review_media.private_dir("alpha").iterdir()) == []
    assert client.get("/match-reports/videos", headers=headers()).json() == []


def test_report_cannot_bind_another_clubs_video(environment, monkeypatch):
    client, _, _ = environment
    video = upload(client, monkeypatch, "beta")
    assert client.post("/match-reports", headers=headers(),
                       json={"video_id": video["id"], "title": "x"}).status_code == 404
    report = create(client, upload(client, monkeypatch))
    for path in (f"/match-reports/{report['id']}", f"/match-reports/{report['id']}/pdf",
                 f"/match-reports/{report['id']}/exports"):
        assert client.get(path, headers=headers("beta")).status_code == 404
    assert client.get("/match-reports", headers=headers("beta")).json() == []


def test_approval_and_editing_require_current_version(environment, monkeypatch):
    client, _, _ = environment
    report = create(client, upload(client, monkeypatch))
    base = f"/match-reports/{report['id']}"
    assert client.get(f"{base}/pdf", headers=headers()).status_code == 409
    assert client.post(f"{base}/approve", headers=headers(), json={"version": 1}).status_code == 422
    saved = save(client, report).json()
    assert saved["version"] == 2 and saved["reviewed_at"] is None
    assert save(client, report).status_code == 409
    assert client.post(f"{base}/approve", headers=headers(), json={"version": 1}).status_code == 409
    approved = approve(client, saved)
    assert approved["reviewed_by"] == "alpha-analyst" and approved["version"] == 3
    assert datetime.fromisoformat(approved["reviewed_at"]).utcoffset() == timedelta(0)
    pdf = client.get(f"{base}/pdf", headers=headers(role="viewer"))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    changed = save(client, approved).json()
    assert changed["reviewed_at"] is None and changed["reviewed_by"] is None
    assert client.get(f"{base}/pdf", headers=headers()).status_code == 409


@pytest.mark.parametrize("start,end", [(-1, 2), (3, 2), (1, 1.1), (0, 130), (29, 31)])
def test_invalid_source_intervals_rejected(environment, monkeypatch, start, end):
    client, _, _ = environment
    report = create(client, upload(client, monkeypatch))
    content = document()
    content["findings"][0].update(start=start, end=end)
    assert save(client, report, content).status_code == 422


def test_duplicate_findings_and_unknown_fields_rejected(environment, monkeypatch):
    client, _, _ = environment
    report = create(client, upload(client, monkeypatch))
    content = document()
    content["findings"].append(content["findings"][0].copy())
    assert save(client, report, content).status_code == 422
    content = document()
    content["reviewed_by"] = "invented-reviewer"
    assert save(client, report, content).status_code == 422


def test_playback_token_scoped_expiring_and_revoked_with_user(environment, monkeypatch):
    client, users, _ = environment
    video = upload(client, monkeypatch)
    other = upload(client, monkeypatch, "beta")
    path = client.post(f"/match-reports/videos/{video['id']}/playback", headers=headers()).json()["path"]
    assert client.get(path).content == b"original-source"
    assert client.get(path.replace(video["id"], other["id"])).status_code == 401
    token = path.split("access=", 1)[1]
    assert client.get("/match-reports", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    claims = jwt.decode(token, match_reports._playback_secret(), algorithms=["HS256"], audience="review-video")
    claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    expired = jwt.encode(claims, match_reports._playback_secret(), algorithm="HS256")
    assert client.get(f"/review-media/{video['id']}?access={expired}").status_code == 401
    users[("alpha", "analyst")].active = False
    assert client.get(path).status_code == 401


def test_export_uses_approved_snapshot_and_is_private(environment, monkeypatch, session):
    client, _, _ = environment
    video = upload(client, monkeypatch)
    report = approve(client, save(client, create(client, video)).json())
    queued = []
    monkeypatch.setattr(review_export, "enqueue_export", lambda *args: queued.append(args) or True)
    monkeypatch.setattr(review_export, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(review_export, "cut_clip", lambda src, dest, start, end: dest.write_bytes(b"clip"))
    base = f"/match-reports/{report['id']}"
    response = client.post(f"{base}/exports", headers=headers(), json={"version": report["version"]})
    assert response.status_code == 202
    job_id = response.json()["id"]
    path = f"{base}/exports/{job_id}"
    assert client.get(path, headers=headers("beta")).status_code == 404
    assert client.get(f"{path}/download", headers=headers()).status_code == 409
    assert client.post(f"{base}/exports", headers=headers(), json={"version": report["version"]}).status_code == 409
    edited = document()
    edited["summary"] = "New draft must not alter the export snapshot"
    assert save(client, report, edited).status_code == 200
    review_export.run_export(*queued[0])
    session.expire_all()
    assert client.get(path, headers=headers()).json()["state"] == "done"
    response = client.get(f"{path}/download", headers=headers(role="viewer"))
    assert response.status_code == 200 and response.content[:2] == b"PK"
    with zipfile.ZipFile(review_media.asset_path("alpha", job_id, ".zip")) as archive:
        assert set(archive.namelist()) == {"report.pdf", "index.html", "manifest.json", "clips/01.mp4"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["document"]["summary"] != edited["summary"]
        assert manifest["version"] == report["version"]
        assert manifest["source_hash"] == hashlib.sha256(b"original-source").hexdigest()
    assert client.get(f"{path}/download", headers=headers("beta")).status_code == 404


def test_export_detects_replaced_source_and_records_failure(environment, monkeypatch, session):
    client, _, _ = environment
    video = upload(client, monkeypatch)
    report = approve(client, save(client, create(client, video)).json())
    queued = []
    monkeypatch.setattr(review_export, "enqueue_export", lambda *args: queued.append(args) or True)
    monkeypatch.setattr(review_export, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False))
    job = client.post(f"/match-reports/{report['id']}/exports", headers=headers(), json={"version": report["version"]}).json()
    review_media.asset_path("alpha", video["id"]).write_bytes(b"changed")
    review_export.run_export(*queued[0])
    session.expire_all()
    response = client.get(f"/match-reports/{report['id']}/exports/{job['id']}", headers=headers()).json()
    assert response["state"] == "failed" and "değişti" in response["error"]
    assert not review_media.asset_path("alpha", job["id"], ".zip").exists()


def test_real_ffmpeg_probe_clip_and_corrupt_input(tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run([review_media.ffmpeg(), "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=320x180:rate=25:duration=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
                   check=True, timeout=30, capture_output=True)
    assert review_media.probe_video(source) == pytest.approx(4, abs=.1)
    clip = tmp_path / "clip.mp4"
    review_media.cut_clip(source, clip, 1, 2.5)
    assert review_media.probe_video(clip) == pytest.approx(1.5, abs=.1)
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")
    with pytest.raises(review_media.MediaError):
        review_media.probe_video(broken)
    incompatible = tmp_path / "mpeg4.mp4"
    subprocess.run([review_media.ffmpeg(), "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=size=64x64:rate=10:duration=1", "-c:v", "mpeg4", str(incompatible)],
                   check=True, timeout=30, capture_output=True)
    with pytest.raises(review_media.MediaError, match="H.264"):
        review_media.probe_video(incompatible)


def test_clip_starts_at_selected_frame_and_seeks_late_in_long_video(tmp_path):
    source = tmp_path / "colors.mp4"
    subprocess.run([review_media.ffmpeg(), "-nostdin", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=red:s=64x64:r=10:d=2",
                    "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=10:d=2",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
                   check=True, timeout=30, capture_output=True)
    clip = tmp_path / "blue.mp4"
    review_media.cut_clip(source, clip, 2.2, 3.2)
    pixel = subprocess.run([review_media.ffmpeg(), "-nostdin", "-loglevel", "error", "-i", str(clip),
                            "-vf", "scale=1:1", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                           check=True, timeout=30, capture_output=True).stdout
    assert pixel[2] > 200 and pixel[0] < 30  # Blue segment; ignoring seek would produce red.
    long_source = tmp_path / "ninety-minutes.mp4"
    subprocess.run([review_media.ffmpeg(), "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=green:s=64x64:r=1:d=5400", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(long_source)],
                   check=True, timeout=30, capture_output=True)
    assert review_media.probe_video(long_source) == pytest.approx(5400, abs=.1)
    late_clip = tmp_path / "late.mp4"
    review_media.cut_clip(long_source, late_clip, 5395, 5398)
    assert review_media.probe_video(late_clip) == pytest.approx(3, abs=.1)


def test_html_escapes_authored_content():
    data = document()
    data["summary"] = "<script>alert('x')</script>"
    snapshot = {"title": "<img src=x>", "document": data, "reviewer": "Analist", "version": 2}
    html = review_export.html_report(snapshot)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<img src=x>" not in html


@pytest.mark.parametrize("state", ["queued", "running"])
def test_interrupted_exports_expire_on_poll_and_can_be_retried(environment, monkeypatch, session, state):
    client, _, _ = environment
    report = approve(client, save(client, create(client, upload(client, monkeypatch))).json())
    queued = []
    monkeypatch.setattr(review_export, "enqueue_export", lambda *args: queued.append(args) or True)
    monkeypatch.setattr(review_export, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False))
    base = f"/match-reports/{report['id']}/exports"
    job_id = client.post(base, headers=headers(), json={"version": report["version"]}).json()["id"]
    job = session.get(models.ReviewExport, job_id)
    job.state = state
    job.updated_at = datetime.now(UTC) - timedelta(seconds=review_export.LEASE_SECONDS + 1)
    session.commit()
    polled = client.get(f"{base}/{job_id}", headers=headers()).json()
    assert polled["state"] == "failed" and "kesildi" in polled["error"]
    # A delayed worker must not revive an expired job or publish its files.
    review_export.run_export(*queued[0])
    session.expire_all()
    assert session.get(models.ReviewExport, job_id).state == "failed"
    assert client.post(base, headers=headers(), json={"version": report["version"]}).status_code == 202


def test_database_rejects_concurrent_active_exports(environment, monkeypatch, session):
    client, _, _ = environment
    report = approve(client, save(client, create(client, upload(client, monkeypatch))).json())
    monkeypatch.setattr(review_export, "enqueue_export", lambda *args: True)
    assert client.post(f"/match-reports/{report['id']}/exports", headers=headers(),
                       json={"version": report["version"]}).status_code == 202
    now = datetime.now(UTC)
    session.add(models.ReviewExport(id=str(uuid.uuid4()), tenant_id="alpha", report_id=report["id"],
                                    report_version=report["version"], state="queued", created_at=now, updated_at=now))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_queue_full_records_retryable_failure(environment, monkeypatch):
    client, _, _ = environment
    report = approve(client, save(client, create(client, upload(client, monkeypatch))).json())
    base = f"/match-reports/{report['id']}/exports"
    monkeypatch.setattr(review_export, "enqueue_export", lambda *args: False)
    assert client.post(base, headers=headers(), json={"version": report["version"]}).status_code == 503
    assert client.get(base, headers=headers()).json()[0]["state"] == "failed"
    monkeypatch.setattr(review_export, "enqueue_export", lambda *args: True)
    assert client.post(base, headers=headers(), json={"version": report["version"]}).status_code == 202


def test_private_json_not_cacheable_and_inactive_club_blocked(environment, monkeypatch, session):
    client, _, _ = environment
    report = create(client, upload(client, monkeypatch))
    for path in ("/match-reports", "/match-reports/videos", f"/match-reports/{report['id']}"):
        response = client.get(path, headers=headers())
        assert response.headers["cache-control"] == "private, no-store"
    session.get(models.Tenant, "alpha").active = False
    session.commit()
    assert client.get("/match-reports", headers=headers()).status_code in (401, 403)


def test_fractional_clip_times_and_long_turkish_report():
    import re

    from app.reports.review_document import ReviewDocument, time_label
    from app.reports.review_pdf import build_review_pdf

    assert time_label(59.96) == "01:00"
    assert time_label(1.1) == "00:01.1" and time_label(1.6) == "00:01.6"
    data = document()
    data["summary"] = ("İnceleme, gelişim ve öğrenme. " * 150)[:3000]
    data["findings"] = [{**data["findings"][0], "id": str(uuid.uuid4()),
                          "observation": ("Görüntüden doğrulanmış gözlem. " * 60)[:1500]} for _ in range(12)]
    pdf = build_review_pdf(title="Uzun Türkçe rapor", document=ReviewDocument.model_validate(data),
                           source="maç.mp4", source_hash="a" * 64, reviewer="Analist",
                           reviewed_at="2026-10-10T13:00:00+00:00", version=1)
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) >= 3


def test_heartbeat_keeps_queued_job_alive_without_reviving_failed_job(environment, monkeypatch, session):
    client, _, _ = environment
    report = approve(client, save(client, create(client, upload(client, monkeypatch))).json())
    monkeypatch.setattr(review_export, "enqueue_export", lambda *args: True)
    monkeypatch.setattr(review_export, "SessionLocal", sessionmaker(bind=session.get_bind(), expire_on_commit=False))
    base = f"/match-reports/{report['id']}/exports"
    job_id = client.post(base, headers=headers(), json={"version": report["version"]}).json()["id"]
    for state in ("queued", "failed"):
        job = session.get(models.ReviewExport, job_id)
        job.state = state
        old = datetime.now(UTC) - timedelta(minutes=5)
        job.updated_at = old
        session.commit()
        stop = threading.Event()
        waits = iter([False, True])
        monkeypatch.setattr(stop, "wait", lambda timeout, sequence=waits: next(sequence))
        review_export._heartbeat(job_id, "alpha", stop)
        session.expire_all()
        job = session.get(models.ReviewExport, job_id)
        assert job.state == state
        assert (job.updated_at.replace(tzinfo=UTC) > old) is (state == "queued")
        assert client.get(f"{base}/{job_id}", headers=headers()).json()["state"] == state


def test_draft_copy_is_validated_and_requires_its_own_approval(environment, monkeypatch):
    client, _, _ = environment
    video = upload(client, monkeypatch)
    original = approve(client, save(client, create(client, video)).json())
    response = client.post("/match-reports", headers=headers(), json={
        "video_id": video["id"], "title": "Ayrı taslak", "document": original["document"],
    })
    assert response.status_code == 201
    copy = response.json()
    assert copy["id"] != original["id"] and copy["reviewed_at"] is None and copy["version"] == 1
    assert copy["document"] == original["document"]
    assert client.get(f"/match-reports/{copy['id']}/pdf", headers=headers()).status_code == 409
    data = document()
    data["findings"][0]["end"] = 31
    assert client.post("/match-reports", headers=headers(), json={
        "video_id": video["id"], "title": "Geçersiz kopya", "document": data,
    }).status_code == 422
