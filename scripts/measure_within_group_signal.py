"""Grup İÇİNDE kimin çıkacağını bilen bir sinyal var mı? — ÖLÇ (beklenti: yok).

## Neden bu script var

Karne şunu ölçtü: motor doğru GRUBU buluyor (isabet@3 %47 vs rastgele %28),
doğru KİŞİYİ bulmuyor (%11 vs %9 — `docs/KARNE-SIRALAMA.md`). O ölçüm yorgunluğu
BİLEŞİK olarak sınamıştı; bileşik içinde bir bileşenin maskelenmiş olma ihtimali
açıktı.

Bu script soruyu daraltır: **aynı mevki grubundaki oyuncular arasında**, hangi
tek sinyal antrenörün çıkardığı kişiyi bulur? Grup önselin zaten bildiği şeydir;
geriye kalan tek soru budur.

## Üç koruma

1. **Grup içi.** Adaylar yalnız çıkan oyuncuyla AYNI mevki grubundakiler. Böylece
   önselin bildiği bilgi tekrar ölçülmez; sınanan şey saf grup-içi ayrımdır.
2. **Seçim ayrık yarıda.** Altı sinyal × iki yön = on iki aday var. Hepsini aynı
   veride deneyip en iyisini raporlamak çoklu-karşılaştırma yanılsamasıdır —
   ilk denemede tam olarak bu oldu: ham tabloda iki sinyal yön gösteriyordu,
   ayrık yarıda ikisi de kayboldu. Yarılar MAÇ bazında ayrılır.
3. **Beraberlik tarafsız.** Eşit değerli adaylar ilk sırayı paylaşır (t aday →
   1/t). Sabit bir sıralama kuralı (kimlik, liste sırası) beceri gibi görünür.

## Ters yön neden aday listesinde

Her sinyal iki yönde de denenir. Bir sinyal gerçekten bilgi taşıyorsa doğru yön
ters yönü açık farkla geçmelidir; ikisi eşitse sinyal boştur. Yön aday olarak
girdiği için seçim maliyeti de ayrık yarıya yansır.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.measure_within_group_signal
        --events-dir C:\\sb --out docs/measurements/within-group-signal.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.data.loaders.events import load_match_events
from app.data.sources.statsbomb_open import coach_moves_from_events_json
from app.db import models
from app.db.session import SessionLocal
from app.sports import football
from scripts.validate_who_prior import who_states_from_events

DEFAULT_PERMUTATIONS = 400
# "Son dönem" ve "erken dönem" pencereleri: düşüş sinyalleri bu ikisini kıyaslar.
RECENT_MIN, EARLY_EDGE_MIN = 10.0, 20.0
MIN_GROUP = 2          # grup içi soru ancak iki kişiyle anlamlı
SIGNALS = ("pas_isabeti_son10", "pas_isabeti_dususu", "dokunus_son10",
           "dokunus_dususu", "toplam_pas", "mudahale_son10")
DIRECTIONS = (1, -1)


@dataclass(frozen=True)
class Case:
    """Bir gerçek değişiklik: kim çıktı, grup arkadaşları kimdi, sinyalleri neydi."""

    match_external_id: int
    player_off: int
    group: str
    peers: tuple[int, ...]
    feats: dict[int, dict[str, float | None]]


def _features(
    pid: int, minute: float, passes: Sequence[Any], defs: Sequence[Any],
    carries: Sequence[Any],
) -> dict[str, float | None]:
    ps = [x for x in passes if x.player_external_id == pid and x.minute < minute]
    ds = [x for x in defs if x.player_external_id == pid and x.minute < minute]
    cs = [x for x in carries if x.player_external_id == pid and x.minute < minute]
    recent_p = [x for x in ps if x.minute >= minute - RECENT_MIN]
    early_p = [x for x in ps if x.minute < minute - EARLY_EDGE_MIN]
    recent_touch = (len(recent_p)
                    + len([x for x in ds if x.minute >= minute - RECENT_MIN])
                    + len([x for x in cs if x.minute >= minute - RECENT_MIN]))
    early_touch = (len(early_p)
                   + len([x for x in ds if x.minute < minute - EARLY_EDGE_MIN])
                   + len([x for x in cs if x.minute < minute - EARLY_EDGE_MIN]))
    comp_recent = (sum(1 for x in recent_p if x.completed) / len(recent_p)) if recent_p else None
    comp_early = (sum(1 for x in early_p if x.completed) / len(early_p)) if early_p else None
    per_min_early = early_touch / max(1.0, minute - EARLY_EDGE_MIN)
    return {
        "pas_isabeti_son10": comp_recent,
        "pas_isabeti_dususu": (None if comp_recent is None or comp_early is None
                               else comp_early - comp_recent),
        "dokunus_son10": float(recent_touch),
        "dokunus_dususu": per_min_early * RECENT_MIN - recent_touch,
        "toplam_pas": float(len(ps)),
        "mudahale_son10": float(len([x for x in ds if x.minute >= minute - RECENT_MIN])),
    }


def collect_cases(events_dir: Path, tenant: str, team: int) -> list[Case]:
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
            minute_of = {mv.player_off: mv.minute for mv in coach_moves_from_events_json(ev)
                         if mv.kind == "substitution" and mv.tactical
                         and mv.team_external_id == team and mv.player_off is not None}
            for st in states:
                minute = minute_of.get(st.player_off)
                if minute is None:
                    continue
                group = next((c.group for c in st.candidates
                              if c.player_id == st.player_off), None)
                peers = [c.player_id for c in st.candidates if c.group == group]
                if group is None or len(peers) < MIN_GROUP:
                    continue
                out.append(Case(
                    mid, st.player_off, group, tuple(peers),
                    {pid: _features(pid, minute, loaded.passes, loaded.defensive_actions,
                                    loaded.carries) for pid in peers},
                ))
    return out


def expected_hit(case: Case, signal: str, direction: int) -> float | None:
    """Beraberlik-tarafsız isabet@1: eşit değerli t aday ilk sırayı paylaşır → 1/t."""
    vals = {p: case.feats[p].get(signal) for p in case.peers}
    usable = {p: v for p, v in vals.items() if v is not None}
    if case.player_off not in usable or len(usable) < MIN_GROUP:
        return None
    best = max(direction * v for v in usable.values())
    tied = [p for p, v in usable.items() if direction * v == best]
    return (1.0 / len(tied)) if case.player_off in tied else 0.0


def _mean_hit(cases: Sequence[Case], signal: str, direction: int) -> tuple[float | None, int]:
    vals = [h for c in cases if (h := expected_hit(c, signal, direction)) is not None]
    return (statistics.mean(vals), len(vals)) if vals else (None, 0)


def _random_baseline(cases: Sequence[Case]) -> float:
    return statistics.mean(1.0 / len(c.peers) for c in cases) if cases else 0.0


def _halves(cases: Sequence[Case]) -> tuple[list[Case], list[Case]]:
    """MAÇ bazında ayrık yarı — aynı maçın değişiklikleri bölünmez."""
    ids = sorted({c.match_external_id for c in cases})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    return ([c for c in cases if c.match_external_id in a_ids],
            [c for c in cases if c.match_external_id not in a_ids])


def _split_half(cases: Sequence[Case]) -> dict[str, Any]:
    a, b = _halves(cases)
    rows: list[dict[str, Any]] = []
    for train, test, label in ((a, b, "A'da seç → B'de ölç"), (b, a, "B'de seç → A'da ölç")):
        best = max(((s, d) for s in SIGNALS for d in DIRECTIONS),
                   key=lambda sd: _mean_hit(train, *sd)[0] or 0.0)
        value, n = _mean_hit(test, *best)
        rows.append({"kol": label, "secilen_sinyal": best[0], "yon": best[1],
                     "isabet_at_1": None if value is None else round(value, 3),
                     "rastgele": round(_random_baseline(test), 3), "n": n})
    hits = [r["isabet_at_1"] or 0.0 for r in rows]
    rnd = [r["rastgele"] for r in rows]
    return {"kollar": rows,
            "ortalama": round(statistics.mean(hits), 3),
            "rastgele_ortalama": round(statistics.mean(rnd), 3),
            "fark": round(statistics.mean(hits) - statistics.mean(rnd), 3),
            "ayni_sinyal_mi": rows[0]["secilen_sinyal"] == rows[1]["secilen_sinyal"]
                              and rows[0]["yon"] == rows[1]["yon"]}


def _permutation(cases: Sequence[Case], real: float, trials: int, seed: int) -> dict[str, Any]:
    """Çıkan oyuncu GRUP İÇİNDEN rastgele seçilseydi aynı ayrık-yarı sonucu çıkar mıydı?"""
    rng = random.Random(seed)
    hits = 0
    for _ in range(trials):
        shuffled = [Case(c.match_external_id, rng.choice(c.peers), c.group, c.peers, c.feats)
                    for c in cases]
        if _split_half(shuffled)["ortalama"] >= real:
            hits += 1
    return {"deneme": trials, "seed": seed, "yakalama": hits,
            "p": round((hits + 1) / (trials + 1), 4),
            "not": "p = (yakalama + 1) / (deneme + 1); sıfır olasılık iddia edilmez"}


def main() -> int:
    p = argparse.ArgumentParser(description="Grup içi sinyal ölçümü")
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--team", type=int, default=217)
    p.add_argument("--events-dir", type=Path, required=True)
    p.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    cases = collect_cases(args.events_dir, args.tenant, args.team)
    if not cases:
        print("vaka yok — külliyat olayları ve --events-dir gerekli")
        return 1

    split = _split_half(cases)
    perm = _permutation(cases, split["ortalama"], args.permutations, args.seed)
    in_sample = {
        f"{s} ({d:+d})": {"isabet_at_1": None if v is None else round(v, 3), "n": n}
        for s in SIGNALS for d in DIRECTIONS
        for v, n in [_mean_hit(cases, s, d)]
    }
    verdict = ("grup içi bilgi VAR" if split["fark"] >= 0.05 and perm["p"] <= 0.05
               else "grup içi bilgi YOK")

    doc = {
        "olcum": "Grup içi 'kim çıkar' sinyali",
        "kaynak": {"tenant": args.tenant, "takim_external_id": args.team,
                   "vaka": len(cases),
                   "mac": len({c.match_external_id for c in cases}),
                   "ortalama_grup": round(statistics.mean(len(c.peers) for c in cases), 2),
                   "grup_dagilimi": {g: sum(1 for c in cases if c.group == g)
                                     for g in sorted({c.group for c in cases})},
                   "girdi_sha256": hashlib.sha256(json.dumps(
                       [[c.match_external_id, c.player_off, sorted(c.peers)] for c in cases],
                       sort_keys=True).encode("utf-8")).hexdigest()},
        "ayrik_yari": split,
        "permutasyon": perm,
        "ayni_veride_tum_adaylar": in_sample,
        "uyari_in_sample": ("bu sütun SEÇİM İÇERİR: on iki adayın en iyisi aynı veride "
                            "bakıldığında yüksek çıkar. Hüküm ayrık yarı sütunundan verilir"),
        "hukum": verdict,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(cases)} değişiklik · {doc['kaynak']['mac']} maç · ortalama grup "
          f"{doc['kaynak']['ortalama_grup']} · {doc['kaynak']['grup_dagilimi']}")
    print("\naynı veride tüm adaylar (SEÇİM İÇERİR, hüküm buradan verilmez):")
    for k, v in sorted(in_sample.items(), key=lambda kv: -(kv[1]["isabet_at_1"] or 0))[:4]:
        print(f"  {k:<30} {v['isabet_at_1']}")
    print("\nayrık yarı (maç bazında):")
    for r in split["kollar"]:
        print(f"  {r['kol']}: {r['secilen_sinyal']} yön {r['yon']:+d} → "
              f"{r['isabet_at_1']} (rastgele {r['rastgele']}, n={r['n']})")
    print(f"  iki yarı aynı sinyali mi seçti: {'EVET' if split['ayni_sinyal_mi'] else 'HAYIR'}")
    print(f"  ortalama {split['ortalama']} vs rastgele {split['rastgele_ortalama']} "
          f"· fark {split['fark']:+.3f}")
    print(f"  permütasyon p = {perm['p']}")
    print(f"\nHÜKÜM: {verdict}")
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
