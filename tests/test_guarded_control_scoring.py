"""Use the original scorers; counts cannot conceal loss of a previously correct pair."""
from copy import deepcopy

from scripts.soccertrack_v2.score_guarded_control import compare, scores


def fixture():
    samples, raw_samples, detected, observations, kit = [], [], {}, [], []
    for index, frame in enumerate((374, 404)):
        persons = [[1, 10., 10., 20., 40., .9], [2, 30., 10., 40., 40., .8]]
        samples.append(dict(frame_idx=frame, continuity_id=0, persons=persons, person_teams={"1": 0, "2": 1}))
        raw_samples.append(dict(order=index, frame_idx=frame))
        detected[str(index)] = [dict(box=p[1:5]) for p in persons]
        for p in persons:
            row = dict(id=f"68-{frame}-{p[0]}", segment=68, frame_idx=frame, bbox=p[1:5])
            observations.append(row)
            kit.append(dict(**row, kit="blue" if p[0] == 1 else "white"))
    pairs = dict(observations=observations, pairs=[dict(left="68-374-1", right="68-404-1", relation="same"),
        dict(left="68-374-1", right="68-404-2", relation="different")])
    return {68: dict(samples=samples)}, dict(records=kit), pairs, {68: dict(samples=raw_samples, detected_persons=detected)}


def test_unchanged_source_scores_show_no_positive_correction():
    score = scores(*fixture())
    assert score["kit"]["correct"] == 4
    assert score["pairs"]["control"]["counts"]["same_correct"] == 1
    result = compare(dict(supervision=score, palette=score, guarded=score))
    assert all(v["positive_pair_changes"] == 0 and v["regressions"] == [] for v in result.values())


def test_different_person_join_is_a_regression_against_both_comparisons():
    payloads, labels, pairs, raws = fixture()
    original = scores(payloads, labels, pairs, raws)
    # Same source boxes survive but the track identity moves to a different person.
    payloads[68]["samples"][1]["persons"][0][0] = 3
    payloads[68]["samples"][1]["persons"][1][0] = 1
    payloads[68]["samples"][1]["person_teams"] = {"3": 0, "1": 1}
    candidate = scores(payloads, labels, pairs, raws)
    assert candidate["kit"]["correct"] == 4
    result = compare(dict(supervision=original, palette=original, guarded=candidate))
    for row in result.values():
        assert "control.false_join" in row["regressions"] and "control.false_split" in row["regressions"]
        assert row["positive_pair_changes"] == 0


def test_aggregate_equality_cannot_hide_loss_of_a_previously_correct_relation():
    original = scores(*fixture())
    before, after = deepcopy(original), deepcopy(original)
    before["pairs"]["control"]["outcomes"][1]["passed"] = False
    after["pairs"]["control"]["outcomes"][0]["passed"] = False
    result = compare(dict(supervision=before, palette=before, guarded=after))
    for row in result.values():
        assert "control.68-374-1->68-404-1" in row["regressions"]
        assert row["positive_pair_changes"] == 1
