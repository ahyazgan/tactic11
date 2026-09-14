"""Zamanlama önselini yeniden fit et — çok kümeli, hak-farkındalıklı, LOO doğrulamalı.

## Neden bu script var

`ELITE_SUB_WINDOW_PRIOR` tek kulübün 100 maçından, üstelik 3-hak ve 5-hak
maçlarının KARIŞIMINDAN fit edilmişti (bkz. docs/KARNE-DEGISIKLIK-HAKKI.md).
Hak-bitti kapısı harmanın yarısını mantıkla kesti; bu script tablonun kendisini
yeniden kurar.

## İki kural

1. **Hak-bitmiş tikler fit'e GİRMEZ.** Hak bittiğinde değişiklik imkânsızdır ve
   bu bilgi tabloda değil kapıda durur. Elenince "3 kullanılmış" hücresi her
   rejimde aynı şeyi anlatır: *3 yaptı ve hakkı var*. Kural rejimleri ancak bu
   sayede aynı havuza konabilir.
2. **Hüküm leave-one-out.** Her küme, KENDİSİ hariç ötekilerden fit edilen
   tabloyla ölçülür. İçinde bulunduğu havuzla ölçmek kendini sınamaktır.

## Eşik

Eşik tablonun parçasıdır, bu yüzden birlikte taranır. Plato bulunursa argmax
SEÇİLMEZ: düz bir bölgede en yüksek ortalama gürültüdür. Script platoyu basar,
kararı insan verir (`--threshold` ile sabitlenir).

## Kullanım

    venv\\Scripts\\python.exe -m scripts.fit_timing_prior
        --set "Euro 2024|C:\\sb-euro|5" --set "La Liga 2015/16|C:\\sb-ll|3"
        --out docs/measurements/timing-prior-fit.json

Ayırıcı `|`, çünkü Windows sürücü harfi `:` içerir. `--print-table` Python
sözlüğünü basar (motora yapıştırmak için).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.engine.coach_benchmark import SelectivityStat, TickObservation, selectivity
from app.engine.coach_benchmark.compute import PRIOR_LAPLACE
from app.engine.sub_timing.elite_prior import (
    MAX_SUBS_CELL,
    MINUTE_BANDS,
    SUB_WINDOW_THRESHOLD,
    UNKNOWN_CELL,
)
from scripts.validate_shape_prior import _grid_ticks

DEFAULT_WINDOW_MIN = 12.0
THRESHOLD_SWEEP: tuple[float, ...] = (0.25, 0.30, 0.35, 0.40, 0.45, 0.50)
# Plato genişliği: en iyi ortalamaya bu kadar yakın eşikler "ayırt edilemez".
PLATEAU_BAND = 0.005
# Kıyas tabanı DOSYADAN okunur, canlı sabitten DEĞİL. Sebep: bu script canlı
# sabiti değiştirmek için var; oradan okunursa refit'ten sonra "eski tablo"
# sütunu yeni tablonun kendisi olur ve kıyas kendini ölçer.
BASELINE_TABLE = Path("docs/measurements/timing-prior-baseline.json")

Cell = tuple[int, str, int]
Row = dict[str, Any]


def _band(minute: float) -> int:
    return sum(1 for edge in MINUTE_BANDS if minute >= edge)


def _cell(row: Row) -> Cell:
    return _band(row["minute"]), row["score_state"], min(row["subs_used"], MAX_SUBS_CELL)


def _load(folder: Path, allowed: int, window: float) -> list[Row]:
    ids = sorted(int(f.stem) for f in folder.glob("*.json") if f.stem.isdigit())
    rows = _grid_ticks(folder, ids, window)
    for r in rows:
        r["allowed"] = allowed
        r["remaining"] = max(0, allowed - r["subs_used"])
    return rows


def fit_table(rows: Sequence[Row]) -> tuple[dict[Cell, float], dict[Cell, tuple[int, int]]]:
    """Hücre oranı (Laplace). Hak-bitmiş tikler ELENİR — o bilgi kapıda durur."""
    hits: dict[Cell, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["remaining"] <= 0:
            continue
        hits[_cell(r)][0] += int(r["coach_sub"])
        hits[_cell(r)][1] += 1
    table = {c: round((a + PRIOR_LAPLACE) / (n + 2 * PRIOR_LAPLACE), 3)
             for c, (a, n) in hits.items()}
    return table, {c: (a, n) for c, (a, n) in hits.items()}


def evaluate(table: dict[Cell, float], rows: Sequence[Row], threshold: float) -> SelectivityStat:
    """Kapı her zaman açık: hak bittiyse bayrak yok, tablo ne derse desin."""
    return selectivity([TickObservation(
        r["match"], r["minute"],
        r["remaining"] > 0 and table.get(_cell(r), UNKNOWN_CELL) >= threshold,
        r["coach_sub"]) for r in rows])


def _load_baseline(path: Path) -> dict[str, Any]:
    """Refit ÖNCESİ tabloyu dosyadan oku — kıyasın tekrarlanabilir olması için.

    Canlı sabit (`ELITE_SUB_WINDOW_PRIOR`) bilerek İTHAL EDİLMEZ: bu script onu
    değiştirmek için var, oradan okunursa "eski tablo" sütunu refit sonrası yeni
    tablonun kendisi olur — üstelik örnek-içi ölçüldüğü için refit'i gerileme
    gibi gösterir.
    """
    doc = json.loads(path.read_text(encoding="utf-8"))
    table: dict[Cell, float] = {}
    for key, value in doc["tablo"].items():
        band, state, used = key.split("|")
        table[(int(band), state, int(used))] = float(value)
    return {"tablo": table, "esik": float(doc["esik"]), "ad": doc["ad"],
            "commit": doc.get("commit"), "kaynak": doc.get("kaynak")}


def _loo(sets: dict[str, list[Row]], threshold: float) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in sets:
        train = [r for k, v in sets.items() if k != name for r in v]
        table, _ = fit_table(train)
        out[name] = evaluate(table, sets[name], threshold).f1 or 0.0
    return out


def _loo_groups(sets: dict[str, list[Row]], groups: dict[str, str],
                threshold: float) -> dict[str, float]:
    """Grup bazlı leave-one-out: aynı kulübün iki rejimi BİRLİKTE dışarı çıkar.

    Küme bazlı LOO "Barcelona 3-hak"ı dışarı çıkarırken "Barcelona 5-hak"ı
    eğitimde bırakır — aynı kulüp, büyük ölçüde aynı kadro ve aynı antrenör.
    Bu, kümeler arası genellemeyi olduğundan iyi gösterir. Grup bazlı ölçüm
    daha zor ve daha dürüst olanıdır; ikisi de raporlanır.
    """
    out: dict[str, float] = {}
    for group in sorted(set(groups.values())):
        held = [n for n in sets if groups[n] == group]
        train = [r for n, v in sets.items() if groups[n] != group for r in v]
        if not train:
            continue
        table, _ = fit_table(train)
        rows = [r for n in held for r in sets[n]]
        out[group] = evaluate(table, rows, threshold).f1 or 0.0
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Zamanlama önselini yeniden fit et")
    p.add_argument("--set", action="append", required=True, dest="sets",
                   metavar="AD|KLASÖR|HAK", help="ör. 'Euro 2024|C:\\sb-euro|5'")
    p.add_argument("--window", type=float, default=DEFAULT_WINDOW_MIN)
    p.add_argument("--threshold", type=float, default=SUB_WINDOW_THRESHOLD,
                   help="karar eşiği; tarama basılır ama seçim buradan gelir")
    p.add_argument("--baseline", type=Path, default=BASELINE_TABLE,
                   help="refit öncesi tablo (kıyas tabanı); canlı sabitten okunmaz")
    p.add_argument("--print-table", action="store_true")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    sets: dict[str, list[Row]] = {}
    allowances: dict[str, int] = {}
    groups: dict[str, str] = {}
    for spec in args.sets:
        parts = spec.split("|")
        if len(parts) not in (3, 4):
            print(f"--set biçimi 'AD|KLASÖR|HAK[|GRUP]' olmalı: {spec}")
            return 1
        name, folder, allowed = parts[:3]
        groups[name] = parts[3] if len(parts) == 4 else name
        rows = _load(Path(folder), int(allowed), args.window)
        if not rows:
            print(f"'{name}' kümesinden tik çıkmadı: {folder}")
            return 1
        sets[name], allowances[name] = rows, int(allowed)
    if len(sets) < 2:
        print("leave-one-out için en az iki küme gerekir")
        return 1

    sweep = {f"{t:.2f}": _loo(sets, t) for t in THRESHOLD_SWEEP}
    means = {t: statistics.mean(v.values()) for t, v in sweep.items()}
    top = max(means.values())
    plateau = sorted(t for t, m in means.items() if top - m <= PLATEAU_BAND)

    table, counts = fit_table([r for v in sets.values() for r in v])
    loo = _loo(sets, args.threshold)
    loo_group = _loo_groups(sets, groups, args.threshold)
    base = _load_baseline(args.baseline)
    old = {name: evaluate(base["tablo"], rows, base["esik"]).f1 or 0.0
           for name, rows in sets.items()}
    thin = {f"{c}": n for c, (_a, n) in counts.items() if n < 10}

    doc = {
        "olcum": "Zamanlama önselinin çok kümeli yeniden fit'i",
        "kumeler": {n: {"mac": len({r["match"] for r in rows}), "tik": len(rows),
                        "hak": allowances[n],
                        "taban_orani": round(sum(r["coach_sub"] for r in rows) / len(rows), 3)}
                    for n, rows in sets.items()},
        "fit_kurali": {
            "hak_bitmis_tik_elenir": True,
            "elenen_tik": sum(1 for v in sets.values() for r in v if r["remaining"] <= 0),
            "kullanilan_tik": sum(1 for v in sets.values() for r in v if r["remaining"] > 0),
            "hucre": len(table),
            "not": ("hak bitmişlik tabloda değil kapıda durur; elenince '3 kullanılmış' "
                    "hücresi her rejimde aynı şeyi anlatır"),
        },
        "esik_taramasi": {"loo_ortalama": {t: round(m, 3) for t, m in means.items()},
                          "plato": plateau, "plato_bandi": PLATEAU_BAND,
                          "secilen": args.threshold,
                          "not": ("düz bölgede argmax seçmek gürültüye uymaktır; "
                                  "seçim --threshold ile sabitlenir")},
        "kiyas_tabani": {"ad": base["ad"], "commit": base["commit"],
                         "kaynak": base["kaynak"], "esik": base["esik"],
                         "hucre": len(base["tablo"]), "dosya": str(args.baseline),
                         "not": ("canlı sabitten okunmaz; refit onu değiştirdiği için "
                                 "canlı okuma kıyası kendi kendine yaptırırdı")},
        "leave_one_group_out": {
            "gruplar": {g: sorted(n for n in sets if groups[n] == g)
                        for g in sorted(set(groups.values()))},
            "f1": {k: round(v, 3) for k, v in loo_group.items()},
            "ortalama": round(statistics.mean(loo_group.values()), 3) if loo_group else None,
            "en_kotu": round(min(loo_group.values()), 3) if loo_group else None,
            "not": ("küme bazlı LOO aynı kulübün öteki rejimini eğitimde bırakır; "
                    "grup bazlı olan daha zor ve daha dürüst kıyastır"),
        },
        "leave_one_out": {"yeni_tablo": {k: round(v, 3) for k, v in loo.items()},
                          "eski_tablo": {k: round(v, 3) for k, v in old.items()},
                          "ortalama": {"yeni": round(statistics.mean(loo.values()), 3),
                                       "eski": round(statistics.mean(old.values()), 3)},
                          "en_kotu": {"yeni": round(min(loo.values()), 3),
                                      "eski": round(min(old.values()), 3)}},
        "seyrek_hucreler": thin,
        "tablo": {f"{c[0]}|{c[1]}|{c[2]}": {"onsel": table[c], "olay": counts[c][0],
                                            "tik": counts[c][1]} for c in sorted(table)},
        "girdi_sha256": hashlib.sha256(json.dumps(
            {n: sorted((r["match"], r["team"], r["minute"], r["subs_used"],
                        r["score_state"], r["coach_sub"]) for r in v)
             for n, v in sorted(sets.items())}, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(sets)} küme · {doc['fit_kurali']['kullanilan_tik']} tik "
          f"(hak bitmiş {doc['fit_kurali']['elenen_tik']} elendi) · {len(table)} hücre")
    print("\neşik taraması (LOO ortalama F1):")
    for t, m in means.items():
        mark = " ← plato" if t in plateau else ""
        mark += "  [SEÇİLEN]" if abs(float(t) - args.threshold) < 1e-9 else ""
        print(f"  {t}: {m:.3f}{mark}")
    print(f"\nleave-one-out F1 (eşik {args.threshold}):")
    for n in sets:
        print(f"  {n:<24} eski {old[n]:.3f} → yeni {loo[n]:.3f}")
    print(f"  {'ORTALAMA':<24} eski {statistics.mean(old.values()):.3f} → "
          f"yeni {statistics.mean(loo.values()):.3f}")
    print(f"  {'EN KÖTÜ':<24} eski {min(old.values()):.3f} → yeni {min(loo.values()):.3f}")
    if thin:
        print(f"\nseyrek hücre (n<10): {len(thin)} adet, toplam {sum(thin.values())} tik")
    if args.print_table:
        print("\nELITE_SUB_WINDOW_PRIOR: dict[tuple[int, str, int], float] = {")
        for c in sorted(table):
            a, n = counts[c]
            print(f'    ({c[0]}, "{c[1]}", {c[2]}): {table[c]:.3f},   # {a}/{n}')
        print("}")
    print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
