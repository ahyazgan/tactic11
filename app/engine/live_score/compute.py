"""Live (replay) running score — belirli bir dakikaya kadarki gerçek skor.

Replay'de `Match.home_score`/`away_score` maçın **final** skorudur; canlı
snapshot'ta o dakikadaki gerçek durumu temsil etmez (10. dk'da bile final
gösterilir → score_time_matrix/sub_timing/tactical_trigger yanlış oyun
durumuyla beslenir). Bu saf yardımcı, yüklenmiş şutlardan `current_minute`'a
kadarki koşan skoru türetir.

Saf: yalnız Shot domain'i; DB/HTTP bilmez. `Shot.is_goal` + `Shot.minute` +
`Shot.team_external_id` kullanır. team_external_id=None şutlar (eski kayıtlar)
takıma atfedilemez → atlanır.

NOT (kapsam): StatsBomb own-goal event'leri (type.id 20/25) ingest edilmiyor;
bu skor "şutlardan-gol" temellidir, own-goal'ler Faz B'de ingest edilince
yansır. Penaltılar zaten is_goal şut olarak akar.
"""

from __future__ import annotations

from typing import Iterable

from app.domain import Shot


def running_score_as_of(
    shots: Iterable[Shot],
    *,
    home_team_id: int,
    away_team_id: int,
    current_minute: float,
) -> tuple[int, int]:
    """`current_minute`'a kadar atılmış gollerden (home_score, away_score).

    Gol yoksa (0, 0). team_external_id eşleşmeyen/None şut takıma atfedilmez.
    """
    home = 0
    away = 0
    for s in shots:
        if not s.is_goal or s.minute > current_minute:
            continue
        if s.team_external_id == home_team_id:
            home += 1
        elif s.team_external_id == away_team_id:
            away += 1
        # team_external_id None ya da iki takımdan da değilse: atfedilemez, atla.
    return home, away
