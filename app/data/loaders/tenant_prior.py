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

## Kapı: kiracının kendi ayrık-yarı sınavı

İlk sürüm yalnız MAÇ SAYISINA bakıyordu (20). Üçüncü kulüp bunun yetmediğini
gösterdi: Arsenal WFC'nin hücre sırası genel tablonunkiyle birebir aynı ve 20-30
maçlık tablosu bir kolda genel tablodan KÖTÜ (0,373 vs 0,443). Sayı kapısı o
tabloyu bağlardı. Ölçülen güvenlik hiçbir zaman maç sayısından gelmiyordu;
"genel tabloyu İKİ KOLDA da geçme" kuralından geliyordu — maç sayısı onun
Barcelona'daki vekiliydi.

Şimdi kapı o kuralın kendisi: yükleyici kiracının geçmişini maç bazında ikiye
böler, her yarıda fit edip öteki yarıda genel tabloyla kıyaslar
(beraberlik tarafsız isabet@3) ve tablo ancak İKİ KOLDA da genel tabloyu en az
`MIN_EDGE` geçerse döner. Geçemezse None: kiracı genel tabloda kalır. Bu bir
kusur değil, ölçülmüş doğru varsayılan — Arsenal WFC için genel tablo zaten
doğru tablodur.

`TENANT_PRIOR_MIN_MATCHES` (10) artık yalnız bir TABAN: sınavın anlamlı olması
için her yarıda birkaç maç gerekir. Ölçülen üç kulüpte eğri 10 maçtan itibaren
dümdüzdü (sekiz hücrede yalnız sıra önemli ve 10 maç sırayı sabitliyor); 10,
önceden kapatılmış eğrinin en alt noktasıdır, gerçek asgari daha düşük olabilir
(`docs/KARNE-KIRACI-ONSELI.md`).

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
from app.engine.coach_benchmark import (
    WHO_TOP_K,
    WhoCandidate,
    WhoPrior,
    WhoState,
    fit_who_prior,
    who_prior_agreement,
)
from app.engine.live_sub_recommendation import ELITE_OFF_PRIOR
from app.sports import football

# Sınavın anlamlı olması için TABAN maç sayısı; kapının kendisi değil (bkz.
# modül docstring'i ve docs/KARNE-KIRACI-ONSELI.md). Önceden kapatılmış öğrenme
# eğrisinin en alt noktası; üç kulüpte de eğri buradan itibaren düzdü.
TENANT_PRIOR_MIN_MATCHES = 10
# Kiracı tablosunun bir kolda genel tabloyu "geçmiş" sayılması için gereken
# isabet@3 farkı. Ölçüm scriptiyle aynı sayı; gürültüyü kazanç saymamak için.
MIN_EDGE = 0.02

# Bunlar KARAR değil, mecburiyettir: önsele girmezler.
_NOT_A_DECISION = frozenset({"injury", "red_card"})

# Bir hücreye güvenmek için gereken en az ADAY gözlemi. Laplace düzeltmesi
# (ağırlık 1) 20 gözlemde %5'in altına iner. PSG ölçümünde yedek kaleci hücresi
# 1-2 gözlemle tablonun ikinci sırasına tırmanmıştı — o hücre için genel
# tablonun ÖLÇÜLMÜŞ değeri, kiracının uydurmaya yakın değerinden iyidir.
# Sayı veriye bakılarak SEÇİLMEDİ; maç kapısıyla aynı büyüklük sınıfı.
MIN_CELL_OBS = 20

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


def global_prior() -> WhoPrior:
    """Üretimdeki `ELITE_OFF_PRIOR`, `WhoPrior` anahtar biçiminde. Sayılar aynı."""
    table = {(group, starter): ELITE_OFF_PRIOR[(letter, starter)]
             for letter, group in _LETTER_TO_GROUP.items() for starter in (True, False)}
    return WhoPrior(table=table, fitted_on=0)


def _halves(states: list[WhoState]) -> tuple[list[WhoState], list[WhoState]]:
    """MAÇ bazında ayrık yarı — aynı maçın hamleleri bölünmez."""
    ids = sorted({s.match_external_id for s in states})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    return ([s for s in states if s.match_external_id in a_ids],
            [s for s in states if s.match_external_id not in a_ids])


def _beats_global(train: list[WhoState], test: list[WhoState], genel: WhoPrior) -> bool:
    """Eğitim yarısından fit edilen tablo, ölçüm yarısında genel tabloyu geçiyor mu?

    İnce hücreler burada da genel değere düşer (`off_prior_for` kuralı), yoksa
    sınav üretimde çalışmayan bir nesneyi ölçer.
    """
    raw = fit_who_prior(train)
    guarded = WhoPrior(
        table={k: (v if raw.seen.get(k, 0) >= MIN_CELL_OBS else genel.table.get(k, v))
               for k, v in raw.table.items()},
        fitted_on=raw.fitted_on, seen=raw.seen)
    mine = who_prior_agreement(guarded, test, k=WHO_TOP_K).hit_at_k
    theirs = who_prior_agreement(genel, test, k=WHO_TOP_K).hit_at_k
    return mine is not None and theirs is not None and mine - theirs >= MIN_EDGE


def fit_tenant_off_prior(
    session: Session, *, team_external_id: int, exclude_match_id: int | None = None,
    min_matches: int = TENANT_PRIOR_MIN_MATCHES,
) -> WhoPrior | None:
    """Kiracının kendi tablosu — kendi sınavını geçemezse **None** (genel tabloda kal).

    Sınav: geçmiş maç bazında ikiye bölünür, her yarıdan fit edilen tablo öteki
    yarıda genel tabloyla kıyaslanır; İKİ KOLDA da en az `MIN_EDGE` geçmesi
    şarttır. Tek kolda geçen tablo bağlanmaz — ölçümdeki kuralın aynısı.

    None dönmek başarısızlık değildir. Hücre sırası genel tablonunkiyle aynı
    olan bir kulüp için (Arsenal WFC böyleydi) genel tablo zaten doğru
    tablodur; kendi tablosu en iyi hâlde eşit, kötü hâlde gürültülüdür.
    """
    states = tenant_who_states(
        session, team_external_id=team_external_id, exclude_match_id=exclude_match_id)
    if len({s.match_external_id for s in states}) < min_matches:
        return None
    genel = global_prior()
    a, b = _halves(states)
    if not (_beats_global(a, b, genel) and _beats_global(b, a, genel)):
        return None
    return fit_who_prior(states)


def off_prior_for(
    prior: WhoPrior | None, position: str | None, starter: bool,
) -> float | None:
    """Kiracı tablosundan tek bir oyuncunun önseli; tablo yoksa, hücre boşsa ya da
    hücre `MIN_CELL_OBS`'tan az gözlemliyse None.

    None dönerse çağıran genel `elite_off_prior`'a düşer. Görülmemiş hücreye
    uydurma değer konmaz — 0.5 ("bilinmiyor") burada yanlış olurdu, çünkü genel
    tablonun o hücre için ÖLÇÜLMÜŞ bir değeri var.
    """
    if prior is None:
        return None
    key = (_group(position), starter)
    if prior.seen and prior.seen.get(key, 0) < MIN_CELL_OBS:
        return None          # ince hücre: genel tablonun ölçülmüş değeri kazanır
    return prior.table.get(key)
