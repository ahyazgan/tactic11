"""Koç zekâ karnesi: motor bugün ne kadar "antrenör gibi" düşünüyor — ÖLÇ.

## Neden bu script var

Külliyat karnesi (`decision_corpus report`) tek soruyu tartar: güven sonucu
ayırıyor mu? Bu script "ne kadar zekâlı" sorusunun BUGÜN ölçülebilen bütün
boyutlarını tek karnede toplar ve her birini bir taban çizgisiyle kıyaslar
(`engine.coach_benchmark`). Yeni dış ölçüt: StatsBomb'daki GERÇEK antrenör
hamleleri (oyuncu değişikliği, diziliş değişimi) — motor önerileri ilk kez
elit bir antrenörün fiilen yaptığıyla kıyaslanıyor.

## Kullanım

    venv\\Scripts\\python.exe -m scripts.coach_iq --tenant t-default --team 217
    venv\\Scripts\\python.exe -m scripts.coach_iq --tenant t-default --team 217 --events-dir C:\\sb

`--events-dir` verilirse ham StatsBomb `events/<match_id>.json` dosyaları
oradan okunur (ağ yok); verilmezse `StatsBombOpen` adapter'ı (önbellekli) çeker.

Önkoşul: `decision_corpus seed` + `score` çalışmış olmalı (kararlar ve
`pre_xg_diff` gerekir).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.data.sources.statsbomb_open import CoachMove, coach_moves_from_events_json
from app.db import models
from app.db.session import SessionLocal
from app.engine.coach_benchmark import (
    Dimension,
    TickObservation,
    TickState,
    build_scorecard,
    expected_calibration_error,
    lead_times,
    skill_from_auc,
    split_half_agreement,
    split_half_timing_prior,
)
from app.engine.confidence.attribution import MIN_SAMPLES, attribute_stratified
from app.sports import football

# Antrenör hamlesi motor tikinden en fazla bu kadar dakika SONRA gelirse "uyuştu".
DEFAULT_WINDOW_MIN = 12.0
# Hamleden önce bu kadar dakikaya kadar geriye bakılır (öncü süre).
DEFAULT_LOOKBACK_MIN = 15.0
SUB_SIGNAL_KEY = "sub_timing"


def _events_json(match_id: int, events_dir: Path | None) -> list[dict[str, Any]] | None:
    if events_dir is not None:
        p = events_dir / f"{match_id}.json"
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
        return data if isinstance(data, list) else None
    from app.data.sources.statsbomb_open import StatsBombOpen
    try:
        return StatsBombOpen().get_events(match_id)
    except Exception as e:      # noqa: BLE001 — bir maç düşerse karne sürsün
        print(f"  maç {match_id}: olaylar alınamadı ({type(e).__name__})")
        return None


def _ctx(d: models.Decision) -> dict[str, Any]:
    try:
        x = json.loads(d.context_json or "{}")
    except (ValueError, TypeError):
        return {}
    return x if isinstance(x, dict) else {}


def _sub_minutes(moves: list[CoachMove], team: int) -> list[float]:
    """Takımın TAKTİK değişiklik anları; çifte değişiklik tek an sayılır."""
    return sorted({m.minute for m in moves
                   if m.team_external_id == team and m.kind == "substitution" and m.tactical})


def _shift_minutes(moves: list[CoachMove], team: int) -> list[float]:
    return sorted({m.minute for m in moves
                   if m.team_external_id == team and m.kind == "tactical_shift"})


def _all_sub_minutes(moves: list[CoachMove], team: int) -> list[float]:
    """Sakatlık dahil TÜM değişiklikler — 'o ana kadar kaç değişiklik' sayacı için."""
    return sorted(m.minute for m in moves
                  if m.team_external_id == team and m.kind == "substitution")


def _acted(minute: float, coach: list[float], window: float) -> bool:
    return any(minute < c <= minute + window for c in coach)


def _score_state_asof(minute: float, goals: list[tuple[float, int]], team: int) -> str:
    """O an itibarıyla skor durumu — `events.is_goal`'dan (kendi kalesine gol yok)."""
    mine = sum(1 for m, t in goals if m < minute and t == team)
    theirs = sum(1 for m, t in goals if m < minute and t != team)
    return "leading" if mine > theirs else "trailing" if mine < theirs else "drawing"


