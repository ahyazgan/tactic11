"""Fikstür zorluğu — bir takımın önündeki rakiplerin gücü.

`engine.schedule` "kaç maç" der; bu engine "ne kadar zor" der. Rakip
rating'lerini önceden hesaplanmış bir dict olarak alır (engine pure —
DB/HTTP yok, rakip rating'i üst katman besler).

**v1 → v2:** Side-aware rating. Bir rakip evimize gelirken (deplasman
sıfatıyla) ve evinde oynarken farklı profil sergileyebilir; PR #18'in
`engine.rating` ev/dep ayrımı bunu mümkün kıldı. Engine her upcoming
maçta rakibin O MAÇTAKİ tarafa göre rating'ini seçer:
- Rakip ev sahibi → `opponent.home_rating`
- Rakip deplasman → `opponent.away_rating`
- Side-specific yoksa fallback `opponent.overall_rating`

Zaman ağırlığı: yakın maç daha kritik, uzak maç daha az. Lineer decay:
    w_i = max(MIN_WEIGHT, 1 - days_until_i / DECAY_HORIZON)

Çıktılar rotasyon kararına şu soruları çözer:
- Önümüzdeki maçlar ortalama ne kadar zorlu (side-aware)?
- En zor ve en kolay rakip kim?
- Zaman ağırlıklı zorluk (yakın yüksek ağırlık)?
- Bilinmeyen rating'li rakip var mı (kapsam eksiği)?
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.audit import AuditRecord, EngineResult
from app.engine._protocols import MatchLike
from app.sports import football

ENGINE_NAME = "engine.fixture_difficulty"
ENGINE_VERSION = "2"  # v1 → v2: side-aware rating (OpponentRating)

# Zaman ağırlığı parametreleri
_DECAY_HORIZON_DAYS = 28.0  # 28 günden uzak → minimum ağırlık
_MIN_WEIGHT = 0.2  # uzak maç bile %20 sayar


@dataclass(frozen=True)
class OpponentRating:
    """Bir rakip için side-aware rating + overall fallback.

    Side-specific (`home_rating`, `away_rating`) varsa rakip O TARAFTA
    oynarken kullanılır; yoksa `overall_rating` fallback'i devreye girer.
    Üçü de None ise rakip "rating'i bilinmiyor" sayılır.
    """
    home_rating: float | None = None
    away_rating: float | None = None
    overall_rating: float | None = None

    def for_side(self, opponent_is_home: bool) -> float | None:
        """Rakip ev sahibiyse home_rating; değilse away_rating; yoksa overall."""
        side_specific = self.home_rating if opponent_is_home else self.away_rating
        if side_specific is not None:
            return side_specific
        return self.overall_rating


@dataclass(frozen=True)
class FixtureDifficultyReport:
    team_id: int
    matches_considered: int  # rating'i bilinen rakip maç sayısı
    matches_unknown_opponent: int  # rating'i bilinmeyen rakip (uyarı sinyali)
    avg_opponent_rating: float  # düz ortalama; matches_considered=0 → 0
    weighted_difficulty: float  # zaman ağırlıklı ortalama
    hardest_opponent_id: int | None
    hardest_opponent_rating: float | None
    easiest_opponent_id: int | None
    easiest_opponent_rating: float | None
    home_match_count: int
    away_match_count: int


def _is_upcoming(m: MatchLike, now: datetime) -> bool:
    if m.kickoff <= now:
        return False
    return m.status not in football.FINISHED_STATUSES


def _opponent_id(m: MatchLike, team_id: int) -> int:
    return m.away_team_external_id if m.home_team_external_id == team_id else m.home_team_external_id


def _opponent_is_home(m: MatchLike, team_id: int) -> bool:
    """Rakip o maçta ev sahibi mi? (yani biz deplasmandayız mı?)"""
    return m.away_team_external_id == team_id


def _time_weight(days_until: float) -> float:
    return max(_MIN_WEIGHT, 1.0 - days_until / _DECAY_HORIZON_DAYS)


def compute_fixture_difficulty(
    team_external_id: int,
    matches: Iterable[MatchLike],
    opponent_ratings: dict[int, OpponentRating],
    *,
    now: datetime | None = None,
) -> EngineResult[FixtureDifficultyReport]:
    """Bir takımın upcoming maçlarındaki rakip zorluğu (side-aware).

    `matches` HER maçı içerebilir — fonksiyon upcoming + team-içeren olanları
    filtreler. `opponent_ratings`: external_id → `OpponentRating`. Her maçta
    rakibin o maçtaki tarafına göre uygun rating seçilir. Hiçbir rating
    bulunamazsa `matches_unknown_opponent`'a sayılır.
    """
    ref_now = now or datetime.now(UTC)

    upcoming = [
        m
        for m in matches
        if _is_upcoming(m, ref_now)
        and team_external_id in (m.home_team_external_id, m.away_team_external_id)
    ]
    upcoming.sort(key=lambda m: m.kickoff)

    home_count = sum(1 for m in upcoming if m.home_team_external_id == team_external_id)
    away_count = len(upcoming) - home_count

    rated_entries: list[tuple[int, float, float]] = []  # (opp_id, rating, weight)
    unknown_count = 0
    for m in upcoming:
        opp = _opponent_id(m, team_external_id)
        opp_rating = opponent_ratings.get(opp)
        if opp_rating is None:
            unknown_count += 1
            continue
        rating = opp_rating.for_side(_opponent_is_home(m, team_external_id))
        if rating is None:
            unknown_count += 1
            continue
        days_until = (m.kickoff - ref_now).total_seconds() / 86400
        rated_entries.append((opp, rating, _time_weight(days_until)))

    hardest_id: int | None = None
    easiest_id: int | None = None
    hardest_rating: float | None = None
    easiest_rating: float | None = None
    if rated_entries:
        avg = sum(r for _, r, _ in rated_entries) / len(rated_entries)
        weight_sum = sum(w for _, _, w in rated_entries)
        weighted = sum(r * w for _, r, w in rated_entries) / weight_sum
        hardest = max(rated_entries, key=lambda e: e[1])
        easiest = min(rated_entries, key=lambda e: e[1])
        hardest_id, hardest_rating = hardest[0], hardest[1]
        easiest_id, easiest_rating = easiest[0], easiest[1]
    else:
        avg = 0.0
        weighted = 0.0

    report = FixtureDifficultyReport(
        team_id=team_external_id,
        matches_considered=len(rated_entries),
        matches_unknown_opponent=unknown_count,
        avg_opponent_rating=round(avg, 3),
        weighted_difficulty=round(weighted, 3),
        hardest_opponent_id=hardest_id,
        hardest_opponent_rating=round(hardest_rating, 3) if hardest_rating is not None else None,
        easiest_opponent_id=easiest_id,
        easiest_opponent_rating=round(easiest_rating, 3) if easiest_rating is not None else None,
        home_match_count=home_count,
        away_match_count=away_count,
    )

    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="team",
        subject_id=team_external_id,
        metric="fixture_difficulty",
        value=asdict(report),
        inputs={
            "now_iso": ref_now.isoformat(),
            "upcoming_match_ids": [m.external_id for m in upcoming],
            "known_opponents": sorted(opponent_ratings.keys()),
            "decay_horizon_days": _DECAY_HORIZON_DAYS,
            "min_weight": _MIN_WEIGHT,
        },
        formula=(
            "weighted = Σ(rating_i · w_i) / Σ(w_i); "
            f"w_i = max({_MIN_WEIGHT}, 1 - days_until_i/{_DECAY_HORIZON_DAYS}); "
            "avg = düz ortalama (ağırlıksız); "
            "rating_i = opp.home_rating (rakip ev sahibi) ya da "
            "opp.away_rating (rakip dep); side-specific yoksa overall fallback"
        ),
    )
    return EngineResult(value=report, audit=audit)
