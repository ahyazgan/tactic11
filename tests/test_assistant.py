"""Manager assistant: chat (tool loop) + memory + simulator + recommendation agents."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agents import (
    LineupRecommendationAgent,
    SubstitutionAdviceAgent,
    TacticalAdjustmentAgent,
)
from app.ai import AnthropicClient, ClaudeCommentator
from app.ai.anthropic_client import ToolCall, ToolUseResult
from app.assistant import (
    chat,
    execute_tool,
    get_tool_schemas,
    memory_delete,
    memory_get,
    memory_list,
    memory_set,
)
from app.db import models
from app.sports import football


@pytest.fixture()
def commentator_stub():
    return ClaudeCommentator(AnthropicClient())


def _seed_basic(session, base: datetime) -> None:
    """611 + 607 için form + h2h + future match=99."""
    rows = [
        models.Team(sport=football.SPORT_NAME, external_id=611, name="Galatasaray"),
        models.Team(sport=football.SPORT_NAME, external_id=607, name="Fenerbahce"),
        models.Match(
            sport=football.SPORT_NAME, external_id=10, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=20), status="FT",
            home_team_external_id=611, away_team_external_id=614,
            home_score=2, away_score=1,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=11, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=10), status="FT",
            home_team_external_id=998, away_team_external_id=611,
            home_score=0, away_score=2,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=20, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=8), status="FT",
            home_team_external_id=607, away_team_external_id=614,
            home_score=3, away_score=0,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=30, league_external_id=203,
            season=2024, kickoff=base - timedelta(days=40), status="FT",
            home_team_external_id=611, away_team_external_id=607,
            home_score=2, away_score=1,
        ),
        models.Match(
            sport=football.SPORT_NAME, external_id=99, league_external_id=203,
            season=2024, kickoff=base + timedelta(days=3), status="NS",
            home_team_external_id=611, away_team_external_id=607,
            home_score=None, away_score=None,
        ),
    ]
    session.add_all(rows)
    session.flush()


# --------------------------------------------------------------------------- #
# tools.execute_tool — her tool için kontrat
# --------------------------------------------------------------------------- #


def test_tool_schemas_have_required_fields():
    schemas = get_tool_schemas()
    assert len(schemas) >= 10
    for s in schemas:
        assert "name" in s and "description" in s and "input_schema" in s


def test_execute_unknown_tool_returns_error(session):
    out = execute_tool(session, "does_not_exist", {})
    assert "error" in out and "bilinmeyen" in out


def test_tool_get_team_form(session):
    _seed_basic(session, datetime.now(UTC))
    import json
    out = json.loads(execute_tool(session, "get_team_form", {"team_external_id": 611}))
    assert out["team_id"] == 611
    assert out["matches_played"] >= 1
    assert "points_per_game" in out


def test_tool_get_match_prediction(session):
    _seed_basic(session, datetime.now(UTC))
    import json
    out = json.loads(execute_tool(session, "get_match_prediction", {
        "match_external_id": 99, "use_ml": False,
    }))
    assert out["match_id"] == 99
    assert 0 <= out["prob_home_win"] <= 1
    assert out["ml_status"] in ("default", "fresh", "untrained")


def test_tool_get_upcoming_matches(session):
    _seed_basic(session, datetime.now(UTC))
    import json
    out = json.loads(execute_tool(session, "get_upcoming_matches", {
        "team_external_id": 611, "days": 7,
    }))
    # match=99 base+3d
    assert len(out["upcoming"]) >= 1
    assert out["upcoming"][0]["match_id"] == 99


def test_tool_get_ml_status_untrained_when_cache_empty(session):
    import json
    out = json.loads(execute_tool(session, "get_ml_status", {}))
    assert out["status"] == "untrained"


# --------------------------------------------------------------------------- #
# chat — stub mode + mocked tool_use loop
# --------------------------------------------------------------------------- #


def test_chat_stub_mode_returns_canned(session):
    result = chat(session, user_message="Fener nasıl?")
    assert result.stub is True
    assert "ANTHROPIC_API_KEY" in result.text
    assert "get_team_form" in result.text  # tools list var


class _FakeClient:
    """is_stub=False; message_with_tools'u scripted yanıt verir."""
    def __init__(self, scripted: list[ToolUseResult]):
        self._scripted = list(scripted)
        self.call_count = 0

    def is_stub(self) -> bool:
        return False

    def message_with_tools(self, *, system, messages, tools, max_tokens):
        self.call_count += 1
        if not self._scripted:
            raise AssertionError("script bitti, beklenmeyen çağrı")
        return self._scripted.pop(0)


