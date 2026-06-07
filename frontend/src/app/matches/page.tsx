"use client";

/**
 * Maç — Yaklaşan Maçlar. ConsoleShell çatısını kullanır.
 * Takım programından yaklaşan maçlar (kickoff listesi) + sıradaki maç kartı.
 * Backend: GET /teams/{id}/schedule (value.next_kickoffs: ISO[]).
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

interface ScheduleResp {
  value?: { next_kickoffs?: string[] };
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

function fmt(iso: string): { date: string; time: string } {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return { date: iso.slice(0, 10), time: iso.slice(11, 16) };
  return {
    date: d.toLocaleDateString("tr-TR", { day: "2-digit", month: "short", weekday: "short" }),
    time: d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
  };
}

export default function MatchesConsolePage() {
  const [team, setTeam] = React.useState("611");
  const [search, setSearch] = React.useState("611");

  const { data, error, isLoading } = useSWR<ScheduleResp>(
    team ? `/teams/${team}/schedule` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  const kickoffs = (data?.value?.next_kickoffs ?? []).filter(Boolean);
  const next = kickoffs[0];
  const nextF = next ? fmt(next) : null;

  const right = (
    <div className="rc">
      <h3>Sıradaki Maç <span className="tiny">Takım #{team}</span></h3>
      <div className="nm-vs"><span className="t">#{team}</span><span className="x">vs</span><span className="t away">—</span></div>
      <div className="nm-when">{nextF ? `${nextF.date} · ${nextF.time}` : "Program verisi yok"}</div>
      <div className="probbar">
        <i style={{ width: "34%", background: "var(--low)" }} />
        <i style={{ width: "33%", background: "var(--dim)" }} />
        <i style={{ width: "33%", background: "var(--high)" }} />
      </div>
      <div className="probleg">
        <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>—</div><div className="pl">Galibiyet</div></div>
        <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>—</div><div className="pl">Berabere</div></div>
        <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>—</div><div className="pl">Mağlubiyet</div></div>
      </div>
    </div>
  );

  return (
    <ConsoleShell
      active="/matches"
      title="Maç"
      sub="Yaklaşan program"
      desc="Takım programındaki yaklaşan maçlar. Detay için maça tıkla."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Takım Programı</h2>
        <form onSubmit={(e) => { e.preventDefault(); setTeam(search.trim()); }} style={{ display: "flex", gap: 6 }}>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Takım ID" inputMode="numeric" style={inputStyle} />
          <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Getir</button>
        </form>
      </div>

      <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
        <div className="kpi"><div className="kl">Yaklaşan Maç</div><div className="kn">{kickoffs.length}</div><div className="kd">programda</div></div>
        <div className="kpi"><div className="kl">Sıradaki</div><div className="kn" style={{ fontSize: 18 }}>{nextF ? nextF.date : "—"}</div><div className="kd">{nextF ? nextF.time : "tarih yok"}</div></div>
        <div className="kpi"><div className="kl">Takım</div><div className="kn">#{team}</div><div className="kd">seçili</div></div>
      </div>

      {isLoading && <div className="pgdesc">Program yükleniyor…</div>}
      {error && <div className="pgdesc">Program verisi alınamadı (sync_league çalıştırıldı mı?).</div>}

      <div className="st"><h2>Yaklaşan Maçlar</h2><span className="ep">GET /teams/{team}/schedule</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th><th>Tarih</th><th className="c">Saat</th><th>Eşleşme</th><th className="r">Detay</th>
          </tr></thead>
          <tbody>
            {kickoffs.length === 0 && (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                Maç yok (backend bağlı değilse veya program boşsa).
              </td></tr>
            )}
            {kickoffs.map((iso, i) => {
              const f = fmt(iso);
              const mid = 1000 + i;
              return (
                <tr key={mid}>
                  <td className="pnum c">{i + 1}</td>
                  <td><span className="nm">{f.date}</span></td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{f.time}</td>
                  <td><span className="nm">#{team}</span> <span className="nat">vs —</span></td>
                  <td className="r">
                    <Link href={`/matches/${mid}`} style={{ color: "var(--low)", textDecoration: "none", fontSize: 12, fontWeight: 600 }}>Detay →</Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
