"""Player similarity engine — per-90 stat vektörü + cosine similarity.

Wyscout/StatsBomb tarzı "scout aracı": hedef oyuncuya benzer profili olan
N oyuncuyu bul. Vektör temsili `player_appearances` tablosunun zenginleşmiş
hâlinden çıkarılır (Prompt 4 ile rating, passes, shots, dribbles, fouls,
cards available).

Per-90 normalize: her metrik (toplam / dakika) × 90.

Pure compute — DB'ye dokunmaz. Caller (`/admin/scout/similar` endpoint'i ya
da scheduler job) PlayerAppearance listesini hazırlayıp geçer.

Sınırlama: pas type'i (key pass, through pass), pres regains, xG/xA gibi
event-level metrikler player_appearances'ta yok (Prompt 4 lineup+box-score
seviyesinde durdu). Vendor entegrasyonu gelince vektöre eklenir; bu engine
şu an mevcut 6 metrikten oluşan minimal-ama-anlamlı versiyon.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import PlayerAppearanceLike

ENGINE_NAME = "engine.player_similarity"
ENGINE_VERSION = "1"

# Vektör boyutları — her biri per-90 normalize, min_minutes altında oyuncular
# similarity'e dahil edilmez (sample size guard).
FEATURE_NAMES: tuple[str, ...] = (
    "rating_avg",            # API-Football rating ortalaması (per maç)
    "passes_per_90",
    "passes_accuracy_avg",   # 0-100, zaten yüzde
    "shots_per_90",
    "dribbles_success_per_90",
    "fouls_drawn_per_90",
)

MIN_MINUTES_FOR_SIMILARITY = 270  # ~3 maç (sample size guard)


@dataclass(frozen=True)
class PlayerProfile:
    """Bir oyuncunun aggregate per-90 stat vektörü."""
    player_external_id: int
    total_minutes: int
    matches_played: int
    features: dict[str, float]


@dataclass(frozen=True)
class SimilarityMatch:
    """Bir oyuncuya benzeyen oyuncu + similarity skoru."""
    player_external_id: int
    similarity: float  # -1..1, cosine
    total_minutes: int


@dataclass(frozen=True)
class SimilarityReport:
    """Hedef oyuncu için top-N benzer oyuncu listesi."""
    target_player_id: int
    candidates_considered: int
    candidates_eligible: int  # min_minutes geçen
    top_matches: list[SimilarityMatch]


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _profile_from_appearances(
    player_id: int,
    appearances: Iterable[PlayerAppearanceLike],
) -> PlayerProfile:
    """Bir oyuncunun appearance'larını per-90 vector'a aggregate et."""
    apps = [a for a in appearances if a.player_external_id == player_id]
    total_minutes = sum(a.minutes for a in apps)
    n_matches = len([a for a in apps if a.minutes > 0])

    # Rating ortalaması — None'ları atla
    ratings = [getattr(a, "rating_apifootball", None) for a in apps]
    valid_ratings = [r for r in ratings if r is not None]
    rating_avg = sum(valid_ratings) / len(valid_ratings) if valid_ratings else 0.0

    # Toplamlar (per-90 için)
    def _sum_attr(name: str) -> float:
        return float(sum((getattr(a, name, None) or 0) for a in apps))

    passes_total = _sum_attr("passes_total")
    shots_total = _sum_attr("shots_total")
    dribbles_success = _sum_attr("dribbles_success")
    fouls_drawn = _sum_attr("fouls_drawn")

    # passes_accuracy — averaj (her maçın yüzde'si var; agirlikli per-pass'le yapılabilir
    # ama minimal versiyon: simple avg of game-level percentages, weighted by minutes)
    weighted_acc_sum = 0.0
    weight_sum = 0.0
    for a in apps:
        acc = getattr(a, "passes_accuracy", None)
        if acc is not None and a.minutes > 0:
            weighted_acc_sum += float(acc) * a.minutes
            weight_sum += a.minutes
    passes_accuracy_avg = weighted_acc_sum / weight_sum if weight_sum else 0.0

    per_90 = 90.0 / total_minutes if total_minutes else 0.0
    features = {
        "rating_avg": round(rating_avg, 3),
        "passes_per_90": round(passes_total * per_90, 3),
        "passes_accuracy_avg": round(passes_accuracy_avg, 2),
        "shots_per_90": round(shots_total * per_90, 3),
        "dribbles_success_per_90": round(dribbles_success * per_90, 3),
        "fouls_drawn_per_90": round(fouls_drawn * per_90, 3),
    }
    return PlayerProfile(
        player_external_id=player_id,
        total_minutes=total_minutes,
        matches_played=n_matches,
        features=features,
    )


def compute_player_profile(
    player_external_id: int,
    appearances: Iterable[PlayerAppearanceLike],
) -> EngineResult[PlayerProfile]:
    """Tek oyuncunun vektörünü hesapla + audit."""
    profile = _profile_from_appearances(player_external_id, appearances)
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="player",
        subject_id=player_external_id,
        metric="player_profile",
        value=asdict(profile),
        inputs={
            "feature_names": list(FEATURE_NAMES),
            "min_minutes_for_similarity": MIN_MINUTES_FOR_SIMILARITY,
        },
        formula=(
            "per-90 normalize: sum_attr / total_minutes * 90; "
            "passes_accuracy: minutes-weighted avg"
        ),
    )
    return EngineResult(value=profile, audit=audit)


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """İki feature dict'i arasında cosine similarity (-1..1).

    Sıfır vektör → 0.0 (orthogonal). Numerical stability için
    küçük epsilon değil; sıfır norm'da explicit 0 döner.
    """
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for k in FEATURE_NAMES:
        va = a.get(k, 0.0)
        vb = b.get(k, 0.0)
        dot += va * vb
        norm_a += va * va
        norm_b += vb * vb
    denom = math.sqrt(norm_a) * math.sqrt(norm_b)
    if denom == 0:
        return 0.0
    return dot / denom


def compute_similar_players(
    target_player_id: int,
    target_appearances: Iterable[PlayerAppearanceLike],
    candidate_appearances_by_pid: dict[int, list[PlayerAppearanceLike]],
    *,
    top_n: int = 10,
    min_minutes: int = MIN_MINUTES_FOR_SIMILARITY,
) -> EngineResult[SimilarityReport]:
    """Top-N benzer oyuncuyu bul.

    `target_appearances`: hedef oyuncunun appearance'ları
    `candidate_appearances_by_pid`: aday oyuncular için pid → appearances
    """
    target_profile = _profile_from_appearances(target_player_id, target_appearances)
    eligible_candidates = 0
    matches: list[SimilarityMatch] = []
    for pid, apps in candidate_appearances_by_pid.items():
        if pid == target_player_id:
            continue
        cand_profile = _profile_from_appearances(pid, apps)
        if cand_profile.total_minutes < min_minutes:
            continue
        eligible_candidates += 1
        sim = _cosine_similarity(target_profile.features, cand_profile.features)
        matches.append(SimilarityMatch(
            player_external_id=pid,
            similarity=round(sim, 4),
            total_minutes=cand_profile.total_minutes,
        ))
    matches.sort(key=lambda m: m.similarity, reverse=True)
    top = matches[:top_n]
    report = SimilarityReport(
        target_player_id=target_player_id,
        candidates_considered=len(candidate_appearances_by_pid),
        candidates_eligible=eligible_candidates,
        top_matches=top,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="player",
        subject_id=target_player_id,
        metric="player_similarity",
        value={
            "target": target_player_id,
            "top_matches": [asdict(m) for m in top],
            "candidates_eligible": eligible_candidates,
            "candidates_considered": len(candidate_appearances_by_pid),
        },
        inputs={
            "feature_names": list(FEATURE_NAMES),
            "min_minutes": min_minutes,
            "top_n": top_n,
        },
        formula="cosine_similarity(target.features, candidate.features)",
    )
    return EngineResult(value=report, audit=audit)