def test_chat_runs_tool_loop_then_returns_final_text(session):
    _seed_basic(session, datetime.now(UTC))
    # Tur 1: tool_use → get_team_form(611)
    # Tur 2: end_turn → final text
    fake = _FakeClient([
        ToolUseResult(
            text="", stop_reason="tool_use",
            tool_calls=[ToolCall(id="t1", name="get_team_form", input={"team_external_id": 611})],
            raw_content=[{
                "type": "tool_use", "id": "t1",
                "name": "get_team_form", "input": {"team_external_id": 611},
            }],
            input_tokens=100, output_tokens=50,
        ),
        ToolUseResult(
            text="Galatasaray son 5 maçta iyi formda.",
            stop_reason="end_turn", tool_calls=[],
            raw_content=[{"type": "text", "text": "Galatasaray son 5 maçta iyi formda."}],
            input_tokens=150, output_tokens=20,
        ),
    ])
    result = chat(session, user_message="611 nasıl?", client=fake)  # type: ignore[arg-type]
    assert result.stub is False
    assert "iyi formda" in result.text
    assert result.iterations == 2
    assert len(result.tool_traces) == 1
    assert result.tool_traces[0].name == "get_team_form"
    assert result.total_tokens == 320


def test_chat_respects_max_iterations(session):
    """Tool loop sonsuza gitmesin — max_iterations'tan fazlasını engelle."""
    forever_tool = ToolUseResult(
        text="", stop_reason="tool_use",
        tool_calls=[ToolCall(id="x", name="get_ml_status", input={})],
        raw_content=[{"type": "tool_use", "id": "x", "name": "get_ml_status", "input": {}}],
        input_tokens=10, output_tokens=10,
    )
    fake = _FakeClient([forever_tool] * 5)
    result = chat(session, user_message="kalibrasyon?", client=fake, max_iterations=3)  # type: ignore[arg-type]
    assert result.iterations == 3
    assert "Maks tool tur" in result.text  # canned warning


# --------------------------------------------------------------------------- #
# memory
# --------------------------------------------------------------------------- #


def test_memory_set_get(session):
    memory_set(session, subject_type="team", subject_id=611,
               key="preferred_formation", value="4-3-3")
    session.flush()
    assert memory_get(session, subject_type="team", subject_id=611,
                      key="preferred_formation") == "4-3-3"


def test_memory_upsert_updates(session):
    memory_set(session, subject_type="team", subject_id=611, key="style", value="possession")
    memory_set(session, subject_type="team", subject_id=611, key="style", value="counter")
    session.flush()
    assert memory_get(session, subject_type="team", subject_id=611, key="style") == "counter"
    # 1 satır olmalı
    rows = session.query(models.AssistantMemory).filter_by(subject_id=611).all()
    assert len(rows) == 1


def test_memory_list_returns_all_keys(session):
    memory_set(session, subject_type="team", subject_id=611, key="a", value=1)
    memory_set(session, subject_type="team", subject_id=611, key="b", value={"x": 2})
    session.flush()
    mem = memory_list(session, subject_type="team", subject_id=611)
    assert mem == {"a": 1, "b": {"x": 2}}


