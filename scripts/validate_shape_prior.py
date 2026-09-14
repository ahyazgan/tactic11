"""Şekil kapısı külliyat DIŞINDA da tutuyor mu — BAĞIMSIZ maçlarda ölç.

## Neden bu script var

`measure_shape_selectivity` kapıyı tek külliyatın (100 La Liga maçı, takım 217)
ayrık yarılarında ölçer. Ayrık yarı, eşik seçimini dürüst tutar ama aynı takımın
aynı sezonlarındaki alışkanlığı öğrenmiş olma ihtimalini elemez. Bu script
kapıyı HİÇ görmediği maçlara taşır: başka sezonlar, başka takımlar, başka lig.

## Ne taşınabilir, ne taşınamaz

Kapı üç parçadır: motorun `adjust_shape` bayrağı ∧ durum önseli ∧ destekleyici
sinyal sayısı. Bağımsız maçlarda motor tiki YOKTUR — o maçlar için karar
külliyatı üretilmemiştir. Dolayısıyla yalnız **durum önseli** taşınabilir.
Bu bir kısıtlama değil, ölçümün kendi sonucudur: külliyatta motor bayrağının
kaldırması 0,91/1,08 (bilgi yok) çıkmıştı; sinyali taşıyan parça önseldir.
Destek eşiği de motor tikine bağlıdır ve bu sınavın dışındadır.

## Üç soru, üç sütun

1. **Taşıma (asıl soru)** — karnenin külliyattan öğrendiği önsel, dondurulmuş
   hâliyle bağımsız maçlarda kaldırma üretiyor mu?
2. **Izgara taşıması** — aynı önsel külliyat maçlarında ama AYNI ızgara
   üzerinde kurulursa ne olur? Tik dağılımı farkını taşıma farkından ayırır.
3. **Tavan** — bağımsız kümenin kendi içinde (ayrık yarı) ulaşılabilen kaldırma.
   Taşıma bunun altındaysa önsel külliyata özgüdür; eşitse taşınıyordur.

Bağımsız maçlarda motor tiki olmadığı için anlar sabit bir ızgaradan alınır
(`GRID_MINUTES`, `coach_iq`'nun plasebo ızgarasıyla aynı). Izgara, motor
tiklerinin dağılımı değildir; sütun 2 tam da bu farkı ölçmek için vardır.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.validate_shape_prior
        --events-dir C:\\sb --independent-dir C:\\sb-ind
        --out docs/measurements/karne-sekil-bagimsiz.json

`--events-dir` külliyatın ham olayları (önsel oradan öğrenilir, DB gerekir),
`--independent-dir` külliyatta BULUNMAYAN maçların ham olaylarıdır. Kesişim
varsa script durur: sızıntılı bir "bağımsız" küme ölçüm değildir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.data.sources.statsbomb_open import (
    coach_moves_from_events_json,
    shots_from_events_json,
)
from app.engine.coach_benchmark import (
    SHAPE_MIN_LIFT,
    SelectivityStat,
    ShapePrior,
    ShapeState,
    TickObservation,
    apply_shape_gate,
    fit_shape_prior,
    selectivity,
)
from app.engine.decision_baseline import score_state
from scripts.measure_shape_selectivity import collect_corpus_ticks, shape_states

DEFAULT_WINDOW_MIN = 12.0
DEFAULT_PERMUTATIONS = 400
# Bağımsız maçlarda motor tiki yok; anlar bu ızgaradan alınır (coach_iq ile aynı).
GRID_MINUTES: tuple[float, ...] = tuple(float(m) for m in range(10, 90, 5))
# Önsel tek başına ölçülürken destek eşiği devre dışı bırakılır: bağımsız
# maçlarda destekleyici sinyal diye bir şey yoktur, 0 eşiği her tiki geçirir.
PRIOR_ONLY_SUPPORT: tuple[int, ...] = (0,)


def _grid_ticks(
    events_dir: Path, match_ids: list[int], window: float,
) -> list[dict[str, Any]]:
    """Her maçın İKİ takımı için ızgara anları + durum + gerçek hamleler.

    `coach_shift` diziliş değişimi (şekil kapısının hedefi), `coach_sub` taktik
    oyuncu değişikliği (zamanlama önselinin hedefi) — ikisi aynı ızgaradan çıkar.
    """
    rows: list[dict[str, Any]] = []
    for mid in match_ids:
        p = events_dir / f"{mid}.json"
        if not p.is_file():
            continue
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        moves = coach_moves_from_events_json(ev)
        teams = sorted({m.team_external_id for m in moves})
        if len(teams) != 2:
            continue
        goals = [(s.minute, s.team_external_id) for s in shots_from_events_json(ev, match_id=mid)
                 if s.is_goal and s.team_external_id is not None]
        for team in teams:
            shifts = sorted({m.minute for m in moves
                             if m.team_external_id == team and m.kind == "tactical_shift"})
            # Aynı dakikadaki iki oyuncu değişikliği iki hak kullanır (tekilleştirme yok).
            subs = sorted(m.minute for m in moves
                          if m.team_external_id == team and m.kind == "substitution")
            # Zamanlama önselinin hedefi TAKTİK değişikliktir; sakatlık hamlesi
            # antrenörün kararı sayılmaz. Kullanılan hak sayımı ise hepsini içerir.
            tactical = sorted({m.minute for m in moves if m.team_external_id == team
                               and m.kind == "substitution" and m.tactical})
            for t in GRID_MINUTES:
                mine = sum(1 for g, tm in goals if g < t and tm == team)
                theirs = sum(1 for g, tm in goals if g < t and tm != team)
                rows.append(dict(
                    match=mid, team=team, minute=t,
                    score_state=score_state(mine, theirs),
                    subs_used=sum(1 for c in subs if c <= t),
                    coach_shift=any(t < c <= t + window for c in shifts),
                    coach_sub=any(t < c <= t + window for c in tactical),
                ))
    return rows


def _prior_only_states(rows: list[dict[str, Any]]) -> list[ShapeState]:
    """Izgara anları → ShapeState. Motor bayrağı yok sayılır (hepsi açık),
    destek sayısı 0'dır; böylece yalnız önsel karar verir."""
    return [ShapeState(
        r["match"], r["minute"], score_state=r["score_state"], subs_used=r["subs_used"],
        engine_flag=True, support_count=0, coach_acted=r["coach_shift"],
    ) for r in rows]


