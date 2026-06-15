"""Concept Recognizer — taktiksel konsept tespit motoru.

`app/data/knowledge/tactical_concepts.yaml` içeriğini canlı snapshot'a
uygular; trigger_signals tutan her konsept "aktif" sayılır. Hem RAKİP'in
hem BİZİM uyguladığımız konseptleri ayrı liste olarak ayrıştırır.

Pure compute. Snapshot dict (mevcut live-decision body) + perspective
(us|opp) input.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.concept_recognizer"
ENGINE_VERSION = "1"

# YAML KB yolu — relative repo root
KB_PATH = Path(__file__).resolve().parents[3] / "app" / "data" / "knowledge" / "tactical_concepts.yaml"

# Process-life cache (her boot 1 kez yükle)
_KB_CACHE: dict[str, Any] | None = None
_KB_LOCK = threading.Lock()


@dataclass(frozen=True)
class ActiveConcept:
    name: str
    label: str
    family: str
    definition: str
    counter_when_opp_uses_it: tuple[str, ...] = field(default_factory=tuple)
    advice_when_we_use_it: tuple[str, ...] = field(default_factory=tuple)
    perspective: str = "opp"  # "opp" | "us"


@dataclass(frozen=True)
class ConceptRecognitionReport:
    snapshot_minute: float
    opponent_concepts: tuple[ActiveConcept, ...]
    our_concepts: tuple[ActiveConcept, ...]
    families_seen: tuple[str, ...]
    counter_advice: tuple[str, ...]   # rakibin konseptlerine karşı bizim aksiyon listesi
    summary: str


def load_concepts(path: Path | None = None) -> list[dict[str, Any]]:
    """KB'yi disk'ten oku ve cache'le. path verilirse cache bypass."""
    global _KB_CACHE
    if path is not None:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return list(data.get("concepts", []))
    with _KB_LOCK:
        if _KB_CACHE is None:
            with KB_PATH.open(encoding="utf-8") as f:
                _KB_CACHE = yaml.safe_load(f)
        return list((_KB_CACHE or {}).get("concepts", []))


# Operator implementasyonları (snapshot value vs threshold)
_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _signals_satisfied(
    triggers: dict[str, Any], snapshot: dict[str, Any],
) -> bool:
    """Tüm trigger_signals snapshot'ta sağlanıyor mu?"""
    if not triggers:
        return False
    for sig_name, condition in triggers.items():
        if sig_name not in snapshot:
            return False
        snap_val = snapshot.get(sig_name)
        op = condition.get("op")
        threshold = condition.get("value")
        fn = _OPS.get(op)
        if fn is None or snap_val is None:
            return False
        try:
            if not fn(snap_val, threshold):
                return False
        except TypeError:
            return False
    return True


def _to_active(c: dict[str, Any], perspective: str) -> ActiveConcept:
    return ActiveConcept(
        name=str(c.get("name", "")),
        label=str(c.get("label", c.get("name", ""))),
        family=str(c.get("family", "general")),
        definition=str(c.get("definition", "")).strip(),
        counter_when_opp_uses_it=tuple(c.get("counter_when_opp_uses_it") or []),
        advice_when_we_use_it=tuple(c.get("advice_when_we_use_it") or []),
        perspective=perspective,
    )


def compute_active_concepts(
    snapshot: dict[str, Any],
    *,
    current_minute: float,
    kb: list[dict[str, Any]] | None = None,
) -> EngineResult[ConceptRecognitionReport]:
    """Snapshot'a uygulanmış aktif taktiksel konseptler.

    snapshot: dict, anahtar isimleri yaml'daki trigger_signals isimleriyle eşleşmeli.
              "opp_*" prefix RAKİBİN konsepti için, prefix'siz alanlar BİZİM
              tarafımız için kullanılır. (Örnek: "my_score_diff" bizim açımız.)
    """
    concepts = kb if kb is not None else load_concepts()
    opp_active: list[ActiveConcept] = []
    our_active: list[ActiveConcept] = []
    counter_advice: list[str] = []
    families: set[str] = set()

    for c in concepts:
        triggers = c.get("trigger_signals") or {}
        if not triggers:
            continue
        # Konsept opp_* sinyalleri içeriyorsa rakip perspective; aksi halde bizim
        opp_keys = [k for k in triggers if k.startswith("opp_")]
        is_opp = len(opp_keys) > 0
        if _signals_satisfied(triggers, snapshot):
            act = _to_active(c, perspective="opp" if is_opp else "us")
            if is_opp:
                opp_active.append(act)
                # Karşı-tavsiye dökümü
                for line in act.counter_when_opp_uses_it:
                    counter_advice.append(f"[{act.label}] {line}")
            else:
                our_active.append(act)
            families.add(act.family)

    summary_parts = []
    if opp_active:
        summary_parts.append(
            f"Rakip {len(opp_active)} konsept aktif: "
            + ", ".join(c.label for c in opp_active[:3]),
        )
    if our_active:
        summary_parts.append(
            f"Bizim {len(our_active)} konsept tetiklendi: "
            + ", ".join(c.label for c in our_active[:3]),
        )
    if not summary_parts:
        summary_parts.append("Aktif taktiksel konsept yok")
    summary = " · ".join(summary_parts)

    report = ConceptRecognitionReport(
        snapshot_minute=current_minute,
        opponent_concepts=tuple(opp_active),
        our_concepts=tuple(our_active),
        families_seen=tuple(sorted(families)),
        counter_advice=tuple(counter_advice[:6]),
        summary=summary,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=0,
        metric="concept_recognition",
        value={
            "opp_concepts": [c.name for c in opp_active],
            "our_concepts": [c.name for c in our_active],
            "families": list(families),
            "counter_advice_count": len(counter_advice),
            "summary": summary,
        },
        inputs={
            "current_minute": current_minute,
            "kb_size": len(concepts),
            "snapshot_keys": sorted(snapshot.keys())[:20],  # debug için kısaltıldı
        },
        formula=(
            "trigger_signals tüm key'leri snapshot'ta op+value tutar → konsept aktif; "
            "opp_* prefix → rakip perspective"
        ),
    )
    return EngineResult(value=report, audit=audit)
