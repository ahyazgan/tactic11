"""Elit ZAMANLAMA önseli külliyat dışında da tutuyor mu — BAĞIMSIZ maçlarda ölç.

## Neden bu script var

Canlı motorda veriden türetilmiş üç donmuş tablo var. İkisi bağımsız maçlarda
sınandı: şekil kapısının durum önseli (taşındı) ve "kim çıkar" önseli (tek
kulübe özgü çıktı, yeniden fit edildi). Üçüncüsü `ELITE_SUB_WINDOW_PRIOR`
(`app/engine/sub_timing/elite_prior.py`): "bu durumda antrenör 12 dk içinde
değişiklik yapar mı?" Kaynağı Barcelona'nın 100 maçındaki İKİ takımın
antrenörleri, 3200 ızgara tiki. Hiç dışarıda sınanmadı.

Bu tablo panelde `sub_timing` sinyalini yakıyor, yani koça "şimdi değişiklik
penceresi" diyen şey bu. Sınanan nesne tablonun ve eşiğin **kendisidir**;
yeniden fit edilmez.

## Ölçü: seçicilik, F1 değil

Hedef nadir değil (ızgarada ~%30-40) ama soru yine "kaç bayrakla ne kadar
isabet"tir. `selectivity` kullanılır: kaldırma = isabet / taban oranı, yanında
bayrak oranı. Kıyaslar:

1. **Donmuş tablo + donmuş eşik** — üretimdeki nesne.
2. **Saat kuralı** — eşiği bağımsız kümede EN İYİ olacak şekilde seçilir;
   yani tabana kasten avantaj verilir. Önsel bunu geçemiyorsa geçemiyordur.
3. **Küme içi tavan** — bağımsız kümenin kendi ayrık yarısında öğrenilen önsel.
4. **Hep-evet** — kaldırması tanım gereği 1.0.

## Bilinen karışıklık: değişiklik hakkı

Tablo 3 hakkın geçerli olduğu 2018-21 sezonlarından (2020/21 hariç) geliyor ve
hücrenin bir ekseni "o ana kadar yapılan değişiklik". Bağımsız kümeler 2015/16,
yine 3 hak. Yani bu ölçüm 5-hak kuralını SINAMAZ; tablonun doküstringindeki
"5-hak kuralıyla yeniden fit gerekir" uyarısı yerinde duruyor.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.validate_timing_prior
        --corpus-dir C:\\sb --independent-dir C:\\sb-ind
        --out docs/measurements/karne-zamanlama-bagimsiz.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.engine.coach_benchmark import (
    MIN_F1_GAIN,
    SelectivityStat,
    TickObservation,
    selectivity,
)
from app.engine.coach_benchmark.compute import PRIOR_LAPLACE
from app.engine.sub_timing.elite_prior import (
    ELITE_SUB_WINDOW_PRIOR,
    MAX_SUBS_CELL,
    MINUTE_BANDS,
    SUB_WINDOW_THRESHOLD,
    UNKNOWN_CELL,
)
from scripts.validate_shape_prior import GRID_MINUTES, _grid_ticks

DEFAULT_WINDOW_MIN = 12.0
# Saat kuralına kasten avantaj: eşiği bağımsız kümede en iyi olacak şekilde seç.
CLOCK_THRESHOLDS: tuple[float, ...] = GRID_MINUTES

Cell = tuple[int, str, int]
Row = dict[str, Any]


def _band(minute: float) -> int:
    return sum(1 for edge in MINUTE_BANDS if minute >= edge)


def _cell(row: Row) -> Cell:
    return _band(row["minute"]), row["score_state"], min(row["subs_used"], MAX_SUBS_CELL)


def _obs(rows: Sequence[Row], flag: Callable[[Row], bool]) -> list[TickObservation]:
    return [TickObservation(r["match"], r["minute"], flag(r), r["coach_sub"]) for r in rows]


def _fit(rows: Sequence[Row]) -> dict[Cell, float]:
    """`fit_timing_prior` ile aynı kural: hücre oranı, Laplace düzeltmeli."""
    hits: dict[Cell, list[int]] = {}
    for r in rows:
        cell = _cell(r)
        hits.setdefault(cell, [0, 0])
        hits[cell][0] += int(r["coach_sub"])
        hits[cell][1] += 1
    return {c: (a + PRIOR_LAPLACE) / (n + 2 * PRIOR_LAPLACE) for c, (a, n) in hits.items()}


def _apply(table: dict[Cell, float], threshold: float, unknown: float) -> Callable[[Row], bool]:
    return lambda r: table.get(_cell(r), unknown) >= threshold


def _best_clock(rows: Sequence[Row]) -> tuple[float, SelectivityStat]:
    """Tabana avantaj: eşik AYNI kümede en iyi F1'e göre seçilir."""
    best: tuple[float, SelectivityStat] | None = None
    for t in CLOCK_THRESHOLDS:
        st = selectivity(_obs(rows, lambda r, t=t: r["minute"] >= t))
        if best is None or (st.f1 or 0.0) > (best[1].f1 or 0.0):
            best = (t, st)
    assert best is not None
    return best


