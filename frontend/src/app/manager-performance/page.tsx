"use client";

/**
 * TD Performansı — beklenen puan (xPts) vs gerçek puan + maç bazlı olasılıklar.
 * ConsoleShell çatısında.
 * Backend: GET /admin/manager-performance?team_external_id={id}&days={n}.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

interface PerMatch {
  match_id: number;
  is_home: boolean;
  xpts: number;
  actual_pts: number;
  delta: number;
  p_win: number;
  p_draw: number;
  p_loss: number;
}
interface MgrResp {
  team_id: number;
  days: number;
  matches_considered: number;
  xpts: number;
  actual_points: number;
  overperformance: number;
  per_match: PerMatch[];
}

const DAYS = [30, 90, 180];

function signed(v: number, d = 2): string {
  return (v >= 0 ? "+" : "") + v.toFixed(d);
}
function signColor(v: number): string {
  return v > 0.05 ? "var(--low)" : v < -0.05 ? "var(--crit)" : "var(--muted)";
}

const inputStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 10px",
  borderRadius: "7px",
  width: "120px",
  fontFamily: "inherit",
};

export default function ManagerPerfConsolePage() {
  const [team, setTeam] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [days, setDays] = React.useState(90);

  const { data, isLoading, error } = useSWR<MgrResp>(
    team ? `/admin/manager-performance?team_external_id=${team}&days=${days}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const rows = data?.per_match ?? [];
  const has = !!data && data.matches_considered > 0;
  const op = data?.overperformance ?? 0;

  const right = (
    <div className="rc">
      <h3>Nasıl Okunur?</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
        <b style={{ color: "var(--ink)" }}>xPts</b> = maç olasılıklarından beklenen puan.
        <div style={{ marginTop: 8 }}><span style={{ color: "var(--low)" }}>Pozitif fark</span> = modelin üstünde sonuç (iyi yönetim/şans).</div>
        <div style={{ marginTop: 4 }}><span style={{ color: "var(--crit)" }}>Negatif</span> = altında sonuç.</div>
        <div style={{ marginTop: 8, color: "var(--dim)" }}>Çubuk: galibiyet / beraberlik / mağlubiyet olasılığı.</div>
      </div>
    </div>
  );

  return (
    <ConsoleShell
      active="/manager-performance"
      title="TD Performansı"
      sub="Beklenen vs gerçek puan"
      desc="Beklenen puan (xPts) vs gerçek puan. Pozitif fark = modelin üstünde sonuç (iyi yönetim/şans), negatif = altında."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Takım Seç</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <form onSubmit={(e) => { e.preventDefault(); setTeam(search.trim()); }} style={{ display: "flex", gap: 6 }}>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Takım ID" inputMode="numeric" style={inputStyle} />
            <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Getir</button>
          </form>
          <div className="seg">
            {DAYS.map((d) => (
              <button key={d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>{d}g</button>
            ))}
          </div>
        </div>
      </div>

      {!team && <div className="pgdesc">Bir takım ID gir (örn. 611) ve dönem seç.</div>}
      {team && isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {error && <div className="pgdesc">Veri üretilemedi ya da yetki yok.</div>}

      {has && (
        <>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
            <div className="kpi"><div className="kl">xPts (beklenen)</div><div className="kn">{data!.xpts.toFixed(1)}</div><div className="kd">{data!.matches_considered} maç</div></div>
            <div className="kpi"><div className="kl">Gerçek Puan</div><div className="kn">{data!.actual_points}</div><div className="kd">toplanan</div></div>
            <div className="kpi"><div className="kl">Fark</div><div className="kn" style={{ color: signColor(op) }}>{signed(op, 1)}</div><div className="kd">gerçek − xPts</div></div>
          </div>

          <div className="st"><h2>Maç Bazlı</h2><span className="ep">{data!.matches_considered} maç · {data!.days}g</span></div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th>Maç</th><th className="c">Saha</th><th>Olasılık (G/B/M)</th>
                <th className="r">xP</th><th className="r">Gerçek</th><th className="r">Fark</th>
              </tr></thead>
              <tbody>
                {rows.map((m) => (
                  <tr key={m.match_id}>
                    <td><span className="nm" style={{ fontFamily: "JetBrains Mono" }}>#{m.match_id}</span></td>
                    <td className="c" style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--dim)" }}>{m.is_home ? "Ev" : "Dep"}</td>
                    <td>
                      <span className="probbar" style={{ marginBottom: 0, width: 140 }}>
                        <i style={{ width: `${m.p_win * 100}%`, background: "var(--low)" }} />
                        <i style={{ width: `${m.p_draw * 100}%`, background: "var(--dim)" }} />
                        <i style={{ width: `${m.p_loss * 100}%`, background: "var(--high)" }} />
                      </span>
                    </td>
                    <td className="r" style={{ color: "var(--muted)" }}>{m.xpts.toFixed(1)}</td>
                    <td className="r">{m.actual_pts}p</td>
                    <td className="r" style={{ color: signColor(m.delta) }}>{signed(m.delta, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