def _ruler_on_coach(session, match, team: int, minutes: list[float]) -> tuple[int, int, int]:
    """Bizim etki cetveli elit antrenörün hamlelerine ne diyor? (olumlu, olumsuz, nötr)"""
    from app.data.loaders.events import load_match_events
    from app.engine.decision_impact import DecisionContext, compute_decision_impact

    loaded = load_match_events(session, match.external_id)
    if loaded.total == 0:
        return 0, 0, 0
    opp = (match.away_team_external_id if team == match.home_team_external_id
           else match.home_team_external_id)
    pos = neg = neu = 0
    for i, m in enumerate(minutes):
        ctx = DecisionContext(
            decision_id=-(i + 1), match_external_id=match.external_id,
            team_external_id=team, opponent_external_id=opp,
            minute=m, decision_type="substitution", period=1 if m < 45 else 2,
            recommended=False,
        )
        v = compute_decision_impact(
            ctx, passes=loaded.passes, carries=loaded.carries, shots=loaded.shots,
            defensive_actions=loaded.defensive_actions,
        ).value.verdict
        if v == "positive":
            pos += 1
        elif v == "negative":
            neg += 1
        elif v == "neutral":
            neu += 1
    return pos, neg, neu


def _hit(pos: int, neg: int) -> float | None:
    return round(pos / (pos + neg), 3) if pos + neg else None


