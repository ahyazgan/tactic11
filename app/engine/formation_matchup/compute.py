"""Formation Matchup — (bizim × rakip) formasyon kombosu beklentisi.

8 ana formasyon × 8-vektör maç beklentisi + 3 spesifik taktiksel ipucu.
Pure compute, YAML KB tüketir.

Vektör boyutları (0..1):
  our_xt_expected, opp_xt_expected,
  our_ppda_advantage, midfield_control,
  width_clash, set_piece_clash, transition_speed, space_behind_lines

Eşleşme yoksa (her iki yön de) → notes ile uyarı + nötr ortalama vektör.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.formation_matchup"
ENGINE_VERSION = "1"

KB_PATH = (
    Path(__file__).resolve().parents[3]
    / "app" / "data" / "knowledge" / "formation_matchups.yaml"
)

_KB_CACHE: dict[str, Any] | None = None
_KB_LOCK = threading.Lock()

VECTOR_DIM = 8
VECTOR_LABELS = (
    "our_xt_expected", "opp_xt_expected",
    "our_ppda_advantage", "midfield_control",
    "width_clash", "set_piece_clash",
    "transition_speed", "space_behind_lines",
)


@dataclass(frozen=True)
class FormationDef:
    id: str
    label: str
    typical_for: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MatchupExpectation:
    """8-vektör — labeled dict + raw tuple."""
    values: dict[str, float]
    raw: tuple[float, ...]


@dataclass(frozen=True)
class FormationMatchupReport:
    our_formation: str
    opp_formation: str
    expectation: MatchupExpectation
    advice: tuple[str, ...]
    summary: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def _load_kb(path: Path | None = None) -> dict[str, Any]:
    global _KB_CACHE
    if path is not None:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    with _KB_LOCK:
        if _KB_CACHE is None:
            with KB_PATH.open(encoding="utf-8") as f:
                _KB_CACHE = yaml.safe_load(f)
        return _KB_CACHE or {}


def list_formations() -> list[FormationDef]:
    """Tanımlı formasyon listesini döner (UI dropdown için)."""
    kb = _load_kb()
    return [
        FormationDef(
            id=str(f.get("id", "")),
            label=str(f.get("label", f.get("id", ""))),
            typical_for=tuple(f.get("typical_for") or []),
        )
        for f in kb.get("formations") or []
    ]


def _find_matchup(
    matchups: list[dict[str, Any]], our: str, opp: str,
) -> dict[str, Any] | None:
    for m in matchups:
        if m.get("our") == our and m.get("opp") == opp:
            return m
    return None


def _invert_expectation(vec: tuple[float, ...]) -> tuple[float, ...]:
    """Ters yön: our_xt ↔ opp_xt; our_ppda_advantage 1-x; midfield_control 1-x."""
    if len(vec) != VECTOR_DIM:
        return vec
    return (
        vec[1], vec[0],            # our_xt ↔ opp_xt
        round(1 - vec[2], 3),      # our_ppda_advantage tersi
        round(1 - vec[3], 3),      # midfield_control tersi
        vec[4],                    # width_clash simetrik
        vec[5],                    # set_piece_clash simetrik
        vec[6],                    # transition_speed simetrik
        round(1 - vec[7], 3),      # space_behind_lines tersi
    )


def _neutral_vector() -> tuple[float, ...]:
    return (0.50,) * VECTOR_DIM


def _build_summary(
    our: str, opp: str, exp: dict[str, float], inverted: bool,
) -> str:
    advantage_pts: list[str] = []
    if exp["our_ppda_advantage"] >= 0.55:
        advantage_pts.append("pres baskınlığı")
    if exp["midfield_control"] >= 0.55:
        advantage_pts.append("orta saha")
    if exp["our_xt_expected"] - exp["opp_xt_expected"] >= 0.08:
        advantage_pts.append("hücum tehdidi")
    if exp["width_clash"] >= 0.6:
        advantage_pts.append("kanat yoğunluğu")
    if exp["set_piece_clash"] >= 0.55:
        advantage_pts.append("duran top kritik")
    note_inv = " (yön ters çevrilmiş eşleşmeden)" if inverted else ""
    if not advantage_pts:
        return f"{our} vs {opp}: dengeli karşılaşma{note_inv}"
    return f"{our} vs {opp}: " + " + ".join(advantage_pts) + note_inv


def compute_formation_matchup(
    our_formation: str,
    opp_formation: str,
    *,
    kb: dict[str, Any] | None = None,
) -> EngineResult[FormationMatchupReport]:
    """Formasyon × formasyon → 8-vektör + 3 spesifik tavsiye.

    KB'de (our, opp) bulunmazsa (opp, our) ters çevrilmiş ile dener;
    yine yoksa nötr vektör + uyarı notu.
    """
    knowledge = kb if kb is not None else _load_kb()
    matchups = knowledge.get("matchups") or []
    notes: list[str] = []

    m = _find_matchup(matchups, our_formation, opp_formation)
    inverted = False
    if m is None:
        # ters eşleşmeyi dene
        rev = _find_matchup(matchups, opp_formation, our_formation)
        if rev is not None:
            inverted = True
            vec = _invert_expectation(tuple(rev.get("expectation") or _neutral_vector()))
            advice = tuple(rev.get("advice") or [])
            notes.append(
                f"Eşleşme ({our_formation} × {opp_formation}) yok — "
                f"({opp_formation} × {our_formation}) ters çevrilmiş kullanıldı",
            )
        else:
            vec = _neutral_vector()
            advice = (
                "Bu formasyon kombosu KB'de tanımlı değil — "
                "individual quality + uyum belirleyici olur",
            )
            notes.append(
                f"({our_formation} × {opp_formation}) hiç tanımlı değil; "
                "nötr 0.5 vektör + generic advice",
            )
    else:
        vec = tuple(m.get("expectation") or _neutral_vector())
        advice = tuple(m.get("advice") or [])

    if len(vec) != VECTOR_DIM:
        # KB hatalı veri savunması
        vec = _neutral_vector()
        notes.append("vektör boyut hatalı — nötr fallback")

    values = {
        label: round(float(v), 3)
        for label, v in zip(VECTOR_LABELS, vec, strict=False)
    }
    expectation = MatchupExpectation(values=values, raw=tuple(vec))
    summary = _build_summary(our_formation, opp_formation, values, inverted)

    report = FormationMatchupReport(
        our_formation=our_formation,
        opp_formation=opp_formation,
        expectation=expectation,
        advice=advice,
        summary=summary,
        notes=tuple(notes),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=0,
        metric="formation_matchup",
        value={
            "our": our_formation, "opp": opp_formation,
            "expectation": values,
            "advice_count": len(advice),
            "inverted": inverted,
            "summary": summary,
        },
        inputs={"kb_size": len(matchups)},
        formula=(
            "(our × opp) → 8-vektör + advice; "
            "fallback: (opp × our) ters çevirme; sonra nötr 0.5"
        ),
    )
    return EngineResult(value=report, audit=audit)
