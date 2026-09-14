"""Koç zekâ karnesi: motor bugün ne kadar "antrenör gibi" düşünüyor — ÖLÇ.

## Neden bu script var

Külliyat karnesi (`decision_corpus report`) tek soruyu tartar: güven sonucu
ayırıyor mu? Bu script "ne kadar zekâlı" sorusunun BUGÜN ölçülebilen bütün
boyutlarını tek karnede toplar ve her birini bir taban çizgisiyle kıyaslar
(`engine.coach_benchmark`). Yeni dış ölçüt: StatsBomb'daki GERÇEK antrenör
hamleleri (oyuncu değişikliği, diziliş değişimi) — motor önerileri ilk kez
elit bir antrenörün fiilen yaptığıyla kıyaslanıyor.

Cetvel kontrolü iki cetveli yan yana tartar: v1 (mutlak xG farkı,
`decision_impact`) ve v2 adayı (aynı Δ, "bu durumda olağan olan"a göre
düzeltilmiş, `decision_baseline`). Üç küme: elit hamle · motor tiki · plasebo
(kimsenin bir şey yapmadığı anlar). İyi cetvel eliti plasebodan ayırmalı.
2026-09-12 ölçümü: ikisi de ayırmıyor (bkz. `decision_baseline` doküstringi).

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

from app.data.sources.statsbomb_open import (
    CoachMove,
    appearances_from_events_json,
    coach_moves_from_events_json,
    lineup_positions_from_events_json,
    position_group,
)
from app.db import models
from app.db.session import SessionLocal
from app.engine.coach_benchmark import (
    Dimension,
    SelectivityStat,
    ShapeState,
    TickObservation,
    TickState,
    WhoCandidate,
    WhoSample,
    WhoState,
    build_scorecard,
    expected_calibration_error,
    lead_times,
    skill_from_auc,
    split_half_agreement,
    split_half_shape_gate,
    split_half_timing_prior,
    split_half_who_prior,
    who_agreement,
)
from app.engine.confidence.attribution import MIN_SAMPLES, attribute_stratified
from app.engine.decision_baseline import (
    BaselineSample,
    adjusted_delta,
    fit_state_baseline,
    minute_band,
    score_state,
)
from app.sports import football

# Antrenör hamlesi motor tikinden en fazla bu kadar dakika SONRA gelirse "uyuştu".
DEFAULT_WINDOW_MIN = 12.0
# Hamleden önce bu kadar dakikaya kadar geriye bakılır (öncü süre).
DEFAULT_LOOKBACK_MIN = 15.0
SUB_SIGNAL_KEY = "sub_timing"
# Plasebo ve taban ızgarası: her 5 dk; kendi değişikliğine ±12 dk yakın anlar atılır.
GRID_MINUTES: tuple[float, ...] = tuple(float(m) for m in range(10, 90, 5))
GRID_EXCLUDE_MIN = 12.0
# Cetvel kabul ölçütü: elit − plasebo (ham isabet VE hücre-içi fark) en az bu kadar.
RULER_MIN_GAP = 0.10


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


def _sub_minutes(
    moves: list[CoachMove], team: int, *, tactical_only: bool, unique: bool = True,
) -> list[float]:
    """Hamle anları tekilleşir; unique=False ile değişen her oyuncu korunur."""
    minutes = [m.minute for m in moves
               if m.team_external_id == team and m.kind == "substitution"
               and (m.tactical or not tactical_only)]
    return sorted(set(minutes) if unique else minutes)


def _shift_minutes(moves: list[CoachMove], team: int) -> list[float]:
    return sorted({m.minute for m in moves
                   if m.team_external_id == team and m.kind == "tactical_shift"})


def _acted(minute: float, coach: list[float], window: float) -> bool:
    return any(minute < c <= minute + window for c in coach)


def _near(minute: float, subs: list[float], w: float) -> bool:
    return any(abs(c - minute) <= w for c in subs)


def _asof(goals: list[tuple[float, int]], minute: float, team: int) -> str:
    """O an itibarıyla skor durumu — şut listesindeki gollerden (kendi kalesine gol yok)."""
    mine = sum(1 for g, t in goals if g < minute and t == team)
    theirs = sum(1 for g, t in goals if g < minute and t != team)
    return score_state(mine, theirs)


# (dakika, skor durumu, Δxg_diff, v1 hükmü)
Moment = tuple[float, str, float, str]


def _moments(session, match, team: int, minutes: list[float]) -> list[Moment]:
    """Her an için v1 etki ölçümü; v2 aynı Δ'yı duruma göre düzeltir."""
    from app.data.loaders.events import load_match_events
    from app.engine.decision_impact import DecisionContext, compute_decision_impact

    loaded = load_match_events(session, match.external_id)
    if loaded.total == 0:
        return []
    opp = (match.away_team_external_id if team == match.home_team_external_id
           else match.home_team_external_id)
    goals = [(sh.minute, sh.team_external_id or 0) for sh in loaded.shots if sh.is_goal]
    out: list[Moment] = []
    for i, m in enumerate(minutes):
        ctx = DecisionContext(
            decision_id=-(i + 1), match_external_id=match.external_id,
            team_external_id=team, opponent_external_id=opp,
            minute=m, decision_type="substitution", period=1 if m < 45 else 2,
            recommended=False,
        )
        imp = compute_decision_impact(
            ctx, passes=loaded.passes, carries=loaded.carries, shots=loaded.shots,
            defensive_actions=loaded.defensive_actions,
        ).value
        if imp.verdict == "insufficient_data":
            continue
        out.append((imp.minute, _asof(goals, imp.minute, team), imp.xg_diff_delta, imp.verdict))
    return out


