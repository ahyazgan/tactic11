/**
 * Hedef takibi — backend assess_target aynası.
 *
 * Oyuncu/protokol hedef değeri; ilerleme oyuncunun test geçmişinden türetilir:
 * least-squares eğim (development_curve) → "bu hızla ~N ölçüm sonra".
 * Eğim için ≥3 ölçüm; N > 12 ise tempo yetersiz (off_track). İddia yoksa "yetersiz".
 * DEMO: hedefler localStorage, geçmiş demoHistoryFor; production: /physical-tests/targets.
 */

import { demoHistoryFor, demoProtocols } from "@/lib/demo-data";

export const LS_TARGETS_KEY = "fi_demo_targets";
export const TARGET_MIN_POINTS = 3;     // compute.TARGET_MIN_POINTS
export const TARGET_MAX_HORIZON = 12;   // compute.TARGET_MAX_HORIZON

export type TargetStatus = "reached" | "on_track" | "off_track" | "insufficient";
export const STATUS_ORDER: TargetStatus[] = ["off_track", "on_track", "insufficient", "reached"];
export const STATUS_LABEL: Record<TargetStatus, string> = {
  reached: "ulaşıldı", on_track: "yolda", off_track: "rotadan sapıyor", insufficient: "yetersiz veri",
};
export const STATUS_VAR: Record<TargetStatus, string> = {
  reached: "var(--low)", on_track: "var(--accent)", off_track: "var(--crit)", insufficient: "var(--mid)",
};

export interface StoredTarget {
  id: number;
  player_id: string;
  player_name: string;
  protocol: string;
  target_value: number;
  due_date: string | null;
  note: string | null;
}

export interface TargetProgress {
  current: number | null;
  current_date: string | null;
  n_points: number;
  gap: number | null;
  progress_pct: number | null;
  slope: number | null;
  tests_to_target: number | null;
  status: TargetStatus;
  progress_note: string;
}

export interface TargetRow extends StoredTarget, TargetProgress {
  protocol_name: string;
  unit: string;
  higher_is_better: boolean;
}

const round = (x: number, d: number) => Math.round(x * 10 ** d) / 10 ** d;

/** development_curve._linreg aynası: least-squares eğim, x = 0..n-1 (4 ondalık). */
export function linregSlope(values: number[]): number {
  const n = values.length;
  if (n < 2) return 0;
  const mx = (n - 1) / 2;
  const my = values.reduce((a, b) => a + b, 0) / n;
  let num = 0, den = 0;
  values.forEach((y, x) => { num += (x - mx) * (y - my); den += (x - mx) ** 2; });
  return den === 0 ? 0 : round(num / den, 4);
}

/** assess_target aynası. */
export function assessTarget(target: number, values: number[], higherIsBetter: boolean): TargetProgress {
  const base = { current_date: null, n_points: values.length };
  if (!values.length) {
    return { ...base, current: null, gap: null, progress_pct: null, slope: null, tests_to_target: null, status: "insufficient", progress_note: "ölçüm yok" };
  }
  const current = values[values.length - 1];
  const sign = higherIsBetter ? 1 : -1;
  const gap = round(sign * (target - current), 3);
  const start = values[0];
  const total = sign * (target - start);
  let progress_pct: number | null;
  if (total <= 0) progress_pct = gap <= 0 ? 100 : null;
  else progress_pct = round(Math.max(0, Math.min(100, (100 * sign * (current - start)) / total)), 1);
  if (gap <= 0) {
    return { ...base, current, gap, progress_pct: 100, slope: null, tests_to_target: 0, status: "reached", progress_note: "hedefe ulaşıldı" };
  }
  if (values.length < TARGET_MIN_POINTS) {
    return { ...base, current, gap, progress_pct, slope: null, tests_to_target: null, status: "insufficient",
      progress_note: `eğim için en az ${TARGET_MIN_POINTS} ölçüm gerekir (n=${values.length})` };
  }
  const slope = linregSlope(values);
  const rate = sign * slope;
  if (rate <= 0) {
    return { ...base, current, gap, progress_pct, slope, tests_to_target: null, status: "off_track",
      progress_note: "eğim hedefin tersine ya da düz — bu gidişle ulaşılmaz" };
  }
  const tests = Math.ceil(gap / rate);
  if (tests > TARGET_MAX_HORIZON) {
    return { ...base, current, gap, progress_pct, slope, tests_to_target: tests, status: "off_track",
      progress_note: `bu hızla ~${tests} ölçüm sonra (> ${TARGET_MAX_HORIZON}) — tempo yetersiz` };
  }
  return { ...base, current, gap, progress_pct, slope, tests_to_target: tests, status: "on_track", progress_note: `bu hızla ~${tests} ölçüm sonra` };
}

export function loadTargets(): StoredTarget[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LS_TARGETS_KEY);
    return raw ? (JSON.parse(raw) as StoredTarget[]) : [];
  } catch {
    return [];
  }
}

export function saveTargets(rows: StoredTarget[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_TARGETS_KEY, JSON.stringify(rows));
  } catch {
    /* kota/erişim — yoksay */
  }
}

/** Demo: saklanan hedefler + demoHistoryFor geçmişi → ilerleme satırları (backend sırasıyla). */
export function demoTargetRows(stored: StoredTarget[]): TargetRow[] {
  const rows: TargetRow[] = [];
  for (const t of stored) {
    const p = demoProtocols.find((x) => x.key === t.protocol);
    if (!p) continue;
    const hist = demoHistoryFor(Number(t.player_id))
      .filter((h) => h.protocol === t.protocol)
      .sort((a, b) => a.test_date.localeCompare(b.test_date));
    const prog = assessTarget(t.target_value, hist.map((h) => h.value), p.higher_is_better);
    rows.push({
      ...t, ...prog, current_date: hist.length ? hist[hist.length - 1].test_date : null,
      protocol_name: p.name, unit: p.unit, higher_is_better: p.higher_is_better,
    });
  }
  rows.sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status)
    || a.player_name.localeCompare(b.player_name, "tr") || a.protocol.localeCompare(b.protocol));
  return rows;
}
