"""Tactical Counter — (rakip stili × bizim stilimiz) → spesifik öneri.

`counter_tactics.yaml` matrisini tüketir. style_fingerprint engine'inin
ürettiği top arketipi + bizim stilimiz girilir; en uygun 3-6 satır taktik
ayar döner.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.tactical_counter"
ENGINE_VERSION = "1"

KB_PATH = (
    Path(__file__).resolve().parents[3]
    / "app" / "data" / "knowledge" / "counter_tactics.yaml"
)

_KB_CACHE: dict[str, Any] | None = None
_KB_LOCK = threading.Lock()


@dataclass(frozen=True)
class CounterAdvice:
    text: str
    focus: str                  # shape | press | transition | set_piece | sub | defending
    tags: tuple[str, ...] = field(default_factory=tuple)
    matched_opp: str = ""
    matched_our: str = ""


@dataclass(frozen=True)
class CounterMatchupReport:
    opponent_style: str
    our_style: str
    advices: tuple[CounterAdvice, ...]
    focuses: tuple[str, ...]    # benzersiz focus listesi
    summary: str


def _load_kb(path: Path | None = None) -> list[dict[str, Any]]:
    global _KB_CACHE
    if path is not None:
        with path.open(encoding="utf-8") as f:
            return list((yaml.safe_load(f) or {}).get("matchups", []))
    with _KB_LOCK:
        if _KB_CACHE is None:
            with KB_PATH.open(encoding="utf-8") as f:
                _KB_CACHE = yaml.safe_load(f)
        return list((_KB_CACHE or {}).get("matchups", []))


def compute_counter_advice(
    *,
    opponent_style: str,
    our_style: str = "any",
    max_advice: int = 6,
    kb: list[dict[str, Any]] | None = None,
) -> EngineResult[CounterMatchupReport]:
    """En uygun counter taktik öneri.

    Önce (opp_style, our_style) tam eşleşme aranır; bulunmazsa (opp, any),
    yine yoksa (any, our), son fallback (any, any).
    """
    matchups = kb if kb is not None else _load_kb()
    seen: list[CounterAdvice] = []

    def _collect(opp_key: str, our_key: str) -> None:
        for m in matchups:
            if m.get("opp") != opp_key or m.get("our") != our_key:
                continue
            for adv in m.get("advice") or []:
                seen.append(CounterAdvice(
                    text=str(adv.get("text", "")),
                    focus=str(adv.get("focus", "shape")),
                    tags=tuple(adv.get("tags") or []),
                    matched_opp=opp_key, matched_our=our_key,
                ))

    # Sıralı arama: spesifik → universal
    for opp_key, our_key in [
        (opponent_style, our_style),
        (opponent_style, "any"),
        ("any", our_style),
        ("any", "any"),
    ]:
        if not seen:
            _collect(opp_key, our_key)
        else:
            # Hem opp spesifik hem our any de varsa onları da topla (tek seferlik)
            _collect(opp_key, our_key)

    # Tekrarları kırp (text-based)
    deduped: list[CounterAdvice] = []
    seen_texts: set[str] = set()
    for a in seen:
        if a.text in seen_texts:
            continue
        seen_texts.add(a.text)
        deduped.append(a)
        if len(deduped) >= max_advice:
            break

    focuses = tuple(sorted({a.focus for a in deduped}))
    if not deduped:
        summary = (
            f"Eşleşme yok ({opponent_style} × {our_style}) "
            f"— matris boş veya isimler tanımsız"
        )
    else:
        summary = (
            f"{opponent_style} × {our_style} → "
            f"{len(deduped)} öneri ({', '.join(focuses)})"
        )

    report = CounterMatchupReport(
        opponent_style=opponent_style, our_style=our_style,
        advices=tuple(deduped),
        focuses=focuses, summary=summary,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=0,
        metric="tactical_counter",
        value={
            "opponent_style": opponent_style,
            "our_style": our_style,
            "advice_count": len(deduped),
            "focuses": list(focuses),
            "summary": summary,
        },
        inputs={"matchup_pool_size": len(matchups), "max_advice": max_advice},
        formula=(
            "Spesifik (opp×our) → (opp×any) → (any×our) → (any×any) "
            "fallback; text dedup; max_advice cap"
        ),
    )
    return EngineResult(value=report, audit=audit)
