"""Set-Piece Pattern Library — 15+ köşe/serbest vuruş/penaltı routine.

Pure compute, YAML KB. Caller bağlam verir (type, side, attribute scores)
→ engine en uygun 1-3 pattern'i döner.

Skoring (basit):
  base_score = 100 (eşleşen type)
  type ve side eşleşmesi tam → bonus
  ideal_attributes ile context.attributes vektörü cosine → 0-30 bonus
  rakip stili "atletico_compact" gibi → set-piece bonus +10
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.set_piece_library"
ENGINE_VERSION = "1"

KB_PATH = (
    Path(__file__).resolve().parents[3]
    / "app" / "data" / "knowledge" / "set_piece_patterns.yaml"
)

_KB_CACHE: dict[str, Any] | None = None
_KB_LOCK = threading.Lock()


@dataclass(frozen=True)
class SetPieceContext:
    """Set-piece bağlamı — pattern seçimi için input."""
    type: str                              # "corner" | "free_kick" | "throw_in" | "penalty" | "kick_off"
    side: str | None = None                # "short" | "long" | None
    distance_m: float | None = None        # serbest vuruş için
    our_attributes: dict[str, float] = field(default_factory=dict)
    # Örnek: {"aerial": 0.8, "technique": 0.5, "shot_power": 0.7}
    opponent_setpiece_marking: str = "mixed"  # zonal | adam | mixed
    opponent_style: str | None = None      # style_fingerprint top arketipi


@dataclass(frozen=True)
class PatternRecommendation:
    name: str
    label: str
    type: str
    side: str | None
    score: float
    steps: tuple[str, ...]
    ideal_attributes: tuple[str, ...]
    when_use: tuple[str, ...]
    counter_if_opponent: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SetPiecePatternReport:
    request_type: str
    candidates_considered: int
    top_recommendations: tuple[PatternRecommendation, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""


def _load_kb(path: Path | None = None) -> list[dict[str, Any]]:
    global _KB_CACHE
    if path is not None:
        with path.open(encoding="utf-8") as f:
            return list((yaml.safe_load(f) or {}).get("patterns", []))
    with _KB_LOCK:
        if _KB_CACHE is None:
            with KB_PATH.open(encoding="utf-8") as f:
                _KB_CACHE = yaml.safe_load(f)
        return list((_KB_CACHE or {}).get("patterns", []))


def list_patterns() -> list[PatternRecommendation]:
    """Tüm KB pattern'lerini PatternRecommendation listesi olarak döner."""
    return [
        PatternRecommendation(
            name=str(p.get("name", "")),
            label=str(p.get("label", "")),
            type=str(p.get("type", "")),
            side=p.get("side"),
            score=0.0,
            steps=tuple(p.get("steps") or []),
            ideal_attributes=tuple(p.get("ideal_attributes") or []),
            when_use=tuple(p.get("when_use") or []),
            counter_if_opponent=tuple(p.get("counter") or []),
        )
        for p in _load_kb()
    ]


def _attribute_match_score(
    ideal: list[str], our_attrs: dict[str, float],
) -> float:
    """0..30 — bizim attribute skorlarımız ideal listeyle ne kadar örtüşüyor."""
    if not ideal or not our_attrs:
        return 0.0
    scores: list[float] = []
    for attr in ideal:
        v = our_attrs.get(attr)
        if v is None:
            continue
        scores.append(max(0.0, min(1.0, float(v))))
    if not scores:
        return 0.0
    avg = sum(scores) / len(scores)
    coverage = len(scores) / len(ideal)
    return round(30.0 * avg * (0.5 + 0.5 * coverage), 2)


def _style_bonus(opp_style: str | None) -> float:
    """Rakip stili set-piece'e açık mı? +10 bonus."""
    if opp_style is None:
        return 0.0
    if opp_style in ("atletico_compact", "italian_zonal"):
        return 10.0
    return 0.0


def compute_set_piece_recommendation(
    context: SetPieceContext,
    *,
    top_n: int = 3,
    kb: list[dict[str, Any]] | None = None,
) -> EngineResult[SetPiecePatternReport]:
    """Bağlama uygun en üst N pattern öneri."""
    patterns = kb if kb is not None else _load_kb()
    notes: list[str] = []
    candidates: list[tuple[PatternRecommendation, float]] = []

    for p in patterns:
        if str(p.get("type", "")) != context.type:
            continue
        # side filtre yumuşak: pattern.side "any" veya None ise herkes eşleşir
        p_side = p.get("side")
        if context.side is not None and p_side not in (None, "any", context.side):
            continue

        ideal_attrs = list(p.get("ideal_attributes") or [])
        attr_score = _attribute_match_score(ideal_attrs, context.our_attributes)
        style_bonus = _style_bonus(context.opponent_style)
        score = 100.0 + attr_score + style_bonus

        candidates.append((
            PatternRecommendation(
                name=str(p.get("name", "")),
                label=str(p.get("label", "")),
                type=str(p.get("type", "")),
                side=p.get("side"),
                score=round(score, 2),
                steps=tuple(p.get("steps") or []),
                ideal_attributes=tuple(ideal_attrs),
                when_use=tuple(p.get("when_use") or []),
                counter_if_opponent=tuple(p.get("counter") or []),
            ),
            score,
        ))

    candidates.sort(key=lambda x: x[1], reverse=True)
    top = tuple(rec for rec, _ in candidates[:top_n])

    if not top:
        notes.append(
            f"'{context.type}' (side={context.side}) için pattern bulunamadı"
        )
        summary = "Pattern bulunamadı — KB eksik"
    else:
        summary = (
            f"{context.type} × {len(candidates)} aday → "
            f"top {len(top)}: {', '.join(r.label for r in top)}"
        )

    report = SetPiecePatternReport(
        request_type=context.type,
        candidates_considered=len(candidates),
        top_recommendations=top,
        notes=tuple(notes),
        summary=summary,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=0,
        metric="set_piece_recommendation",
        value={
            "type": context.type,
            "side": context.side,
            "candidates": len(candidates),
            "top_n": min(top_n, len(top)),
            "top_names": [r.name for r in top],
            "summary": summary,
        },
        inputs={
            "kb_size": len(patterns),
            "our_attribute_keys": sorted(context.our_attributes.keys()),
            "opponent_style": context.opponent_style,
        },
        formula=(
            "base 100 + attribute_match (0-30) + style_bonus (+10 for "
            "atletico/italian); sort desc; top_n"
        ),
    )
    return EngineResult(value=report, audit=audit)


# Cosine helper if needed (unused for now, score is additive)
def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
