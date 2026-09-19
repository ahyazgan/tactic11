"""Kiracının KENDİ "kim çıkar" önseli — player_appearances'tan fit edilir.

## Neden gerek var

`ELITE_OFF_PRIOR` tek bir genel tablodur ve bağımsız doğrulamada bir sınırı
ölçüldü: **kendi verisine benzemeyen bir kulüp için genel tablo kötüdür.**
Barcelona'da en çok orta saha çıkıyor (0,185), başka her yerde forvet (0,215);
genel tablo Barcelona'ya uygulanınca eskisinden geriye gidiyordu
(`docs/KARNE-KIM-BAGIMSIZ.md`).

Motorun kancası zaten vardı — `compute_live_sub_recommendation(off_prior=...)`
ve `compute_sub_timing(off_prior=...)` oyuncu→önsel eşlemesini dışarıdan alır.
Eksik olan, o eşlemeyi kiracının kendi geçmişinden üreten ve **ne zaman
güvenilir olduğunu bilen** parçaydı.

## Kapı: 20 maç

Ölçüldü, seçilmedi. Ayrık yarıda (maç bazında, beraberlik tarafsız) kiracının
kendi tablosu genel tabloyu İKİ KOLDA da ancak 20 maçtan sonra geçiyor; 10
maçta bir kol geçiyor, öteki geçmiyor. Kapı kuralı veriden ÖNCE yazılmıştı:
*iki kolda birden geçen en küçük maç sayısı* (`scripts/fit_tenant_prior.py`,
`docs/KARNE-KIRACI-ONSELI.md`).

Altındaki kiracı genel tabloyu kullanmaya devam eder. Bu bir kusur değil,
doğru varsayılan: 8 hücreli bir tablo az veriyle kolayca gürültüye oturur.

## İki bilinen sınır

1. **Sebepsiz eski kayıtlar.** 0036 göçünden beri her değişiklik sebebini
   taşıyor (`substitution_reason`) ve sakatlık hamleleri artık ayıklanıyor —
   sakatlık bir karar değil, mecburiyettir. Ama o göçten ÖNCE yazılmış satırlar
   NULL'dur ve geriye dönük "taktik" VARSAYILMAZ; kullanılırlar ama sebepli
   olmadıkları `reason_coverage` ile raporlanır. Kapsama düşükse tablo hâlâ
   seyreltilmiş demektir.
2. **Sızıntı riski.** Canlı maçta fit yapılırken o maç DIŞARIDA bırakılmalıdır,
   yoksa tablo tahmin ettiği hamleden öğrenir. `exclude_match_id` bunun içindir
   ve çağıranın sorumluluğunda değil, varsayılan davranıştır.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.engine.coach_benchmark import WhoCandidate, WhoPrior, WhoState, fit_who_prior
from app.sports import football

# Ölçülmüş kapı — bkz. modül docstring'i ve docs/KARNE-KIRACI-ONSELI.md.
TENANT_PRIOR_MIN_MATCHES = 20

# Bunlar KARAR değil, mecburiyettir: önsele girmezler.
_NOT_A_DECISION = frozenset({"injury", "red_card"})

# position_played (StatsBomb/API-Football kısa kodu) → önsel grubu.
# Bilinmeyen "MID" sayılır: canlı motordaki `elite_off_prior` da bilinmeyeni
# orta saha kabul eder — en kalabalık grup, en yüksek önselli değil.
_LETTER_TO_GROUP = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}


def _group(position: str | None) -> str:
    letter = (position or "M")[:1].upper()
    return _LETTER_TO_GROUP.get(letter, "MID")


def tenant_who_states(
    session: Session, *, team_external_id: int, exclude_match_id: int | None = None,
) -> list[WhoState]:
    """Kiracının geçmişindeki her TAKTİK değişiklik: kim çıktı, o an sahada kimler?

    Hamle sayılmayanlar — ikisi de KARAR değil, mecburiyet:

    - **kırmızı kart** (`red_cards` ya da `substitution_reason == "red_card"`),
    - **sakatlık** (`substitution_reason == "injury"`).

    İkisi de sahadaki oyuncu havuzundan düşer: çıktıktan sonra aday olamazlar.

    Sebebi NULL olan satırlar (0036 göçünden öncesi) hamle SAYILIR — geriye
    dönük "sakatlıktı" demek de "taktikti" demek kadar uydurma olurdu. Kaçının
    sebepli olduğu `reason_coverage` ile ölçülebilir.
    """
    rows = session.execute(
        select(models.PlayerAppearance).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.team_external_id == team_external_id,
        )
    ).scalars().all()

    by_match: dict[int, list[models.PlayerAppearance]] = {}
    for r in rows:
        if exclude_match_id is not None and r.match_external_id == exclude_match_id:
            continue
        by_match.setdefault(r.match_external_id, []).append(r)

    states: list[WhoState] = []
    for mid, squad in by_match.items():
        for r in squad:
            if r.substituted_out_minute is None or r.red_cards:
                continue
            if r.substitution_reason in _NOT_A_DECISION:
                continue
            minute = float(r.substituted_out_minute)
            # Aday havuzu: o dakikada sahada olanlar. Yarı açık aralık motordaki
            # `resolve_on_pitch` ile aynı — çıkan oyuncunun kendisi dahildir
            # (çıktığı an hâlâ sahadaydı), o dakika GİREN dahil değildir.
            cands = tuple(
                WhoCandidate(
                    player_id=c.player_external_id,
                    group=_group(c.position_played),
                    starter=not c.substituted_in_minute,
                )
                for c in squad
                if float(c.substituted_in_minute or 0) < minute
                and (c.substituted_out_minute is None
                     or minute <= float(c.substituted_out_minute))
            )
            if len(cands) < 2:
                continue
            states.append(WhoState(match_external_id=mid, player_off=r.player_external_id,
                                   candidates=cands))
    return states


def reason_coverage(session: Session, *, team_external_id: int) -> dict[str, int | float]:
    """Kiracının değişikliklerinin kaçı SEBEPLİ kaydedilmiş?

    Kapsama düşükse tablo hâlâ seyreltilmiş demektir: sebebi bilinmeyen
    hamlelerin bir kısmı sakatlıktır ve önsele girmemeliydi. Bu sayı
    raporlanmazsa sınır görünmez olur — 0036 göçünden önceki bütün veri
    NULL'dur ve sessizce "taktik" gibi davranır.
    """
    rows = session.execute(
        select(models.PlayerAppearance.substitution_reason).where(
            models.PlayerAppearance.sport == football.SPORT_NAME,
            models.PlayerAppearance.team_external_id == team_external_id,
            models.PlayerAppearance.substituted_out_minute.is_not(None),
        )
    ).scalars().all()
    toplam = len(rows)
    sebepli = sum(1 for r in rows if r)
    return {
        "cikis": toplam, "sebepli": sebepli, "sebepsiz": toplam - sebepli,
        "kapsama": round(sebepli / toplam, 3) if toplam else 0.0,
        "taktik": sum(1 for r in rows if r == "tactical"),
        "sakatlik": sum(1 for r in rows if r == "injury"),
        "kirmizi_kart": sum(1 for r in rows if r == "red_card"),
    }


def fit_tenant_off_prior(
    session: Session, *, team_external_id: int, exclude_match_id: int | None = None,
    min_matches: int = TENANT_PRIOR_MIN_MATCHES,
) -> WhoPrior | None:
    """Kiracının kendi tablosu — yeterli geçmiş yoksa **None** (genel tabloya düş).

    None dönmek başarısızlık değildir: 8 hücreli bir tablo az veriyle gürültüye
    oturur ve ölçüm 20 maçın altında genel tabloyu geçemediğini gösterdi.
    """
    states = tenant_who_states(
        session, team_external_id=team_external_id, exclude_match_id=exclude_match_id)
    if len({s.match_external_id for s in states}) < min_matches:
        return None
    return fit_who_prior(states)


def off_prior_for(
    prior: WhoPrior | None, position: str | None, starter: bool,
) -> float | None:
    """Kiracı tablosundan tek bir oyuncunun önseli; tablo yoksa/hücre boşsa None.

    None dönerse çağıran genel `elite_off_prior`'a düşer. Görülmemiş hücreye
    uydurma değer konmaz — 0.5 ("bilinmiyor") burada yanlış olurdu, çünkü genel
    tablonun o hücre için ÖLÇÜLMÜŞ bir değeri var.
    """
    if prior is None:
        return None
    return prior.table.get((_group(position), starter))
