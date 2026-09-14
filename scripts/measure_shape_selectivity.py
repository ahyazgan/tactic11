"""Karne şekil seçiciliği: "şekil ayarla" önerisi ne kadar seçici — ÖLÇ.

## Neden bu script var

Karnedeki diziliş satırı motoru F1 ile tartıyordu ve motor saatin altında
çıkıyordu. Sorun motorun kötülüğünden önce CETVELİN kendisi: hedef nadir
(taban ~%21), F1 ise nadir hedefte bol bayrağı ödüllendirir — hep-evet demek
motorun skorundan yüksek F1 verir. Seçicilik sorusu "kaç bayrakla ne kadar
isabet" sorusudur; cetveli kaldırma (precision / taban oranı).

Bu script iki şeyi ayrı ayrı ölçer ve ayrık yarılarda doğrular:
1. **Diziliş değişimi önseli** — (dakika bandı × skor durumu × yapılan
   değişiklik) hücresinden P(antrenör dizilişi değiştirir).
2. **Sinyal eşikleri** — motorun ham bayrağı ve destekleyici sinyal sayısı.

Eşiklerin ikisi de EĞİTİM yarısında seçilir, ölçüm ÖTEKİ yarıda yapılır.
Ayrıca permütasyon sınavı: etiketler karıştırılıp bütün kapı yeniden kurulur;
gerçek isabet karıştırılmışın dağılımından ayrılıyor mu?

## Kullanım

    venv\\Scripts\\python.exe -m scripts.measure_shape_selectivity
        --events-dir C:\\sb --out docs/measurements/karne-sekil-seciciligi.json

Önkoşul: `decision_corpus seed` + `score` (kararlar ve `context_json` gerekir)
ve ham StatsBomb `events/<match_id>.json` dosyaları (diziliş değişimi yalnız
ham olayda var; DB olay tablosunda pas/şut/müdahale tutulur).
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

from sqlalchemy import select

from app.data.sources.statsbomb_open import coach_moves_from_events_json
from app.db import models
from app.db.session import SessionLocal
from app.engine.coach_benchmark import (
    SHAPE_MIN_FLAG_RATE,
    SHAPE_MIN_LIFT,
    SelectivityStat,
    ShapeState,
    TickObservation,
    apply_shape_gate,
    fit_shape_prior,
    selectivity,
    split_half_agreement,
    split_half_shape_gate,
)
from app.engine.decision_baseline import score_state
from app.sports import football

DEFAULT_WINDOW_MIN = 12.0
DEFAULT_PERMUTATIONS = 400
# Motorun sakladığı sürekli sayılar: hangisi diziliş değişimini ayırıyor?
AUC_FIELDS = ("minute", "priority", "urgency", "confidence", "magnitude",
              "corroboration", "quality", "sample", "score", "n_support", "subs_used")


def _collect(events_dir: Path, tenant: str, team: int, window: float) -> list[dict[str, Any]]:
    """Her motor tiki için durum + o anki motor sayıları + gerçek diziliş değişimi."""
    with SessionLocal() as s:
        s.info["tenant_id"] = tenant
        decisions = [d for d in s.execute(select(models.Decision).where(
            models.Decision.sport == football.SPORT_NAME,
            models.Decision.tenant_id == tenant,
            models.Decision.team_external_id == team,
        )).scalars() if d.context_json]
        mids = sorted({d.match_external_id for d in decisions})
        goals: dict[int, list[tuple[float, int]]] = defaultdict(list)
        for minute, team_id, mid in s.execute(select(
            models.EventRow.minute, models.EventRow.team_external_id,
            models.EventRow.match_external_id,
        ).where(
            models.EventRow.sport == football.SPORT_NAME,
            models.EventRow.is_goal.is_(True),
            models.EventRow.match_external_id.in_(mids),
        )):
            goals[mid].append((float(minute), int(team_id)))

    shifts: dict[int, list[float]] = {}
    subs: dict[int, list[float]] = {}
    for mid in mids:
        p = events_dir / f"{mid}.json"
        if not p.is_file():
            continue
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        moves = coach_moves_from_events_json(ev)
        shifts[mid] = sorted({m.minute for m in moves if m.team_external_id == team
                              and m.kind == "tactical_shift"})
        subs[mid] = sorted({m.minute for m in moves if m.team_external_id == team
                            and m.kind == "substitution"})

    rows: list[dict[str, Any]] = []
    for d in decisions:
        mid = d.match_external_id
        if mid not in shifts:
            continue
        try:
            ctx = json.loads(d.context_json or "{}")
        except (ValueError, TypeError):
            ctx = {}
        if not isinstance(ctx, dict):
            ctx = {}
        mine = sum(1 for g, t in goals.get(mid, []) if g < d.minute and t == team)
        theirs = sum(1 for g, t in goals.get(mid, []) if g < d.minute and t != team)
        terms = ctx.get("confidence_terms") or {}
        rows.append(dict(
            match=mid, minute=d.minute, theme=ctx.get("theme"),
            priority=ctx.get("priority"), urgency=ctx.get("urgency"),
            confidence=d.confidence, magnitude=terms.get("magnitude"),
            corroboration=terms.get("corroboration"), quality=terms.get("quality"),
            sample=terms.get("sample"), score=terms.get("score"),
            n_support=len(ctx.get("supporting_keys") or []),
            score_state=score_state(mine, theirs),
            subs_used=sum(1 for c in subs[mid] if c <= d.minute),
            coach_shift=any(d.minute < c <= d.minute + window for c in shifts[mid]),
        ))
    return rows


def _states(rows: list[dict[str, Any]]) -> list[ShapeState]:
    return [ShapeState(
        r["match"], r["minute"], score_state=r["score_state"], subs_used=r["subs_used"],
        engine_flag=r["theme"] == "adjust_shape", support_count=r["n_support"],
        coach_acted=r["coach_shift"],
    ) for r in rows]


def _halves(rows: list[ShapeState]) -> tuple[list[ShapeState], list[ShapeState]]:
    ids = sorted({s.match_external_id for s in rows})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    return ([s for s in rows if s.match_external_id in a_ids],
            [s for s in rows if s.match_external_id not in a_ids])


def _gated_precision(rows: list[ShapeState]) -> list[float | None]:
    """Kapı ÖTEKİ yarıda kurulur; iki yarının precision'ı."""
    a, b = _halves(rows)
    return [selectivity(apply_shape_gate(fit_shape_prior(tr), te)).precision
            for tr, te in ((b, a), (a, b))]


