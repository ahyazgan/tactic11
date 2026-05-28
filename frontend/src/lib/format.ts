/**
 * Format yardımcıları — DESIGN.md §4 referansı.
 */

export function ppg(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(decimals);
}

/** Gol farkı: +N veya -N veya 0 (her zaman işaretli). */
export function goalDiff(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value > 0) return `+${value}`;
  return String(value);
}

/** Yüzde, 0-1 aralığını "% N" string'e (Türkçe formata yakın). */
export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `%${Math.round(value * 100)}`;
}

/** Dakika: "67" veya "67'" — kısa form. */
export function minute(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.floor(value)}'`;
}