def _prior_component(prior: ShapePrior) -> ShapePrior:
    """Kapının YALNIZ önsel bileşeni: aynı tablo ve aynı eşik, destek eşiği kapalı.

    Karnenin öğrendiği destek eşiği (≥2) motor tikine bağlıdır; bağımsız
    maçlarda karşılığı yoktur ve bu sınava sokulmaz.
    """
    return ShapePrior(table=prior.table, threshold=prior.threshold,
                      support_threshold=0, fitted_on=prior.fitted_on)


def _sel(x: SelectivityStat) -> dict[str, Any]:
    return dict(n=x.n, flagged=x.flagged, flag_rate=x.flag_rate, base_rate=x.base_rate,
                precision=x.precision, recall=x.recall, f1=x.f1, lift=x.lift)


def _apply(prior: ShapePrior, states: list[ShapeState]) -> SelectivityStat:
    return selectivity(apply_shape_gate(_prior_component(prior), states))


def _ceiling(states: list[ShapeState]) -> tuple[SelectivityStat, SelectivityStat]:
    """Bağımsız kümenin kendi ayrık yarısı: önsel bir yarıda öğrenilir, ötekinde ölçülür."""
    ids = sorted({s.match_external_id for s in states})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    a = [s for s in states if s.match_external_id in a_ids]
    b = [s for s in states if s.match_external_id not in a_ids]
    fit_a = fit_shape_prior(b, support_thresholds=PRIOR_ONLY_SUPPORT)
    fit_b = fit_shape_prior(a, support_thresholds=PRIOR_ONLY_SUPPORT)
    return _apply(fit_a, a), _apply(fit_b, b)