def _verdict_from_delta(delta: float) -> str:
    from app.engine.decision_impact.compute import NEGATIVE_XG_DELTA, POSITIVE_XG_DELTA

    if delta >= POSITIVE_XG_DELTA:
        return "positive"
    if delta <= NEGATIVE_XG_DELTA:
        return "negative"
    return "neutral"


class _Tally:
    """Bir cetvelin bir kümedeki olumlu/olumsuz/nötr sayımı."""

    def __init__(self) -> None:
        self.pos = self.neg = self.neu = 0

    def add(self, verdict: str) -> None:
        if verdict == "positive":
            self.pos += 1
        elif verdict == "negative":
            self.neg += 1
        elif verdict == "neutral":
            self.neu += 1

    @property
    def n(self) -> int:
        return self.pos + self.neg

    @property
    def hit(self) -> float | None:
        return round(self.pos / self.n, 3) if self.n else None

    def __str__(self) -> str:
        h = "—" if self.hit is None else f"{self.hit:.0%}"
        return f"{h} (n={self.n}, nötr {self.neu})"


def _mh_gap(rows: list[tuple[tuple[int, str], str, str]], grp: str) -> tuple[float | None, int]:
    """Hücre-içi (dakika bandı × skor) isabet farkı grp − plasebo, Mantel-Haenszel ağırlıklı."""
    cells: dict[tuple[int, str], dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0]))
    for cell, key, v in rows:
        if v == "positive":
            cells[cell][key][0] += 1
        elif v == "negative":
            cells[cell][key][1] += 1
    num = den = 0.0
    used = 0
    for g in cells.values():
        a, b = g[grp], g["plasebo"]
        na, nb = sum(a), sum(b)
        if not na or not nb:
            continue
        w = na * nb / (na + nb)
        num += w * (a[0] / na - b[0] / nb)
        den += w
        used += 1
    return (None if not den else round(num / den, 3)), used


