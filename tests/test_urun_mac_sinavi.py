"""Ürün tam maç sınavı: şartlar ölçülemeyeni geçirmez, uçlar gerçekten çağrılır."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from scripts import urun_mac_sinavi as exam


def _frame(minute: float, players: int = 20, ball: bool = True) -> dict:
    return {"minute": minute, "players": [{}] * players, "ball": {"x": 1} if ball else None}


def _passing() -> dict:
    return {
        "job_state": "done", "status_frames": 3, "processing_ratio": 4.0, "shape_ok_share": 1.0,
        "min_free_disk_gb": 10.0,
        "metrics": {"frames": 3, "minute_coverage": 1.0, "median_players": 20, "frames_8plus_share": 1.0},
    }


def test_frame_metrics_counts_coverage_and_players():
    m = exam.frame_metrics([_frame(0.5), _frame(1.2, players=4, ball=False)], 180)
    assert m["expected_minutes"] == 3 and m["covered_minutes"] == 2
    assert m["median_players"] == 12 and m["frames_8plus_share"] == 0.5 and m["ball_share"] == 0.5


def test_frame_metrics_empty_is_zero_not_invented():
    m = exam.frame_metrics([], 600)
    assert m["frames"] == 0 and m["minute_coverage"] == 0 and m["median_players"] == 0


def test_evaluate_passes_only_when_all_gates_hold():
    assert exam.evaluate(_passing())["automatic_gates_passed"] is True
    verdict = exam.evaluate({**_passing(), "processing_ratio": 6.1})
    assert verdict["automatic_gates_passed"] is False and verdict["checks"]["processing_ratio"] is False


def test_evaluate_failed_job_without_measurements_never_passes():
    verdict = exam.evaluate({"job_state": "failed"})
    assert verdict["automatic_gates_passed"] is False
    assert not any(verdict["checks"].values())


def test_review_sample_is_fixed_by_seed():
    frames = [_frame(i / 10) for i in range(500)]
    assert exam.review_sample(frames) == exam.review_sample(frames)
    assert len(exam.review_sample(frames)) == exam.REVIEW_SAMPLES


def test_preregistration_matches_code_gates():
    path = Path(__file__).parents[1] / "docs" / "measurements" / "product-full-match-exam-preregistration.json"
    prereg = json.loads(path.read_text(encoding="utf-8"))
    assert prereg["video"]["seconds"] == 5652
    assert set(prereg["automatic_gates"]) == set(exam.evaluate(_passing())["checks"])


class _Resp:
    def __init__(self, code: int, body: dict):
        self.status_code = code
        self._body = body

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        assert self.status_code < 400


class _Client:
    """Bitmiş bir işi ve ürün uçlarını taklit eder; çağrılan yolları kaydeder."""

    def __init__(self, state: str = "done", status_code: int = 200):
        self.state, self.status_code = state, status_code
        self.body: dict | None = None

    def post(self, path: str, json: dict) -> _Resp:
        self.body = json
        return _Resp(202, {"id": "j1", "state": "queued"})

    def get(self, path: str, params: dict | None = None) -> _Resp:
        if path.endswith("/status"):
            return _Resp(self.status_code, {"frames": 2})
        if path.endswith("/shape"):
            return _Resp(200, {"teams": {"home": {"shape": {"a": 1}}, "away": {"shape": {"a": 1}}}})
        return _Resp(200, {"id": "j1", "state": self.state, "error": "x" if self.state == "failed" else None})


def _args(tmp_path: Path) -> Namespace:
    return Namespace(video="m.mp4", calibration="c", match_id=7, max_seconds=None, expected_seconds=120.0,
                     poll_seconds=0.0, out=str(tmp_path / "r.json"))


def _write_output(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    payload = {"frames": [_frame(0.5), _frame(1.5)]}
    (tmp_path / "out" / "job_j1_frames.json").write_text(json.dumps(payload), encoding="utf-8")


def test_run_exam_measures_output_and_probes_product(tmp_path):
    _write_output(tmp_path)
    client = _Client()
    result = exam.run_exam(client, _args(tmp_path), tmp_path)
    assert client.body == {"video": "m.mp4", "calibration": "c", "match_id": 7}
    assert result["job_state"] == "done" and result["status_frames"] == 2
    assert result["metrics"]["minute_coverage"] == 1.0


def test_run_exam_missing_match_is_reported_as_failure(tmp_path):
    _write_output(tmp_path)
    result = exam.run_exam(_Client(status_code=404), _args(tmp_path), tmp_path)
    assert result["status_http"] == 404
    assert result["verdict"]["checks"]["ingest_complete"] is False


def test_run_exam_failed_job_keeps_error(tmp_path):
    result = exam.run_exam(_Client(state="failed"), _args(tmp_path), tmp_path)
    assert result["job_state"] == "failed" and result["job_error"] == "x"
    assert result["verdict"]["automatic_gates_passed"] is False


def test_system_memory_is_measured_or_absent_never_invented():
    memory = exam.system_memory_mb()
    assert memory is None or (memory["avail_phys_mb"] > 0 and memory["avail_commit_mb"] > 0)


def test_run_exam_records_memory_alongside_the_result(tmp_path, monkeypatch):
    _write_output(tmp_path)
    readings = iter([{"avail_phys_mb": 900.0, "avail_commit_mb": 5000.0},
                     {"avail_phys_mb": 400.0, "avail_commit_mb": 7000.0}])
    monkeypatch.setattr(exam, "system_memory_mb", lambda: next(readings))
    result = exam.run_exam(_Client(), _args(tmp_path), tmp_path)
    assert result["system_memory_start"] == {"avail_phys_mb": 900.0, "avail_commit_mb": 5000.0}
    assert result["system_memory_min"] == {"avail_phys_mb": 400.0, "avail_commit_mb": 5000.0}
