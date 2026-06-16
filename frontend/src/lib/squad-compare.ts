/**
 * Kadro karşılaştırma / yüzdelik — backend score_test/squad_percentile aynası.
 *
 * Bir protokolde kadronun SON değerlerini sıralar; her oyuncu için norm rating
 * (elit/iyi/ortalama/zayıf) + kadro-içi yüzdelik (100 = en iyi, yön-duyarlı).
 * DEMO: demoHistoryFor'dan; production: GET /physical-tests/squad-comparison.
 */

import { demoSquad, demoHistoryFor, demoProtocols, type ProtocolInfo } from "@/lib/demo-data";

export type Rating = "elit" | "iyi" | "ortalama" | "zayıf";

export const RATING_VAR: Record<Rating, string> = {
  elit: "var(--low)", iyi: "var(--low)", ortalama: "var(--mid)", "zayıf": "var(--crit)",
};

/** rate_against_norms aynası: norm bantlarına göre etiket (yön-duyarlı). */
export function rateAgainstNorms(value: number, p: ProtocolInfo): Rating {
  if (p.higher_is_better) {
    if (value >= p.norm_elite) return "elit";
    if (value >= p.norm_good) return "iyi";
    if (value >= p.norm_average) return "ortalama";
  } else {
    if (value <= p.norm_elite) return "elit";
    if (value <= p.norm_good) return "iyi";
    if (value <= p.norm_average) return "ortalama";
  }
  return "zayıf";
}

/** squad_percentile aynası: kadronun yüzde kaçından iyi (100 = en iyi). */
export function squadPercentile(value: number, refs: number[], higherIsBetter: boolean): number | null {
  if (!refs.length) return null;
  const worse = higherIsBetter
    ? refs.filter((r) => r < value).length
    : refs.filter((r) => r > value).length;
  return Math.round((100 * worse) / refs.length * 10) / 10;
}

export interface CompareRow {
  player_id: string;
  player_name: string;
  value: number;
  rating: Rating;
  percentile: number | null;
}

export interface SquadComparison {
  protocol: string;
  protocol_name: string;
  unit: string;
  higher_is_better: boolean;
  n: number;
  rows: CompareRow[];
}

// demoHistoryFor'un ürettiği protokoller (karşılaştırılabilir olanlar).
export const COMPARABLE_PROTOCOLS = ["sprint_10m", "sprint_30m", "yoyo_irl1", "cmj", "vo2max"];

/** Demo: bir protokolde kadronun son değerleri → sıralı karşılaştırma. */
export function demoSquadComparison(protocolKey: string): SquadComparison | null {
  const p = demoProtocols.find((x) => x.key === protocolKey);
  if (!p) return null;

  const raw: { player_id: string; player_name: string; value: number }[] = [];
  for (const player of demoSquad) {
    const hist = demoHistoryFor(player.player_id)
      .filter((t) => t.protocol === protocolKey)
      .sort((a, b) => a.test_date.localeCompare(b.test_date));
    const latest = hist[hist.length - 1];
    if (latest) raw.push({ player_id: String(player.player_id), player_name: player.player_name, value: latest.value });
  }

  const refs = raw.map((r) => r.value);
  const rows: CompareRow[] = raw.map((r) => ({
    ...r,
    rating: rateAgainstNorms(r.value, p),
    percentile: squadPercentile(r.value, refs, p.higher_is_better),
  }));
  rows.sort((a, b) => (p.higher_is_better ? b.value - a.value : a.value - b.value));

  return {
    protocol: protocolKey, protocol_name: p.name, unit: p.unit,
    higher_is_better: p.higher_is_better, n: rows.length, rows,
  };
}
