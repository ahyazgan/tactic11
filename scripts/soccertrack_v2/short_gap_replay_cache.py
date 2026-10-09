"""Verify secondary replay evidence before reusing it for a new primary candidate."""

from __future__ import annotations

from pathlib import Path

from scripts.soccertrack_v2.benchmark_tracker_backends import digest, load

# Primary candidates and measurement orchestration may change. Cached secondary
# evidence keeps its ORIGINAL producing driver hash/decoder metadata in the prior
# report; it is not represented as inference by a revised driver. Its standalone
# tracker implementation, source inputs, model, palettes and labels must match.
EXPERIMENT_FILES = {
    Path("scripts/soccertrack_v2/benchmark_short_gap_motion.py").resolve(),
    Path("scripts/soccertrack_v2/short_gap_replay_cache.py").resolve(),
    Path("scripts/soccertrack_v2/candidates/short_gap_motion_v1.py").resolve(),
    Path("scripts/soccertrack_v2/candidates/palette_motion_partitions_v1.py").resolve(),
    Path("scripts/soccertrack_v2/benchmark_guarded_identity.py").resolve(),
    Path("scripts/soccertrack_v2/candidates/guarded_identity_v2.py").resolve(),
}


def local_path(value):
    return Path(value.replace("\\", "/"))


class SecondaryCache:
    def __init__(self, report_path: Path, versions: dict):
        self.report_path = report_path
        self.report = load(report_path)
        self.report_hash = digest(report_path)
        self.used = {}
        if not self.report.get("completed_at_utc") or self.report.get("versions") != versions:
            raise ValueError("Completed secondary replay with identical runtime versions required")
        if not self.report.get("input_code_sha256") or not self.report.get("output_sha256"):
            raise ValueError("Secondary replay provenance is missing")
        self.validate()

    def validate(self):
        if digest(self.report_path) != self.report_hash:
            raise ValueError("Secondary report changed")
        for name, sha in self.report["input_code_sha256"].items():
            path = local_path(name)
            if path.resolve() in EXPERIMENT_FILES:
                continue
            if not path.is_file() or digest(path) != sha:
                raise ValueError(f"Secondary source/code changed: {name}")
        for path, sha in self.used.items():
            if digest(path) != sha:
                raise ValueError(f"Secondary predictions changed: {path}")

    def read(self, group, segment):
        path = self.report_path.parent / group / "secondary" / f"seg_{segment:04d}.json"
        registered = {
            local_path(p).resolve(): sha for p, sha in self.report["output_sha256"].items()
        }
        sha = registered.get(path.resolve())
        if sha is None or digest(path) != sha:
            raise ValueError("Secondary output is not registered or its hash changed")
        self.used[path] = sha
        stats = dict(self.report["results"][group]["segments"][str(segment)]["secondary"])
        stats["reused_from_report"] = str(self.report_path)
        stats["reused_report_sha256"] = self.report_hash
        return load(path), stats