def _permutation(rows: list[ShapeState], trials: int, seed: int) -> dict[str, Any]:
    """Etiketleri karıştırıp bütün kapıyı yeniden kur — gerçek ayrılıyor mu?"""
    real = _gated_precision(rows)
    rng = random.Random(seed)
    hits = [0, 0]
    for _ in range(trials):
        labels = [s.coach_acted for s in rows]
        rng.shuffle(labels)
        got = _gated_precision([ShapeState(
            s.match_external_id, s.minute, s.score_state, s.subs_used,
            s.engine_flag, s.support_count, lab,
        ) for s, lab in zip(rows, labels, strict=True)])
        for i in (0, 1):
            if (got[i] or 0.0) >= (real[i] or 0.0):
                hits[i] += 1
    return {"deneme": trials, "seed": seed, "gercek_precision": real,
            "karistirilmisin_yakalama_sayisi": hits,
            "p": [round(h / trials, 4) for h in hits],
            "not": "etiketler karıştırılıp kapı sıfırdan kuruldu; p = karıştırılmış "
                   "verinin gerçeği yakalama payı"}


def _auc(pairs: list[tuple[float, bool]]) -> float | None:
    """Mann-Whitney U tabanlı AUC; beraberliklere ortalama sıra."""
    pos = [v for v, y in pairs if y]
    neg = [v for v, y in pairs if not y]
    if not pos or not neg:
        return None
    srt = sorted(v for v, _ in pairs)
    rank: dict[float, float] = {}
    i = 0
    while i < len(srt):
        j = i
        while j + 1 < len(srt) and srt[j + 1] == srt[i]:
            j += 1
        rank[srt[i]] = (i + j) / 2 + 1
        i = j + 1
    u = sum(rank[v] for v in pos) - len(pos) * (len(pos) + 1) / 2
    return round(u / (len(pos) * len(neg)), 3)


