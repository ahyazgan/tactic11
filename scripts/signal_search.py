"""Sinyal arama: karar anındaki HANGİ gözlemlenebilir büyüklük sonucu öngörüyor?

## Neden bu script var

Güven makinesindeki ölçülebilir kusurların hepsi kapatıldı (#211, #214, #218)
ve sonuç değişmedi: **hiçbir sürücü sonucu ayırt etmiyor**. Yani sorun artık
mevcut sürücüleri onarmak değil, ayırt EDEN bir sinyal bulmak.

Tek tek sinyal tasarlayıp motor yazıp denemek yavaş ve pahalı. Bu script tersini
yapar: karar anında ölçülebilen bir **aday büyüklük bataryasını** ham event
verisinden hesaplar ve her birinin ayrım gücünü ölçer. Motor kurmadan önce
"bu veride bilgi var mı" sorusunu cevaplar.

## Neden KATMANLI ölçüm şart

Karar etkisi cetveli `sonraki pencere − önceki pencere` farkıdır ve
**ortalamaya dönüş** taşır: iyi giderken verilen karar sistematik olarak
cezalandırılır. Uçta ateşleyen HER aday ham ölçümde yanıltıcı görünür.
O yüzden her aday, karar öncesi durum katman değişkeni yapılarak da ölçülür
(`attribution.attribute_stratified`). Hüküm katmanlı sayıya göre verilir.

## Aday türleri — bilerek iki grup

1. **SEVİYE** (mevcut sürücülerin yaptığı): pencerede kaç şut, ne kadar xG…
   Bunlar ortalamaya dönüşe en açık olanlar.
2. **DİNAMİK / YAPI**: pencere içindeki eğilim (ilk yarı vs ikinci yarı),
   oynaklık, şut kalitesi dağılımı. Bunlar seviyeden bağımsız bilgi taşıyabilir
   — hipotez budur, veri karar verir.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.signal_search --tenant t-default --team 217

Külliyat önce `decision_corpus seed` + `score` ile üretilmiş olmalı (kararlarda
`pre_xg_diff` bulunmalı; yoksa katmanlı ölçüm yapılamaz).
"""
from __future__ import annotations

import argparse
import json
import sys
from statistics import pstdev

from sqlalchemy import select

from app.data.loaders import load_match_events
from app.db import models
from app.db.session import SessionLocal
from app.engine.confidence.attribution import (
    attribute_driver,
    attribute_stratified,
    auc_score,
)
from app.engine.xt import xt_value_at
from app.sports import football

WINDOW_MIN = 15.0          # karar öncesi pencere (cetvelle aynı)
FINAL_THIRD_X = 66.0


def _xg_proxy(s) -> float:
    """Basit mesafe-tabanlı xG vekili (momentum_tracker ile aynı ölçek)."""
    dx, dy = 100.0 - s.x, 50.0 - s.y
    dist = (dx * dx + dy * dy) ** 0.5
    if dist <= 5.0:
        return 0.55
    if dist <= 12.0:
        return 0.25
    if dist <= 20.0:
        return 0.10
    if dist <= 30.0:
        return 0.04
    return 0.01


