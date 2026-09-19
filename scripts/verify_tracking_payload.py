"""Read a real tracking output and verify its ingest in disposable memory only.

No configured/live database is opened. This checks transport and idempotency,
not whether the detected people, ball or derived events are correct.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Fresh report path required")
    # Set before any application import. Engine below must independently prove
    # it is ephemeral; an already imported/configured engine is rejected.
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    from sqlalchemy import select

    from app.db import models
    from app.db.session import SessionLocal, engine
    from app.tracking.frames import frames_from_json
    from scripts.ingest_tracking_json import ingest_json

    if engine.url.get_backend_name() != "sqlite" or engine.url.database != ":memory:":
        raise RuntimeError("Refusing verification against a persistent database")
    source_bytes = args.json.read_bytes()
    payload = json.loads(source_bytes)
    frames = frames_from_json(payload)
    if not frames:
        raise ValueError("No tracking frames to verify")
    first = ingest_json(path=str(args.json), tenant_id="tracking-verification")
    second = ingest_json(path=str(args.json), tenant_id="tracking-verification", append=True)
    with SessionLocal() as session:
        rows = session.scalars(select(models.TrackingFrameRow).order_by(models.TrackingFrameRow.timestamp)).all()
        events = session.scalars(select(models.EventRow)).all()
        if len(rows) != len(frames) or len(events) != len(payload.get("derived_passes", [])) + len(payload.get("derived_defensive_actions", [])):
            raise ValueError("Ingest count mismatch or duplicate events")
        for original, row in zip(sorted(frames, key=lambda f: f.timestamp), rows, strict=True):
            people = json.loads(row.players_json)
            expected = [p.model_dump(mode="json") for p in original.players]
            if len(people) != len(expected) or any(any(p[k] != e[k] for k in p) for p, e in zip(people, expected, strict=True)):
                raise ValueError("Player identity, location or metadata changed during ingest")
            meta = json.loads(row.meta_json)
            if (meta["ball_estimated"] != original.ball_estimated
                    or meta["continuity_id"] != original.continuity_id
                    or meta["source"] != original.source
                    or meta["possession_team_external_id"] != original.possession_team_external_id
                    or row.ball_x != (original.ball.x if original.ball else None)
                    or row.ball_y != (original.ball.y if original.ball else None)):
                raise ValueError("Ball or continuity evidence changed during ingest")
        if second["passes_written"] or second["defensive_actions_written"]:
            raise ValueError("Repeated append duplicated derived events")
    engine.dispose()
    if args.json.read_bytes() != source_bytes:
        raise ValueError("Source payload changed during verification")
    report = dict(scope=__doc__, payload_sha256=hashlib.sha256(source_bytes).hexdigest(),
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        database="sqlite:///:memory:", first_ingest=first, repeat_append=second,
        frames_verified=len(frames), players_verified=sum(len(f.players) for f in frames),
        derived_events_verified=len(events), evidence_preserved=True,
        accuracy_validated=False, persistent_database_written=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