def _sel(x: SelectivityStat) -> dict[str, Any]:
    return dict(n=x.n, flagged=x.flagged, flag_rate=x.flag_rate, base_rate=x.base_rate,
                precision=x.precision, recall=x.recall, f1=x.f1, lift=x.lift)


def main() -> int:
    p = argparse.ArgumentParser(description="Karne şekil önerisi seçiciliği")
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--team", type=int, default=217)
    p.add_argument("--events-dir", type=Path, required=True,
                   help="ham StatsBomb events/<id>.json klasörü")
    p.add_argument("--window", type=float, default=DEFAULT_WINDOW_MIN)
    p.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    rows = _collect(args.events_dir, args.tenant, args.team, args.window)
    if not rows:
        print("tik yok — `decision_corpus seed`/`score` ve --events-dir gerekli")
        return 1
    st = _states(rows)
    gate = split_half_shape_gate(st)
    raw_obs = [TickObservation(s.match_external_id, s.minute, s.engine_flag, s.coach_acted)
               for s in st]
    f1_row = split_half_agreement(raw_obs)
    always = selectivity([TickObservation(s.match_external_id, s.minute, True, s.coach_acted)
                          for s in st])

    theme: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        key = r["theme"] or "(tema yok)"
        theme[key][0] += int(r["coach_shift"])
        theme[key][1] += 1

    doc = {
        "olcum": "Karne şekil değişikliği seçiciliği",
        "kaynak": {
            "tenant": args.tenant, "takim_external_id": args.team,
            "mac": len({r["match"] for r in rows}), "tik": len(rows),
            "pencere_dk": args.window,
            "hedef": "StatsBomb Tactical Shift, (dakika, dakika+pencere] aralığı",
            "girdi_sha256": hashlib.sha256(
                json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest(),
        },
        "eski_cetvel_F1": {
            "motor_f1": f1_row.engine_f1, "saat_f1": f1_row.baseline_f1,
            "hukum": f1_row.verdict, "hep_evet_f1": always.f1,
            "not": "hep-evet F1'i motorunkinden yüksek olabilir: nadir hedefte F1 "
                   "seçicilik cetveli değildir",
        },
        "yeni_cetvel_secicilik": {
            "esik_secimi": f"eğitim yarısında bayrak bütçesi ≥{SHAPE_MIN_FLAG_RATE} "
                           "olan adaylar arasında en yüksek precision",
            "kabul_esigi_lift": SHAPE_MIN_LIFT,
            "once_ham_bayrak": {"A": _sel(gate.raw_a), "B": _sel(gate.raw_b)},
            "sonra_kapili_bayrak": {"A": _sel(gate.gated_a), "B": _sel(gate.gated_b)},
            "ogrenilen_esikler": {
                "A": {"onsel": gate.prior_for_a.threshold,
                      "destek": gate.prior_for_a.support_threshold,
                      "ogrenildigi_tik": gate.prior_for_a.fitted_on},
                "B": {"onsel": gate.prior_for_b.threshold,
                      "destek": gate.prior_for_b.support_threshold,
                      "ogrenildigi_tik": gate.prior_for_b.fitted_on},
            },
            "hukum": gate.verdict, "not": gate.note,
        },
        "permutasyon_sinavi": _permutation(st, args.permutations, args.seed),
        "sinyal_auc_sekil": {f: _auc([(float(r[f]), bool(r["coach_shift"]))
                                      for r in rows if r.get(f) is not None])
                             for f in AUC_FIELDS},
        "tema_sekil_orani": {k: {"oran": round(a / n, 3), "n": n}
                             for k, (a, n) in sorted(theme.items(), key=lambda x: -x[1][1])},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(rows)} tik · {doc['kaynak']['mac']} maç → {args.out}")
    print(f"  ham bayrak   : oran {gate.raw_a.flag_rate}/{gate.raw_b.flag_rate} · "
          f"kaldırma {gate.raw_a.lift}/{gate.raw_b.lift}")
    print(f"  kapılı bayrak: oran {gate.gated_a.flag_rate}/{gate.gated_b.flag_rate} · "
          f"kaldırma {gate.gated_a.lift}/{gate.gated_b.lift}")
    print(f"  hüküm: {gate.verdict} · permütasyon p={doc['permutasyon_sinavi']['p']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