def test_memory_delete(session):
    memory_set(session, subject_type="team", subject_id=611, key="x", value="y")
    assert memory_delete(session, subject_type="team", subject_id=611, key="x") is True
    assert memory_get(session, subject_type="team", subject_id=611, key="x") is None
    # ikinci silme False döner
    assert memory_delete(session, subject_type="team", subject_id=611, key="x") is False


def test_chat_injects_team_memory_into_system_prompt(session, monkeypatch):
    """team_external_id ile çağırırsan system prompt'a memory eklenmiş olmalı."""
    captured_systems: list[str] = []

    class _Capture(_FakeClient):
        def message_with_tools(self, *, system, messages, tools, max_tokens):
            captured_systems.append(system)
            return super().message_with_tools(
                system=system, messages=messages, tools=tools, max_tokens=max_tokens,
            )

    memory_set(session, subject_type="team", subject_id=611,
               key="preferred_formation", value="4-3-3")
    session.flush()

    fake = _Capture([
        ToolUseResult(
            text="OK", stop_reason="end_turn", tool_calls=[], raw_content=[],
            input_tokens=10, output_tokens=5,
        ),
    ])
    chat(session, user_message="hi", client=fake, team_external_id=611)  # type: ignore[arg-type]
    assert "preferred_formation" in captured_systems[0]
    assert "4-3-3" in captured_systems[0]


# --------------------------------------------------------------------------- #
# Recommendation agents
# --------------------------------------------------------------------------- #


def test_lineup_recommendation_uses_roster_proxy(session, commentator_stub):
    _seed_basic(session, datetime.now(UTC))
    # 611 son maçında oynayan 11+ oyuncu kaydet
    for i, pid in enumerate(range(611001, 611015)):
        session.add(models.PlayerAppearance(
            sport=football.SPORT_NAME,
            player_external_id=pid,
            match_external_id=10,
            minutes=90 if i < 11 else 30,
            kickoff=datetime.now(UTC) - timedelta(days=20),
        ))
    session.flush()
    agent = LineupRecommendationAgent(commentator=commentator_stub)
    r = agent.run(session, context={"match_external_id": 99, "team_external_id": 611})
    assert len(r.output_json["recommended_starting_xi"]) == 11
    assert r.subject_type == "match" and r.subject_id == 99


def test_lineup_recommendation_raises_when_team_not_in_match(session, commentator_stub):
    _seed_basic(session, datetime.now(UTC))
    agent = LineupRecommendationAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="tarafı değil"):
        agent.run(session, context={"match_external_id": 99, "team_external_id": 999})


def test_substitution_advice_priority_chase(session, commentator_stub):
    _seed_basic(session, datetime.now(UTC))
    agent = SubstitutionAdviceAgent(commentator=commentator_stub)
    r = agent.run(session, context={
        "match_external_id": 99, "team_external_id": 611,
        "minute": 60, "current_home_score": 0, "current_away_score": 2,
        "on_pitch_player_ids": [611001, 611002, 611003],
        "bench_player_ids": [611010, 611011],
    })
    assert r.output_json["priority"] == "chase"
    assert r.output_json["score"]["diff"] == -2


def test_substitution_advice_priority_protect_late(session, commentator_stub):
    _seed_basic(session, datetime.now(UTC))
    agent = SubstitutionAdviceAgent(commentator=commentator_stub)
    r = agent.run(session, context={
        "match_external_id": 99, "team_external_id": 611,
        "minute": 75, "current_home_score": 2, "current_away_score": 1,
        "on_pitch_player_ids": [611001], "bench_player_ids": [611010],
    })
    assert r.output_json["priority"] == "protect"


def test_substitution_advice_raises_for_empty_pitch(session, commentator_stub):
    _seed_basic(session, datetime.now(UTC))
    agent = SubstitutionAdviceAgent(commentator=commentator_stub)
    with pytest.raises(ValueError, match="on_pitch_player_ids"):
        agent.run(session, context={
            "match_external_id": 99, "team_external_id": 611,
            "minute": 30, "current_home_score": 0, "current_away_score": 0,
            "on_pitch_player_ids": [], "bench_player_ids": [],
        })


