"""Elit "kim çıkar" önseli külliyat DIŞINDA da tutuyor mu — BAĞIMSIZ maçlarda ölç.

## Neden bu script var

`ELITE_OFF_PRIOR` (`app/engine/live_sub_recommendation`) karnede taban çizgisini
geçen TEK boyutun çekirdeğidir ve şekil kapısından farklı olarak **canlı öneri
motorunda kullanılır** (`ROLE_PRIOR_WEIGHT = 0.6`). Kaynağı tek kulübün üç
sezonudur: Barcelona, La Liga 2018–21, 331 taktik değişiklik. O tablo bugüne
kadar hiç külliyat dışında sınanmadı.

Soru basit: bu sekiz sayı Barcelona'nın alışkanlığı mı, yoksa futbolun genel
yapısı mı? Cevap ikincisiyse tablo canlı motorda durmayı hak ediyor; birincisiyse
başka lig/takımda yanlış oyuncuyu öne çıkarıyor demektir.

## Dört sütun

1. **Donmuş üretim tablosu** — `ELITE_OFF_PRIOR` olduğu gibi bağımsız maçlara
   uygulanır. Asıl soru budur: üretimdeki nesne taşınıyor mu?
2. **Külliyattan yeniden fit** — aynı külliyat maçlarından `fit_who_prior` ile
   kurulan tablo. Donmuş tablonun beyan edilen kaynağıyla tutarlılığını gösterir.
3. **Küme içi tavan** — bağımsız kümenin kendi ayrık yarısında öğrenilen tablo.
   Taşıma bunun altındaysa önsel külliyata özgüdür.
4. **Rastgele sahadaki** — analitik taban: sahada n oyuncu varsa k/n.

Ölçü `who_agreement` ile aynıdır (isabet@1, isabet@3, rastgele taban), yani
karnenin kullandığı cetvelin ta kendisi.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.validate_who_prior
        --events-dir C:\\sb --independent-dir C:\\sb-ind
        --out docs/measurements/karne-kim-bagimsiz.json

`--events-dir` külliyatın ham olayları, `--independent-dir` külliyatta
BULUNMAYAN maçların ham olaylarıdır. Kesişim varsa script durur.
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
    CoachMove,
    appearances_from_events_json,
    coach_moves_from_events_json,
    lineup_positions_from_events_json,
    position_group,
)
from app.engine.coach_benchmark import (
    WHO_TOP_K,
    WhoCandidate,
    WhoPrior,
    WhoStat,
    WhoState,
    fit_who_prior,
    who_prior_agreement,
)
from app.engine.live_sub_recommendation import ELITE_OFF_PRIOR

DEFAULT_PERMUTATIONS = 400
# position_group() çıktısı → ELITE_OFF_PRIOR'ın tek harfli anahtarı.
# "UNK" → "M": canlı motordaki `elite_off_prior` da bilinmeyeni orta saha sayar,
# bu sınav üretimdeki davranışı değiştirmeden ölçer.
GROUP_TO_LETTER = {"GK": "G", "DEF": "D", "MID": "M", "FWD": "F", "UNK": "M"}


def _positions_with_inheritance(moves: list[CoachMove], base: dict[int, int]) -> dict[int, int]:
    """Değişiklikle giren oyuncu, çıkanın mevkisini devralır (diziliş olayı yoksa)."""
    pos = dict(base)
    for mv in sorted(moves, key=lambda x: x.minute):
        if (mv.kind == "substitution" and mv.player_on is not None
                and mv.player_off is not None and mv.player_on not in pos
                and mv.player_off in pos):
            pos[mv.player_on] = pos[mv.player_off]
    return pos


def who_states_from_events(
    events_json: list[dict[str, Any]], match_id: int, *, team: int | None = None,
) -> list[WhoState]:
    """Her gerçek TAKTİK değişiklik için: kim çıktı, o an sahada kimler vardı?

    `coach_iq` aynı yapıyı kurar ama yalnız motorun önceden konuştuğu hamleler
    için ve tek takım için — orası motor/antrenör kıyasıdır. Burada motor yoktur:
    bağımsız maçlarda karar külliyatı üretilmemiştir, bu yüzden filtre de yoktur
    ve iki takım birden alınır. İki kurulumu birleştirmek karnenin ölçülmüş
    sayılarını değiştirirdi; kasıtlı olarak ayrı tutuldu.
    """
    moves = coach_moves_from_events_json(events_json)
    apps = appearances_from_events_json(events_json)
    pos = _positions_with_inheritance(moves, lineup_positions_from_events_json(events_json))
    out: list[WhoState] = []
    for mv in moves:
        if (mv.kind != "substitution" or not mv.tactical or mv.player_off is None
                or (team is not None and mv.team_external_id != team)):
            continue
        mine = [a for a in apps if a["team_external_id"] == mv.team_external_id]
        # Bu dakikada SAHAYA GİREN aday değildir: aynı anda çıkamaz. Aynı dakikada
        # çıkan bir başka oyuncu ise adaydır (o an hâlâ sahadaydı).
        on_pitch = [int(a["player_external_id"]) for a in mine
                    if a["start_minute"] < mv.minute
                    and (a["end_minute"] is None or a["end_minute"] >= mv.minute)]
        if int(mv.player_off) not in on_pitch:
            continue          # kadro kaydı eksik: uydurma aday listesi kurulmaz
        starters = {int(a["player_external_id"]) for a in mine if a["start_minute"] == 0.0}
        out.append(WhoState(match_id, int(mv.player_off), tuple(
            WhoCandidate(pid, position_group(pos.get(pid, 0)), pid in starters)
            for pid in on_pitch)))
    return out


def _collect(events_dir: Path, match_ids: list[int], *, team: int | None) -> list[WhoState]:
    states: list[WhoState] = []
    for mid in match_ids:
        p = events_dir / f"{mid}.json"
        if not p.is_file():
            continue
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        states.extend(who_states_from_events(ev, mid, team=team))
    return states


def _frozen_prior() -> WhoPrior:
    """Üretimdeki `ELITE_OFF_PRIOR`, `WhoPrior` arayüzüne çevrilmiş hâli.

    Anahtar dönüşümü dışında hiçbir sayı değişmez; sınanan nesne canlı motorun
    kullandığı tablonun kendisidir.
    """
    table = {(group, starter): ELITE_OFF_PRIOR[(letter, starter)]
             for group, letter in GROUP_TO_LETTER.items()
             for starter in (True, False)}
    return WhoPrior(table=table, fitted_on=0)


def _rank(prior: WhoPrior, states: list[WhoState], *, k: int) -> WhoStat:
    """Önselin isabeti — BERABERLİK TARAFSIZ.

    Önce `apply_who_prior` + `who_agreement` kullanılıyordu; o yol kademe içini
    `player_id`'ye göre sıralıyor ve bu veri kümesinde kimlik sırası bilgi
    taşıdığı için külliyat isabet@1'ini 0.125'ten 0.181'e çıkarıyordu. Ölçüm
    artık kademeleri sayıyor (`who_prior_agreement`).
    """
    return who_prior_agreement(prior, states, k=k)


def _ceiling(states: list[WhoState], *, k: int) -> tuple[WhoStat, WhoStat]:
    ids = sorted({s.match_external_id for s in states})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    a = [s for s in states if s.match_external_id in a_ids]
    b = [s for s in states if s.match_external_id not in a_ids]
    return _rank(fit_who_prior(b), a, k=k), _rank(fit_who_prior(a), b, k=k)


def _permutation(
    prior: WhoPrior, states: list[WhoState], trials: int, seed: int, *, k: int,
) -> dict[str, Any]:
    """Her hamlede "çıkan oyuncu"yu sahadakilerden rastgele seç; donmuş tablo
    yine de bu kadar isabet eder mi? p = (yakalama + 1) / (deneme + 1)."""
    real = _rank(prior, states, k=k).hit_at_k
    if real is None:
        return {"deneme": 0, "istenen_deneme": trials, "seed": seed,
                "gercek_isabet_at_k": None, "karistirilmisin_yakalama_sayisi": 0,
                "p": None, "not": "örnek yok — hüküm verilmedi"}
    rng = random.Random(seed)
    hits = 0
    for _ in range(trials):
        shuffled = [WhoState(s.match_external_id,
                             rng.choice([c.player_id for c in s.candidates]), s.candidates)
                    for s in states]
        got = _rank(prior, shuffled, k=k).hit_at_k
        if (got or 0.0) >= real:
            hits += 1
    return {"deneme": trials, "seed": seed, "gercek_isabet_at_k": real,
            "karistirilmisin_yakalama_sayisi": hits, "p": (hits + 1) / (trials + 1),
            "not": "çıkan oyuncu sahadakilerden rastgele seçildi, tablo dondurulmuş; "
                   "p = (yakalama + 1) / (deneme + 1)"}


def _stat(x: WhoStat) -> dict[str, Any]:
    return dict(n=x.n, hit_at_1=x.hit_at_1, hit_at_k=x.hit_at_k,
                baseline_at_1=x.baseline_at_1, baseline_at_k=x.baseline_at_k,
                verdict=x.verdict, note=x.note)


def main() -> int:
    p = argparse.ArgumentParser(description="Elit 'kim çıkar' önselinin bağımsız doğrulaması")
    p.add_argument("--team", type=int, default=217, help="külliyat takımı")
    p.add_argument("--events-dir", type=Path, required=True)
    p.add_argument("--independent-dir", type=Path, required=True)
    p.add_argument("--label", default="bağımsız küme")
    p.add_argument("--k", type=int, default=WHO_TOP_K)
    p.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    corpus_ids = sorted(int(f.stem) for f in args.events_dir.glob("*.json") if f.stem.isdigit())
    ind_ids = sorted(int(f.stem) for f in args.independent_dir.glob("*.json") if f.stem.isdigit())
    overlap = sorted(set(corpus_ids) & set(ind_ids))
    if overlap:
        print(f"BAĞIMSIZ DEĞİL: {len(overlap)} maç külliyatta da var ({overlap[:5]}…)")
        return 1
    if not corpus_ids or not ind_ids:
        print("külliyat ya da bağımsız klasör boş")
        return 1

    corpus_states = _collect(args.events_dir, corpus_ids, team=args.team)
    ind_states = _collect(args.independent_dir, ind_ids, team=None)
    if not corpus_states or not ind_states:
        print("değişiklik örneği çıkmadı")
        return 1

    frozen = _frozen_prior()
    refit = fit_who_prior(corpus_states)
    transfer = _rank(frozen, ind_states, k=args.k)
    refit_transfer = _rank(refit, ind_states, k=args.k)
    ceil_a, ceil_b = _ceiling(ind_states, k=args.k)
    corpus_self = _rank(frozen, corpus_states, k=args.k)

    groups: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for s in ind_states:
        for c in s.candidates:
            key = f"{c.group}/{'ilk11' if c.starter else 'giren'}"
            groups[key][1] += 1
            if c.player_id == s.player_off:
                groups[key][0] += 1

    doc = {
        "olcum": "Elit 'kim çıkar' önselinin bağımsız maçlarda doğrulaması",
        "sinanan_nesne": {
            "ad": "ELITE_OFF_PRIOR (app/engine/live_sub_recommendation)",
            "canli_motorda_kullaniliyor": True,
            "tablo": {f"{g}/{'ilk11' if s else 'giren'}": v
                      for (g, s), v in sorted(frozen.table.items())},
            "not": "position_group çıktısı tek harfe eşlenir; UNK→M, canlı "
                   "motordaki elite_off_prior ile aynı",
        },
        "kulliyat": {"takim_external_id": args.team, "mac": len(corpus_ids),
                     "taktik_degisiklik": len(corpus_states),
                     "donmus_tablo_isabet_at_k": corpus_self.hit_at_k,
                     "yeniden_fit_tablo": {f"{g}/{'ilk11' if s else 'giren'}": round(v, 4)
                                           for (g, s), v in sorted(refit.table.items())}},
        "bagimsiz_kume": {
            "ad": args.label, "mac": len({s.match_external_id for s in ind_states}),
            "taktik_degisiklik": len(ind_states), "k": args.k,
            "kulliyatla_kesisim": 0,
            "girdi_sha256": hashlib.sha256(json.dumps(
                [[s.match_external_id, s.player_off,
                  [[c.player_id, c.group, c.starter] for c in s.candidates]]
                 for s in ind_states], sort_keys=True).encode("utf-8")).hexdigest(),
        },
        "tasima": {
            "donmus_uretim_tablosu": _stat(transfer),
            "kulliyattan_yeniden_fit": _stat(refit_transfer),
            "kume_ici_tavan_A": _stat(ceil_a),
            "kume_ici_tavan_B": _stat(ceil_b),
        },
        "permutasyon_sinavi": _permutation(frozen, ind_states, args.permutations,
                                           args.seed, k=args.k),
        "bagimsiz_kumede_grup_oranlari": {
            k: {"cikma_orani": round(a / n, 4), "aday_gozlemi": n}
            for k, (a, n) in sorted(groups.items())},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{args.label}: {doc['bagimsiz_kume']['mac']} bağımsız maç · "
          f"{len(ind_states)} taktik değişiklik (külliyat: {len(corpus_states)})")
    print(f"  rastgele sahadaki   : isabet@{args.k} {transfer.baseline_at_k} · "
          f"@1 {transfer.baseline_at_1}")
    print(f"  DONMUŞ üretim tablosu: isabet@{args.k} {transfer.hit_at_k} · "
          f"@1 {transfer.hit_at_1} — {transfer.verdict}")
    print(f"  külliyattan yeniden fit: isabet@{args.k} {refit_transfer.hit_at_k} · "
          f"@1 {refit_transfer.hit_at_1}")
    print(f"  küme içi tavan      : isabet@{args.k} {ceil_a.hit_at_k}/{ceil_b.hit_at_k}")
    print(f"  külliyatın kendisinde: isabet@{args.k} {corpus_self.hit_at_k}")
    print(f"  permütasyon p={doc['permutasyon_sinavi']['p']} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
