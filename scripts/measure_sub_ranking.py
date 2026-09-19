"""Değişiklik önerisi sıralaması: motor doğru GRUBU mu, doğru KİŞİYİ mi biliyor?

## Neden bu script var

`live_sub_recommendation` iki bilgiyi harmanlar: elit "kim çıkar" önseli (mevki
grubu × ilk 11) ve yorgunluk bileşiği (yorgunluk, son 10 dk pas isabeti, skor
baskısı, dakika). Harman ağırlığı `ROLE_PRIOR_WEIGHT = 0.6` bir ölçüme dayanarak
seçilmemişti. Bu script iki ayrı soruyu ayırır:

- **Doğru grup mu?** — isabet@3: antrenörün çıkardığı oyuncu motorun ilk üçünde mi?
- **Doğru kişi mi?** — isabet@1: ilk sıradaki gerçekten o mu?

## Ters kontrol

Bir sinyalin bilgi taşıyıp taşımadığını anlamanın en ucuz yolu YÖNÜNÜ ters
çevirmektir. Yorgunluk grup içindeki sırayı gerçekten belirliyorsa, "en az yorgun
önce" kuralı "en yorgun önce"den KÖTÜ olmalıdır. Olmuyorsa sinyal o kararda
bilgi taşımıyordur ve ağırlığını ayarlamak boş iştir.

Beraberlik uyarısı: motor `urgency`'yi 3 haneye yuvarlar, bu yüzden saf önselde
aynı mevki grubundaki oyuncular eşitlenir. Eşitliği HERHANGİ bir sabit kurala
(küme yineleme sırası, oyuncu kimliği) bırakmak ölçümü bozar: bu veri kümesinde
küçük kimlik = daha eski oyuncu olduğu için kimliğe göre sıralamak tek başına
isabet@1'i 0.09'dan 0.18'e çıkarıyor — beceri değil, veri kümesi tesadüfü.
Bu script beraberlik-TARAFSIZ ölçer: eşit adaylar arasında rastgele seçim
varsayılıp BEKLENEN isabet hesaplanır (aynı anahtara sahip t adayın ilk sırayı
paylaşması → 1/t). Motorun kendi sıralaması ayrıca belirlenimlidir
(bkz. `live_sub_recommendation`), ama ölçüm o sırayı ödüllendirmez.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.measure_sub_ranking
        --events-dir C:\\sb --out docs/measurements/sub-ranking.json

Önkoşul: külliyat maçlarının olayları DB'de (pas/müdahale) ve ham StatsBomb
`events/<match_id>.json` dosyaları (gerçek değişiklikler yalnız ham olayda).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.data.loaders.events import load_match_events
from app.data.sources.statsbomb_open import coach_moves_from_events_json
from app.db import models
from app.db.session import SessionLocal
from app.engine.fatigue_signal import compute_fatigue_signal
from app.engine.live_sub_recommendation import elite_off_prior
from app.engine.live_sub_recommendation.compute import (
    RECENT_WINDOW_MIN,
    ROLE_PRIOR_WEIGHT,
    _minute_urgency,
    _recent_pass_completion,
    _score_state_from_score,
    _score_state_weight,
)
from app.sports import football
from scripts.validate_who_prior import who_states_from_events

MIN_ACTIONS = 5          # motorun kendi eşiği: bu kadar olayı olmayan aday değerlendirilmez
URGENCY_DECIMALS = 3     # motorla aynı yuvarlama; beraberlikler burada doğuyor

# (oyuncu, önsel, bileşik aciliyet)
Candidate = tuple[int, float, float]
# Bir kural, o vakanın adaylarını ve HAVUZ TEPE ÖNSELİNİ görüp her aday için
# SIRALAMA ANAHTARI üretir. Eşit anahtar = beraberlik; ölçüm beraberliği
# rastgele sayar. Tepe önsel ayrı geçilir çünkü motor onu eylem eşiğinden
# ÖNCEKİ havuzdan alır, aday listesinden değil.
Ranker = Callable[[Sequence[Candidate], float], Callable[[Candidate], tuple[float, ...]]]
# Bir vaka: (maç, çıkan oyuncu, adaylar, eşik öncesi havuzun en yüksek önseli)
# Maç kimliği taşınır çünkü ayrık yarı MAÇ bazında bölünmelidir: aynı maçın
# değişiklikleri iki yarıya dağılırsa yarılar bağımsız olmaz.
Case = tuple[int, int, list[Candidate], float]


def _collect_cases(
    events_dir: Path, tenant: str, team: int,
) -> list[Case]:
    """Her gerçek taktik değişiklik için: kim çıktı + adayların önsel/bileşik
    değerleri + eylem eşiğinden ÖNCEKİ havuzun en yüksek önseli."""
    out: list[Case] = []
    with SessionLocal() as s:
        s.info["tenant_id"] = tenant
        mids = sorted({m for (m,) in s.execute(select(
            models.Decision.match_external_id,
        ).where(
            models.Decision.sport == football.SPORT_NAME,
            models.Decision.tenant_id == tenant,
            models.Decision.team_external_id == team,
        ).distinct())})
        for mid in mids:
            p = events_dir / f"{mid}.json"
            if not p.is_file():
                continue
            try:
                ev = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            states = who_states_from_events(ev, mid, team=team)
            if not states:
                continue
            loaded = load_match_events(s, mid)
            if loaded.total == 0:
                continue
            goals = [(sh.minute, sh.team_external_id) for sh in loaded.shots if sh.is_goal]
            minute_of = {mv.player_off: mv.minute for mv in coach_moves_from_events_json(ev)
                         if mv.kind == "substitution" and mv.tactical
                         and mv.team_external_id == team and mv.player_off is not None}
            for st in states:
                minute = minute_of.get(st.player_off)
                if minute is None:
                    continue
                mine = sum(1 for g, t in goals if g < minute and t == team)
                theirs = sum(1 for g, t in goals if g < minute and t != team)
                state = _score_state_from_score(mine, theirs)
                weight = _score_state_weight(state)
                pressure = 1.0 if state == "losing" else (0.5 if state == "drawing" else 0.2)
                progression = _minute_urgency(minute)
                passes = [x for x in loaded.passes if x.minute < minute]
                defs = [x for x in loaded.defensive_actions if x.minute < minute]
                # Önsel normalizasyonunun TEPE DEĞERİ, motordaki gibi eylem
                # eşiğinden ÖNCEKİ havuzdan gelir. Motor `prior_max`'ı sahadaki
                # tüm oyunculardan alır; script filtreden SONRAKİ aday
                # listesinden alıyordu. En yüksek önselli oyuncu eşikte elenirse
                # tepe düşer ve herkesin normalize önseli şişer — modellenen
                # sıralayıcı motorunki olmaktan çıkar.
                pool_top = max((elite_off_prior(c.group, c.starter)
                                for c in st.candidates), default=0.0)
                cands: list[Candidate] = []
                for c in st.candidates:
                    edge = max(15.0, minute - 15.0)
                    fatigue = compute_fatigue_signal(
                        c.player_id, passes, defs, early_end=edge, late_start=edge,
                        minutes_window=(0.0, minute),
                    ).value
                    if fatigue.early_actions + fatigue.late_actions < MIN_ACTIONS:
                        continue
                    recent = _recent_pass_completion(
                        [x for x in passes if x.player_external_id == c.player_id],
                        max(0.0, minute - RECENT_WINDOW_MIN))
                    composite = (
                        0.50 * fatigue.fatigue_score
                        + 0.20 * (1.0 - recent if recent > 0 else 0.5)
                        + 0.15 * pressure + 0.15 * progression
                    ) * weight
                    cands.append((c.player_id, elite_off_prior(c.group, c.starter), composite))
                if cands:
                    out.append((mid, st.player_off, cands, pool_top))
    return out


def _blend(w: float) -> Ranker:
    """Motorun bugünkü kuralı: aciliyet = (1−w)·bileşik + w·(önsel / en yüksek önsel).

    Normalizasyon motordaki gibi O VAKANIN sahadaki oyuncularının en yüksek
    önseline göredir — sahada forvet yoksa tepe değer de düşer. `pool_top`
    eylem eşiğinden ÖNCEKİ havuzdan gelir; verilmezse (eski davranış) aday
    listesinden hesaplanır ve motordan sapar.
    """
    def factory(cands: Sequence[Candidate],
                pool_top: float) -> Callable[[Candidate], tuple[float, ...]]:
        top = (pool_top or max((pr for _, pr, _ in cands), default=0.0)) or 1.0
        return lambda x: (-round(max(0.0, min(1.0, (1.0 - w) * x[2] + w * x[1] / top)),
                                 URGENCY_DECIMALS),)
    return factory


def _blend_reversed(w: float) -> Ranker:
    """Harmanın TERS KONTROLü: bileşiğin yönü çevrilir, ağırlık aynı kalır.

    Ayrık yarıda seçilen ağırlık bugünkünden iyi çıkarsa akla ilk gelen şey
    "yorgunluk bilgi taşıyor, ağırlığı düşürelim" olur. Ters kontrol bunu
    sınar: bileşik gerçekten kimin çıkacağını biliyorsa, yönü çevrilince sonuç
    BELİRGİN ŞEKİLDE kötüleşmelidir. Az kötüleşiyorsa — ve ters sürüm hâlâ saf
    önseli geçiyorsa — kazanç bilgiden değil, iki kaba ölçeği karıştırmanın
    yarattığı sıralama yapısından geliyordur.
    """
    def factory(cands: Sequence[Candidate],
                pool_top: float) -> Callable[[Candidate], tuple[float, ...]]:
        top = (pool_top or max((pr for _, pr, _ in cands), default=0.0)) or 1.0
        return lambda x: (-round(max(0.0, min(1.0,
            (1.0 - w) * (1.0 - x[2]) + w * x[1] / top)), URGENCY_DECIMALS),)
    return factory


def _lexicographic(reverse_secondary: bool = False) -> Ranker:
    """Önsel grubu belirler, bileşik grup içini sıralar (ters kontrol için ters çevrilir)."""
    sign = 1.0 if reverse_secondary else -1.0
    return lambda cands, _pool_top: (lambda x: (-x[1], sign * x[2]))


def _expected_hits(
    cands: Sequence[Candidate], off: int, rank: Ranker, *, k: int,
    pool_top: float = 0.0,
) -> tuple[float, float]:
    """Eşit anahtarlı adaylar arasında rastgele seçim varsayıp BEKLENEN isabet.

    Beraberlik yoksa sonuç 0/1'dir; tarafsız ölçüm kesin durumları bozmaz.
    Aynı anahtarı paylaşan t aday ilk sırayı paylaşır → isabet@1 = 1/t; ilk k
    sınırı bir kademeyi ortadan böldüğünde beklenen pay kalan yer / kademe boyu.
    """
    key = rank(cands, pool_top)
    keyed = sorted(((key(c), c[0]) for c in cands), key=lambda t: t[0])
    tiers: list[list[int]] = []
    prev: tuple[float, ...] | None = None
    for k_val, pid in keyed:
        if prev is None or k_val != prev:
            tiers.append([pid])
            prev = k_val
        else:
            tiers[-1].append(pid)
    before = 0
    for tier in tiers:
        if off in tier:
            size = len(tier)
            at1 = (1.0 / size) if before == 0 else 0.0
            slots = k - before
            atk = 0.0 if slots <= 0 else (1.0 if slots >= size else slots / size)
            return at1, atk
        before += len(tier)
    return 0.0, 0.0


def _score(rows: Sequence[Case], rank: Ranker, *, k: int = 3) -> dict[str, Any]:
    hit1 = hitk = 0.0
    for _mid, off, cands, pool_top in rows:
        a, b = _expected_hits(cands, off, rank, k=k, pool_top=pool_top)
        hit1 += a
        hitk += b
    n = len(rows)
    return {"n": n, "isabet_at_1": round(hit1 / n, 3), "isabet_at_3": round(hitk / n, 3)}


def _random_baseline(rows: Sequence[Case]) -> dict[str, Any]:
    n = len(rows)
    return {"n": n,
            "isabet_at_1": round(sum(1 / len(c) for _m, _o, c, _t in rows) / n, 3),
            "isabet_at_3": round(sum(min(1.0, 3 / len(c)) for _m, _o, c, _t in rows) / n, 3)}


WEIGHT_SWEEP: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def _halves(rows: Sequence[Case]) -> tuple[list[Case], list[Case]]:
    """MAÇ bazında ayrık yarı — aynı maçın değişiklikleri bölünmez."""
    ids = sorted({r[0] for r in rows})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    return ([r for r in rows if r[0] in a_ids], [r for r in rows if r[0] not in a_ids])


def _split_half_weight(rows: Sequence[Case], *, k: int = 1) -> dict[str, Any]:
    """Harman ağırlığını ÖTEKİ yarıda seç, bu yarıda ölç.

    Örneklem içi süpürmede on bir adayın en iyisi, ortada hiçbir bilgi olmasa
    bile tabanın üstüne çıkar — bu depoda ölçülmüş bir tuzak: altı sinyalin en
    iyisi rastgele tabanı 0,056 geçiyordu (docs/KARNE-GRUP-ICI-SINYAL.md).
    Ağırlık da bir seçimdir ve bedeli ödenmeden raporlanamaz.

    Hüküm ölçütü: iki yarı AYNI ağırlığı seçmezse sonuç kararsızdır ve
    ağırlığın bilgi taşıdığı söylenemez.
    """
    a, b = _halves(rows)
    metric = "isabet_at_1" if k == 1 else "isabet_at_3"
    kollar: list[dict[str, Any]] = []
    for train, test, label in ((a, b, "A'da seç → B'de ölç"), (b, a, "B'de seç → A'da ölç")):
        if not train or not test:
            continue
        best = max(WEIGHT_SWEEP, key=lambda w: _score(train, _blend(w), k=k)[metric])
        kollar.append({"kol": label, "secilen_w": best,
                       "egitimde": _score(train, _blend(best), k=k)[metric],
                       "olcumde": _score(test, _blend(best), k=k)[metric],
                       "n": len(test)})
    if not kollar:
        return {"hukum": "yetersiz veri"}
    disari = round(sum(r["olcumde"] for r in kollar) / len(kollar), 3)
    icerde = round(max(_score(rows, _blend(w), k=k)[metric] for w in WEIGHT_SWEEP), 3)
    kararli = len({r["secilen_w"] for r in kollar}) == 1
    return {
        "olcut": metric, "kollar": kollar,
        "ornek_disi": disari, "ornek_ici_en_iyi": icerde,
        "secim_bedeli": round(icerde - disari, 3),
        "ayni_agirlik_mi": kararli,
        "suanki_w": ROLE_PRIOR_WEIGHT,
        "suanki_w_ornek_ici": _score(rows, _blend(ROLE_PRIOR_WEIGHT), k=k)[metric],
        "not": ("örneklem içi en iyi ile örneklem dışı arasındaki fark SEÇİM BEDELİdir; "
                "iki yarı farklı ağırlık seçerse sonuç kararsızdır"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Değişiklik önerisi sıralamasının ölçümü")
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--team", type=int, default=217)
    p.add_argument("--events-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    rows = _collect_cases(args.events_dir, args.tenant, args.team)
    if not rows:
        print("değişiklik örneği çıkmadı — külliyat olayları ve --events-dir gerekli")
        return 1

    rules: dict[str, Ranker] = {
        f"motor harmanı (w={ROLE_PRIOR_WEIGHT})": _blend(ROLE_PRIOR_WEIGHT),
        "saf yorgunluk bileşiği (w=0)": _blend(0.0),
        "saf önsel (w=1)": _blend(1.0),
        "önsel, eşitlikte bileşik": _lexicographic(),
        "TERS KONTROL: önsel, eşitlikte ters bileşik": _lexicographic(reverse_secondary=True),
    }
    results = {name: _score(rows, rank) for name, rank in rules.items()}
    baseline = _random_baseline(rows)
    weight = {"isabet_at_1": _split_half_weight(rows, k=1),
              "isabet_at_3": _split_half_weight(rows, k=3)}
    # Ayrık yarıda seçilen ağırlık için TERS KONTROL: bileşiğin yönü çevrilince
    # ne oluyor? Az kötüleşiyorsa kazanç yorgunluğun bilgisinden değildir.
    ters: dict[str, Any] = {}
    for metric, k in (("isabet_at_1", 1), ("isabet_at_3", 3)):
        w = weight[metric].get("kollar", [{}])[0].get("secilen_w")
        if w is None:
            continue
        ileri = _score(rows, _blend(w), k=k)[metric]
        geri = _score(rows, _blend_reversed(w), k=k)[metric]
        ters[metric] = {
            "secilen_w": w, "dogru_yon": ileri, "ters_yon": geri,
            "fark": round(ileri - geri, 3),
            "saf_onsel": _score(rows, _blend(1.0), k=k)[metric],
            "saf_bilesik": _score(rows, _blend(0.0), k=k)[metric],
            "rastgele": baseline[metric],
            "not": ("ters yön saf önseli de geçiyorsa kazanç bilgiden değil "
                    "karışımın sıralama yapısındandır"),
        }

    correct = results["önsel, eşitlikte bileşik"]
    reverse = results["TERS KONTROL: önsel, eşitlikte ters bileşik"]
    group_gain = results[f"motor harmanı (w={ROLE_PRIOR_WEIGHT})"]["isabet_at_3"] \
        - baseline["isabet_at_3"]
    within_informative = correct["isabet_at_1"] > reverse["isabet_at_1"]

    doc = {
        "olcum": "Değişiklik önerisi sıralaması: doğru grup mu, doğru kişi mi?",
        "kaynak": {
            "tenant": args.tenant, "takim_external_id": args.team,
            "taktik_degisiklik": len(rows),
            "ortalama_aday": round(sum(len(c) for _m, _o, c, _t in rows) / len(rows), 2),
            "aday_esigi": MIN_ACTIONS,
            "girdi_sha256": hashlib.sha256(json.dumps(
                [[off, sorted((pid, round(pr, 6), round(co, 6)) for pid, pr, co in c)]
                 for _m, off, c, _t in rows], sort_keys=True).encode("utf-8")).hexdigest(),
        },
        "rastgele_taban": baseline,
        "siralama_kurallari": results,
        "harman_agirligi_ayrik_yari": weight,
        "harman_ters_kontrol": ters,
        "hukum": {
            "grup_bilgisi": ("var" if group_gain >= 0.10 else "yok"),
            "grup_kazanci_at_3": round(group_gain, 3),
            "grup_ici_bilgi": ("var" if within_informative else "YOK"),
            "not": ("ters kontrol doğru yönü geçiyorsa grup içindeki sıralama bilgi "
                    "taşımıyordur; harman ağırlığını ayarlamak o kararı düzeltmez"),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(rows)} gerçek taktik değişiklik · ortalama "
          f"{doc['kaynak']['ortalama_aday']} aday → {args.out}")
    print(f"\n  {'sıralama kuralı':<46}{'isabet@1':>10}{'isabet@3':>10}")
    for name, r in results.items():
        print(f"  {name:<46}{r['isabet_at_1']:>10.3f}{r['isabet_at_3']:>10.3f}")
    print(f"  {'rastgele':<46}{baseline['isabet_at_1']:>10.3f}{baseline['isabet_at_3']:>10.3f}")
    print(f"\n  grup bilgisi: {doc['hukum']['grup_bilgisi']} "
          f"(+{group_gain:.3f} isabet@3, rastgeleye göre)")
    print(f"  grup içi bilgi: {doc['hukum']['grup_ici_bilgi']} — "
          f"doğru yön {correct['isabet_at_1']:.3f} vs ters yön {reverse['isabet_at_1']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