def test_tactical_adjustment_produces_signals(session, commentator_stub):
    _seed_basic(session, datetime.now(UTC))
    agent = TacticalAdjustmentAgent(commentator=commentator_stub)
    r = agent.run(session, context={"match_external_id": 99, "team_external_id": 611})
    assert r.output_json["opponent_id"] == 607
    assert r.output_json["preferred_formation"] == "4-3-3"
    # Sinyaller list (boş olabilir, ama liste tipinde)
    assert isinstance(r.output_json["signals"], list)
    # Rakip özet dolu
    assert "form_wdl" in r.output_json["opponent_summary"]


def test_tactical_adjustment_v3_includes_match_plan(session, commentator_stub):
    """v3: engine.match_plan_builder kompoziti output'a eklenir."""
    _seed_basic(session, datetime.now(UTC))
    agent = TacticalAdjustmentAgent(commentator=commentator_stub)
    assert agent.version == "3"
    r = agent.run(session, context={"match_external_id": 99, "team_external_id": 611})
    mp = r.output_json.get("match_plan")
    assert mp is not None
    assert "headline" in mp
    assert "matchup_vector" in mp
    assert "matchup_advice" in mp
    assert "set_piece_top" in mp
    assert "plan_lines" in mp
    assert "opponent_style_inferred" in mp
    # 8 boyut matchup vector
    expected_dims = {
        "our_xt_expected", "opp_xt_expected", "our_ppda_advantage",
        "midfield_control", "width_clash", "set_piece_clash",
        "transition_speed", "space_behind_lines",
    }
    assert expected_dims.issubset(set(mp["matchup_vector"].keys()))
    # Plan satırlarından en az biri signals'da
    assert any("Plan:" in s or "Set-piece" in s for s in r.output_json["signals"])


# --------------------------------------------------------------------------- #
# Simulator API + memory API (TestClient)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def client(session):
    from fastapi.testclient import TestClient

    from app.api.main import app
    from app.db.session import get_session

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_simulate_endpoint_runs_counterfactual(session, client):
    _seed_basic(session, datetime.now(UTC))
    r = client.post("/matches/99/simulate", json={
        "home_form_override": {"goals_for_per_match": 3.0, "goals_against_per_match": 0.5},
    })
    assert r.status_code == 200
    data = r.json()
    assert data["match_id"] == 99
    # Override uygulandı mı
    assert data["applied_form"]["home"]["goals_for_per_match"] == 3.0
    # Baseline'la farklı tahmin çıktı (override etkili)
    assert "simulated_prediction" in data
    assert "prob_home_win" in data["simulated_prediction"]


def test_simulate_endpoint_404_for_missing_match(client):
    r = client.post("/matches/9999999/simulate", json={})
    assert r.status_code == 404


def test_memory_api_set_get_delete(session, client):
    # set
    r = client.put("/assistant/memory/team/611/style", json={"value": "high_press"})
    assert r.status_code == 200
    session.commit()
    # list
    r = client.get("/assistant/memory/team/611")
    assert r.status_code == 200
    assert r.json()["memory"] == {"style": "high_press"}
    # delete
    r = client.delete("/assistant/memory/team/611/style")
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_assistant_chat_endpoint_stub(client):
    r = client.post("/assistant/chat", json={"message": "Fener nasıl?"})
    assert r.status_code == 200
    data = r.json()
    assert data["stub"] is True
    assert "tool_traces" in data
    assert "ANTHROPIC_API_KEY" in data["text"]


def test_assistant_chat_endpoint_422_for_empty_message(client):
    r = client.post("/assistant/chat", json={"message": ""})
    assert r.status_code == 422
