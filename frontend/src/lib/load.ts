/**
 * Günlük antrenman/maç yükü → ACWR — backend engine'lerinin TS aynası.
 *
 * srpeLoad  = gps_load.srpe_session_load (Foster: RPE × süre = AU)
 * acwrFromSeries = workload.compute_workload (acute 7g / chronic 28g)
 *
 * DEMO_MODE'da seanslar localStorage'da (LS_LOAD_KEY); production'da
 * POST /physical-tests/session-load. Kaynak-agnostik: sRPE / GPS / dakika hepsi
 * aynı AU serisine yazılır, ACWR aynı hesaplanır. Hazırlık Kararı'na beslenir.
 */

import { demoSquad } from "@/lib/demo-data";

export const LS_LOAD_KEY = "fi_demo_session_loads";

export type LoadSource = "srpe" | "gps" | "minutes";

export interface LoadSession {
  id: number;
  player_id: string;
  player_name: string;
  session_date: string;     // YYYY-MM-DD
  source: LoadSource;
  load_au: number;
  rpe?: number;
  duration_min?: number;
}

/** Foster sRPE iç-yük (AU) — engine srpe_session_load aynası. */
export const srpeLoad = (rpe: number, durationMin: number) =>
  Math.round(rpe * durationMin * 10) / 10;

// GPS iç-yük (AU) — engine compute_gps_load.session_load aynası. Cihaz
// player_load varsa onu; yoksa ağırlıklı tahmin (mesafe/HSR/sprint/ivme).
const GW_DISTANCE = 0.01, GW_HSR = 0.05, GW_SPRINT = 0.08, GW_HI_EVENT = 0.5;

export interface GpsMetrics {
  total_distance_m?: number;
  hsr_distance_m?: number;
  sprint_distance_m?: number;
  accelerations?: number;
  decelerations?: number;
  player_load?: number | null;
}

export function gpsSessionLoad(m: GpsMetrics): number {
  if (m.player_load != null && m.player_load > 0) return Math.round(m.player_load * 10) / 10;
  const au =
    (m.total_distance_m ?? 0) * GW_DISTANCE +
    (m.hsr_distance_m ?? 0) * GW_HSR +
    (m.sprint_distance_m ?? 0) * GW_SPRINT +
    ((m.accelerations ?? 0) + (m.decelerations ?? 0)) * GW_HI_EVENT;
  return Math.round(au * 10) / 10;
}

const ACUTE = 7;
const CHRONIC = 28;
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

export type AcwrZone = "yetersiz" | "ideal" | "dikkat" | "yüksek_risk" | "bilinmiyor";

export interface AcwrResult {
  acwr: number | null;
  zone: AcwrZone;
  acute: number;
  chronic: number;
  days: number;
}

/** compute_workload aynası: kronolojik günlük yük → ACWR + bölge. */
export function acwrFromSeries(dailyLoads: number[]): AcwrResult {
  const n = dailyLoads.length;
  if (n < ACUTE) return { acwr: null, zone: "bilinmiyor", acute: 0, chronic: 0, days: n };
  const acute = mean(dailyLoads.slice(-ACUTE));
  const chronic = mean(dailyLoads.slice(-CHRONIC));
  if (chronic <= 0) return { acwr: null, zone: "bilinmiyor", acute, chronic, days: n };
  const acwr = Math.round((acute / chronic) * 100) / 100;
  const zone: AcwrZone =
    acwr < 0.8 ? "yetersiz" : acwr <= 1.3 ? "ideal" : acwr <= 1.5 ? "dikkat" : "yüksek_risk";
  return { acwr, zone, acute: Math.round(acute * 10) / 10, chronic: Math.round(chronic * 10) / 10, days: n };
}

export const ZONE_VAR: Record<AcwrZone, string> = {
  ideal: "var(--low)", yetersiz: "var(--mid)", dikkat: "var(--mid)",
  "yüksek_risk": "var(--crit)", bilinmiyor: "var(--dim)",
};

// ── localStorage deposu ────────────────────────────────────────────────────
export function loadSessions(): LoadSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LS_LOAD_KEY);
    return raw ? (JSON.parse(raw) as LoadSession[]) : [];
  } catch {
    return [];
  }
}

export function saveSessions(sessions: LoadSession[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_LOAD_KEY, JSON.stringify(sessions));
  } catch {
    /* kota/erişim hatası — yoksay */
  }
}

/** Oyuncunun seanslarından kronolojik günlük seri (gün başına AU toplamı). */
export function dailySeriesFor(playerId: number | string, sessions: LoadSession[]): number[] {
  const byDate: Record<string, number> = {};
  for (const s of sessions) {
    if (String(s.player_id) !== String(playerId)) continue;
    byDate[s.session_date] = (byDate[s.session_date] ?? 0) + s.load_au;
  }
  return Object.keys(byDate).sort().map((d) => byDate[d]);
}

export function acwrForPlayer(playerId: number | string, sessions: LoadSession[]): number | null {
  return acwrFromSeries(dailySeriesFor(playerId, sessions)).acwr;
}

export function acwrResultFor(playerId: number | string, sessions: LoadSession[]): AcwrResult {
  return acwrFromSeries(dailySeriesFor(playerId, sessions));
}

function dateMinus(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

/**
 * Demo: bir oyuncu için deterministik 28 günlük sRPE serisi.
 * Risk profili yüksekse son 7 gün (akut pencere) yükselir → ACWR artar.
 */
export function demoSeedSeriesFor(playerId: number): LoadSession[] {
  const p = demoSquad.find((s) => s.player_id === playerId);
  const r = p ? p.risk_score / 100 : 0.3;
  const base = 250;
  const out: LoadSession[] = [];
  const now = Date.now();
  for (let day = 0; day < 28; day++) {
    const daysAgo = 27 - day;
    const recent = day >= 21;                          // son 7 gün = akut pencere
    const spike = recent ? 1 + r * 1.2 : 1;            // riskli → akut yük sıçraması
    const wave = Math.sin((playerId + day) * 1.3) * 0.1 + 1;  // ±%10 (monotony kırar)
    const duration = 60;
    const au = Math.round(base * spike * wave * 10) / 10;
    out.push({
      id: now + day,
      player_id: String(playerId),
      player_name: p?.player_name ?? `#${playerId}`,
      session_date: dateMinus(daysAgo),
      source: "srpe",
      rpe: Math.round((au / duration) * 10) / 10,
      duration_min: duration,
      load_au: au,
    });
  }
  return out;
}