def _permutation(
    prior: ShapePrior, states: list[ShapeState], trials: int, seed: int,
) -> dict[str, Any]:
    """Bağımsız etiketleri karıştır; DONDURULMUŞ önsel yine de ayırıyor mu?

    Önsel yeniden kurulmaz — taşınan nesne sabittir, sınanan tek şey onun bu
    kümedeki isabetidir. p = (yakalama + 1) / (deneme + 1); sıfır olasılık
    iddia edilmez.
    """
    real = _apply(prior, states).precision
    if real is None:
        return {"deneme": 0, "istenen_deneme": trials, "seed": seed,
                "gercek_precision": None, "karistirilmisin_yakalama_sayisi": 0,
                "p": None, "not": "kapıdan bayrak geçmedi — hüküm verilmedi"}
    rng = random.Random(seed)
    hits = 0
    for _ in range(trials):
        labels = [s.coach_acted for s in states]
        rng.shuffle(labels)
        got = _apply(prior, [ShapeState(
            s.match_external_id, s.minute, s.score_state, s.subs_used,
            s.engine_flag, s.support_count, lab,
        ) for s, lab in zip(states, labels, strict=True)]).precision
        if (got or 0.0) >= real:
            hits += 1
    return {"deneme": trials, "seed": seed, "gercek_precision": real,
            "karistirilmisin_yakalama_sayisi": hits, "p": (hits + 1) / (trials + 1),
            "not": "dondurulmuş önsel, karıştırılmış etiketler; "
                   "p = (yakalama + 1) / (deneme + 1); tik düzeyinde keşifsel sınav"}


def _verdict(transfer: SelectivityStat, ceiling: list[SelectivityStat]) -> tuple[str, str]:
    lifts = [c.lift for c in ceiling]
    if transfer.lift is None:
        return "yetersiz veri", "bağımsız kümede kapıdan bayrak geçmedi"
    ceil_txt = ("—" if any(x is None for x in lifts)
                else f"{lifts[0]:.2f}/{lifts[1]:.2f}")
    if transfer.lift >= SHAPE_MIN_LIFT:
        return ("taşınıyor",
                f"dondurulmuş önsel bağımsız maçlarda tabanın {transfer.lift:.2f} katı "
                f"isabetli (kabul eşiği {SHAPE_MIN_LIFT}); küme içi tavan {ceil_txt}")
    return ("taşınmıyor",
            f"kaldırma {transfer.lift:.2f} < {SHAPE_MIN_LIFT}; küme içi tavan {ceil_txt} "
            "— önsel külliyata özgü ya da bu kümede öğrenilecek yapı yok")


