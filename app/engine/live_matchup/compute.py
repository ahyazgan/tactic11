"""Live Matchup — bireysel eşleşme okuma (Faz 7 G: #4, #5, #6).

Üç canlı sinyal (event-window proxy):
4. Düello kaybeden eşleşme: bizim bir oyuncumuz düello/defansif aksiyonların
   çoğunu kaybediyor → "yardım gönder ya da eşleşmeyi değiştir".
5. Sıcak el yakalama: rakibin bir oyuncusu her topa giriyor (pas katılımı
   patladı) → "özel markaj".
6. Kendi yıldızını besle: belirlenen yıldız oyuncumuz son window'da topa az
   dokundu → "oyunu ona çevir".

Saf hesap. Pas + def listesi + window + (opsiyonel star_player_id).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.audit import AuditRecord, EngineResult
from app.domain import DefensiveAction, PassEvent

ENGINE_NAME = "engine.live_matchup"
ENGINE_VERSION = "1"

WINDOW_MIN = 15.0
# Düello: en az bu kadar deneme + başarı oranı altı
DUEL_MIN_ATTEMPTS = 4
DUEL_LOSE_RATE = 0.4
# Sıcak el: rakip oyuncu katılımı >= bu + window payı >= bu
HOT_MIN_TOUCHES = 6
HOT_SHARE = 0.35
# Yıldız besle: touch <= bu → besleme uyarısı
STAR_LOW_TOUCHES = 2

# Düello sayılan defansif aksiyon tipleri
DUEL_TYPES = ("tackle", "duel_won", "pressure", "block")


@dataclass(frozen=True)
class StrugglingDefender:
    player_external_id: int
    attempts: int
    lost: int
    lose_rate: float


@dataclass(frozen=True)
class HotPlayer:
    player_external_id: int
    touches: int
    window_share: float


@dataclass(frozen=True)
class LiveMatchupReport:
    team_external_id: int
    opponent_external_id: int
    current_minute: float
    window_min: float
    # #4 düello kaybeden
    struggling_defender: StrugglingDefender | None
    # #5 sıcak el
    hot_opponent: HotPlayer | None
    # #6 yıldız besle
    star_player_id: int | None
    star_touches: int
    feed_star: bool
    alerts: tuple[str, ...] = field(default_factory=tuple)


def compute_live_matchup(
    team_external_id: int,
    opponent_external_id: int,
    passes: list[PassEvent],
    defs: list[DefensiveAction],
    *,
    current_minute: float,
    window_min: float = WINDOW_MIN,
    star_player_id: int | None = None,
) -> EngineResult[LiveMatchupReport]:
    win_start = current_minute - window_min
    in_win = lambda m: win_start <= m <= current_minute  # noqa: E731

    # #4 düello kaybeden — bizim oyuncu bazlı defansif düello başarısı
    our_duels = [
        d for d in defs
        if d.team_external_id == team_external_id
        and d.action_type in DUEL_TYPES and in_win(d.minute)
    ]
    by_player: dict[int, list[bool]] = {}
    for d in our_duels:
        by_player.setdefault(d.player_external_id, []).append(d.successful)
    struggling: StrugglingDefender | None = None
    worst_rate = 1.0
    for pid, results in by_player.items():
        att = len(results)
        lost = sum(1 for r in results if not r)
        if att < DUEL_MIN_ATTEMPTS:
            continue
        rate = lost / att
        if rate >= (1.0 - DUEL_LOSE_RATE) and rate > (1.0 - worst_rate):
            # rate burada kayıp oranı; lose_rate >= eşik
            worst_rate = 1.0 - rate
            struggling = StrugglingDefender(pid, att, lost, round(rate, 3))

    # #5 sıcak el — rakip oyuncu pas katılımı
    opp_p = [p for p in passes if p.team_external_id == opponent_external_id
             and in_win(p.minute)]
    opp_touch: dict[int, int] = {}
    for p in opp_p:
        opp_touch[p.player_external_id] = opp_touch.get(p.player_external_id, 0) + 1
    hot: HotPlayer | None = None
    total_opp = len(opp_p)
    if opp_touch:
        pid, touches = max(opp_touch.items(), key=lambda kv: kv[1])
        share = touches / total_opp if total_opp else 0.0
        if touches >= HOT_MIN_TOUCHES and share >= HOT_SHARE:
            hot = HotPlayer(pid, touches, round(share, 3))

    # #6 yıldız besle
    star_touches = 0
    feed = False
    if star_player_id is not None:
        star_touches = sum(
            1 for p in passes
            if p.team_external_id == team_external_id
            and p.player_external_id == star_player_id and in_win(p.minute)
        )
        feed = star_touches <= STAR_LOW_TOUCHES

    # Alert metinleri
    alerts: list[str] = []
    if struggling:
        alerts.append(
            f"DÜELLO: #{struggling.player_external_id} {struggling.attempts} "
            f"düellodan {struggling.lost} kaybetti — yardım gönder / eşleşmeyi değiştir"
        )
    if hot:
        alerts.append(
            f"SICAK EL: rakip #{hot.player_external_id} her topa giriyor "
            f"({hot.touches} dokunuş, %{int(hot.window_share*100)}) — özel markaj"
        )
    if feed:
        alerts.append(
            f"YILDIZ: #{star_player_id} son {int(window_min)}dk topa az dokundu "
            f"({star_touches}) — oyunu ona çevir"
        )

    report = LiveMatchupReport(
        team_external_id=team_external_id,
        opponent_external_id=opponent_external_id,
        current_minute=current_minute,
        window_min=window_min,
        struggling_defender=struggling,
        hot_opponent=hot,
        star_player_id=star_player_id,
        star_touches=star_touches,
        feed_star=feed,
        alerts=tuple(alerts),
    )
    audit = AuditRecord(
        engine=ENGINE_NAME, engine_version=ENGINE_VERSION,
        subject_type="match", subject_id=team_external_id,
        metric="live_matchup",
        value={
            "struggling_defender": struggling.player_external_id if struggling else None,
            "hot_opponent": hot.player_external_id if hot else None,
            "feed_star": feed, "alerts": list(alerts),
        },
        inputs={
            "current_minute": current_minute, "window_min": window_min,
            "opponent_external_id": opponent_external_id,
            "star_player_id": star_player_id,
        },
        formula="oyuncu düello kayıp oranı + rakip pas katılım payı + yıldız dokunuş sayısı",
    )
    return EngineResult(value=report, audit=audit)
