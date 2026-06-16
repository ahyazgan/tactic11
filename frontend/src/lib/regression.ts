/**
 * Regresyon erken uyarısı — backend interpret_progression/detect_anomalies aynası.
 *
 * Test trendinde ani düşüş (form kırılması): son 3 ölçüm vs önceki 3, fark ≥1σ
 * ve iyi-yönün tersineyse → regresyon (sakatlık/aşırı yük erken-uyarı). Mirror
 * birebir: BREAK_WINDOW=3, BREAK_SIGMA=1.0, pstdev (development_curve eğimi
 * regression_alert'i etkilemez, sadece anomaly break). DEMO: zengin seri üretir;
 * production: gerçek test geçmişi (squad-readiness backend).
 */

import { demoSquad } from "@/lib/demo-data";

const BREAK_WINDOW = 3;
const BREAK_SIGMA = 1.0;
const mean = (a: number[]) => a.reduce((x, y) => x + y, 0) / a.length;

export interface RegressionSeries {
  protocol: string;
  values: number[];
  higherIsBetter: boolean;
}

/** detect_anomalies break + interpret_progression regression mantığı (aynı). */
export function detectRegression(values: number[], higherIsBetter: boolean): boolean {
  const n = values.length;
  if (n < BREAK_WINDOW * 2) return false;
  const m = mean(values);
  const stdev = Math.sqrt(mean(values.map((v) => (v - m) ** 2))); // pstdev
  if (stdev <= 0) return false;
  const recent = values.slice(-BREAK_WINDOW);
  const prior = values.slice(-BREAK_WINDOW * 2, -BREAK_WINDOW);
  const diff = mean(recent) - mean(prior);
  if (Math.abs(diff) < BREAK_SIGMA * stdev) return false;
  const direction = diff > 0 ? "yükseliş" : "düşüş";
  return (direction === "düşüş") === higherIsBetter;
}

/**
 * Demo: risk profiline göre 8 noktalı CMJ serisi (yüksek iyi). risk>0.5 →
 * son 3 ölçümde belirgin düşüş → regresyon; düşük risk düz → bayrak yok.
 */
export function demoRegressionSeriesFor(playerId: number): RegressionSeries[] {
  const p = demoSquad.find((s) => s.player_id === playerId);
  const r = p ? p.risk_score / 100 : 0;
  const base = 50;
  const drop = Math.max(0, r - 0.5) * 24; // sadece risk>0.5 → akut düşüş
  const values: number[] = [];
  for (let i = 0; i < 8; i++) {
    const recent = i >= 5; // son 3 nokta
    values.push(Math.round((base - (recent ? drop : 0)) * 10) / 10);
  }
  return [{ protocol: "CMJ", values, higherIsBetter: true }];
}
