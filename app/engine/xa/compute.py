"""Expected Assists (xA) — şutu hazırlayan asistana xG değerini atar.

Tanım: bir oyuncunun yaptığı `key_pass` (asist olabilen pas) için, o pas
sonrası gelen şutun xG'si o oyuncuya xA olarak yazılır. Gerçek gol asisti
gerekmez — beklenen değer.

Veri: PassEvent (key_pass=True olanlar) + Shot listesi. Genellikle
StatsBomb event'inde `pass.shot_assist=True` flag'i veya `pass.goal_assist`
işareti var.

Bu engine bu iki listeyi `match_external_id` + `minute` üzerinden eşler:
key_pass yapan oyuncu için ardından gelen shot.xG'yi xA'sına ekler.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.audit import AuditRecord, EngineResult
from app.domain import PassEvent, Shot
from app.engine.xg import compute_shot_xg

ENGINE_NAME = "engine.xa"
ENGINE_VERSION = "1"

# Pas → şut eşleştirme penceresi (saniye). StatsBomb event'inde key_pass
# flag zaten direkt eşleştirme yapıyor ama defensive: ±10 sn aralık.
SHOT_ASSIST_WINDOW_SECONDS = 10.0


@dataclass(frozen=True)
class PlayerXAReport:
    player_external_id: int
    minutes: int
    key_passes: int        # toplam key_pass sayısı
    xa_total: float        # toplam xA
    xa_per_90: float
    goals_assisted: int    # gerçek asist sayısı (kalibrasyon için)


def compute_player_xa(
    player_external_id: int,
    passes: Iterable[PassEvent],
    shots: Iterable[Shot],
    *,
    minutes_played: int = 90,
) -> EngineResult[PlayerXAReport]:
    """Bir oyuncunun xA katkısı.

    Yöntem:
    1. Player'ın `key_pass=True` olan paslarını al
    2. Her key_pass için: aynı match'te + minute aralığında (±window) shot var mı
    3. Shot bulunursa engine.xg ile xG hesapla, oyuncunun xA'sına ekle
    4. `goal_assist=True` paslar gerçek goal_assists sayısını verir
    """
    pass_list = list(passes)
    shot_list = list(shots)
    key_passes = 0
    xa_total = 0.0
    goals_assisted = 0
    for p in pass_list:
        if p.player_external_id != player_external_id:
            continue
        if not (p.key_pass or p.assist):
            continue
        key_passes += 1
        if p.assist:
            goals_assisted += 1
        # Eşleşen şut bul — aynı maç + minute aralığı
        # StatsBomb'da key_pass yapan oyuncudan SONRA gelen shot eşleşir
        matching_shot = None
        for s in shot_list:
            if s.match_external_id != p.match_external_id:
                continue
            if s.minute < p.minute:
                continue
            if (s.minute - p.minute) * 60.0 > SHOT_ASSIST_WINDOW_SECONDS:
                continue
            matching_shot = s
            break
        if matching_shot is not None:
            xg = compute_shot_xg(matching_shot).value.xg
            xa_total += xg
    per_90 = (xa_total / max(1, minutes_played)) * 90.0
    report = PlayerXAReport(
        player_external_id=player_external_id,
        minutes=minutes_played,
        key_passes=key_passes,
        xa_total=round(xa_total, 4),
        xa_per_90=round(per_90, 4),
        goals_assisted=goals_assisted,
    )
    audit = AuditRecord(
        engine=ENGINE_NAME,
        engine_version=ENGINE_VERSION,
        subject_type="player",
        subject_id=player_external_id,
        metric="player_xa",
        value={
            "key_passes": report.key_passes,
            "xa_total": report.xa_total,
            "xa_per_90": report.xa_per_90,
            "goals_assisted": report.goals_assisted,
            "minutes": report.minutes,
        },
        inputs={
            "shot_assist_window_seconds": SHOT_ASSIST_WINDOW_SECONDS,
        },
        formula=(
            "key_pass + 10s within shot → xA += compute_shot_xg(shot); "
            "goal_assist flag → goals_assisted+=1"
        ),
    )
    return EngineResult(value=report, audit=audit)
