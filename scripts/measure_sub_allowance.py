"""Değişiklik hakkı kuralı: "3 kullanılmış" hücresi iki zıt gerçeği harmanlıyor mu?

## Neden bu script var

Zamanlama önselinin hücresi `(dakika bandı, skor durumu, kullanılmış hak ≤ 3)`.
Kural 3 hakken "3 kullanılmış" = **hak bitti, değişiklik imkânsız**. Kural 5
hakken aynı hücre = **2 hak var, değişiklik çok olası**. Tablo bu iki dünyanın
karışımından fit edildiyse ikisine de yanlış cevap verir.

## Doğal deney

Külliyat kural değişimini içeriyor: La Liga COVID sonrası **2020-06-11**'de
5 hakla yeniden başladı. Aynı kulüp, aynı lig, aynı hakem düzeni — değişen tek
şey kural. Maçlar tarihe göre ayrılır (sezona göre AYIRMAK YANLIŞ: 2019/20'nin
son çeyreği de 5 haklıdır).

## Ölçülen üç şey

1. **Ayrım gerçek mi?** — dönem başına takım başına değişiklik sayısı.
2. **Hücre harmanlanıyor mu?** — "3 kullanılmış" hücresinin her dönemdeki
   gerçek oranı.
3. **Hak-bitti kapısı ne kazandırıyor?** — hak bittiğinde olasılığı 0 saymak.
   Bu kapı yalnız YANLIŞ POZİTİF siler: hak bitmişken değişiklik imkânsız
   olduğundan oradaki her bayrak zaten yanlıştı, dolayısıyla yakalama
   matematiksel olarak değişemez. Ölçüm bunu doğrular.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.measure_sub_allowance
        --events-dir C:\\sb --match-index C:\\sb-idx --cutoff 2020-06-11
        --out docs/measurements/sub-allowance.json

`--match-index` StatsBomb `matches/<comp>/<season>.json` dosyalarının klasörü
(maç tarihleri oradan gelir). Ek `--extra-set AD|KLASÖR|HAK` ile başka kümeler
(ör. bağımsız 2015/16 ligleri, 3 hak) aynı cetvele sokulabilir. Ayırıcı "|";
Windows sürücü harfi ":" içerdiği için iki nokta kullanılamaz.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.data.sources.statsbomb_open import coach_moves_from_events_json
from app.engine.coach_benchmark import SelectivityStat, TickObservation, selectivity
from app.engine.coach_benchmark.compute import PRIOR_LAPLACE
from app.engine.sub_timing.elite_prior import (
    ELITE_SUB_WINDOW_PRIOR,
    MAX_SUBS_CELL,
    MINUTE_BANDS,
    SUB_WINDOW_THRESHOLD,
    UNKNOWN_CELL,
)
from scripts.validate_shape_prior import _grid_ticks

DEFAULT_CUTOFF = "2020-06-11"   # La Liga'nın 5 hakla yeniden başladığı tarih
DEFAULT_WINDOW_MIN = 12.0
THREE_SUB_ERA, FIVE_SUB_ERA = 3, 5

Cell = tuple[int, str, int]
Row = dict[str, Any]


def _band(minute: float) -> int:
    return sum(1 for edge in MINUTE_BANDS if minute >= edge)


def _cell(row: Row) -> Cell:
    return _band(row["minute"]), row["score_state"], min(row["subs_used"], MAX_SUBS_CELL)


def _match_dates(index_dir: Path) -> dict[int, str]:
    dates: dict[int, str] = {}
    for p in glob.glob(os.path.join(str(index_dir), "*.json")):
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
        except ValueError:
            continue
        for m in data if isinstance(data, list) else []:
            if "match_id" in m and "match_date" in m:
                dates[int(m["match_id"])] = str(m["match_date"])
    return dates


def _ticks(events_dir: Path, ids: Sequence[int], allowed: int, window: float) -> list[Row]:
    rows = _grid_ticks(events_dir, list(ids), window)
    for r in rows:
        r["allowed"] = allowed
        r["remaining"] = max(0, allowed - r["subs_used"])
    return rows


def _subs_per_team(events_dir: Path, ids: Sequence[int]) -> list[int]:
    out: list[int] = []
    for mid in ids:
        p = events_dir / f"{mid}.json"
        if not p.is_file():
            continue
        moves = coach_moves_from_events_json(json.loads(p.read_text(encoding="utf-8")))
        for team in {m.team_external_id for m in moves}:
            out.append(sum(1 for m in moves
                           if m.team_external_id == team and m.kind == "substitution"))
    return out


def _fit(rows: Sequence[Row], *, skip_exhausted: bool) -> dict[Cell, float]:
    hits: dict[Cell, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if skip_exhausted and r["remaining"] <= 0:
            continue
        hits[_cell(r)][0] += int(r["coach_sub"])
        hits[_cell(r)][1] += 1
    return {c: (a + PRIOR_LAPLACE) / (n + 2 * PRIOR_LAPLACE) for c, (a, n) in hits.items()}


def _apply(
    table: dict[Cell, float], rows: Sequence[Row], *, gate: bool,
) -> SelectivityStat:
    return selectivity([TickObservation(
        r["match"], r["minute"],
        (not (gate and r["remaining"] <= 0))
        and table.get(_cell(r), UNKNOWN_CELL) >= SUB_WINDOW_THRESHOLD,
        r["coach_sub"]) for r in rows])


def _sel(x: SelectivityStat) -> dict[str, Any]:
    return dict(n=x.n, flagged=x.flagged, flag_rate=x.flag_rate, base_rate=x.base_rate,
                precision=x.precision, recall=x.recall, f1=x.f1, lift=x.lift)


def _rate_by_used(rows: Sequence[Row]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for used in range(0, 6):
        sel = [r for r in rows if min(r["subs_used"], 5) == used]
        if sel:
            out[str(used)] = {"oran": round(sum(r["coach_sub"] for r in sel) / len(sel), 3),
                              "n": len(sel)}
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Değişiklik hakkı kuralının önsele etkisi")
    p.add_argument("--events-dir", type=Path, required=True)
    p.add_argument("--match-index", type=Path, required=True)
    p.add_argument("--cutoff", default=DEFAULT_CUTOFF)
    p.add_argument("--window", type=float, default=DEFAULT_WINDOW_MIN)
    p.add_argument("--extra-set", action="append", default=[],
                   metavar="AD:KLASÖR:HAK", help="ek küme, ör. 'PL 15/16:C:\\pl:3'")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    dates = _match_dates(args.match_index)
    ids = sorted(int(f.stem) for f in args.events_dir.glob("*.json") if f.stem.isdigit())
    known = [m for m in ids if m in dates]
    if not known:
        print("maç tarihi bulunamadı — --match-index StatsBomb matches/ klasörü olmalı")
        return 1
    three = [m for m in known if dates[m] < args.cutoff]
    five = [m for m in known if dates[m] >= args.cutoff]
    if not three or not five:
        print(f"kural değişimi bu kümede yok ({len(three)} / {len(five)} maç)")
        return 1

    sets: dict[str, list[Row]] = {
        f"3-hak (<{args.cutoff})": _ticks(args.events_dir, three, THREE_SUB_ERA, args.window),
        f"5-hak (≥{args.cutoff})": _ticks(args.events_dir, five, FIVE_SUB_ERA, args.window),
    }
    counts = {f"3-hak (<{args.cutoff})": _subs_per_team(args.events_dir, three),
              f"5-hak (≥{args.cutoff})": _subs_per_team(args.events_dir, five)}
    for spec in args.extra_set:
        parts = spec.split("|")
        if len(parts) != 3:
            print(f"--extra-set biçimi 'AD|KLASÖR|HAK' olmalı: {spec}")
            return 1
        name, folder, allowed = parts
        d = Path(folder)
        eids = sorted(int(f.stem) for f in d.glob("*.json") if f.stem.isdigit())
        sets[name] = _ticks(d, eids, int(allowed), args.window)
        counts[name] = _subs_per_team(d, eids)

    names = list(sets)
    doc: dict[str, Any] = {
        "olcum": "Değişiklik hakkı kuralının zamanlama önseline etkisi",
        "dogal_deney": {
            "kesim_tarihi": args.cutoff, "mac": {"3-hak": len(three), "5-hak": len(five)},
            "takim_basina_degisiklik": {
                k: {"dagilim": dict(sorted(Counter(v).items())),
                    "ortalama": round(sum(v) / len(v), 2),
                    "dort_arti_orani": round(sum(1 for x in v if x >= 4) / len(v), 3)}
                for k, v in counts.items() if v},
        },
        "kullanilmis_hakka_gore_gercek_oran": {k: _rate_by_used(v) for k, v in sets.items()},
        "hak_bitti_kapisi": {
            "uretim_tablosu": {
                k: {"kapisiz": _sel(_apply(ELITE_SUB_WINDOW_PRIOR, v, gate=False)),
                    "kapili": _sel(_apply(ELITE_SUB_WINDOW_PRIOR, v, gate=True))}
                for k, v in sets.items()},
            "not": ("kapı yalnız yanlış pozitif siler: hak bitmişken değişiklik "
                    "imkânsız olduğundan yakalama değişemez"),
        },
        "capraz_donem_matrisi": {
            "aciklama": "satır: fit edilen küme, sütun: uygulanan küme, değer: F1",
            "kapisiz": {tr: {te: _apply(_fit(sets[tr], skip_exhausted=False),
                                        sets[te], gate=False).f1 for te in names}
                        for tr in names},
            "kapili": {tr: {te: _apply(_fit(sets[tr], skip_exhausted=True),
                                       sets[te], gate=True).f1 for te in names}
                       for tr in names},
        },
        "girdi_sha256": hashlib.sha256(json.dumps(
            {k: v for k, v in sorted(sets.items())}, sort_keys=True,
            default=str).encode("utf-8")).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"doğal deney: {len(three)} maç 3-hak · {len(five)} maç 5-hak "
          f"(kesim {args.cutoff})")
    for k, v in doc["dogal_deney"]["takim_basina_degisiklik"].items():
        print(f"  {k:<24} ortalama {v['ortalama']} · 4+ yapan oran {v['dort_arti_orani']}")
    print("\n'3 kullanılmış' hücresinin gerçek oranı:")
    for k in names:
        r = doc["kullanilmis_hakka_gore_gercek_oran"][k].get("3")
        shown = "—" if r is None else f"{r['oran']} (n={r['n']})"
        print(f"  {k:<24} {shown}")
    print("\nüretim tablosu + hak-bitti kapısı:")
    for k in names:
        g = doc["hak_bitti_kapisi"]["uretim_tablosu"][k]
        print(f"  {k:<24} F1 {g['kapisiz']['f1']} → {g['kapili']['f1']} · "
              f"yakalama {g['kapisiz']['recall']} → {g['kapili']['recall']}")
    print(f"\n→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
