"""Star Feed — yıldız oyuncuya top besleme monitörü (G.3).

TD'nin "yıldız oyuncuya top gitmiyor" şüphesini sayıyla doğrulayan engine.
Pencere içi pas + xT katkı + son üçte varlık → involvement_state.

Pure compute. PassEvent + Shot listesi + star_player_id input.
"Yıldıza dik pas hattı kur" / "Yıldız orta sahada kalıyor, son üçe çek"
gibi somut taktik tavsiyeleri üretir.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent, Shot
from app.engine.xt import xt_value_at

ENGINE_NAME = "engine.star_feed"
ENGINE_VERSION = "1"

DEFAULT_WINDOW_MIN = 15.0

# Pas paylaşım eşikleri (window içinde yıldızın takım pasındaki %'si)
PASS_SHARE_STARVED = 5.0       # < %5 → aç
PASS_SHARE_UNDERFED = 10.0     # < %10 → az besleniyor
PASS_SHARE_WELLFED = 20.0      # >= %20 → çok besleniyor

# Son üç eşiği (saha %66+)
FINAL_THIRD_X = 66.0

# Final-third share eşiği (yıldız paslarının kaçı son üçte başladı)
FINAL_THIRD_LOW_SHARE = 25.0


@dataclass(frozen=True)
class StarFeedReport:
    star_player_id: int
    team_external_id: int
    current_minute: float
    window_min: float
    # Etkileşim
    star_passes_window: int
    star_passes_total: int
    star_shots_window: int
    star_touches_per_10min: float
    team_passes_window: int
    pass_share_pct: float
    # Saha
    final_third_passes: int
    final_third_share_pct: float
    # xT
    star_xt_window: float
    team_xt_window: float
    star_xt_share_pct: float
    # Çıkarım
    involvement_state: str
    suggested_action: str          # ON | OK | NUDGE | OVERLOAD
    tactical_advice: str


def _pass_xt_delta(p: PassEvent) -> float:
    """Bir pasın xT katkısı (negatif → -xT, completed=False ise)."""
    if not p.completed:
        return -xt_value_at(p.start_x, p.start_y)
    return xt_value_at(p.end_x, p.end_y) - xt_value_at(p.start_x, p.start_y)


def _involvement_from_share(share_pct: float) -> tuple[str, str]:
    """Pass share → (state, action) tuple."""
    if share_pct < PASS_SHARE_STARVED:
        return "starved", "ON"
    if share_pct < PASS_SHARE_UNDERFED:
        return "underfed", "NUDGE"
    if share_pct < PASS_SHARE_WELLFED:
        return "balanced", "OK"
    return "well-fed", "OVERLOAD"


def _build_advice(
    state: str, final_third_share: float, star_passes_window: int,
) -> str:
    if star_passes_window == 0:
        return (
            "Yıldız son pencerede HİÇ pas atmadı — "
            "kanat oyuncularını içe çek, dik pas hattı kur, "
            "yıldız üzerinden çevirme oyunu başlat"
        )
    if state == "starved":
        return (
            "Yıldız top almıyor — kanat oyuncuları içe çek, "
            "yıldıza dik pas hattı yarat, çevre üçgenler oluştur"
        )
    if state == "underfed":
        base = "Yıldıza top az gidiyor — orta sahadan çevirme paslar yönlendir"
        if final_third_share < FINAL_THIRD_LOW_SHARE:
            return base + ", final 3.'te buluşturma artır"
        return base
    if state == "well-fed":
        return (
            "Yıldız sürekli topta — yorgunluk + savunma yığını riski. "
            "İkinci nokta için kanat overload, yıldızı kesişimde tutma"
        )
    # balanced
    if final_third_share < FINAL_THIRD_LOW_SHARE:
        return (
            "Yıldız dengeli besleniyor ama orta sahada kalıyor — "
            "son üçte buluşmayı artır"
        )
    return "Yıldız dengeli besleniyor, tempo standart"


def compute_star_feed(
    team_external_id: int,
    star_player_id: int,
    passes: Iterable[PassEvent],
    shots: Iterable[Shot] = (),
    *,
    current_minute: float,
    window_min: float = DEFAULT_WINDOW_MIN,
) -> EngineResult[StarFeedReport]:
    """Yıldızın takım pasındaki payı + xT katkısı + son üç varlığı.

    "Top dokunma" proxy'si: oyuncunun yaptığı paslar (player_external_id eşitliği).
    Gerçek receiver alanı domain'de olmadığı için outgoing-pass yaklaşımı.
    """
    window_lo = current_minute - window_min

    star_passes_total = 0
    star_passes_window = 0
    team_passes_window = 0
    final_third_passes = 0
    star_xt_window = 0.0
    team_xt_window = 0.0

    for p in passes:
        is_team = p.team_external_id == team_external_id
        if not is_team:
            continue
        in_window = window_lo <= p.minute <= current_minute
        if in_window:
            team_passes_window += 1
            team_xt_window += max(0.0, _pass_xt_delta(p))

        if p.player_external_id == star_player_id:
            star_passes_total += 1
            if in_window:
                star_passes_window += 1
                star_xt_window += max(0.0, _pass_xt_delta(p))
                if p.start_x >= FINAL_THIRD_X:
                    final_third_passes += 1

    star_shots_window = 0
    for s in shots:
        if (s.player_external_id == star_player_id
                and window_lo <= s.minute <= current_minute):
            star_shots_window += 1

    pass_share = (
        round((star_passes_window / team_passes_window) * 100.0, 2)
        if team_passes_window > 0 else 0.0
    )
    final_third_share = (
        round((final_third_passes / star_passes_window) * 100.0, 2)
        if star_passes_window > 0 else 0.0
    )
    xt_share = (
        round((star_xt_window / team_xt_window) * 100.0, 2)
        if team_xt_window > 0 else 0.0
    )
    touches_per_10min = (
        round(((star_passes_window + star_shots_window) / window_min) * 10.0, 2)
        if window_min > 0 else 0.0
    )

    state, action = _involvement_from_share(pass_share)
    advice = _build_advice(state, final_third_share, star_passes_window)

    report = StarFeedReport(
        star_player_id=star_player_id,
        team_external_id=team_external_id,
        current_minute=current_minute,
        window_min=window_min,
        star_passes_window=star_passes_window,
        star_passes_total=star_passes_total,
        star_shots_window=star_shots_window,
        star_touches_per_10min=touches_per_10min,
        team_passes_window=team_passes_window,
        pass_share_pct=pass_share,
        final_third_passes=final_third_passes,
        final_third_share_pct=final_third_share,
        star_xt_window=round(star_xt_window, 4),
        team_xt_window=round(team_xt_window, 4),
        star_xt_share_pct=xt_share,
        involvement_state=state,
        suggested_action=action,
        tactical_advice=advice,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="player", subject_id=star_player_id,
        metric="star_feed",
        value={
            "involvement_state": state,
            "suggested_action": action,
            "pass_share_pct": pass_share,
            "star_xt_share_pct": xt_share,
            "final_third_share_pct": final_third_share,
            "star_passes_window": star_passes_window,
            "team_passes_window": team_passes_window,
            "star_shots_window": star_shots_window,
            "touches_per_10min": touches_per_10min,
            "tactical_advice": advice,
        },
        inputs={
            "current_minute": current_minute,
            "window_min": window_min,
            "team_external_id": team_external_id,
            "thresholds": {
                "pass_share_starved": PASS_SHARE_STARVED,
                "pass_share_underfed": PASS_SHARE_UNDERFED,
                "pass_share_wellfed": PASS_SHARE_WELLFED,
                "final_third_x": FINAL_THIRD_X,
                "final_third_low_share": FINAL_THIRD_LOW_SHARE,
            },
        },
        formula=(
            "star_passes_window/team_passes_window → involvement_state; "
            "star_xt/team_xt → xt_share"
        ),
    )
    return EngineResult(value=report, audit=audit)
