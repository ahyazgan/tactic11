"""Opponent Style Fingerprint — bir takımın 8-vektör taktik kimliği.

Son N maç engine çıktılarından (PPDA, FieldTilt, Direct Play, Counter Threat,
Set-piece Reliance, Width, High Line Risk, Press Height) 8-vektör çıkarır;
8 arketiple cosine benzerlikle eşleştirir. En yakın iki arketip + güven
skoru + tarz özet metni.

Pure compute. TeamMatchStat listesi + opsiyonel meta input.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult

ENGINE_NAME = "engine.style_fingerprint"
ENGINE_VERSION = "1"


@dataclass(frozen=True)
class TeamMatchStat:
    """Bir takımın bir maçtaki taktik metrikleri (engine çıktısı sentezi).

    Tüm değerler 0..1 normalize (ppda hariç — ham sayı).
    """
    ppda: float                          # 4-25 arası ham
    field_tilt_pct: float                # 0-100
    direct_play_pct: float               # 0-100 (uzun pas oranı)
    counter_threat: float                # 0-1 (kontradan açıklara şut/xG)
    set_piece_share_pct: float           # 0-100 (set-piece kaynaklı xG / toplam xG)
    width_pct: float                     # 0-100 (kanat saldırı payı)
    high_line_risk: float                # 0-1 (savunma çizgisi yükseklik proxy)
    press_height: float                  # 0-1 (def aksiyon ortalama x)


@dataclass(frozen=True)
class StyleVector:
    """Normalize 8-vektör (her boyut 0..1)."""
    pressing: float                      # PPDA tersi → yüksek pres
    possession: float                    # 1 - field_tilt benzeri inversi (alt; düz field_tilt da kullanılır)
    direct_play: float
    counter_threat: float
    set_piece_reliance: float
    width: float
    high_line_risk: float
    press_height: float

    def to_tuple(self) -> tuple[float, ...]:
        return (
            self.pressing, self.possession, self.direct_play,
            self.counter_threat, self.set_piece_reliance, self.width,
            self.high_line_risk, self.press_height,
        )


@dataclass(frozen=True)
class StyleArchetype:
    name: str
    label: str
    description: str
    vector: tuple[float, ...]            # 8-tuple, hedef stil değerleri


@dataclass(frozen=True)
class StyleFingerprint:
    sample_size: int                     # kaç maç verisi
    avg_vector: StyleVector
    top_archetype: StyleArchetype
    top_similarity: float                # 0-1 cosine
    second_archetype: StyleArchetype | None
    second_similarity: float
    confidence: str                      # "high" | "medium" | "low" | "insufficient"
    summary: str
    counter_play_advice: tuple[str, ...] = field(default_factory=tuple)


# Arketip kütüphanesi — kanonik 8-vektör formatlarıyla
ARCHETYPES: list[StyleArchetype] = [
    StyleArchetype(
        name="klopp_press", label="Klopp-Pres",
        description="Yüksek pres + hızlı kontra; gegenpressing temel",
        vector=(0.90, 0.55, 0.30, 0.80, 0.20, 0.55, 0.70, 0.80),
    ),
    StyleArchetype(
        name="pep_possession", label="Pep-Possession",
        description="Yüksek possession + pozisyonel oyun, dış pres az",
        vector=(0.45, 0.90, 0.15, 0.30, 0.18, 0.50, 0.50, 0.55),
    ),
    StyleArchetype(
        name="atletico_compact", label="Atletico-Kompakt",
        description="Düşük blok + bireysel duels + set-piece",
        vector=(0.40, 0.40, 0.35, 0.50, 0.55, 0.30, 0.20, 0.30),
    ),
    StyleArchetype(
        name="italian_zonal", label="İtalyan-Zonal",
        description="Orta blok zonal savunma + standart toplara yatırım",
        vector=(0.50, 0.55, 0.40, 0.45, 0.65, 0.40, 0.35, 0.45),
    ),
    StyleArchetype(
        name="bvb_counter", label="BVB-Kontra",
        description="Direkt pas + hızlı kanat patlaması",
        vector=(0.55, 0.45, 0.65, 0.85, 0.25, 0.75, 0.40, 0.50),
    ),
    StyleArchetype(
        name="lecce_direct", label="Lecce-Direkt",
        description="Uzun top + 2 forvet + minimum yapı",
        vector=(0.35, 0.30, 0.85, 0.55, 0.40, 0.55, 0.30, 0.40),
    ),
    StyleArchetype(
        name="conte_3_5_2_wing", label="Conte-Wing 3-5-2",
        description="3 savunma + wing-back yoğun kanat",
        vector=(0.55, 0.60, 0.45, 0.60, 0.45, 0.80, 0.50, 0.55),
    ),
    StyleArchetype(
        name="ten_hag_modern_pos", label="Modern Possession",
        description="Possession + pozisyonel + yüksek 6n yapı",
        vector=(0.60, 0.80, 0.20, 0.50, 0.30, 0.50, 0.60, 0.65),
    ),
]


# Arketipe karşı oynama tavsiyeleri (counter playbook)
_COUNTER_PLAYBOOK: dict[str, list[str]] = {
    "klopp_press": [
        "Üçüncü oyuncu kombinasyonu — geriden GK ile riskli kısa pas yapma",
        "Forvet derinlik versin; pres'i uzun topla aş",
        "Pres kırılınca anında 5-3-2 düşük blok ile çekil",
    ],
    "pep_possession": [
        "Kalabalık orta saha + pas linelarini kapat (pas %75'ten az tutturt)",
        "Switch'e karşı sabırlı 4-4-2 mid-block",
        "Top sahipliği değil pas line kontrolünü hedefle",
    ],
    "atletico_compact": [
        "Sahanın bir yanını yığ, sonra switch of play yıldıza",
        "Half-space inverted FB ile diziden çık",
        "Uzaktan şut + ikinci top hazırlığı",
    ],
    "italian_zonal": [
        "Zonal-koruma karşıya hareketli blok (köşelerde)",
        "Cut-back alçak orta tercih",
    ],
    "bvb_counter": [
        "Top kazanırken üst 4 hat boş bırakma",
        "Defansif geçişte sayısal eşitlik şart",
        "Yıldız taşıyıcılarına body-up + foul tehdidi",
    ],
    "lecce_direct": [
        "Hava topu uzman stoper koy",
        "Forvet önünde 'second-ball' avcısı",
    ],
    "conte_3_5_2_wing": [
        "Wing-back'leri yüksekte tut (defansif geri çekildiklerinde alanı doldur)",
        "5'li ofansif baskıya karşı orta saha çıkış yolu",
    ],
    "ten_hag_modern_pos": [
        "Düşük 6n'a hızlı pres",
        "Inverted FB izlerini kapat (orta hat geri itme)",
    ],
}


def _safe_avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _normalize_stats(stats: list[TeamMatchStat]) -> StyleVector:
    """Ham maç istatistiklerini 8-vektör 0..1 normalize."""
    # PPDA: 4 (çok yüksek pres) → 1.0; 25 (zayıf pres) → 0.0; linear
    ppda_avg = _safe_avg([s.ppda for s in stats])
    pressing = _clip01((25.0 - ppda_avg) / 21.0)
    # field_tilt direct olarak possession proxy (0-100 → 0..1)
    possession = _clip01(_safe_avg([s.field_tilt_pct for s in stats]) / 100.0)
    direct_play = _clip01(_safe_avg([s.direct_play_pct for s in stats]) / 100.0)
    counter_threat = _clip01(_safe_avg([s.counter_threat for s in stats]))
    set_piece = _clip01(_safe_avg([s.set_piece_share_pct for s in stats]) / 100.0)
    width = _clip01(_safe_avg([s.width_pct for s in stats]) / 100.0)
    high_line = _clip01(_safe_avg([s.high_line_risk for s in stats]))
    press_h = _clip01(_safe_avg([s.press_height for s in stats]))
    return StyleVector(
        pressing=round(pressing, 3),
        possession=round(possession, 3),
        direct_play=round(direct_play, 3),
        counter_threat=round(counter_threat, 3),
        set_piece_reliance=round(set_piece, 3),
        width=round(width, 3),
        high_line_risk=round(high_line, 3),
        press_height=round(press_h, 3),
    )


def _cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _confidence(sample_size: int, top_sim: float, gap: float) -> str:
    if sample_size < 3:
        return "insufficient"
    if top_sim >= 0.95 and gap >= 0.05:
        return "high"
    if top_sim >= 0.88:
        return "medium"
    return "low"


def _build_summary(arch: StyleArchetype, conf: str, vec: StyleVector) -> str:
    base = f"Stil: {arch.label} — {arch.description}"
    if conf == "insufficient":
        return f"{base} (örnek yetersiz, en yakın eşleşme)"
    parts = []
    if vec.pressing >= 0.7:
        parts.append("yüksek pres")
    elif vec.pressing <= 0.3:
        parts.append("düşük pres")
    if vec.possession >= 0.7:
        parts.append("possession ağırlıklı")
    if vec.direct_play >= 0.6:
        parts.append("direkt oyun")
    if vec.counter_threat >= 0.7:
        parts.append("kontra tehdidi yüksek")
    if vec.set_piece_reliance >= 0.55:
        parts.append("set-piece eğilimli")
    if parts:
        return f"{base} · {' + '.join(parts)}"
    return base


def list_archetypes() -> list[StyleArchetype]:
    return list(ARCHETYPES)


def compute_style_fingerprint(
    stats: Iterable[TeamMatchStat],
    *,
    archetypes: list[StyleArchetype] | None = None,
) -> EngineResult[StyleFingerprint]:
    """Takım stil parmak izi — cosine match."""
    arch_list = archetypes or ARCHETYPES
    slist = list(stats)
    if not slist:
        vec = StyleVector(0, 0, 0, 0, 0, 0, 0, 0)
        # Tüm 0 vektörü cosine'da tanımsız — placeholder
        fp = StyleFingerprint(
            sample_size=0, avg_vector=vec,
            top_archetype=arch_list[0], top_similarity=0.0,
            second_archetype=None, second_similarity=0.0,
            confidence="insufficient",
            summary="Veri yok (sample_size=0)",
        )
        return EngineResult(value=fp, audit=AuditRecord(
            engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
            subject_type="team", subject_id=0, metric="style_fingerprint",
            value={"sample_size": 0, "confidence": "insufficient"},
            inputs={}, formula="empty",
        ))

    vec = _normalize_stats(slist)
    vec_t = vec.to_tuple()

    sims = [
        (a, _cosine_similarity(vec_t, a.vector))
        for a in arch_list
    ]
    sims.sort(key=lambda x: x[1], reverse=True)
    top, top_sim = sims[0]
    second, second_sim = (sims[1] if len(sims) > 1 else (None, 0.0))

    gap = top_sim - second_sim if second is not None else 0.0
    conf = _confidence(len(slist), top_sim, gap)
    summary = _build_summary(top, conf, vec)
    counter = tuple(_COUNTER_PLAYBOOK.get(top.name, []))

    fp = StyleFingerprint(
        sample_size=len(slist),
        avg_vector=vec,
        top_archetype=top, top_similarity=round(top_sim, 3),
        second_archetype=second, second_similarity=round(second_sim, 3),
        confidence=conf, summary=summary,
        counter_play_advice=counter,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="team", subject_id=0, metric="style_fingerprint",
        value={
            "sample_size": len(slist),
            "top_archetype": top.name,
            "top_similarity": round(top_sim, 3),
            "second_archetype": second.name if second else None,
            "confidence": conf,
            "summary": summary,
            "counter_count": len(counter),
        },
        inputs={
            "archetype_count": len(arch_list),
            "vector_dim": len(vec_t),
        },
        formula=(
            "8-vektör (pressing=PPDA-tersi, possession=field_tilt, "
            "direct_play, counter_threat, set_piece, width, high_line, "
            "press_height) → cosine → top arketip"
        ),
    )
    return EngineResult(value=fp, audit=audit)
