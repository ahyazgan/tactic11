/**
 * Rating gradyanı — DESIGN.md §1 (kırmızı → sarı → yeşil, 5 durak).
 * 0-100 normalize scale. Diğer scale'ler (0-10) için caller önce normalize eder.
 */

export const RATING_THRESHOLDS = [
  { min: 0, max: 39, color: "#e5534b", token: "loss" },     // kırmızı
  { min: 40, max: 54, color: "#d97742", token: "orange" },  // turuncu
  { min: 55, max: 69, color: "#d4a72c", token: "draw" },    // sarı
  { min: 70, max: 84, color: "#7bc96f", token: "lightgreen" },
  { min: 85, max: 100, color: "#3fb950", token: "win" },    // yeşil
] as const;

export function ratingColor(value: number): string {
  const clamped = Math.max(0, Math.min(100, value));
  for (const t of RATING_THRESHOLDS) {
    if (clamped >= t.min && clamped <= t.max) return t.color;
  }
  return "#9aa1ad"; // fallback (textmut)
}

/** 0-10 scale'i 0-100'e çevir. */
export function normalize10to100(value: number): number {
  return Math.max(0, Math.min(100, value * 10));
}
