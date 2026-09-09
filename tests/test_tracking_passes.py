"""Takipten pas çıkarımı — video karelerinden pas olayı üretme.

Tanım fiziksel: `build_frame` aktörü yalnız oyuncu topa yakınken işaretler, pas
uçarken aktör YOKTUR. Yani "A tutuyor → boşluk → B tutuyor" geçişi pasın
kendisidir.

Bu testlerin asıl işi kabul değil, **REDDETME**: video türevi pas kırılgandır
ve sistem uydurmaktansa susmalı. Kimlik takası, kayıp top, sekme — hepsi sahte
pas üretebilir.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.tracking import PlayerPosition, TrackingFrame
from app.tracking.passes import (
    MAX_FLIGHT_SECONDS,
    MIN_HOLD_FRAMES,
    MIN_PASS_DISTANCE_M,
    extract_passes,
)

BIZ, RAKIP = 217, 213
T0 = datetime(2026, 1, 1, tzinfo=UTC)
# Hat `fps_out` varsayılanı 5 fps → kare başına 0.2 sn. Zamanlamalar gerçek
# olmalı: 1 sn'lik aralıklarla kurulan bir test "uçuş çok uzun" kapısına
# takılır ve testin ölçtüğü şey pas mantığı değil, kapı olur.
DT = 1.0 / 5.0 / 60.0          # dakika cinsinden bir kare


class _Akis:
    """Kare akışı kurucusu — zaman imleci gerçekçi ilerler."""

    def __init__(self, baslangic: float = 10.0) -> None:
        self.t = baslangic
        self.frames: list[TrackingFrame] = []

    def _kare(self, aktor: int | None, x: float, takim: int,
              top_enterpole: bool) -> None:
        oyuncular = tuple(
            PlayerPosition(
                player_external_id=pid, x=max(0.0, min(100.0, px)), y=50.0,
                team_external_id=(RAKIP if pid == 903 else takim),
                is_actor=(pid == aktor),
            )
            for pid, px in ((901, x), (902, x), (903, x))
        )
        self.frames.append(TrackingFrame(
            sport="football", match_external_id=1,
            timestamp=T0 + timedelta(seconds=self.t * 60), period=1,
            minute=round(self.t, 6), players=oyuncular,
            ball_estimated=top_enterpole,
        ))
        self.t += DT

    def tut(self, pid: int, n: int = MIN_HOLD_FRAMES, *, x: float = 50.0,
            takim: int = BIZ) -> _Akis:
        """`pid` oyuncusu `n` kare boyunca topu tutar (x konumunda)."""
        for _ in range(n):
            self._kare(pid, x, takim, False)
        return self

    def ucus(self, n: int = 1, *, top_enterpole: bool = False) -> _Akis:
        """`n` kare boyunca topu tutan yok — pas uçuyor."""
        for _ in range(n):
            self._kare(None, 50.0, BIZ, top_enterpole)
        return self


def test_holder_change_within_team_is_a_pass() -> None:
    """Asıl iş: A tutuyor → boşluk → B tutuyor = pas."""
    a = _Akis().tut(901, x=30.0).ucus(2).tut(902, x=60.0)
    r = extract_passes(a.frames)
    assert len(r.passes) == 1, r.note
    p = r.passes[0]
    assert p.from_player_external_id == 901
    assert p.to_player_external_id == 902
    assert p.team_external_id == BIZ
    assert p.distance_m > MIN_PASS_DISTANCE_M
    assert p.flight_seconds <= MAX_FLIGHT_SECONDS
    assert p.estimated is True, "video türevi pas kesin olarak sunulamaz"


def test_same_player_keeping_the_ball_is_not_a_pass() -> None:
    """Top sürme pas değildir."""
    r = extract_passes(_Akis().tut(901, 8, x=30.0).frames)
    assert r.passes == ()
    assert r.turnovers == 0


def test_intercepted_pass_is_recorded_as_incomplete_not_dropped() -> None:
    """Kesilen pas ATILMAMALI — atılırsa isabet oranı HER ZAMAN %100 çıkar.

    Uzun mesafeli rakibe geçiş bir pas DENEMESİDİR; alıcı rakip olduğu için
    tamamlanmamıştır. Takım daima pası ATANIN takımıdır.
    """
    a = _Akis().tut(901, x=30.0).ucus(2).tut(903, x=60.0)   # 903 rakip
    r = extract_passes(a.frames)
    assert len(r.passes) == 1, r.note
    p = r.passes[0]
    assert p.complete is False
    assert p.team_external_id == BIZ, "pas atanın takımına yazılmalı"
    assert p.to_player_external_id == 903
    assert r.turnovers == 1
    assert "isabet" in r.note


def test_short_range_dispossession_is_not_a_pass_attempt() -> None:
    """Ayak altında kaptırmak pas denemesi değildir."""
    a = _Akis().tut(901, x=50.0).ucus(2).tut(903, x=50.5)
    r = extract_passes(a.frames)
    assert r.passes == ()
    assert r.turnovers == 1
    assert any("kaptırma" in k for k in r.rejected), r.rejected


def test_single_frame_identity_flicker_is_rejected() -> None:
    """Tek karelik kimlik takası sahte pas üretmemeli.

    ByteTrack kimlikleri kalabalıkta takas edebiliyor; kararlılık kapısı
    olmadan her takas bir "pas" olurdu.
    """
    a = _Akis().tut(901, 4, x=30.0).tut(902, 1, x=60.0).tut(901, 4, x=30.0)
    r = extract_passes(a.frames)
    assert r.passes == ()


def test_lost_ball_does_not_become_a_pass() -> None:
    """Uçuş çok uzunsa top izlenememiştir — ne olduğunu bilmiyoruz, iddia etme."""
    kare = int(MAX_FLIGHT_SECONDS * 5) + 10          # 5 fps
    a = _Akis().tut(901, x=30.0).ucus(kare).tut(902, x=60.0)
    r = extract_passes(a.frames)
    assert r.passes == ()
    assert any("uçuş çok uzun" in k for k in r.rejected), r.rejected


def test_too_short_a_move_is_rejected() -> None:
    """Ayak altı mücadelesi pas değildir."""
    a = _Akis().tut(901, x=50.0).ucus(2).tut(902, x=50.5)   # ~0.5 m
    r = extract_passes(a.frames)
    assert r.passes == ()
    assert any("mesafe çok kısa" in k for k in r.rejected), r.rejected


def test_interpolated_ball_is_flagged_not_hidden() -> None:
    """Top görülmemişken yapılan geçiş kırılgandır — atılmaz ama İŞARETLENİR."""
    a = _Akis().tut(901, x=30.0).ucus(2, top_enterpole=True).tut(902, x=60.0)
    r = extract_passes(a.frames)
    assert len(r.passes) == 1, r.note
    assert r.passes[0].ball_estimated is True
    assert "enterpole" in r.note


def test_no_actor_anywhere_says_so_instead_of_returning_empty() -> None:
    """Boş liste iki şey demek olabilir: "pas yok" ya da "çalışmadı". Ayır."""
    r = extract_passes(_Akis().ucus(20).frames)
    assert r.passes == ()
    assert r.actor_ratio == 0.0
    assert "belirlenemedi" in r.note


def test_weak_tracking_warns_that_the_list_is_incomplete() -> None:
    """Aktör oranı düşükse pas listesi EKSİKTİR; sessizce sunmak yanıltıcı."""
    a = _Akis().tut(901, 3, x=30.0).ucus(40).tut(902, 3, x=60.0)
    r = extract_passes(a.frames)
    assert r.actor_ratio < 0.25
    assert "EKSİK" in r.note


def test_empty_input_is_honest() -> None:
    r = extract_passes([])
    assert r.passes == () and r.frames_seen == 0
    assert r.note == "kare yok"
