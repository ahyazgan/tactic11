"""Kapsama → veri kalitesi: pozisyon motorlarının ortak ölçüsü.

Kamera sahadaki 22 oyuncunun kaçını görüyor? Görünmeyen oyuncu "yok" değildir;
şekil, bölge sayımı ve hat boşluğu eksik ölçülür. Bu modül tek bir eşleme verir
ki tracking_signals ve space_map aynı dili konuşsun ve signal_quality tek bir
`detail.data_quality` alanıyla güveni düşürsün.

kalite = (kapsama − COVERAGE_FLOOR) / (1 − COVERAGE_FLOOR), 0..1'e kırpılır:
oyuncuların yarısı görünmüyorsa şekil/bölge bilgisi YOK (0), hepsi görünüyorsa tam (1).
Ölçülen sebep: SoccerTrack v2 hızlı geçişinde 8-11 görünen oyuncuyla "sağ kanat
0 oyuncu" / "7'e 0" bulguları güven 1.00 ile çıkıyordu.
"""

from __future__ import annotations

FULL_PLAYERS = 22.0        # iki takım sahada
COVERAGE_FLOOR = 0.5       # bu kapsamanın altında konum bilgisi yok sayılır (kalite 0)


def coverage_quality(players_visible: float) -> tuple[float, float]:
    """(kapsama, veri kalitesi) — kapsama = görünen oyuncu (iki takım) / 22."""
    coverage = max(0.0, min(1.0, players_visible / FULL_PLAYERS))
    quality = max(0.0, min(1.0, (coverage - COVERAGE_FLOOR) / (1.0 - COVERAGE_FLOOR)))
    return round(coverage, 3), round(quality, 3)


def coverage_note(coverage: float, quality: float) -> str:
    return (f"kapsama %{coverage * 100:.0f} (görünen {coverage * FULL_PLAYERS:.0f}/22) — "
            f"veri kalitesi {quality:.2f}, güven buna göre düşürülür")
