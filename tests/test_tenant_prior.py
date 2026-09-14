"""Kiracının kendi "kim çıkar" önseli: kapı, sızıntı koruması ve geri düşüş."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.data.loaders.tenant_prior import (
    TENANT_PRIOR_MIN_MATCHES,
    fit_tenant_off_prior,
    off_prior_for,
    tenant_who_states,
)
from app.db import models
from app.sports import football

TEAM = 11


def _squad(session, match_id: int, *, off: int | None, off_minute: float = 60.0,
           red: int | None = None) -> None:
    """11 oyunculu bir maç: 1 kaleci, 4 defans, 4 orta saha, 2 forvet."""
    plan = [("G", 1)] + [("D", i) for i in range(2, 6)] \
        + [("M", i) for i in range(6, 10)] + [("F", i) for i in (10, 11)]
    for pos, pid in plan:
        session.add(models.PlayerAppearance(
            sport=football.SPORT_NAME, tenant_id="t-default",
            player_external_id=pid, match_external_id=match_id,
            team_external_id=TEAM, minutes=90,
            kickoff=datetime.now(UTC) - timedelta(days=1),
            position_played=pos,
            substituted_in_minute=None,
            substituted_out_minute=(off_minute if pid in {off, red} else None),
            red_cards=(1 if pid == red else None),
        ))
    # Yerine giren oyuncu: ilk 11'den DEĞİL.
    if off is not None:
        session.add(models.PlayerAppearance(
            sport=football.SPORT_NAME, tenant_id="t-default",
            player_external_id=100 + match_id, match_external_id=match_id,
            team_external_id=TEAM, minutes=30,
            kickoff=datetime.now(UTC) - timedelta(days=1),
            position_played="M",
            substituted_in_minute=int(off_minute), substituted_out_minute=None,
        ))


def _seed(session, matches: int, *, off_pos_player: int = 6) -> None:
    for i in range(matches):
        _squad(session, 1000 + i, off=off_pos_player)
    session.commit()


def test_gate_returns_none_below_the_measured_threshold(session) -> None:
    """20 maçın altında kiracı tablosu ÜRETİLMEZ — genel tabloya düşülür.

    Kapı ölçüldü, seçilmedi: ayrık yarıda kiracının kendi tablosu genel tabloyu
    İKİ KOLDA da ancak 20 maçtan sonra geçiyor (docs/KARNE-KIRACI-ONSELI.md).
    Sekiz hücreli bir tablo az veriyle gürültüye oturur.
    """
    session.info["tenant_id"] = "t-default"
    _seed(session, TENANT_PRIOR_MIN_MATCHES - 1)
    assert fit_tenant_off_prior(session, team_external_id=TEAM) is None


def test_gate_opens_at_the_threshold(session) -> None:
    session.info["tenant_id"] = "t-default"
    _seed(session, TENANT_PRIOR_MIN_MATCHES)
    prior = fit_tenant_off_prior(session, team_external_id=TEAM)
    assert prior is not None
    assert prior.fitted_on == TENANT_PRIOR_MIN_MATCHES


def test_current_match_is_excluded_from_its_own_fit(session) -> None:
    """Canlı maç fit'e GİRMEZ — tablo tahmin ettiği hamleden öğrenmemeli."""
    session.info["tenant_id"] = "t-default"
    _seed(session, TENANT_PRIOR_MIN_MATCHES + 1)

    hepsi = tenant_who_states(session, team_external_id=TEAM)
    haric = tenant_who_states(session, team_external_id=TEAM, exclude_match_id=1000)
    assert len({s.match_external_id for s in hepsi}) == TENANT_PRIOR_MIN_MATCHES + 1
    assert len({s.match_external_id for s in haric}) == TENANT_PRIOR_MIN_MATCHES
    assert all(s.match_external_id != 1000 for s in haric)

    # Dışlama kapıyı da gerçekten daraltır: tam sınırdayken bir maç eksilince
    # tablo üretilmez.
    session.query(models.PlayerAppearance).filter(
        models.PlayerAppearance.match_external_id == 1020).delete()
    session.commit()
    assert fit_tenant_off_prior(session, team_external_id=TEAM) is not None
    assert fit_tenant_off_prior(
        session, team_external_id=TEAM, exclude_match_id=1000) is None


def test_red_cards_are_not_treated_as_decisions(session) -> None:
    """Kırmızı kart bir KARAR değil: hamle sayılmaz, ama sahadan da düşer."""
    session.info["tenant_id"] = "t-default"
    _squad(session, 2000, off=None, red=6)
    session.commit()
    assert tenant_who_states(session, team_external_id=TEAM) == []


def test_the_fitted_table_learns_this_tenants_habit(session) -> None:
    """Hep orta saha çıkaran bir kulüpte orta saha önseli forvetinkini geçmeli.

    Genel tablo bunun TERSİNİ söyler (forvet 0.2151, orta saha 0.1400) — ve
    ölçülen sorun tam buydu: Barcelona'da en çok orta saha çıkıyor.
    """
    session.info["tenant_id"] = "t-default"
    _seed(session, TENANT_PRIOR_MIN_MATCHES, off_pos_player=6)   # 6 = orta saha
    prior = fit_tenant_off_prior(session, team_external_id=TEAM)
    assert prior is not None
    assert prior.table[("MID", True)] > prior.table[("FWD", True)]


def test_off_prior_for_falls_back_when_there_is_no_table_or_cell(session) -> None:
    """Tablo yoksa ya da hücre görülmemişse None — çağıran genel tabloya düşer.

    Görülmemiş hücreye 0.5 ("bilinmiyor") konmaz: genel tablonun o hücre için
    ÖLÇÜLMÜŞ bir değeri var ve uydurma bir sayı ondan kötüdür.
    """
    assert off_prior_for(None, "M", True) is None

    session.info["tenant_id"] = "t-default"
    _seed(session, TENANT_PRIOR_MIN_MATCHES)
    prior = fit_tenant_off_prior(session, team_external_id=TEAM)
    assert prior is not None
    assert off_prior_for(prior, "M", True) is not None
    # Yedek kaleci hiç görülmedi (kaleci ilk 11'dir ve çıkmaz).
    assert off_prior_for(prior, "G", False) is None


@pytest.mark.parametrize("position,expected", [
    ("G", "GK"), ("D", "DEF"), ("M", "MID"), ("F", "FWD"),
    (None, "MID"), ("X", "MID"), ("", "MID"),
])
def test_unknown_position_counts_as_midfield_like_the_engine(
    session, position: str | None, expected: str,
) -> None:
    """Bilinmeyen mevki en KALABALIK gruba düşer, en yüksek önsele değil.

    Canlı motordaki `elite_off_prior` de aynısını yapar; iki yol ayrışırsa
    panelde ölçülen motor karnede ölçülenle aynı olmaz.
    """
    session.info["tenant_id"] = "t-default"
    _squad(session, 3000, off=6)
    session.commit()
    states = tenant_who_states(session, team_external_id=TEAM)
    assert states
    from app.data.loaders.tenant_prior import _group
    assert _group(position) == expected