def main() -> int:
    p = argparse.ArgumentParser(description="Şekil önselinin bağımsız maçlarda doğrulaması")
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--team", type=int, default=217)
    p.add_argument("--events-dir", type=Path, required=True,
                   help="külliyatın ham StatsBomb olayları (önsel buradan öğrenilir)")
    p.add_argument("--independent-dir", type=Path, required=True,
                   help="külliyatta BULUNMAYAN maçların ham olayları")
    p.add_argument("--label", default="bağımsız küme",
                   help="rapora yazılacak küme adı (ör. 'La Liga 2015/16')")
    p.add_argument("--window", type=float, default=DEFAULT_WINDOW_MIN)
    p.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    corpus_rows = collect_corpus_ticks(args.events_dir, args.tenant, args.team, args.window)
    if not corpus_rows:
        print("külliyat tiki yok — `decision_corpus seed`/`score` ve --events-dir gerekli")
        return 1
    corpus_ids = {int(r["match"]) for r in corpus_rows}
    ind_ids = sorted(int(f.stem) for f in args.independent_dir.glob("*.json")
                     if f.stem.isdigit())
    overlap = sorted(corpus_ids & set(ind_ids))
    if overlap:
        print(f"BAĞIMSIZ DEĞİL: {len(overlap)} maç külliyatta da var ({overlap[:5]}…)")
        return 1
    if not ind_ids:
        print("bağımsız klasörde maç yok")
        return 1

    # 1) Karnenin kendi önseli: külliyat MOTOR TİKLERİNDEN, tam olarak
    #    measure_shape_selectivity'deki gibi öğrenilir.
    corpus_states = shape_states(corpus_rows)
    karne_prior = fit_shape_prior(corpus_states)
    # 2) Aynı ızgarayla külliyattan öğrenilen önsel (tik dağılımı kontrolü).
    corpus_grid_rows = _grid_ticks(args.events_dir, sorted(corpus_ids), args.window)
    grid_prior = fit_shape_prior(_prior_only_states(corpus_grid_rows),
                                 support_thresholds=PRIOR_ONLY_SUPPORT)

    ind_rows = _grid_ticks(args.independent_dir, ind_ids, args.window)
    if not ind_rows:
        print("bağımsız maçlardan tik çıkmadı")
        return 1
    ind_states = _prior_only_states(ind_rows)
    ind_matches = len({r["match"] for r in ind_rows})

    transfer = _apply(karne_prior, ind_states)
    grid_transfer = _apply(grid_prior, ind_states)
    ceil_a, ceil_b = _ceiling(ind_states)
    # Taban referansı: hep-evet. Kaldırması tanım gereği 1.0 — kapının kaldırması
    # bunun üstünde değilse bayrak hiçbir şey bilmiyordur.
    always = selectivity([TickObservation(s.match_external_id, s.minute, True, s.coach_acted)
                          for s in ind_states])
    verdict, note = _verdict(transfer, [ceil_a, ceil_b])

    band: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in ind_rows:
        key = r["score_state"]
        band[key][0] += int(r["coach_shift"])
        band[key][1] += 1

    doc = {
        "olcum": "Şekil önselinin bağımsız maçlarda doğrulaması",
        "kulliyat": {
            "tenant": args.tenant, "takim_external_id": args.team,
            "mac": len(corpus_ids), "motor_tiki": len(corpus_rows),
            "onsel_esigi": karne_prior.threshold,
            "destek_esigi": karne_prior.support_threshold,
            "not": "destek eşiği motor tikine bağlıdır; bu sınava girmez",
        },
        "bagimsiz_kume": {
            "ad": args.label, "mac": ind_matches, "tik": len(ind_rows),
            "izgara_dk": list(GRID_MINUTES), "pencere_dk": args.window,
            "taban_orani": transfer.base_rate,
            "kulliyatla_kesisim": 0,
            "girdi_sha256": hashlib.sha256(
                json.dumps(ind_rows, sort_keys=True).encode("utf-8")).hexdigest(),
        },
        "tasima": {
            "karne_onseli_dondurulmus": _sel(transfer),
            "izgara_onseli_dondurulmus": _sel(grid_transfer),
            "kume_ici_tavan_A": _sel(ceil_a),
            "kume_ici_tavan_B": _sel(ceil_b),
            "hep_evet": _sel(always),
            "hukum": verdict, "not": note,
        },
        "permutasyon_sinavi": _permutation(karne_prior, ind_states,
                                           args.permutations, args.seed),
        "skor_durumuna_gore_taban": {k: {"oran": round(a / n, 3), "n": n}
                                     for k, (a, n) in sorted(band.items())},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{args.label}: {ind_matches} bağımsız maç · {len(ind_rows)} ızgara tiki · "
          f"taban {transfer.base_rate}")
    print(f"  hep-evet            : kaldırma {always.lift} (tanım gereği 1.0)")
    print(f"  KARNE önseli (dondurulmuş): bayrak {transfer.flag_rate} · "
          f"isabet {transfer.precision} · kaldırma {transfer.lift} · "
          f"yakalama {transfer.recall}")
    print(f"  ızgara önseli (dondurulmuş): bayrak {grid_transfer.flag_rate} · "
          f"kaldırma {grid_transfer.lift}")
    print(f"  küme içi tavan (ayrık yarı): kaldırma {ceil_a.lift}/{ceil_b.lift} · "
          f"bayrak {ceil_a.flag_rate}/{ceil_b.flag_rate}")
    print(f"  hüküm: {verdict} — {note}")
    print(f"  permütasyon p={doc['permutasyon_sinavi']['p']} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