def features(loaded, *, team: int, minute: float) -> dict[str, float]:
    """Karar anında ölçülebilen aday büyüklükler.

    Yalnız KARAR ÖNCESİ pencere kullanılır — sonrasına bakmak sızıntı olurdu
    ve her aday mükemmel görünürdü.
    """
    lo, mid = minute - WINDOW_MIN, minute - WINDOW_MIN / 2
    p = [x for x in loaded.passes if lo <= x.minute < minute]
    s = [x for x in loaded.shots if lo <= x.minute < minute]
    d = [x for x in loaded.defensive_actions if lo <= x.minute < minute]

    biz_p = [x for x in p if x.team_external_id == team]
    rak_p = [x for x in p if x.team_external_id != team]
    biz_s = [x for x in s if x.team_external_id in (team, None)]
    rak_s = [x for x in s if x.team_external_id not in (team, None)]
    biz_d = [x for x in d if x.team_external_id == team]

    biz_xg = sum(_xg_proxy(x) for x in biz_s)
    rak_xg = sum(_xg_proxy(x) for x in rak_s)

    def _xt(pl) -> float:
        return sum(max(0.0, xt_value_at(x.end_x, x.end_y) - xt_value_at(x.start_x, x.start_y))
                   for x in pl if x.completed)

    biz_xt, rak_xt = _xt(biz_p), _xt(rak_p)
    toplam_p = len(biz_p) + len(rak_p)

    f: dict[str, float] = {
        # --- SEVİYE ---
        "xg_diff": biz_xg - rak_xg,
        "xt_diff": biz_xt - rak_xt,
        "sut_farki": float(len(biz_s) - len(rak_s)),
        "topla_oynama": (len(biz_p) / toplam_p) if toplam_p else 0.5,
        "def_aksiyon": float(len(biz_d)),
        "son_ucte_bir_pay": (
            sum(1 for x in biz_p if x.end_x >= FINAL_THIRD_X) / len(biz_p)
        ) if biz_p else 0.0,
        "pas_isabet": (
            sum(1 for x in biz_p if x.completed) / len(biz_p)
        ) if biz_p else 0.0,
        "dakika": minute,

        # --- DİNAMİK: pencere içi eğilim (ikinci yarı eksi ilk yarı) ---
        # Seviye değil DEĞİŞİM ölçer; ortalamaya dönüşten daha az etkilenmesi
        # beklenir — hipotez budur, veri karar verir.
        "xg_egilim": (sum(_xg_proxy(x) for x in biz_s if x.minute >= mid)
                      - sum(_xg_proxy(x) for x in biz_s if x.minute < mid)),
        "rakip_xg_egilim": (sum(_xg_proxy(x) for x in rak_s if x.minute >= mid)
                            - sum(_xg_proxy(x) for x in rak_s if x.minute < mid)),
        "pas_egilim": float(sum(1 for x in biz_p if x.minute >= mid)
                            - sum(1 for x in biz_p if x.minute < mid)),
        "def_egilim": float(sum(1 for x in biz_d if x.minute >= mid)
                            - sum(1 for x in biz_d if x.minute < mid)),

        # --- YAPI: kalite dağılımı ---
        # Aynı xG'yi az sayıda NET fırsattan mı yoksa çok sayıda uzak şuttan mı
        # topladık? İkisi aynı sürdürülebilirlikte olmayabilir.
        "en_iyi_sut": max((_xg_proxy(x) for x in biz_s), default=0.0),
        "sut_kalite_ort": (biz_xg / len(biz_s)) if biz_s else 0.0,
        "sut_oynaklik": pstdev([_xg_proxy(x) for x in biz_s]) if len(biz_s) >= 2 else 0.0,
        "sut_yogunluk": float(len(biz_s)) / WINDOW_MIN,
    }
    return f


