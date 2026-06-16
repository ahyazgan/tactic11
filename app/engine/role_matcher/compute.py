"""Role Matcher — oyuncu stat'larından taktiksel rol çıkarımı.

30+ rol arketipiyle cosine match: defensive_actions, tackle, interception,
pass_completion, progressive_pass, key_pass, dribble, shot_per_90 8-vektörü
oyuncunun stat profilinden 0-1 normalize edilir, en yakın 3 rol döner.

Pure compute. PlayerStatVector input + opsiyonel position filter.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.role_matcher"
ENGINE_VERSION = "1"

KB_PATH = (
    Path(__file__).resolve().parents[3]
    / "app" / "data" / "knowledge" / "player_roles.yaml"
)

_KB_CACHE: dict[str, Any] | None = None
_KB_LOCK = threading.Lock()


@dataclass(frozen=True)
class PlayerStatVector:
    """Oyuncu stat profili — 8-vektör 0-1 normalize.

    Tüm değerler 0..1 arasında; orijinal istatistikleri liga ortalamasına göre
    yüzdelik (percentile) normalize ediyoruz (caller doldurur).
    """
    defensive_actions_pct: float
    tackle_pct: float
    interception_pct: float
    pass_completion_pct: float
    progressive_pass_pct: float
    key_pass_pct: float
    dribble_pct: float
    shot_per_90_pct: float

    def to_tuple(self) -> tuple[float, ...]:
        return (
            self.defensive_actions_pct, self.tackle_pct,
            self.interception_pct, self.pass_completion_pct,
            self.progressive_pass_pct, self.key_pass_pct,
            self.dribble_pct, self.shot_per_90_pct,
        )


@dataclass(frozen=True)
class RoleMatch:
    name: str
    label: str
    position_group: str
    description: str
    similarity: float                   # 0-1 cosine
    typical_attributes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RoleMatchReport:
    player_external_id: int
    position_group_filter: str | None
    top_match: RoleMatch | None
    secondary_matches: tuple[RoleMatch, ...]
    confidence: str                     # "high" | "medium" | "low"
    summary: str


def _load_roles(path: Path | None = None) -> list[dict[str, Any]]:
    global _KB_CACHE
    if path is not None:
        with path.open(encoding="utf-8") as f:
            return list((yaml.safe_load(f) or {}).get("roles", []))
    with _KB_LOCK:
        if _KB_CACHE is None:
            with KB_PATH.open(encoding="utf-8") as f:
                _KB_CACHE = yaml.safe_load(f)
        return list((_KB_CACHE or {}).get("roles", []))


def list_roles() -> list[dict[str, Any]]:
    return _load_roles()


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _confidence(top_sim: float, gap: float) -> str:
    if top_sim >= 0.95 and gap >= 0.05:
        return "high"
    if top_sim >= 0.88:
        return "medium"
    return "low"


def compute_role_match(
    player_external_id: int,
    stats: PlayerStatVector,
    *,
    position_group: str | None = None,
    top_n_secondary: int = 2,
    kb: list[dict[str, Any]] | None = None,
) -> EngineResult[RoleMatchReport]:
    """Oyuncu stat'ını rol arketipleriyle eşleştir."""
    roles = kb if kb is not None else _load_roles()
    if position_group:
        roles = [r for r in roles if r.get("position_group") == position_group]

    if not roles:
        report = RoleMatchReport(
            player_external_id=player_external_id,
            position_group_filter=position_group,
            top_match=None, secondary_matches=(),
            confidence="low",
            summary=(
                f"Rol eşleşmesi yok (filter: {position_group or 'tümü'})"
            ),
        )
        return EngineResult(value=report, audit=AuditRecord(
            engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
            subject_type="player", subject_id=player_external_id,
            metric="role_match",
            value={"role_count": 0, "confidence": "low"},
            inputs={"position_group": position_group}, formula="empty",
        ))

    stat_t = stats.to_tuple()
    matches: list[RoleMatch] = []
    for r in roles:
        vec = tuple(r.get("archetype_vector") or [])
        sim = _cosine(stat_t, vec)
        matches.append(RoleMatch(
            name=str(r.get("name", "")),
            label=str(r.get("label", r.get("name", ""))),
            position_group=str(r.get("position_group", "")),
            description=str(r.get("description", "")),
            similarity=round(sim, 3),
            typical_attributes=tuple(r.get("typical_attributes") or []),
        ))
    matches.sort(key=lambda m: m.similarity, reverse=True)

    top = matches[0]
    secondary = tuple(matches[1: 1 + top_n_secondary])
    gap = top.similarity - (secondary[0].similarity if secondary else 0.0)
    conf = _confidence(top.similarity, gap)
    summary = f"{top.label} ({top.position_group}) — {top.description}"
    if conf == "high":
        summary += f" (güven: yüksek, ≥%{int(top.similarity * 100)})"

    report = RoleMatchReport(
        player_external_id=player_external_id,
        position_group_filter=position_group,
        top_match=top, secondary_matches=secondary,
        confidence=conf, summary=summary,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=player_external_id,
        metric="role_match",
        value={
            "top_role": top.name,
            "top_similarity": top.similarity,
            "secondary_roles": [m.name for m in secondary],
            "confidence": conf,
            "summary": summary,
            "candidates_count": len(roles),
        },
        inputs={
            "position_group": position_group,
            "vector_dim": len(stat_t),
        },
        formula=(
            "8-vektör (def_actions/tackle/intercept/pass/progressive/key_pass/"
            "dribble/shot_per_90) → cosine → top + secondary"
        ),
    )
    return EngineResult(value=report, audit=audit)
