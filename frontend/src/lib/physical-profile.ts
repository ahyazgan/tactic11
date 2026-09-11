/**
 * Fiziksel profil radarı — backend attribute-percentiles aynası.
 *
 * 5 protokolde yön-duyarlı yüzdelik (0..1, 1 = havuzun en iyisi), iki havuz:
 * kadro (tüm oyuncuların SON değerleri) ve aynı mevki. Mevki normu repo'da
 * kaynaklı olarak bulunmadığından "norm" değil, kadro-içi mevki yüzdeliğidir.
 * DEMO: demoHistoryFor + demoSquad.position; production:
 * GET /physical-tests/{id}/attribute-percentiles.
 */

import { demoSquad, demoHistoryFor, demoProtocols } from "@/lib/demo-data";
import { pctRank } from "@/lib/attributes";

export const RADAR_PROTOCOLS = ["sprint_10m", "sprint_30m", "yoyo_irl1", "cmj", "vo2max"] as const;
export type RadarProto = (typeof RADAR_PROTOCOLS)[number];

export const RADAR_LABEL: Record<RadarProto, string> = {
  sprint_10m: "İvmelenme (10m)", sprint_30m: "Hız (30m)", yoyo_irl1: "Yo-Yo IR1", cmj: "Sıçrama (CMJ)", vo2max: "VO2max",
};

// players.position / demoSquad.position → tek harf kodu (backend _position_code aynası).
const POSITION_ALIAS: Record<string, string> = { GK: "G", DF: "D", MF: "M", FW: "F", G: "G", D: "D", M: "M", F: "F" };
export const POSITION_NAME: Record<string, string> = { G: "Kaleci", D: "Defans", M: "Orta saha", F: "Forvet" };
export const positionCode = (raw: string | null | undefined): string | null =>
  raw ? (POSITION_ALIAS[raw.trim().toUpperCase()] ?? null) : null;

export interface AttrPercentiles {
  player_id: string;
  percentiles: Record<string, number>;
  available: string[];
  squad_pool_n: Record<string, number>;
  position: string | null;
  position_percentiles: Record<string, number>;
  position_pool_n: Record<string, number>;
}

export interface ProfileRow {
  protocol: RadarProto;
  label: string;
  value: number | null;
  unit: string;
  higher_is_better: boolean;
  squad_pct: number | null;      // 0..100
  squad_n: number;
  position_pct: number | null;   // 0..100
  position_n: number;
}

/** Demo: bir oyuncunun 5 protokolde kadro + mevki yüzdeliği (backend ile aynı kural). */
export function demoAttrPercentiles(playerId: number): AttrPercentiles {
  const me = demoSquad.find((p) => p.player_id === playerId);
  const myPos = positionCode(me?.position);
  const latestOf = (pid: number, proto: string): number | null => {
    const h = demoHistoryFor(pid).filter((t) => t.protocol === proto).sort((a, b) => a.test_date.localeCompare(b.test_date));
    return h.length ? h[h.length - 1].value : null;
  };
  const out: AttrPercentiles = {
    player_id: String(playerId), percentiles: {}, available: [], squad_pool_n: {},
    position: myPos, position_percentiles: {}, position_pool_n: {},
  };
  for (const proto of RADAR_PROTOCOLS) {
    const p = demoProtocols.find((x) => x.key === proto);
    if (!p) continue;
    const my = latestOf(playerId, proto);
    if (my == null) continue;
    const pool: { pid: number; v: number }[] = [];
    for (const s of demoSquad) {
      const v = latestOf(s.player_id, proto);
      if (v != null) pool.push({ pid: s.player_id, v });
    }
    out.percentiles[proto] = Math.round(pctRank(my, pool.map((x) => x.v), p.higher_is_better) * 10000) / 10000;
    out.squad_pool_n[proto] = pool.length;
    out.available.push(proto);
    if (myPos) {
      const posPool = pool.filter((x) => positionCode(demoSquad.find((s) => s.player_id === x.pid)?.position) === myPos).map((x) => x.v);
      out.position_percentiles[proto] = Math.round(pctRank(my, posPool, p.higher_is_better) * 10000) / 10000;
      out.position_pool_n[proto] = posPool.length;
    }
  }
  return out;
}

/** API/demo cevabı + ham değerler → tablo satırları (radar bu satırlardan çizilir). */
export function profileRows(
  pct: AttrPercentiles | null,
  latestValue: (proto: RadarProto) => number | null,
): ProfileRow[] {
  return RADAR_PROTOCOLS.map((proto) => {
    const p = demoProtocols.find((x) => x.key === proto);
    const has = !!pct && pct.available.includes(proto);
    const hasPos = has && pct!.position != null && proto in pct!.position_percentiles;
    return {
      protocol: proto, label: RADAR_LABEL[proto], value: latestValue(proto),
      unit: p?.unit ?? "", higher_is_better: p?.higher_is_better ?? true,
      squad_pct: has ? Math.round(pct!.percentiles[proto] * 1000) / 10 : null,
      squad_n: has ? (pct!.squad_pool_n[proto] ?? 0) : 0,
      position_pct: hasPos ? Math.round(pct!.position_percentiles[proto] * 1000) / 10 : null,
      position_n: hasPos ? (pct!.position_pool_n[proto] ?? 0) : 0,
    };
  });
}
