"use client";

/**
 * Fiziksel Profil Radarı — bir oyuncunun 5 protokoldeki yön-duyarlı yüzdeliği,
 * iki havuz üst üste: kadro (dolgu) + aynı mevki (çizgi).
 *
 * "Mevki normu" DEĞİL: kaynaklı mevki norm tablosu yok; aynı mevkideki takım
 * arkadaşlarına göre yüzdeliktir ve havuz boyutu (n) her eksende yazılır.
 * DEMO: demoHistoryFor; production: GET /physical-tests/{id}/attribute-percentiles.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoSquad, demoHistoryFor } from "@/lib/demo-data";
import {
  demoAttrPercentiles, profileRows, RADAR_PROTOCOLS, POSITION_NAME, type AttrPercentiles, type ProfileRow, type RadarProto,
} from "@/lib/physical-profile";

const SQUAD = "var(--accent)";
const POS = "var(--high)";

const field: React.CSSProperties = {
  fontFamily: "inherit", fontSize: 12.5, padding: "6px 8px", borderRadius: 8,
  border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)",
};

/** 5 eksenli radar — kadro (dolgu) + mevki (çizgi). Saf SVG, tactical-radar kalıbı. */
function Radar({ rows, size = 280 }: { rows: ProfileRow[]; size?: number }) {
  const cx = size / 2, cy = size / 2, R = size / 2 - 52;
  const n = rows.length;
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const pt = (i: number, v: number) => {
    const r = (v / 100) * R;
    return [cx + r * Math.cos(angle(i)), cy + r * Math.sin(angle(i))];
  };
  const poly = (pick: (r: ProfileRow) => number | null) =>
    rows.map((r, i) => pt(i, pick(r) ?? 0).map((x) => x.toFixed(1)).join(",")).join(" ");
  const hasPos = rows.some((r) => r.position_pct != null);
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width="100%" height={size} style={{ display: "block", maxWidth: size, margin: "0 auto", overflow: "visible" }} role="img" aria-label="Fiziksel profil radarı">
      {[25, 50, 75, 100].map((g) => (
        <polygon key={g} points={rows.map((_, i) => pt(i, g).map((x) => x.toFixed(1)).join(",")).join(" ")}
          fill="none" stroke="var(--line)" strokeWidth={g === 100 ? 1.2 : 0.7} />
      ))}
      {rows.map((r, i) => {
        const [ex, ey] = pt(i, 100);
        const [lx, ly] = pt(i, 124);
        return (
          <g key={r.protocol}>
            <line x1={cx} y1={cy} x2={ex} y2={ey} stroke="var(--line)" strokeWidth={0.6} />
            <text x={lx} y={ly} fontSize={9.5} fill="var(--muted)" textAnchor={lx > cx + 4 ? "start" : lx < cx - 4 ? "end" : "middle"} dominantBaseline="middle">{r.label}</text>
          </g>
        );
      })}
      <polygon points={poly((r) => r.squad_pct)} fill={SQUAD} fillOpacity={0.18} stroke={SQUAD} strokeWidth={2} />
      {hasPos && <polygon points={poly((r) => r.position_pct)} fill="none" stroke={POS} strokeWidth={2} strokeDasharray="5 3" />}
      {rows.map((r, i) => { const [x, y] = pt(i, r.squad_pct ?? 0); return <circle key={"s" + i} cx={x} cy={y} r={2.4} fill={SQUAD} />; })}
      {hasPos && rows.map((r, i) => { const [x, y] = pt(i, r.position_pct ?? 0); return <circle key={"p" + i} cx={x} cy={y} r={2.4} fill={POS} />; })}
    </svg>
  );
}

export function PhysicalRadar() {
  const [pid, setPid] = React.useState(String(demoSquad[0].player_id));
  const api = useSWR<AttrPercentiles>(
    DEMO_MODE ? null : `/physical-tests/${pid}/attribute-percentiles`, apiFetch, { shouldRetryOnError: false });
  const pct: AttrPercentiles | null = DEMO_MODE ? demoAttrPercentiles(Number(pid)) : (api.data ?? null);
  const player = demoSquad.find((s) => String(s.player_id) === pid);

  const latest = (proto: RadarProto): number | null => {
    if (!DEMO_MODE) return null;   // production: ham değer bu uçta yok; yüzdelik yeter
    const h = demoHistoryFor(Number(pid)).filter((t) => t.protocol === proto).sort((a, b) => a.test_date.localeCompare(b.test_date));
    return h.length ? h[h.length - 1].value : null;
  };
  const rows = profileRows(pct, latest);
  const posName = pct?.position ? (POSITION_NAME[pct.position] ?? pct.position) : null;
  const strongest = [...rows].filter((r) => r.squad_pct != null).sort((a, b) => (b.squad_pct ?? 0) - (a.squad_pct ?? 0));

  return (
    <>
      <div className="st"><h2>Fiziksel Profil Radarı</h2><span className="ep">5 protokol · kadro ve aynı-mevki yüzdeliği</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }} data-testid="radar-panel">
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
          <select value={pid} onChange={(e) => setPid(e.target.value)} style={field} aria-label="Oyuncu">
            {demoSquad.map((s) => <option key={s.player_id} value={String(s.player_id)}>{s.player_name}</option>)}
          </select>
          {player && <span style={{ fontSize: 11.5, color: "var(--dim)" }}>{player.pos_detail}{posName ? ` · mevki havuzu: ${posName}` : " · mevki bilgisi yok"}</span>}
          <span style={{ marginLeft: "auto", fontSize: 11, display: "flex", gap: 14 }}>
            <span style={{ color: SQUAD }}>● kadro</span>
            <span style={{ color: POS }}>┅ aynı mevki</span>
          </span>
        </div>

        {!pct || !pct.available.length ? (
          <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
            {api.error ? "Bu oyuncu için fiziksel test verisi yok." : "Veri yok."}
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16, alignItems: "start" }}>
            <Radar rows={rows} />
            <div>
              <div className="tbl">
                <table>
                  <thead>
                    <tr><th>Protokol</th><th className="r">Değer</th><th className="r">Kadro %</th><th className="r">Mevki % (n)</th></tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.protocol} data-proto={r.protocol}>
                        <td>{r.label}</td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono" }}>{r.value == null ? "—" : `${r.value} ${r.unit}`}</td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono", color: SQUAD }}>{r.squad_pct == null ? "—" : `%${r.squad_pct}`}</td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono", color: POS }}>{r.position_pct == null ? "—" : `%${r.position_pct} (${r.position_n})`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {strongest.length >= 2 && (
                <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8 }}>
                  En güçlü: <b style={{ color: "var(--ink)" }}>{strongest[0].label}</b> · en zayıf: <b style={{ color: "var(--ink)" }}>{strongest[strongest.length - 1].label}</b> (kadro yüzdeliğine göre)
                </div>
              )}
              <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 6 }}>
                Yüzdelik = havuzda yendiği oyuncu oranı (yön-duyarlı; sprint'te düşük süre iyi). Mevki havuzu = aynı mevkideki takım arkadaşları;
                küçük havuzda (n ≤ 3) yüzdelik kaba bir sıradır, norm değildir. Kaynaklı mevki normu yoktur; uydurulmadı.
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