def _shape_line(label: str, a: SelectivityStat, b: SelectivityStat) -> None:
    """Seçicilik satırı: bayrak oranı · precision · kaldırma · recall (iki yarı)."""
    def _n(x: float | None) -> str:
        return "—" if x is None else f"{x:.2f}"
    print(f"      {label:<32} bayrak {a.flag_rate:.2f}/{b.flag_rate:.2f} "
          f"({a.flagged}/{b.flagged} tik) · isabet {_n(a.precision)}/{_n(b.precision)} · "
          f"kaldırma {_n(a.lift)}/{_n(b.lift)} · yakalama {_n(a.recall)}/{_n(b.recall)}")


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
        moves_by_match: dict[int, list[CoachMove]] = {}
        appearances: dict[int, list[dict[str, Any]]] = {}
        positions: dict[int, dict[int, int]] = {}
        injury_subs = 0
        for mid in sorted(matches):
            ev = _events_json(mid, args.events_dir)
            if ev is None:
                continue
            moves = coach_moves_from_events_json(ev)
            moves_by_match[mid] = moves
            appearances[mid] = [a for a in appearances_from_events_json(ev)
                                if a["team_external_id"] == args.team]
            positions[mid] = lineup_positions_from_events_json(ev)
            coach_subs[mid] = _sub_minutes(moves, args.team, tactical_only=True)
            coach_shifts[mid] = _shift_minutes(moves, args.team)
            coach_all_subs[mid] = _sub_minutes(moves, args.team, tactical_only=False,
                                               unique=False)
            injury_subs += sum(1 for m in moves if m.team_external_id == args.team
                               and m.kind == "substitution" and not m.tactical)
        if not coach_subs:
            print("hiçbir maçın ham olayı okunamadı — --events-dir ya da ağ gerekli")
            return 1

        # ---- cetvel kontrolü: taban ızgarası + üç küme ------------------------ #
        # Taban: karar OLMAYAN anlar, iki takım perspektifi; her maç için taban
        # tablosu o maç HARİÇ kurulur (leave-one-out).
        grid_samples: dict[int, list[BaselineSample]] = {}
        per_match: dict[int, dict[str, list[Moment]]] = {}
        for mid, moves in moves_by_match.items():
            m = matches[mid]
            rows: list[BaselineSample] = []
            for team_id in (m.home_team_external_id, m.away_team_external_id):
                own = _sub_minutes(moves, team_id, tactical_only=False)
                grid = [g for g in GRID_MINUTES if not _near(g, own, GRID_EXCLUDE_MIN)]
                rows.extend(BaselineSample(mn, st, delta)
                            for mn, st, delta, _v1 in _moments(s, m, team_id, grid))
            grid_samples[mid] = rows

            own = coach_all_subs[mid]
            ticks_here = sorted({d.minute for d in decisions if d.match_external_id == mid})
            placebo = [g for g in GRID_MINUTES if not _near(g, own, GRID_EXCLUDE_MIN)]
            per_match[mid] = {
                key: _moments(s, m, args.team, minutes)
                for key, minutes in (("elit", coach_subs[mid]), ("motor", ticks_here),
                                     ("plasebo", placebo))
            }

    tal = {k: (_Tally(), _Tally()) for k in ("elit", "motor", "plasebo")}
    cell_rows: dict[int, list[tuple[tuple[int, str], str, str]]] = {0: [], 1: []}
    for mid, sets in per_match.items():
        base = fit_state_baseline(
            r for other, rows in grid_samples.items() if other != mid for r in rows
        )
        for key, moments in sets.items():
            for minute, st, delta, v1 in moments:
                v2 = _verdict_from_delta(
                    adjusted_delta(base, minute=minute, score_state=st, xg_delta=delta))
                for idx, v in ((0, v1), (1, v2)):
                    tal[key][idx].add(v)
                    cell_rows[idx].append(((minute_band(minute), st), key, v))
    baseline_n = sum(len(v) for v in grid_samples.values())

    # ---- motor tikleri --------------------------------------------------- #
    strict: list[TickObservation] = []
    loose: list[TickObservation] = []
    shape: list[TickObservation] = []
    shape_states: list[ShapeState] = []
    states: list[TickState] = []
    eng_sub_minutes: dict[int, list[float]] = defaultdict(list)
    fc_samples: list[tuple[float, bool, float]] = []
    cal_samples: list[tuple[float, bool]] = []
    raw_conf_samples: list[tuple[float, bool]] = []   # kalibre edilmemiş ham kanıt skoru
    applied_t = applied_f = 0

    for d in decisions:
        mid = d.match_external_id
        if mid not in coach_subs:
            continue
        ctx = _ctx(d)
        is_sub = d.decision_type == "substitution"
        # Panel sinyali (enrich ile yazılır) varsa doğrudan o; yoksa külliyat
        # kaydındaki birincil/destekleyici anahtarlardan çıkarım.
        fired = ctx.get("sub_signal_fired")
        has_sub_signal = (bool(fired) if isinstance(fired, bool)
                          else is_sub or SUB_SIGNAL_KEY in (ctx.get("supporting_keys") or []))
        acted_sub = _acted(d.minute, coach_subs[mid], args.window)
        acted_shift = _acted(d.minute, coach_shifts.get(mid, []), args.window)
        as_of = _asof(goals.get(mid, []), d.minute, args.team)
        subs_used = sum(1 for c in coach_all_subs.get(mid, []) if c <= d.minute)
        strict.append(TickObservation(mid, d.minute, is_sub, acted_sub))
        loose.append(TickObservation(mid, d.minute, has_sub_signal, acted_sub))
        shape_flag = ctx.get("theme") == "adjust_shape"
        shape.append(TickObservation(mid, d.minute, shape_flag, acted_shift))
        shape_states.append(ShapeState(
            mid, d.minute, score_state=as_of, subs_used=subs_used,
            engine_flag=shape_flag,
            support_count=len(ctx.get("supporting_keys") or []),
            coach_acted=acted_shift,
        ))
        states.append(TickState(
            mid, d.minute, score_state=as_of, subs_used=subs_used, coach_acted=acted_sub,
        ))
        if has_sub_signal:
            eng_sub_minutes[mid].append(d.minute)

        if d.outcome in {"positive", "negative"} and d.confidence is not None:
            ok = d.outcome == "positive"
            # ECE yalnız KALİBRE olasılıkta anlamlı. Ham kanıt skoru (kalibrasyon
            # kurulmadıysa saklanan sayı) olasılık değildir; panel de bunu yüzde
            # olarak göstermez. Olasılık gibi okuyup ECE hesaplamak ölçüm hatası olur.
            (cal_samples if ctx.get("calibrated") else raw_conf_samples).append((float(d.confidence), ok))
            pre = ctx.get("pre_xg_diff")
            if pre is not None:
                fc_samples.append((float(d.confidence), ok, float(pre)))
        if d.applied is True:
            applied_t += 1
        elif d.applied is False:
            applied_f += 1

    # ---- "kim": antrenörün çıkardığı oyuncu motorun listesinde miydi? ----- #
    cand_by_tick: dict[tuple[int, float], tuple[int, ...]] = {}
    for d in decisions:
        cands = _ctx(d).get("sub_candidates")
        if isinstance(cands, list):
            cand_by_tick[(d.match_external_id, d.minute)] = tuple(int(c) for c in cands)
    who_samples: list[WhoSample] = []
    who_states: list[WhoState] = []
    for mid, moves in moves_by_match.items():
        # değişiklikle giren oyuncu çıkanın mevkisini devralır (diziliş olayı yoksa)
        pos = dict(positions.get(mid, {}))
        for mv in sorted(moves, key=lambda x: x.minute):
            if (mv.kind == "substitution" and mv.player_on is not None
                    and mv.player_off is not None and mv.player_on not in pos
                    and mv.player_off in pos):
                pos[mv.player_on] = pos[mv.player_off]
        for mv in moves:
            if (mv.team_external_id != args.team or mv.kind != "substitution"
                    or not mv.tactical or mv.player_off is None):
                continue
            prior_ticks = sorted(
                t for (m_id, t) in cand_by_tick
                if m_id == mid and mv.minute - args.lookback <= t < mv.minute
            )
            if not prior_ticks:
                continue
            # Bu dakikada sahaya GİREN oyuncu aday değildir — aynı anda çıkamaz.
            # Aynı dakikada çıkan başka bir oyuncu adaydır (o an hâlâ sahadaydı).
            # Dahil etmek aday havuzunu her hamlede en az 1 şişiriyor ve rastgele
            # tabanı (k/n) düşürüyordu; bkz. docs/KARNE-KIM-BAGIMSIZ.md.
            on_pitch = tuple(
                int(a["player_external_id"]) for a in appearances.get(mid, [])
                if a["start_minute"] < mv.minute
                and (a["end_minute"] is None or a["end_minute"] >= mv.minute)
            )
            who_samples.append(WhoSample(
                player_off=int(mv.player_off),
                candidates=cand_by_tick[(mid, prior_ticks[-1])],
                on_pitch=on_pitch,
            ))
            starters = {int(a["player_external_id"]) for a in appearances.get(mid, [])
                        if a["start_minute"] == 0.0}
            who_states.append(WhoState(mid, int(mv.player_off), tuple(
                WhoCandidate(pid, position_group(pos.get(pid, 0)), pid in starters)
                for pid in on_pitch
            )))
    who = who_agreement(who_samples)
    who_prior = split_half_who_prior(who_states)

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
        raw_ece, raw_mean, raw_hit = expected_calibration_error(raw_conf_samples)
        if raw_ece is not None and raw_mean is not None and raw_hit is not None:
            raw_note = (f" Ham kanıt skoru olasılık gibi okunsaydı: ECE {raw_ece:.2f}, ortalama "
                        f"{raw_mean:.0%} vs isabet {raw_hit:.0%} (n={len(raw_conf_samples)}) — "
                        "bu yüzden gösterilmiyor.")
        else:
            raw_note = ""
        dims.append(Dimension(
            "Kalibrasyon", "ECE", None, None, None, False,
            "ölçülemez — kalibre olasılık yok",
            (f"kalibre güvenli karar n={len(cal_samples)} < {MIN_SAMPLES}; saklanan sayı KANIT GÜCÜ, "
             "olasılık değil (kalibrasyon uygulanmış kararların geçmişinden kurulur; külliyat "
             f"uygulanmamış öneri).{raw_note}"),
        ))

    # ---- boyut 3: elit antrenörle uyum --------------------------------- #
    sh_strict = split_half_agreement(strict)
    sh_loose = split_half_agreement(loose)
    sh_shape = split_half_agreement(shape)
    sh_gate = split_half_shape_gate(shape_states)
    sh_prior = split_half_timing_prior(states)
    lt = lead_times(coach_subs, eng_sub_minutes, lookback_min=args.lookback)
    best = sh_loose if (sh_loose.engine_f1 or 0) >= (sh_strict.engine_f1 or 0) else sh_strict
    dims.append(Dimension(
        name="Elit antrenörle uyum (değişiklik)",
        metric="F1 vs saat-kuralı (ayrık yarı)",
        value=best.engine_f1, baseline=best.baseline_f1,
        skill=None, measurable=best.verdict != "yetersiz veri", verdict=best.verdict,
        note=best.note,
    ))

    dims.append(Dimension(
        name="Kim çıkacak (elit antrenörle)", metric="isabet@3 vs rastgele sahadaki",
        value=who.hit_at_k, baseline=who.baseline_at_k, skill=None,
        measurable=who.verdict != "yetersiz veri", verdict=who.verdict,
        note=(f"n={who.n} gerçek değişiklik · isabet@1 {who.hit_at_1} (rastgele "
              f"{who.baseline_at_1}) · {who.note}"),
    ))

    # ---- boyut 4: cetvel kontrolü (v1 ve v2) ----------------------------- #
    # Kabul ölçütü (önceden yazıldı): elit − plasebo ≥ RULER_MIN_GAP hem ham
    # isabette hem hücre-içi (Mantel-Haenszel) kıyasta.
    for idx, label in ((0, "v1 (mutlak xG farkı)"), (1, "v2 (duruma göre düzeltilmiş)")):
        e, pl, mo = tal["elit"][idx], tal["plasebo"][idx], tal["motor"][idx]
        mh_e, cells_e = _mh_gap(cell_rows[idx], "elit")
        mh_m, _ = _mh_gap(cell_rows[idx], "motor")
        if (e.n < MIN_SAMPLES or pl.n < MIN_SAMPLES or e.hit is None or pl.hit is None
                or mh_e is None):
            verdict = "yetersiz veri"
        elif e.hit - pl.hit >= RULER_MIN_GAP and mh_e >= RULER_MIN_GAP:
            verdict = "taban çizgisini geçiyor"
        else:
            verdict = "taban çizgisiyle aynı"
        note = f"elit {e} · plasebo {pl} · motor {mo}"
        if mh_e is not None:
            note += f" · hücre-içi fark elit {mh_e:+.3f} ({cells_e} hücre)"
        if mh_m is not None:
            note += f", motor {mh_m:+.3f}"
        dims.append(Dimension(
            name=f"Cetvel kontrolü {label}", metric="elit isabet − plasebo isabet",
            value=e.hit, baseline=pl.hit, skill=None,
            measurable=verdict != "yetersiz veri", verdict=verdict, note=note,
        ))

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
          f"{n_shifts} diziliş değişimi · taban ızgarası {baseline_n} karar-dışı an\n")
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
    for ad, sh in (("motor birincil öneri 'değişiklik' (külliyat kaydı)", sh_strict),
                   ("değişiklik sinyali yandı (panel: şimdi / paket / elit pencere)", sh_loose)):
        ea, eb, ba, bb = sh.engine_a, sh.engine_b, sh.baseline_a, sh.baseline_b
        print(f"    {ad}:")
        print(f"      motor    F1 {sh.engine_f1} · precision {ea.precision}/{eb.precision} · "
              f"recall {ea.recall}/{eb.recall} · bayrak oranı {ea.flag_rate}/{eb.flag_rate}")
        print(f"      saat     F1 {sh.baseline_f1} · precision {ba.precision}/{bb.precision} · "
              f"recall {ba.recall}/{bb.recall} · eşik {sh.threshold_for_a}/{sh.threshold_for_b} dk")
        print(f"      hüküm: {sh.verdict}")
    print("    (diziliş satırı ZAYIF VEKİL: elit diziliş değişimlerinin %74'ü değişiklikle "
          "birlikte, hiçbir durum önseli öngörmüyor; motorun 'şekil ayarla' teması "
          "taktik sinyallerin ortak çatısı — bkz. coach_benchmark doküstringi)")
    print(f"    diziliş değişimi ↔ motor 'şekil ayarla': motor F1 {sh_shape.engine_f1} vs saat "
          f"{sh_shape.baseline_f1} · motor bayrak oranı "
          f"{sh_shape.engine_a.flag_rate}/{sh_shape.engine_b.flag_rate} "
          f"(antrenör taban oranı {sh_shape.engine_a.act_rate}/{sh_shape.engine_b.act_rate}) "
          f"— {sh_shape.verdict}")
    print("    (F1 bu satırda YANILTIR: hedef nadir olduğundan hep-evet demek F1'i "
          "yükseltir; seçicilik kaldırmayla ölçülür — aşağı bkz.)")

    print()
    print("  ŞEKİL ÖNERİSİ SEÇİCİLİĞİ (kapı ayrık yarıda öğrenildi)")
    _shape_line("ham bayrak (tema)", sh_gate.raw_a, sh_gate.raw_b)
    _shape_line("kapılı bayrak (önsel ∧ destek)", sh_gate.gated_a, sh_gate.gated_b)
    pa, pb = sh_gate.prior_for_a, sh_gate.prior_for_b
    print(f"      eşikler  önsel {pa.threshold if pa.threshold is not None else '—'}/"
          f"{pb.threshold if pb.threshold is not None else '—'} · destekleyici sinyal "
          f"≥{pa.support_threshold if pa.support_threshold is not None else '—'}/"
          f"{pb.support_threshold if pb.support_threshold is not None else '—'} "
          f"(öteki yarıda {pa.fitted_on}/{pb.fitted_on} tikten)")
    print(f"      hüküm: {sh_gate.verdict} — {sh_gate.note}")
    pa, pb = sh_prior.engine_a, sh_prior.engine_b
    print("    ADAY — elit zamanlama önseli (dakika bandı × skor durumu × yapılan değişiklik, "
          "ayrık yarıda öğrenildi):")
    print(f"      önsel   F1 {sh_prior.engine_f1} · precision {pa.precision}/{pb.precision} · "
          f"recall {pa.recall}/{pb.recall} · bayrak oranı {pa.flag_rate}/{pb.flag_rate}")
    print(f"      saat    F1 {sh_prior.baseline_f1} · hüküm: {sh_prior.verdict}")
    print("    ADAY — elit 'kim çıkar' önseli (mevki grubu × ilk 11, ayrık yarıda öğrenildi):")
    print(f"      önsel   isabet@3 {who_prior.hit_at_k} · isabet@1 {who_prior.hit_at_1} · "
          f"rastgele {who_prior.baseline_at_k}/{who_prior.baseline_at_1} · n={who_prior.n}")
    print(f"      motor   isabet@3 {who.hit_at_k} · isabet@1 {who.hit_at_1} · hüküm (önsel): "
          f"{who_prior.verdict}")
    print(f"    öncü süre: {lt.moves} gerçek değişikliğin {lt.covered}'inde motor önceki "
          f"{args.lookback:.0f} dk içinde sinyal vermiş (kapsama {lt.coverage}); "
          f"ort. {lt.mean_lead_min} dk, medyan {lt.median_lead_min} dk önce")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
