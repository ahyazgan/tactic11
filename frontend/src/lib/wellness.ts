/**
 * Öznel günlük hazırlık (wellness) — backend engine.wellness aynası.
 *
 * 5 madde (uyku/yorgunluk/kas ağrısı/stres/ruh hali, 1-7) → readiness 0..1 →
 * zone (hazır≥0.70 / izle≥0.55 / dikkat). ACWR (objektif yük) ile birlikte
 * Hazırlık Kararı'nın öznel yarısı. DEMO: localStorage; production: POST
 * /physical-tests/wellness. squad-readiness her oyuncunun EN SON anketini kullanır.
 */

import { demoSquad } from "@/lib/demo-data";

export const LS_WELLNESS_KEY = "fi_demo_wellness";

export interface WellnessEntry {
  id: number;
  player_id: string;
  player_name: string;
  entry_date: string;     // YYYY-MM-DD
  sleep_quality: number;  // 1-7
  fatigue: number;        // 1-7 (7 = dinç)
  muscle_soreness: number; // 1-7 (7 = ağrısız)
  stress: number;         // 1-7 (7 = sakin)
  mood: number;           // 1-7
  readiness: number;      // 0..1
}

const READY = 0.7;
const MONITOR = 0.55;

export type WellnessZone = "hazır" | "izle" | "dikkat";

export interface WellnessFields {
  sleep_quality: number; fatigue: number; muscle_soreness: number; stress: number; mood: number;
}

export function wellnessReadiness(v: WellnessFields): number {
  const total = v.sleep_quality + v.fatigue + v.muscle_soreness + v.stress + v.mood;
  return Math.round((total / 35) * 1000) / 1000;
}

export function wellnessZone(readiness: number): WellnessZone {
  return readiness >= READY ? "hazır" : readiness >= MONITOR ? "izle" : "dikkat";
}

export const WZONE_VAR: Record<WellnessZone, string> = {
  "hazır": "var(--low)", "izle": "var(--mid)", "dikkat": "var(--crit)",
};

export function loadWellness(): WellnessEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LS_WELLNESS_KEY);
    return raw ? (JSON.parse(raw) as WellnessEntry[]) : [];
  } catch {
    return [];
  }
}

export function saveWellness(entries: WellnessEntry[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_WELLNESS_KEY, JSON.stringify(entries));
  } catch {
    /* kota/erişim — yoksay */
  }
}

/** Oyuncunun EN SON wellness anketi (tarih sonra id'ye göre). */
export function latestWellnessFor(
  playerId: number | string, entries: WellnessEntry[],
): WellnessEntry | null {
  const mine = entries
    .filter((e) => String(e.player_id) === String(playerId))
    .sort((a, b) => b.entry_date.localeCompare(a.entry_date) || b.id - a.id);
  return mine[0] ?? null;
}

const clamp17 = (n: number) => Math.max(1, Math.min(7, Math.round(n)));

/**
 * Demo: tüm kadroya deterministik bir günlük anket üret (risk yüksekse wellness
 * düşük). Tek tıkla pano öznel readiness'le dolar.
 */
export function demoSeedWellnessAll(entryDate: string): WellnessEntry[] {
  const now = Date.now();
  return demoSquad.map((p, i) => {
    const r = p.risk_score / 100;
    const val = (k: number) => clamp17(7 - r * 5 + Math.sin((p.player_id + k) * 1.4) * 0.8);
    const fields: WellnessFields = {
      sleep_quality: val(0), fatigue: val(1), muscle_soreness: val(2),
      stress: val(3), mood: val(4),
    };
    return {
      id: now + i,
      player_id: String(p.player_id),
      player_name: p.player_name,
      entry_date: entryDate,
      ...fields,
      readiness: wellnessReadiness(fields),
    };
  });
}
