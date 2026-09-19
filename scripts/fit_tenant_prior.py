"""Kiracının KENDİ "kim çıkar" önseli — kendi geçmişinden fit, ayrık yarıda sınav.

## Neden

`ELITE_OFF_PRIOR` tek bir genel tablodur ve Barcelona dışı yedi kümeden fit
edildi. Bağımsız doğrulamada bir şey açıkça görüldü: **Barcelona benzeri bir
kulüp için o tablo eskisinden KÖTÜ** (`docs/KARNE-KIM-BAGIMSIZ.md`). Sebebi de
belli — Barcelona'da en çok orta saha çıkıyor, başka her yerde forvet.

Dokümante edilmiş doğru çözüm kiracının kendi geçmişinden fit etmek ve kanca
zaten var: `compute_live_sub_recommendation(off_prior=...)` ve
`compute_sub_timing(off_prior=...)` oyuncu→önsel eşlemesini dışarıdan alır.
Eksik olan tek şey, o eşlemeyi kiracının kendi verisinden üreten ve **ne zaman
güvenilir olduğunu bilen** parçaydı.

## Sorulan soru

Kiracının kendi tablosu, kendi maçlarında genel tabloyu geçiyor mu — ve
geçiyorsa kaç maçtan sonra?

## Kurallar

- **Ayrık yarı, MAÇ bazında.** Tablo bir yarıda fit edilir, öteki yarıda
  ölçülür. Tik bazında bölmek aynı maçı iki yarıya dağıtır.
- **Beraberlik tarafsız.** Tablo yalnız sekiz hücre; aynı gruptaki adaylar
  birebir eşit değer alır. Beraberliği oyuncu kimliğiyle çözmek bu veri
  kümesinde isabet@1'i 0,125'ten 0,181'e çıkarıyordu — beceri değil, tesadüf
  (`docs/KARNE-SIRALAMA.md`). Ölçüm `who_prior_agreement` ile yapılır.
- **Öğrenme eğrisi ÖN-KAYITLI okunur.** Eğrinin en iyi noktasını seçmek, on bir
  adayın en iyisini seçmekle aynı hatadır. Kapı kuralı önceden sabit: genel
  tabloyu **İKİ KOLDA DA** geçen en küçük maç sayısı. Tek kolda geçen sayılmaz.
- **Kapı geçilmezse tablo bağlanmaz** ve kiracı genel tabloyu kullanmaya devam
  eder. Bu bir kusur değil, doğru varsayılan.

## Kullanım

    $env:DATABASE_URL = "sqlite:///C:/.../demo.db"
    venv\\Scripts\\python.exe -m scripts.fit_tenant_prior
        --tenant t-default --team 217 --events-dir C:\\sb
        --out docs/measurements/tenant-prior-217.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from app.engine.coach_benchmark import (
    WHO_TOP_K,
    WhoPrior,
    WhoState,
    fit_who_prior,
    who_prior_agreement,
)
from scripts.validate_who_prior import _frozen_prior, who_states_from_events

# Öğrenme eğrisinde denenen eğitim boyutları (maç). Liste ÖNCEDEN kapalıdır;
# veriye bakıp nokta eklenirse kapı kuralı geçersiz olur.
CURVE_MATCHES: tuple[int, ...] = (10, 20, 30, 40, 50)
# Kiracı tablosunun genel tabloyu geçmiş sayılması için gereken en az fark.
# `WHO_MIN_GAIN` ile aynı büyüklük sınıfı; gürültüyü bulgu saymamak için.
MIN_EDGE = 0.02


def _load(events_dir: Path, team: int | None) -> list[WhoState]:
    states: list[WhoState] = []
    for p in sorted(events_dir.glob("*.json")):
        if not p.stem.isdigit():
            continue
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        states.extend(who_states_from_events(ev, int(p.stem), team=team))
    return states


def _halves(states: list[WhoState]) -> tuple[list[WhoState], list[WhoState]]:
    """MAÇ bazında ayrık yarı — aynı maçın hamleleri bölünmez."""
    ids = sorted({s.match_external_id for s in states})
    a_ids = {m for i, m in enumerate(ids) if i % 2 == 0}
    return ([s for s in states if s.match_external_id in a_ids],
            [s for s in states if s.match_external_id not in a_ids])


def _first_n_matches(states: list[WhoState], n: int) -> list[WhoState]:
    """Eğitim kümesinin ilk n MAÇI — kimlik sırasına göre, deterministik."""
    ids = sorted({s.match_external_id for s in states})[:n]
    keep = set(ids)
    return [s for s in states if s.match_external_id in keep]


def _score(prior: WhoPrior, states: list[WhoState], k: int) -> dict[str, Any]:
    st = who_prior_agreement(prior, states, k=k)
    return {"isabet_at_1": st.hit_at_1, "isabet_at_k": st.hit_at_k,
            "rastgele_at_1": st.baseline_at_1, "rastgele_at_k": st.baseline_at_k,
            "n": st.n}


def _arm(train: list[WhoState], test: list[WhoState], label: str,
         genel: WhoPrior, k: int) -> dict[str, Any]:
    kiraci = fit_who_prior(train)
    kd, gd = _score(kiraci, test, k), _score(genel, test, k)
    egri = []
    for n in CURVE_MATCHES:
        alt = _first_n_matches(train, n)
        if len({s.match_external_id for s in alt}) < n:
            break      # o kadar maç yok; eğri burada biter
        s = _score(fit_who_prior(alt), test, k)
        egri.append({"egitim_mac": n, "egitim_hamle": len(alt),
                     "isabet_at_1": s["isabet_at_1"], "isabet_at_k": s["isabet_at_k"],
                     "genel_gecti_mi": bool(
                         s["isabet_at_k"] is not None and gd["isabet_at_k"] is not None
                         and s["isabet_at_k"] - gd["isabet_at_k"] >= MIN_EDGE)})
    return {
        "kol": label,
        "egitim_mac": len({s.match_external_id for s in train}),
        "egitim_hamle": len(train),
        "olcum_mac": len({s.match_external_id for s in test}),
        "kiraci_tablosu": kd, "genel_tablo": gd,
        "fark_at_k": (None if kd["isabet_at_k"] is None or gd["isabet_at_k"] is None
                      else round(kd["isabet_at_k"] - gd["isabet_at_k"], 3)),
        "ogrenme_egrisi": egri,
        "tablo": {f"{g}|{int(s)}": round(v, 4)
                  for (g, s), v in sorted(fit_who_prior(train).table.items())},
    }


def _gate(arms: list[dict[str, Any]]) -> dict[str, Any]:
    """Kapı: genel tabloyu İKİ KOLDA DA geçen en küçük maç sayısı.

    Tek kolda geçen sayı kabul edilmez — ayrık yarının bütün amacı budur.
    """
    if len(arms) < 2:
        return {"gecen_mac": None, "hukum": "yetersiz veri",
                "not": "iki kol kurulamadı"}
    gecenler = []
    for n in CURVE_MATCHES:
        noktalar = [next((e for e in a["ogrenme_egrisi"] if e["egitim_mac"] == n), None)
                    for a in arms]
        if any(p is None for p in noktalar):
            continue
        if all(p["genel_gecti_mi"] for p in noktalar if p is not None):
            gecenler.append(n)
    if not gecenler:
        return {
            "gecen_mac": None, "hukum": "kiracı tablosu bağlanmaz",
            "not": ("hiçbir eğitim boyutunda genel tabloyu İKİ KOLDA birden "
                    f"en az {MIN_EDGE} geçmedi; kiracı genel tabloyu kullanmaya "
                    "devam eder"),
        }
    return {
        "gecen_mac": min(gecenler), "tum_gecenler": gecenler,
        "hukum": "kiracı tablosu bağlanabilir",
        "not": (f"en az {min(gecenler)} maçtan sonra kiracının kendi tablosu "
                "genel tabloyu iki kolda da geçiyor"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Kiracının kendi 'kim çıkar' önseli")
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--team", type=int, default=None,
                   help="tek takıma daralt; verilmezse dosyadaki iki takım da")
    p.add_argument("--events-dir", type=Path, required=True)
    p.add_argument("--k", type=int, default=WHO_TOP_K)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    states = _load(args.events_dir, args.team)
    if not states:
        print("hamle çıkmadı — --events-dir içinde {match_id}.json gerekir")
        return 1

    genel = _frozen_prior()
    a, b = _halves(states)
    arms = [_arm(a, b, "A'da fit → B'de ölç", genel, args.k),
            _arm(b, a, "B'de fit → A'da ölç", genel, args.k)]
    gate = _gate(arms)

    doc = {
        "olcum": "Kiracının kendi 'kim çıkar' önseli vs genel tablo",
        "kaynak": {
            "tenant": args.tenant, "takim_external_id": args.team,
            "mac": len({s.match_external_id for s in states}),
            "hamle": len(states),
            "girdi_sha256": hashlib.sha256(json.dumps(
                [[s.match_external_id, s.player_off,
                  sorted((c.player_id, c.group, c.starter) for c in s.candidates)]
                 for s in states], sort_keys=True).encode("utf-8")).hexdigest(),
        },
        "cetvel": {
            "olcut": f"beraberlik-tarafsız isabet@{args.k} (who_prior_agreement)",
            "ayrik_yari": "MAÇ bazında",
            "kapi_kurali": (f"genel tabloyu İKİ KOLDA da en az {MIN_EDGE} geçmek; "
                            "eğri noktaları önceden kapalı"),
            "egri_noktalari": list(CURVE_MATCHES),
        },
        "kollar": arms,
        "kapi": gate,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    print(f"{doc['kaynak']['mac']} maç · {len(states)} hamle → {args.out}")
    for arm in arms:
        kd, gd = arm["kiraci_tablosu"], arm["genel_tablo"]
        print(f"\n  {arm['kol']} ({arm['egitim_mac']} maçtan fit)")
        print(f"    kiraci tablosu  isabet@{args.k} {kd['isabet_at_k']} "
              f"· isabet@1 {kd['isabet_at_1']}")
        print(f"    genel tablo     isabet@{args.k} {gd['isabet_at_k']} "
              f"· isabet@1 {gd['isabet_at_1']}")
        print(f"    rastgele        isabet@{args.k} {gd['rastgele_at_k']}")
        print(f"    fark: {arm['fark_at_k']}")
        for e in arm["ogrenme_egrisi"]:
            isaret = "gecti" if e["genel_gecti_mi"] else "-"
            print(f"      {e['egitim_mac']:3d} mac: isabet@{args.k} "
                  f"{e['isabet_at_k']}  {isaret}")
    print(f"\n  KAPI: {gate['hukum']} — {gate['not']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
