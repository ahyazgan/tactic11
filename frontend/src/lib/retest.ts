/**
 * Re-test kadro kıyası — backend assess_change/retest_outcome aynası.
 *
 * Antrenman bloğu öncesi (split tarihinden ÖNCEKİ ölçümler = bireysel baseline)
 * ile sonrası (split ve sonrası SON ölçüm) kıyaslanır. Eşik oyuncunun KENDİ
 * gürültüsü: SWC = 0.2 × baseline SD (Cohen küçük etki). |delta| < SWC →
 * "değişim yok". Baseline < 3 ölçüm → "yetersiz" (iddia üretilmez).
 * DEMO: demoHistoryFor; production: GET /physical-tests/retest?protocol=&split=.
 */

import { demoSquad, demoHistoryFor, demoProtocols } from "@/lib/demo-data";

export const SWC_FACTOR = 0.2;            // compute.SWC_FACTOR
export const RETEST_MIN_BASELINE = 3;     // compute.RETEST_MIN_BASELINE

export type RetestCategory = "declined" | "improved" | "unchanged" | "insufficient";
export const RETEST_ORDER: RetestCategory[] = ["declined", "improved", "unchanged", "insufficient"];

export const CATEGORY_LABEL: Record<RetestCategory, string> = {
  declined: "gerileme", improved: "gelişme", unchanged: "değişim yok", insufficient: "yetersiz baseline",
};
export const CATEGORY_VAR: Record<RetestCategory, string> = {
  declined: "var(--crit)", improved: "var(--low)", unchanged: "var(--dim)", insufficient: "var(--mid)",
};

const round3 = (x: number) => Math.round(x * 1000) / 1000;

/** statistics.pstdev aynası (popülasyon SD). */
function pstdev(xs: number[]): number {
  const m = xs.reduce((a, b) => a + b, 0) / xs.length;
  return Math.sqrt(xs.reduce((a, b) => a + (b - m) * (b - m), 0) / xs.length);
}

/** smallest_worthwhile_change aynası. */
export function smallestWorthwhileChange(baseline: number[], factor = SWC_FACTOR): number {
  if (baseline.length < 2) return 0;
  return round3(factor * pstdev(baseline));
}

export interface RetestRow {
  player_id: string;
  player_name: string;
  baseline_n: number;
  baseline_mean: number | null;
  swc: number | null;
  current: number;
  current_date: string;
  delta: number | null;
  delta_pct: number | null;
  category: RetestCategory;
  verdict: string;
}

export interface RetestComparison {
  protocol: string;
  protocol_name: string;
  unit: string;
  higher_is_better: boolean;
  split: string;
  min_baseline: number;
  n: number;
  improved: number;
  declined: number;
  unchanged: number;
  insufficient: number;
  rows: RetestRow[];
}

/** retest_outcome + assess_change aynası: tek oyuncu için satır üretir. */
export function retestRow(
  base: { player_id: string; player_name: string; current: number; current_date: string },
  baseline: number[], higherIsBetter: boolean,
): RetestRow {
  if (baseline.length < RETEST_MIN_BASELINE) {
    return {
      ...base, baseline_n: baseline.length, baseline_mean: null, swc: null,
      delta: null, delta_pct: null, category: "insufficient",
      verdict: `yetersiz baseline (n=${baseline.length} < ${RETEST_MIN_BASELINE})`,
    };
  }
  const mean = round3(baseline.reduce((a, b) => a + b, 0) / baseline.length);
  const swc = smallestWorthwhileChange(baseline);
  const delta = round3(base.current - mean);
  const beyond = swc > 0 && Math.abs(delta) >= swc;
  let category: RetestCategory;
  let verdict: string;
  if (!beyond) { category = "unchanged"; verdict = "değişim yok (SWC altı — ölçüm gürültüsü olabilir)"; }
  else if ((delta > 0) === higherIsBetter) { category = "improved"; verdict = "anlamlı gelişme"; }
  else { category = "declined"; verdict = "anlamlı düşüş — kontrol et"; }
  return {
    ...base, baseline_n: baseline.length, baseline_mean: mean, swc, delta,
    delta_pct: mean ? Math.round((1000 * delta) / mean) / 10 : null, category, verdict,
  };
}

// demoHistoryFor'un ürettiği protokoller (kıyaslanabilir olanlar).
export const RETEST_PROTOCOLS = ["sprint_10m", "sprint_30m", "yoyo_irl1", "cmj", "vo2max"];
// Demo test tarihleri 2026-05-09 … 2026-06-05; varsayılan split: son 2 ölçüm blok sonrası.
export const DEMO_DEFAULT_SPLIT = "2026-05-30";

/** Demo: bir protokolde blok öncesi/sonrası kadro kıyası (backend sırasıyla). */
export function demoRetestComparison(protocolKey: string, split: string): RetestComparison | null {
  const p = demoProtocols.find((x) => x.key === protocolKey);
  if (!p) return null;
  const rows: RetestRow[] = [];
  for (const player of demoSquad) {
    const hist = demoHistoryFor(player.player_id)
      .filter((t) => t.protocol === protocolKey)
      .sort((a, b) => a.test_date.localeCompare(b.test_date));
    const baseline = hist.filter((t) => t.test_date < split).map((t) => t.value);
    const after = hist.filter((t) => t.test_date >= split);
    const last = after[after.length - 1];
    if (!last) continue;
    rows.push(retestRow(
      { player_id: String(player.player_id), player_name: player.player_name, current: last.value, current_date: last.test_date },
      baseline, p.higher_is_better,
    ));
  }
  rows.sort((a, b) => RETEST_ORDER.indexOf(a.category) - RETEST_ORDER.indexOf(b.category)
    || a.player_name.localeCompare(b.player_name, "tr"));
  const count = (c: RetestCategory) => rows.filter((r) => r.category === c).length;
  return {
    protocol: protocolKey, protocol_name: p.name, unit: p.unit, higher_is_better: p.higher_is_better,
    split, min_baseline: RETEST_MIN_BASELINE, n: rows.length,
    improved: count("improved"), declined: count("declined"), unchanged: count("unchanged"), insufficient: count("insufficient"),
    rows,
  };
}
