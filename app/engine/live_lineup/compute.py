"""Live Lineup — as-of saha-içi oyuncu çözümleme (replay sadakati, Faz B).

Saf fonksiyon: bir maçtaki oyuncu görünümlerinden (`PlayerAppearance`: sahaya
giriş/çıkış dakikası) verilen `current_minute`'da SAHADA olanları ve her birinin
O ANA KADAR oynadığı dakikayı türetir. DB/HTTP bilmez → determinist, test-edilir.

Kusur #3 (maç-içi replay) düzeltmesi: live VAEP'te her oyuncu `current_minute`
oynamış sayılıyordu. Oysa sonradan giren/çıkan oyuncunun dakikası farklı:
- VAEP/90 yanlış normalize oluyordu (10 dk oynayan oyuncu 75 dk'ya bölünüyordu),
- sub önerisi çoktan SAHADAN ÇIKMIŞ oyuncuyu öneriyordu (event'leri pencerede
  hâlâ görünüyor çünkü daha önce oynamıştı).

`resolve_on_pitch` her ikisini de düzeltir: gerçek dakika + sahadaki oyuncu kümesi.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerAppearance:
    """Bir oyuncunun bir maçtaki saha-içi penceresi (event-zaman dakikaları).

    `start_minute`: sahaya giriş. İlk 11 → 0.0. Sonradan giren → sub dakikası.
    `end_minute`: sahadan çıkış. None → (henüz) çıkmadı / maç sonuna kadar.
    """

    player_external_id: int
    team_external_id: int
    start_minute: float
    end_minute: float | None = None


@dataclass(frozen=True)
class OnPitch:
    """`current_minute` itibarıyla saha durumu."""

    player_ids: frozenset[int]              # şu an sahada olanlar
    minutes_by_player: dict[int, float]     # player_id → o ana kadar oynanan dk


def minutes_played_as_of(appearance: PlayerAppearance, current_minute: float) -> float:
    """`appearance`'ın `current_minute`'a kadar sahada geçirdiği dakika.

    Henüz girmemişse 0. Çıkmışsa giriş→çıkış arası (sabit). Hâlâ sahadaysa
    giriş→current arası. Asla negatif değil.
    """
    if current_minute <= appearance.start_minute:
        return 0.0
    end = current_minute if appearance.end_minute is None else min(
        appearance.end_minute, current_minute,
    )
    return max(0.0, end - appearance.start_minute)


def is_on_pitch(appearance: PlayerAppearance, current_minute: float) -> bool:
    """`current_minute`'da sahada mı? Giriş dakikasında sahadadır; çıkış
    dakikasında artık sahada değildir (event-zaman yarı-açık aralık)."""
    if current_minute < appearance.start_minute:
        return False
    if appearance.end_minute is not None and current_minute >= appearance.end_minute:
        return False
    return True


def resolve_on_pitch(
    appearances: Iterable[PlayerAppearance],
    current_minute: float,
    *,
    team_external_id: int | None = None,
) -> OnPitch:
    """`current_minute` itibarıyla sahadaki oyuncular + her oyuncunun oynadığı dk.

    `team_external_id` verilirse yalnızca o takım. Bir oyuncunun birden fazla
    görünümü olursa (teorik) dakikalar toplanır. Hiç oynamamış (0 dk) oyuncu
    `minutes_by_player`'a girmez.
    """
    on_pitch_ids: set[int] = set()
    minutes: dict[int, float] = {}
    for app in appearances:
        if team_external_id is not None and app.team_external_id != team_external_id:
            continue
        played = minutes_played_as_of(app, current_minute)
        if played > 0:
            minutes[app.player_external_id] = round(
                minutes.get(app.player_external_id, 0.0) + played, 1,
            )
        if is_on_pitch(app, current_minute):
            on_pitch_ids.add(app.player_external_id)
    return OnPitch(player_ids=frozenset(on_pitch_ids), minutes_by_player=minutes)