def _ceiling(rows: Sequence[Row], threshold: float, unknown: float) -> list[SelectivityStat]:
    ids = sorted({r["match"] for r in rows})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    a = [r for r in rows if r["match"] in a_ids]
    b = [r for r in rows if r["match"] not in a_ids]
    return [selectivity(_obs(a, _apply(_fit(b), threshold, unknown))),
            selectivity(_obs(b, _apply(_fit(a), threshold, unknown)))]


def _sel(x: SelectivityStat) -> dict[str, Any]:
    return dict(n=x.n, flagged=x.flagged, flag_rate=x.flag_rate, base_rate=x.base_rate,
                precision=x.precision, recall=x.recall, f1=x.f1, lift=x.lift)


def _unknown_split(rows: Sequence[Row]) -> dict[str, Any]:
    """Tablonun hiç görmediği hücreler ne kadar yer kaplıyor ve ne kadar isabetli?"""
    seen = [r for r in rows if _cell(r) in ELITE_SUB_WINDOW_PRIOR]
    unseen = [r for r in rows if _cell(r) not in ELITE_SUB_WINDOW_PRIOR]
    flag = _apply(ELITE_SUB_WINDOW_PRIOR, SUB_WINDOW_THRESHOLD, UNKNOWN_CELL)
    out: dict[str, Any] = {
        "gorulmus": _sel(selectivity(_obs(seen, flag))) if seen else None,
        "gorulmemis": _sel(selectivity(_obs(unseen, flag))) if unseen else None,
        "gorulmemis_tik_payi": round(len(unseen) / len(rows), 3) if rows else None,
    }
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Zamanlama önselinin bağımsız doğrulaması")
    p.add_argument("--corpus-dir", type=Path, required=True,
                   help="tablonun öğrenildiği maçlar (kesişim denetimi için)")
    p.add_argument("--independent-dir", type=Path, required=True)
    p.add_argument("--label", default="bağımsız küme")
    p.add_argument("--window", type=float, default=DEFAULT_WINDOW_MIN)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    corpus_ids = {int(f.stem) for f in args.corpus_dir.glob("*.json") if f.stem.isdigit()}
    ind_ids = sorted(int(f.stem) for f in args.independent_dir.glob("*.json")
                     if f.stem.isdigit())
    overlap = sorted(corpus_ids & set(ind_ids))
    if overlap:
        print(f"BAĞIMSIZ DEĞİL: {len(overlap)} maç külliyatta da var ({overlap[:5]}…)")
        return 1
    if not ind_ids:
        print("bağımsız klasörde maç yok")
        return 1

    rows = _grid_ticks(args.independent_dir, ind_ids, args.window)
    if not rows:
        print("bağımsız maçlardan tik çıkmadı")
        return 1

    frozen = selectivity(_obs(rows, _apply(
        ELITE_SUB_WINDOW_PRIOR, SUB_WINDOW_THRESHOLD, UNKNOWN_CELL)))
    silent = selectivity(_obs(rows, _apply(ELITE_SUB_WINDOW_PRIOR, SUB_WINDOW_THRESHOLD, 0.0)))
    clock_t, clock = _best_clock(rows)
    ceil_a, ceil_b = _ceiling(rows, SUB_WINDOW_THRESHOLD, UNKNOWN_CELL)
    always = selectivity(_obs(rows, lambda r: True))

    lifts = [ceil_a.lift, ceil_b.lift]
    # Hüküm bandı deponun kendi ölçütü: F1 farkı ±MIN_F1_GAIN içindeyse "aynı".
    gap = None if (frozen.f1 is None or clock.f1 is None) else round(frozen.f1 - clock.f1, 3)
    clock_note = (f"saat eşiği {clock_t:.0f} dk, AYNI kümede en iyi olacak şekilde "
                  f"seçildi — tabana kasten avantaj")
    if frozen.lift is None or gap is None:
        verdict, note = "yetersiz veri", "kapıdan hiç bayrak geçmedi"
    elif gap >= MIN_F1_GAIN:
        verdict = "saati geçiyor"
        note = f"önsel F1 {frozen.f1} vs saat {clock.f1} ({gap:+.3f}); {clock_note}"
    elif gap <= -MIN_F1_GAIN:
        verdict = "saatin altında"
        note = f"önsel F1 {frozen.f1} vs saat {clock.f1} ({gap:+.3f}); {clock_note}"
    else:
        verdict = "saatle aynı"
        note = (f"önsel F1 {frozen.f1} vs saat {clock.f1} ({gap:+.3f}) — fark "
                f"±{MIN_F1_GAIN:.2f} bandında; {clock_note}")

    doc = {
        "olcum": "Elit zamanlama önselinin bağımsız maçlarda doğrulaması",
        "sinanan_nesne": {
            "ad": "ELITE_SUB_WINDOW_PRIOR (app/engine/sub_timing)",
            "canli_motorda_kullaniliyor": True,
            "esik": SUB_WINDOW_THRESHOLD, "gorulmemis_hucre": UNKNOWN_CELL,
            "hucre_sayisi": len(ELITE_SUB_WINDOW_PRIOR),
            "kaynak": "Barcelona'nın 100 maçı, iki takımın antrenörleri, 3200 tik",
        },
        "bagimsiz_kume": {
            "ad": args.label, "mac": len({r["match"] for r in rows}), "tik": len(rows),
            "izgara_dk": list(GRID_MINUTES), "pencere_dk": args.window,
            "taban_orani": frozen.base_rate, "kulliyatla_kesisim": 0,
            "girdi_sha256": hashlib.sha256(
                json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest(),
        },
        "tasima": {
            "donmus_tablo_ve_esik": _sel(frozen),
            "donmus_tablo_gorulmemiste_susarak": _sel(silent),
            "saat_kurali_en_iyi_esik": {"esik_dk": clock_t, **_sel(clock)},
            "kume_ici_tavan_A": _sel(ceil_a), "kume_ici_tavan_B": _sel(ceil_b),
            "hep_evet": _sel(always),
            "f1_farki": gap, "hukum_bandi": MIN_F1_GAIN,
            "hukum": verdict, "not": note,
        },
        "gorulmemis_hucre_analizi": _unknown_split(rows),
        "kume_ici_tavan_kaldirma": lifts,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{args.label}: {doc['bagimsiz_kume']['mac']} bağımsız maç · {len(rows)} tik · "
          f"taban {frozen.base_rate}")
    for label, st in (("hep-evet", always), ("DONMUŞ tablo+eşik", frozen),
                      ("donmuş, görülmemişte susarak", silent),
                      (f"saat kuralı (≥{clock_t:.0f} dk, en iyi)", clock),
                      ("küme içi tavan A", ceil_a), ("küme içi tavan B", ceil_b)):
        print(f"  {label:<32} bayrak {st.flag_rate:.2f} · isabet "
              f"{'—' if st.precision is None else f'{st.precision:.3f}'} · kaldırma "
              f"{'—' if st.lift is None else f'{st.lift:.2f}'} · yakalama "
              f"{'—' if st.recall is None else f'{st.recall:.2f}'} · F1 "
              f"{'—' if st.f1 is None else f'{st.f1:.3f}'}")
    u = doc["gorulmemis_hucre_analizi"]
    print(f"  görülmemiş hücre payı: {u['gorulmemis_tik_payi']}")
    print(f"  hüküm: {verdict} — {note}")
    print(f"  → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
