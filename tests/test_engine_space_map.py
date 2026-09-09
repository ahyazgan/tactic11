"""engine.space_map — bölgesel üstünlük, hatlar arası boşluk, hücum yönü.

Yön çıkarımı ve 180° döndürme bu motorun sessizce yanlış olabileceği yerler:
sadece x aynalanırsa koridorlar ters döner ve "sol kanat boş" derken sağı
gösterir. Testler bunu açıkça kovalar.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from app.domain import PlayerPosition, TrackingFrame
from app.engine.space_map import compute_space_map, infer_attack_direction

US, THEM = 100, 200
NOW = datetime.now(UTC)


def _frame(players, minute: float = 10.0) -> TrackingFrame:
    return TrackingFrame(
        sport="football", match_external_id=1, timestamp=NOW, period=1, minute=minute,
        players=tuple(players),
    )


def _p(pid: int, x: float, y: float, team: int, keeper: bool = False) -> PlayerPosition:
    return PlayerPosition(player_external_id=pid, x=x, y=y, team_external_id=team,
                          is_keeper=keeper)


def _squad(team: int, spots: Sequence[tuple[float, float]], base: int, keeper_at=None):
    out = []
    for i, (x, y) in enumerate(spots):
        out.append(_p(base + i, x, y, team, keeper=(keeper_at is not None and i == keeper_at)))
    return out


# Bizim kale x=0'da (kalecimiz orada) → x artan yöne hücum ediyoruz
OUR_SPOTS = [(3, 50), (20, 20), (20, 50), (20, 80), (45, 30), (45, 70),
             (70, 15), (70, 50), (72, 20), (75, 25), (78, 18)]
THEIR_SPOTS = [(97, 50), (80, 30), (80, 50), (80, 70), (60, 40), (60, 60),
               (55, 45), (55, 55), (50, 50), (85, 60), (85, 45)]


def _standard_frames(n: int = 6) -> list[TrackingFrame]:
    return [
        _frame(_squad(US, OUR_SPOTS, 1, keeper_at=0)
               + _squad(THEM, THEIR_SPOTS, 50, keeper_at=0))
        for _ in range(n)
    ]


def _mirrored_frames(n: int = 6) -> list[TrackingFrame]:
    """Aynı dizilim, saha 180° döndürülmüş (ikinci yarı) — sonuçlar AYNI olmalı."""
    def flip(spots):
        return [(100.0 - x, 100.0 - y) for x, y in spots]
    return [
        _frame(_squad(US, flip(OUR_SPOTS), 1, keeper_at=0)
               + _squad(THEM, flip(THEIR_SPOTS), 50, keeper_at=0))
        for _ in range(n)
    ]


def test_attack_direction_from_keeper() -> None:
    d, method = infer_attack_direction(_standard_frames(), US, THEM)
    assert (d, method) == (1, "keeper")
    d2, _ = infer_attack_direction(_mirrored_frames(), US, THEM)
    assert d2 == -1


def test_attack_direction_falls_back_to_deepest_player() -> None:
    """Kaleci bayrağı yoksa (video kaynağı) en derin oyuncudan çıkarılır."""
    frames = [_frame(_squad(US, OUR_SPOTS, 1) + _squad(THEM, THEIR_SPOTS, 50))
              for _ in range(4)]
    d, method = infer_attack_direction(frames, US, THEM)
    assert (d, method) == (1, "deepest")


def test_attack_direction_unknown_when_teams_overlap() -> None:
    """İki takım da aynı derinlikteyse uydurma yön üretilmemeli."""
    spots = [(50, 20), (50, 40), (50, 60), (50, 80)]
    frames = [_frame(_squad(US, spots, 1) + _squad(THEM, spots, 50)) for _ in range(3)]
    d, method = infer_attack_direction(frames, US, THEM)
    assert d == 0 and method == "unknown"


def test_zone_counts_and_overload_are_found() -> None:
    r = compute_space_map(_standard_frames(), our_team_external_id=US,
                          their_team_external_id=THEM, minute=30.0)
    v = r.value
    assert v.attack_direction == 1 and v.frames_used == 6
    assert v.note is None, v.note

    # Sol kanat hücum üçte biri: bizde (70,15) (72,20) (75,25) (78,18) = 4,
    # rakipte (80,30) = 1 → fark 3
    cell = next(z for z in v.zones if z.lane == "sol" and z.third == "hücum")
    assert cell.ours == 4.0 and cell.theirs == 1.0 and cell.delta == 3.0
    assert v.best_overload is not None and v.best_overload.lane == "sol"

    keys = [f.key for f in v.findings]
    assert "overload_sol_hücum" in keys
    head = next(f for f in v.findings if f.key == "overload_sol_hücum").headline
    assert "4.0v1.0" in head and "çevir" in head
    assert r.audit.engine == "engine.space_map"


def test_mirrored_second_half_gives_identical_zones() -> None:
    """Asıl tuzak: yön ters olunca 180° döndürülmeli, yalnız x aynalanmamalı.

    Sadece x aynalansaydı koridorlar ters dönerdi (sol↔sağ) ve bu test düşerdi.
    """
    a = compute_space_map(_standard_frames(), our_team_external_id=US,
                          their_team_external_id=THEM, minute=30.0).value
    b = compute_space_map(_mirrored_frames(), our_team_external_id=US,
                          their_team_external_id=THEM, minute=75.0).value
    assert b.attack_direction == -1
    assert {(z.lane, z.third): z.delta for z in a.zones} == \
           {(z.lane, z.third): z.delta for z in b.zones}
    assert [f.key for f in a.findings] == [f.key for f in b.findings]


def test_line_gap_between_opponent_lines() -> None:
    """Rakip geri hattı 80, orta hattı 55-60 → aralarında sömürülebilir boşluk."""
    v = compute_space_map(_standard_frames(), our_team_external_id=US,
                          their_team_external_id=THEM, minute=30.0).value
    gap = v.line_gap
    assert gap.gap_m is not None and gap.gap_m >= 12.0
    assert gap.def_line_m is not None and gap.mid_line_m is not None
    assert gap.def_line_m > gap.mid_line_m
    assert "line_gap_open" in [f.key for f in v.findings]


def test_weak_side_is_reported_when_opponent_abandons_a_flank() -> None:
    v = compute_space_map(_standard_frames(), our_team_external_id=US,
                          their_team_external_id=THEM, minute=30.0).value
    weak = [f for f in v.findings if f.key.startswith("weak_side_")]
    assert weak, [f.key for f in v.findings]
    assert "kanat değiştir" in weak[0].headline


def test_event_anchored_frames_are_refused() -> None:
    """StatsBomb 360: kareler topun çevresini gösterir → bölge sayımı yapılmaz."""
    v = compute_space_map(_standard_frames(), our_team_external_id=US,
                          their_team_external_id=THEM, minute=30.0,
                          continuous=False).value
    assert v.zones == () and v.findings == ()
    assert "event-çapalı" in (v.note or "")


def test_too_few_visible_players_produces_no_zones() -> None:
    frames = [_frame(_squad(US, [(20, 50), (40, 50)], 1)
                     + _squad(THEM, [(80, 50), (60, 50)], 50)) for _ in range(3)]
    v = compute_space_map(frames, our_team_external_id=US,
                          their_team_external_id=THEM, minute=30.0).value
    assert v.zones == () and "görünür oyuncu az" in (v.note or "")


def test_defensive_third_surplus_is_not_called_an_overload() -> None:
    """Kendi sahamızda kalabalık olmak üstünlük değil — sıkışmışlıktır."""
    spots = [(3, 50)] + [(15, 20 + i * 6) for i in range(9)] + [(18, 50)]
    theirs = [(97, 50), (55, 30), (55, 50), (55, 70), (60, 40), (60, 60),
              (65, 45), (65, 55), (70, 50), (72, 40), (72, 60)]
    frames = [_frame(_squad(US, spots, 1, keeper_at=0)
                     + _squad(THEM, theirs, 50, keeper_at=0)) for _ in range(4)]
    v = compute_space_map(frames, our_team_external_id=US,
                          their_team_external_id=THEM, minute=30.0).value
    assert v.best_overload is None or v.best_overload.third in ("orta", "hücum")
    assert not any(f.key.startswith("overload_") and "savunma" in f.key
                   for f in v.findings)


def test_narrow_camera_view_is_reported_as_coverage_not_direction() -> None:
    """Gerçek vaka: drone klibi sahanın orta bandını gösteriyor.

    Kaleciler kadraja girmediği için yön de çıkarılamıyor, ama koça asıl
    söylenmesi gereken sebep bu: kamera sahanın tamamını görmüyor. Bu yüzden
    kapsama kontrolü yön kontrolünden ÖNCE gelir.
    """
    ours = [(40 + i * 2, 20 + i * 5) for i in range(9)]
    theirs = [(45 + i * 2, 25 + i * 5) for i in range(9)]
    frames = [_frame(_squad(US, ours, 1) + _squad(THEM, theirs, 50)) for _ in range(5)]
    v = compute_space_map(frames, our_team_external_id=US,
                          their_team_external_id=THEM, minute=30.0).value
    assert v.zones == () and v.findings == ()
    assert v.pitch_coverage < 0.45
    assert "kamera sahanın yalnız" in (v.note or ""), v.note


def test_full_pitch_view_reports_high_coverage() -> None:
    v = compute_space_map(_standard_frames(), our_team_external_id=US,
                          their_team_external_id=THEM, minute=30.0).value
    assert v.pitch_coverage >= 0.9


def test_empty_lane_is_not_called_an_abandoned_flank() -> None:
    """Kimsenin olmadığı koridor "rakip terk etti" değildir — kamera görmüyordur.

    Gerçek vakada çıktı: sağ koridorda ne bizden ne rakipten kimse yokken
    "rakip sağ kanadı boşalttı (0.0 oyuncu) — kanat değiştir" üretiliyordu.
    """
    ours = [(3, 50), (20, 20), (20, 40), (30, 30), (45, 25), (45, 45),
            (55, 30), (58, 40), (60, 25), (62, 35), (64, 45)]
    theirs = [(97, 50), (80, 40), (80, 50), (78, 45), (70, 35),
              (70, 50), (68, 40), (66, 45), (64, 50), (72, 42), (74, 48)]
    frames = [_frame(_squad(US, ours, 1, keeper_at=0)
                     + _squad(THEM, theirs, 50, keeper_at=0)) for _ in range(4)]
    v = compute_space_map(frames, our_team_external_id=US,
                          their_team_external_id=THEM, minute=30.0).value
    # Sağ koridorda (y > 66.7) hiç oyuncu yok → zayıf taraf sinyali ÜRETİLMEMELİ
    right_total = sum(z.ours + z.theirs for z in v.zones if z.lane == "sağ")
    assert right_total == 0.0
    assert not any(f.key == "weak_side_sağ" for f in v.findings), \
        [f.key for f in v.findings]


def test_attacking_third_overload_outranks_midfield_one() -> None:
    """Aynı fark hücum üçte birinde daha acildir — koçun sırası buna göre."""
    from app.engine.space_map.compute import LineGapReport, ZoneCell, _findings

    gap = LineGapReport(None, None, None, 0.0)
    mid = ZoneCell(lane="merkez", third="orta", ours=6.0, theirs=4.0, delta=2.0)
    att = ZoneCell(lane="sol", third="hücum", ours=4.0, theirs=2.0, delta=2.0)
    u_mid = _findings((mid,), gap, mid)[0].urgency
    u_att = _findings((att,), gap, att)[0].urgency
    assert u_att > u_mid
    assert u_mid < 0.6, "orta saha üstünlüğü şekil sinyalini (0.6) ezmemeli"
