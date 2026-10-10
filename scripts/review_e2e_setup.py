"""Seed only an explicitly named disposable review-e2e SQLite database."""
from __future__ import annotations

import argparse
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    args = parser.parse_args()
    url = make_url(os.environ.get("DATABASE_URL", "sqlite://"))
    if (url.get_backend_name() != "sqlite" or not url.database
            or not Path(url.database).name.startswith("review-e2e-")
            or not Path(url.database).is_file() or os.environ.get("APP_ENV") == "prod"):
        raise SystemExit("Use a migrated, disposable review-e2e-*.db SQLite database; live databases are refused.")
    if not args.video.name.startswith("review-e2e-"):
        raise SystemExit("Synthetic fixture output must be named review-e2e-*.mp4.")

    from app.auth.service import create_user
    from app.db import models
    from app.db.session import SessionLocal
    from app.reports.review_media import ffmpeg, probe_video

    with SessionLocal() as session:
        if session.get(models.Tenant, "review-pilot") is None:
            session.add(models.Tenant(id="review-pilot", slug="review-pilot", name="Teknik doğrulama kulübü",
                                      active=True, settings_json="{}", created_at=datetime.now(UTC)))
            session.flush()
        if session.scalar(select(models.User).where(models.User.email == "analyst@review-pilot.test")) is None:
            create_user(session, tenant_id="review-pilot", email="analyst@review-pilot.test",
                        password="review-local-test-only", role="analyst")
        session.commit()
    if not args.video.exists():
        args.video.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg(), "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=640x360:rate=25:duration=30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-threads", "2", "-movflags", "+faststart", str(args.video)],
                       check=True, capture_output=True, timeout=60)
    probe_video(args.video)
    print("Disposable report fixture ready (synthetic footage; no customer data).")


if __name__ == "__main__":
    main()
