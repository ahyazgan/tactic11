"""New control labels must not feed back into candidate predictions or kit names."""
from __future__ import annotations

import copy

import pytest

from scripts.soccertrack_v2.benchmark_local_kit_light import benchmark as local_benchmark
from scripts.soccertrack_v2.benchmark_shadow_reassignment import benchmark as shadow_benchmark


@pytest.mark.parametrize("kind,development,control", [
    ("local", {0, 2, 3, 6, 8, 9}, {1, 7}),
    ("shadow", {0, 3, 6, 9}, {2, 8}),
])
def test_fresh_control_cannot_change_mapping_or_development(kind, development, control):
    payloads, rows = {}, []
    for segment in development | control:
        colors = {"1": [[30, 40, 200]] * 4, "2": [[200, 200, 200]] * 4}
        payloads[segment] = {"colors": colors, "samples": [{"persons": [[1], [2]]}],
                             "alternative_colors": {m: copy.deepcopy(colors) for m in ("raw_reextracted", "local_all", "local_grass")}}
        rows.extend({"id": f"{segment}-{track}", "segment": segment, "track": track, "kit": kit}
                    for track, kit in ((1, "blue"), (2, "white")))
    flipped = [{**r, "kit": "white" if r["kit"] == "blue" else "blue"}
               if r["segment"] in control else r for r in rows]
    evaluate = local_benchmark if kind == "local" else lambda p, r: shadow_benchmark(p, r, development)
    before, after = evaluate(payloads, rows), evaluate(payloads, flipped)
    for method in before:
        assert before[method]["predictions"] == after[method]["predictions"]
        assert before[method]["blue_team_from_development"] == after[method]["blue_team_from_development"]
        assert before[method]["development"] == after[method]["development"]
        assert before[method]["control"]["correct"] == 4
        assert after[method]["control"]["wrong"] == 4
