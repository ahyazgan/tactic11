"use client";

/**
 * Analiz — xG Performans. ConsoleShell çatısını kullanır.
 * Beklenen gol (xG) farkı + over/underperformance. Takım ID + dönem seçimi.
 * Backend: GET /admin/teams/{team_id}/xg-difference?days={30..180}.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

interface XgResp {
  team_id: number;
  days: number;
  matches_analyzed: number;
  xg_for: number;
  xg_against: number;
  xg_difference: number;
  goals_for: number;
  goals_against: number;
  actual_goal_difference: number;
  overperformance: number;
  note?: string;
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

export default function XgConsolePage() {
  const [team, setTeam] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [days, setDays] = React.useState(90);

  const { data, isLoading, error } = useSWR<XgResp>(
    team ? `/admin/teams/${team}/xg-difference?days=${days}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  const op = data?.overperformance ?? 0;
  const opHint =
    op > 0.05 ? "Klinik bitiricilik / şans (xG üstü)" : op < -0.05 ? "İsraf / şanssızlık (xG altı)" : "Beklentiyle uyumlu";
  const has = !!data && data.matches_analyzed > 0;

  const right = (
    <>
      <div className="rc">
        <h3>Overperformance Nedir?</h3>
        <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
          Gerçek averaj − xG farkı.
          <div style={{ marginTop: 8 }}><span style={{ color: "var(--low)" }}>Pozitif</span> = xG üstünde skor (klinik/şanslı).</div>
          <div style={{ marginTop: 4 }}><span style={{ color: "var(--crit)" }}>Negatif</span> = xG altında (israf/şanssız).</div>
          <div style={{ marginTop: 8, color: "var(--dim)" }}>Sürdürülebilirlik için 0'a yakınlık beklenir.</div>
        </div>
      </div>
      {has && (
        <div className="rc">
          <h3>Gol Üretimi <span className="tiny">{data!.days}g</span></h3>
          <div className="stat"><span>Attığı</span><span className="sv">{data!.goals_for}</span></div>
          <div className="stat"><span>Yediği</span><span className="sv">{data!.goals_against}</span></div>
          <div className="stat"><span>Analiz edilen maç</span><span className="sv">{data!.matches_analyzed}</span></div>
        </div>
      )}
    </>
  );

  return (
    <ConsoleShell
      active="/xg"
      title="Analiz — xG"
      sub="Beklenen gol performansı"
      desc="Beklenen gol üretimi (xG) vs gerçek skor — over/underperformance ile gerçek verimliliği gösterir."
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

      {!team && <div className="pgdesc">Analiz için bir takım ID gir (örn. 611) ve dönem seç.</div>}
      {team && isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {error && <div className="pgdesc">xG verisi üretilemedi ya da yetki yok.</div>}
      {data?.note && <div className="pgdesc">{data.note}</div>}

      {has && (
        <>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
            <div className="kpi"><div className="kl">xG (lehte)</div><div className="kn">{data!.xg_for.toFixed(2)}</div><div className="kd">üretilen şans</div></div>
            <div className="kpi"><div className="kl">xGA (aleyhte)</div><div className="kn">{data!.xg_against.toFixed(2)}</div><div className="kd">verilen şans</div></div>
            <div className="kpi"><div className="kl">xG Farkı</div><div className="kn" style={{ color: signColor(data!.xg_difference) }}>{signed(data!.xg_difference)}</div><div className="kd">lehte − aleyhte</div></div>
            <div className="kpi"><div className="kl">Gerçek Averaj</div><div className="kn" style={{ color: signColor(data!.actual_goal_difference) }}>{signed(data!.actual_goal_difference, 0)}</div><div className="kd">attığı − yediği</div></div>
            <div className="kpi"><div className="kl">Overperformance</div><div className="kn" style={{ color: signColor(op) }}>{signed(op)}</div><div className="kd">gerçek − xG</div></div>
          </div>

          <div className="st"><h2>Yorum</h2><span className="ep">{data!.matches_analyzed} maç · {data!.days}g</span></div>
          <div className="rc" style={{ margin: 0 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
              <span style={{ fontSize: "32px", fontWeight: 800, fontFamily: "JetBrains Mono", color: signColor(op) }}>{signed(op)}</span>
              <span style={{ fontSize: "13px", color: "var(--muted)" }}>{opHint}</span>
            </div>
            <p style={{ fontSize: "12px", color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>
              Gerçek averaj − xG farkı. Pozitif = xG'nin üstünde skor (klinik/şanslı), negatif = altında (israf/şanssız).
              Sürdürülebilirlik için 0'a yakınlık beklenir.
            </p>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