def main() -> int:
    p = argparse.ArgumentParser(description="Koç zekâ karnesi: motor vs taban çizgileri")
    p.add_argument("--tenant", default="t-default")
    p.add_argument("--team", type=int, default=217)
    p.add_argument("--events-dir", type=Path, default=None,
                   help="ham StatsBomb events/<id>.json klasörü (yoksa adapter çeker)")
    p.add_argument("--window", type=float, default=DEFAULT_WINDOW_MIN)
    p.add_argument("--lookback", type=float, default=DEFAULT_LOOKBACK_MIN)
    args = p.parse_args()

    with SessionLocal() as s:
        s.info["tenant_id"] = args.tenant
        decisions = [d for d in s.execute(select(models.Decision).where(
            models.Decision.sport == football.SPORT_NAME,
            models.Decision.tenant_id == args.tenant,
            models.Decision.team_external_id == args.team,
        )).scalars() if d.context_json]
        if not decisions:
            print("külliyat boş — önce `decision_corpus seed` ve `score`")
            return 1
        matches = {m.external_id: m for m in s.execute(select(models.Match).where(
            models.Match.sport == football.SPORT_NAME,
            models.Match.external_id.in_(sorted({d.match_external_id for d in decisions})),
        )).scalars()}

        goals: dict[int, list[tuple[float, int]]] = defaultdict(list)
        for minute, team_id, mid in s.execute(select(
            models.EventRow.minute, models.EventRow.team_external_id,
            models.EventRow.match_external_id,
        ).where(
            models.EventRow.sport == football.SPORT_NAME,
            models.EventRow.is_goal.is_(True),
            models.EventRow.match_external_id.in_(list(matches)),
        )):
            goals[mid].append((float(minute), int(team_id)))

        # ---- gerçek antrenör hamleleri ------------------------------------ #
        coach_subs: dict[int, list[float]] = {}
        coach_shifts: dict[int, list[float]] = {}
        coach_all_subs: dict[int, list[float]] = {}
        injury_subs = 0
        for mid in sorted(matches):
            ev = _events_json(mid, args.events_dir)
            if ev is None:
                continue
            moves = coach_moves_from_events_json(ev)
            coach_subs[mid] = _sub_minutes(moves, args.team)
            coach_shifts[mid] = _shift_minutes(moves, args.team)
            coach_all_subs[mid] = _all_sub_minutes(moves, args.team)
            injury_subs += sum(1 for m in moves if m.team_external_id == args.team
                               and m.kind == "substitution" and not m.tactical)
        if not coach_subs:
            print("hiçbir maçın ham olayı okunamadı — --events-dir ya da ağ gerekli")
            return 1

        # ---- cetvel kontrolü: elit antrenörün hamleleri bizim cetvelde ----- #
        c_pos = c_neg = c_neu = 0
        for mid, mins in coach_subs.items():
            if not mins:
                continue
            a, b, c = _ruler_on_coach(s, matches[mid], args.team, mins)
            c_pos, c_neg, c_neu = c_pos + a, c_neg + b, c_neu + c

    # ---- motor tikleri --------------------------------------------------- #
    strict: list[TickObservation] = []
    loose: list[TickObservation] = []
    shape: list[TickObservation] = []
    states: list[TickState] = []
    eng_sub_minutes: dict[int, list[float]] = defaultdict(list)
    fc_samples: list[tuple[float, bool, float]] = []
    cal_samples: list[tuple[float, bool]] = []
    e_pos = e_neg = 0
    applied_t = applied_f = 0

    for d in decisions:
        mid = d.match_external_id
        if mid not in coach_subs:
            continue
        ctx = _ctx(d)
        is_sub = d.decision_type == "substitution"
        has_sub_signal = is_sub or SUB_SIGNAL_KEY in (ctx.get("supporting_keys") or [])
        acted_sub = _acted(d.minute, coach_subs[mid], args.window)
        acted_shift = _acted(d.minute, coach_shifts.get(mid, []), args.window)
        strict.append(TickObservation(mid, d.minute, is_sub, acted_sub))
        loose.append(TickObservation(mid, d.minute, has_sub_signal, acted_sub))
        shape.append(TickObservation(mid, d.minute, ctx.get("theme") == "adjust_shape", acted_shift))
        states.append(TickState(
            mid, d.minute,
            score_state=_score_state_asof(d.minute, goals.get(mid, []), args.team),
            subs_used=sum(1 for c in coach_all_subs.get(mid, []) if c <= d.minute),
            coach_acted=acted_sub,
        ))
        if has_sub_signal:
            eng_sub_minutes[mid].append(d.minute)

        if d.outcome == "positive":
            e_pos += 1
        elif d.outcome == "negative":
            e_neg += 1
        if d.outcome in {"positive", "negative"} and d.confidence is not None:
            ok = d.outcome == "positive"
            cal_samples.append((float(d.confidence), ok))
            pre = ctx.get("pre_xg_diff")
            if pre is not None:
                fc_samples.append((float(d.confidence), ok, float(pre)))
        if d.applied is True:
            applied_t += 1
        elif d.applied is False:
            applied_f += 1

    # ---- boyut 1: öngörü ------------------------------------------------- #
    dims: list[Dimension] = []
    if len(fc_samples) >= MIN_SAMPLES:
        att = attribute_stratified(fc_samples, "güven")
        dims.append(Dimension(
            name="Öngörü", metric="katmanlı AUC (güven → 15 dk sonrası)",
            value=att.auc, baseline=0.5, skill=skill_from_auc(att.auc), measurable=True,
            verdict="taban çizgisini geçiyor" if att.verdict == "ayırıyor" else att.verdict,
            note=att.note,
        ))
    else:
        dims.append(Dimension("Öngörü", "katmanlı AUC", None, 0.5, None, False,
                              "yetersiz veri", f"n={len(fc_samples)} < {MIN_SAMPLES}"))

    # ---- boyut 2: kalibrasyon ------------------------------------------- #
    ece, mean_conf, hit = expected_calibration_error(cal_samples)
    if ece is not None and mean_conf is not None and hit is not None and len(cal_samples) >= MIN_SAMPLES:
        naive = round(abs(mean_conf - hit), 3)   # sabit taban oranı söyleyen sistem
        gap = mean_conf - hit
        if ece + 0.02 < naive:
            verdict = "taban çizgisini geçiyor"
        elif ece > naive + 0.02:
            verdict = "taban çizgisinin altında"
        else:
            verdict = "taban çizgisiyle aynı"
        dims.append(Dimension(
            name="Kalibrasyon", metric="ECE (düşük iyi)", value=ece, baseline=naive,
            skill=round(max(0.0, 1.0 - ece / 0.25) * 100, 1), measurable=True, verdict=verdict,
            note=(f"ortalama güven {mean_conf:.0%}, gerçek isabet {hit:.0%} → sistem "
                  f"{'fazla' if gap > 0 else 'az'} güvenli ({gap:+.0%}); taban = hep "
                  f"{mean_conf:.0%} demenin hatası"),
        ))
    else:
        dims.append(Dimension("Kalibrasyon", "ECE", None, None, None, False,
                              "yetersiz veri", f"n={len(cal_samples)} < {MIN_SAMPLES}"))

    # ---- boyut 3: elit antrenörle uyum --------------------------------- #
    sh_strict = split_half_agreement(strict)
    sh_loose = split_half_agreement(loose)
    sh_shape = split_half_agreement(shape)
    lt = lead_times(coach_subs, eng_sub_minutes, lookback_min=args.lookback)
    sh_prior = split_half_timing_prior(states)
    best = sh_loose if (sh_loose.engine_f1 or 0) >= (sh_strict.engine_f1 or 0) else sh_strict
    dims.append(Dimension(
        name="Elit antrenörle uyum (değişiklik)",
        metric="F1 vs saat-kuralı (ayrık yarı)",
        value=best.engine_f1, baseline=best.baseline_f1,
        skill=None, measurable=best.verdict != "yetersiz veri", verdict=best.verdict,
        note=best.note,
    ))

    # ---- boyut 4: cetvel kontrolü --------------------------------------- #
    coach_hit, engine_hit = _hit(c_pos, c_neg), _hit(e_pos, e_neg)
    if coach_hit is not None and c_pos + c_neg >= MIN_SAMPLES:
        if coach_hit >= 0.6:
            verdict = "taban çizgisini geçiyor"
            note = (f"cetvel elit antrenörün hamlelerini {coach_hit:.0%} olumlu görüyor "
                    f"(n={c_pos + c_neg}, nötr {c_neu}) — cetvel iyi hamleyi tanıyor")
        else:
            verdict = "taban çizgisiyle aynı"
            note = (f"cetvel ELİT antrenörün gerçek hamlelerini bile yalnız {coach_hit:.0%} "
                    f"olumlu görüyor (n={c_pos + c_neg}, nötr {c_neu}); motor {engine_hit}. "
                    f"Cetvel iyi ile kötüyü ayıramıyorsa motorun puanı cetvelin körlüğüdür")
        dims.append(Dimension(
            name="Cetvel kontrolü (elit hamle isabeti)", metric="isabet, aynı cetvel",
            value=coach_hit, baseline=0.5, skill=None, measurable=True, verdict=verdict, note=note,
        ))
    else:
        dims.append(Dimension("Cetvel kontrolü", "isabet", coach_hit, 0.5, None, False,
                              "yetersiz veri", f"ölçülen elit hamle {c_pos + c_neg}"))

    # ---- boyut 5: karşı-olgu ------------------------------------------- #
    dims.append(Dimension(
        name="Karşı-olgu (uygulanan vs uygulanmayan)", metric="katmanlı isabet farkı",
        value=None, baseline=0.0, skill=None,
        measurable=applied_t > 0 and applied_f > 0,
        verdict="ölçülemez" if not (applied_t and applied_f) else "bkz. decisions/uplift",
        note=(f"uygulanan {applied_t} · uygulanmayan {applied_f} — pilot işaretlemeden "
              f"'öneri yüzünden ne oldu' bilinemez"),
    ))

    card = build_scorecard(dims)

    # ---- rapor ------------------------------------------------------------ #
    n_matches = len(coach_subs)
    n_subs = sum(len(v) for v in coach_subs.values())
    n_shifts = sum(len(v) for v in coach_shifts.values())
    print(f"\n=== KOÇ ZEKÂ KARNESİ — takım {args.team} ===")
    print(f"  {n_matches} maç · {len(strict)} motor tiki · gerçek antrenör: "
          f"{n_subs} taktik değişiklik anı, {injury_subs} sakatlık değişikliği, "
          f"{n_shifts} diziliş değişimi\n")
    print(f"  {card.headline}\n")
    print(f"  {'boyut':<40}{'ölçü':>8}{'taban':>8}{'beceri':>8}  hüküm")
    print("  " + "-" * 92)
    for d in card.dimensions:
        v = "—" if d.value is None else f"{d.value:.2f}"
        b = "—" if d.baseline is None else f"{d.baseline:.2f}"
        sk = "—" if d.skill is None else f"{d.skill:.0f}"
        print(f"  {d.name:<40}{v:>8}{b:>8}{sk:>8}  {d.verdict}")
    print()
    for d in card.dimensions:
        print(f"  · {d.name}: {d.note}")

    print("\n  UYUM AYRINTISI (antrenör değişikliği, pencere "
          f"{args.window:.0f} dk, eşik ayrık yarıda seçildi)")
    for ad, sh in (("motor 'değişiklik' dedi", sh_strict),
                   ("değişiklik sinyali yandı (destekleyici dahil)", sh_loose)):
        ea, eb, ba, bb = sh.engine_a, sh.engine_b, sh.baseline_a, sh.baseline_b
        print(f"    {ad}:")
        print(f"      motor    F1 {sh.engine_f1} · precision {ea.precision}/{eb.precision} · "
              f"recall {ea.recall}/{eb.recall} · bayrak oranı {ea.flag_rate}/{eb.flag_rate}")
        print(f"      saat     F1 {sh.baseline_f1} · precision {ba.precision}/{bb.precision} · "
              f"recall {ba.recall}/{bb.recall} · eşik {sh.threshold_for_a}/{sh.threshold_for_b} dk")
        print(f"      hüküm: {sh.verdict}")
    print(f"    diziliş değişimi ↔ motor 'şekil ayarla': motor F1 {sh_shape.engine_f1} vs saat "
          f"{sh_shape.baseline_f1} · motor bayrak oranı "
          f"{sh_shape.engine_a.flag_rate}/{sh_shape.engine_b.flag_rate} "
          f"(antrenör taban oranı {sh_shape.engine_a.act_rate}/{sh_shape.engine_b.act_rate}) "
          f"— {sh_shape.verdict}")
    pa, pb = sh_prior.engine_a, sh_prior.engine_b
    print("    ADAY — elit zamanlama önseli (dakika bandı × skor durumu × yapılan değişiklik, "
          "ayrık yarıda öğrenildi):")
    print(f"      önsel   F1 {sh_prior.engine_f1} · precision {pa.precision}/{pb.precision} · "
          f"recall {pa.recall}/{pb.recall} · bayrak oranı {pa.flag_rate}/{pb.flag_rate}")
    print(f"      saat    F1 {sh_prior.baseline_f1} · hüküm: {sh_prior.verdict}")
    print(f"    öncü süre: {lt.moves} gerçek değişikliğin {lt.covered}'inde motor önceki "
          f"{args.lookback:.0f} dk içinde sinyal vermiş (kapsama {lt.coverage}); "
          f"ort. {lt.mean_lead_min} dk, medyan {lt.median_lead_min} dk önce")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
