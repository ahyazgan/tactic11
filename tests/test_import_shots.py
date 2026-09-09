"""scripts/import_shots — CSV'den şut içe aktarma (ölçüme hızlı başlangıç).

Kulüplerin çoğunda koordinatlı event aboneliği yok ve tam etiketleme maç başına
2-3 saat. Yalnız şutlarla (~25 kayıt, ~15 dk) ölçüme başlanabiliyor; bu dosya o
yolun güvenli olduğunu korur: kötü satır sessizce yutulmamalı, tekrar içe
aktarma çift kayıt üretmemeli.
"""
from __future__ import annotations

from scripts.import_shots import read_rows

US, THEM = 217, 213


def _write(tmp_path, text: str) -> str:
    p = tmp_path / "shots.csv"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_reads_turkish_headers_and_team_words(tmp_path) -> None:
    path = _write(tmp_path, "dakika,takim,x,y,gol\n12.5,biz,88,52,0\n23,rakip,80,40,1\n")
    rows, errors = read_rows(path, our=US, their=THEM)
    assert errors == []
    assert [r["team"] for r in rows] == [US, THEM]
    assert rows[0]["minute"] == 12.5 and rows[0]["goal"] is False
    assert rows[1]["goal"] is True


def test_accepts_english_headers_and_ids(tmp_path) -> None:
    path = _write(tmp_path, "minute,team,x,y,goal\n5,217,90,50,true\n")
    rows, errors = read_rows(path, our=US, their=THEM)
    assert errors == [] and rows[0]["team"] == US and rows[0]["goal"] is True


def test_bad_rows_are_reported_not_swallowed(tmp_path) -> None:
    """Sessizce atlamak, kulübün eksik veriyle ölçüm yaptığını fark etmemesi demek."""
    path = _write(tmp_path, "\n".join([
        "dakika,takim,x,y,gol",
        "10,biz,88,50,0",          # iyi
        ",biz,88,50,0",            # dakika yok
        "20,,88,50,0",             # takım yok
        "30,biz,abc,50,0",         # sayı değil
        "40,biz,140,50,0",         # aralık dışı
        "200,biz,88,50,0",         # makul olmayan dakika
        "50,bilinmeyen,88,50,0",   # takım çözülemedi
    ]) + "\n")
    rows, errors = read_rows(path, our=US, their=THEM)
    assert len(rows) == 1, rows
    assert len(errors) == 6, errors
    assert all("satır" in e for e in errors)
    assert any("0-100" in e for e in errors)
    assert any("makul değil" in e for e in errors)


def test_coordinates_are_attacking_direction_normalised(tmp_path) -> None:
    """Kale (100,50): her iki takımın şutu da kendi hücum yönünde kaydedilir.

    Rakip şutunu 'ayna' koordinatla girmek xG'yi ters çevirirdi.
    """
    path = _write(tmp_path, "dakika,takim,x,y,gol\n10,biz,95,50,0\n11,rakip,95,50,0\n")
    rows, _ = read_rows(path, our=US, their=THEM)
    assert rows[0]["x"] == rows[1]["x"] == 95.0


def test_missing_optional_player_defaults_to_zero(tmp_path) -> None:
    path = _write(tmp_path, "dakika,takim,x,y,gol\n10,biz,88,50,0\n")
    rows, _ = read_rows(path, our=US, their=THEM)
    assert rows[0]["player"] == 0


def test_bom_and_spaced_headers_are_tolerated(tmp_path) -> None:
    """Excel'den kaydedilen CSV'ler BOM ve boşluklu başlıkla gelir."""
    p = tmp_path / "excel.csv"
    p.write_bytes("﻿ Dakika , Takim , X , Y , Gol \n10,biz,88,50,1\n".encode())
    rows, errors = read_rows(str(p), our=US, their=THEM)
    assert errors == [] and len(rows) == 1 and rows[0]["goal"] is True


def test_import_is_idempotent(tmp_path, session) -> None:
    """Aynı dosyayı iki kez aktarmak çift şut üretmemeli."""
    from datetime import UTC, datetime

    from scripts.import_shots import import_shots

    rows, _ = read_rows(
        _write(tmp_path, "dakika,takim,x,y,gol\n10,biz,88,50,0\n20,rakip,80,45,1\n"),
        our=US, their=THEM,
    )
    kw = dict(tenant="t-default", match_id=77001, our=US, their=THEM,
              kickoff=datetime(2026, 9, 14, tzinfo=UTC), our_score=1, their_score=1,
              session=session)
    first = import_shots(rows, **kw)
    second = import_shots(rows, **kw)
    assert first["shots_written"] == 2 and first["match_created"] is True
    assert second["shots_written"] == 0 and second["shots_updated"] == 2
    assert second["match_created"] is False