def main() -> int:
    p = argparse.ArgumentParser(description="Aday sinyal taraması")
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--team", type=int, default=217)
    args = p.parse_args()

    with SessionLocal() as s:
        s.info["tenant_id"] = args.tenant
        kararlar = [
            d for d in s.execute(select(models.Decision).where(
                models.Decision.sport == football.SPORT_NAME,
                models.Decision.tenant_id == args.tenant,
                models.Decision.team_external_id == args.team,
            )).scalars()
            if d.outcome in {"positive", "negative"} and d.context_json
        ]
        if not kararlar:
            print("ölçülmüş karar yok — önce decision_corpus seed + score")
            return 1

        # Maç başına event yükle (tekrar tekrar yüklemeyelim)
        onbellek: dict[int, object] = {}
        ornek: dict[str, list[tuple[float, bool, float]]] = {}
        atlanan = 0
        for d in kararlar:
            if not d.context_json:
                continue
            try:
                ctx = json.loads(d.context_json)
            except (ValueError, TypeError):
                continue
            pre = ctx.get("pre_xg_diff")
            if pre is None:
                atlanan += 1
                continue
            mid = d.match_external_id
            if mid not in onbellek:
                onbellek[mid] = load_match_events(s, mid)
            f = features(onbellek[mid], team=args.team, minute=d.minute)
            for k, v in f.items():
                ornek.setdefault(k, []).append(
                    (float(v), d.outcome == "positive", float(pre)))

    if not ornek:
        print(f"karar öncesi durum kaydı yok ({atlanan} karar atlandı) — "
              f"`decision_corpus score` yeniden çalıştır")
        return 1

    n = len(next(iter(ornek.values())))
    print(f"\n=== Aday Sinyal Taraması (n={n} ölçülmüş karar) ===")
    if atlanan:
        print(f"  ({atlanan} karar `pre_xg_diff` olmadığı için atlandı)")
    print(f"\n  {'aday':<20}{'ham':>7}{'katmanlı':>10}  hüküm")
    print("  " + "-" * 60)

    sonuc = []
    for k, v in ornek.items():
        kat = attribute_stratified(v, k)
        ham = attribute_driver(k, [x for x, ok, _ in v if ok],
                               [x for x, ok, _ in v if not ok])
        sonuc.append((abs(kat.auc - 0.5), k, ham.auc, kat))
    sonuc.sort(reverse=True)
    for _, k, ham_auc, kat in sonuc:
        print(f"  {k:<20}{ham_auc:>7.2f}{kat.auc:>10.2f}  {kat.verdict}")

    # AYRIK YARI DOĞRULAMASI — çoklu karşılaştırma tuzağına karşı ZORUNLU.
    #
    # Bu batarya onlarca aday tarıyor. Saf şansla birinin 0.60 vurması olağan;
    # ölçüldü — `def_egilim` tüm külliyatta 0.60 ("ayırıyor") çıkmıştı ama
    # maçlar ikiye bölününce A'da 0.70, B'de 0.52 verdi. Yani GÜRÜLTÜYDÜ.
    # Tek havuzda bakıp motor yazmak, olmayan bir sinyale ürün inşa etmek olurdu.
    aday = [k for _, k, _, kat in sonuc if kat.verdict in {"ayırıyor", "TERS"}]
    print(f"\n  --- AYRIK YARI DOĞRULAMASI ({len(aday)} aday) ---")
    if not aday:
        print("  (doğrulanacak aday yok)")
    else:
        print(f"  {'aday':<20}{'A yarı':>8}{'B yarı':>8}  hüküm")
        print("  " + "-" * 50)
    saglam, vekil = [], []
    for k in aday:
        v = ornek[k]
        yarim = len(v) // 2
        a = attribute_stratified(v[:yarim], k).auc
        b = attribute_stratified(v[yarim:], k).auc
        tutarli = (a - 0.5) * (b - 0.5) > 0 and min(abs(a - 0.5), abs(b - 0.5)) >= 0.04

        # KARIŞTIRICININ VEKİLİ Mİ? Aday, karar öncesi durumu ne kadar iyi
        # tahmin ediyor? Neredeyse mükemmelse aday "bilgi" taşımıyor; cetvelin
        # kendi yanlılığını yeniden ölçüyor demektir. Böyle bir aday ayrık
        # yarıda DA tutarlı çıkar — çünkü artefakt sistematiktir, rastgele değil.
        # Tutarlılığı "gerçek" sanmak tam da bu yüzden tehlikeli.
        preler = sorted(x for _, _, x in v)
        orta = preler[len(preler) // 2]
        vekil_auc = auc_score([d for d, _, pr in v if pr > orta],
                              [d for d, _, pr in v if pr <= orta])
        vekil_mi = abs(vekil_auc - 0.5) >= 0.30

        if tutarli and not vekil_mi:
            saglam.append(k)
        elif tutarli and vekil_mi:
            vekil.append(k)
        hkm = ("CETVEL VEKİLİ" if (tutarli and vekil_mi)
               else "tutarlı" if tutarli else "TUTMUYOR")
        print(f"  {k:<20}{a:>8.2f}{b:>8.2f}  {hkm}")

    print()
    if vekil:
        print(f"  Cetvel vekili (bilgi DEĞİL): {', '.join(vekil)}")
        print("    Bunlar karar öncesi durumu neredeyse birebir ölçüyor; ayrık")
        print("    yarıda tutmaları artefaktın sistematik olmasından, sinyal")
        print("    taşımalarından değil.")
        print()
    if saglam:
        print(f"  Ayrık yarıda AYAKTA KALAN: {', '.join(saglam)}")
        print("  → yine de başka bir TAKIMDA doğrula; tek takımın verisi")
        print("    o takıma özgü bir düzeni yakalıyor olabilir.")
    else:
        print("  Hiçbir aday ayrık yarıda ayakta kalmıyor.")
        print("  → Bu veride, BU CETVELLE, karar anında ölçülebilen hiçbir")
        print("    büyüklük 'bu karar tutar mı'yı öngörmüyor.")
        print("  → Sıradaki soru sinyal değil CETVEL: bu külliyattaki kararlar")
        print("    UYGULANMADI (motor önerisi olarak kaydedildi). 'Sonra ne")
        print("    oldu' ile 'öneri yüzünden ne oldu' aynı şey değildir.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
