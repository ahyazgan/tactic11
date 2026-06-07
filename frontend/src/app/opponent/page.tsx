"use client";

/**
 * Rakip Raporu — eşleşme grid: bizim güç × rakip zaaf (kanal bazlı).
 * ConsoleShell çatısında.
 * Backend: GET /admin/teams/{team_id}/matchup-grid?opponent_id={id}&last_n=5.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

interface ChannelM {
  channel: string;
  our_attacks: number;
  opp_def_actions: number;
  our_strength: number;
  opp_weakness: number;
  matchup_score: number;
  verdict: string;
}
interface GridResp {
  value?: {
    matches_analyzed: number;
    by_channel: ChannelM[];
    best_channel: string;
    worst_channel: string;
    recommendation: string;
  };
  note?: string;
}

const CHANNEL_LABEL: Record<string, string> = {
  left: "Sol kanat",
  center: "Merkez",
  right: "Sağ kanat",
  left_halfspace: "Sol yarı alan",
  right_halfspace: "Sağ yarı alan",
};
const VERDICT_VAR: Record<string, string> = {
  exploit: "var(--low)",
  neutral: "var(--muted)",
  avoid: "var(--crit)",
};
const VERDICT_LABEL: Record<string, string> = {
  exploit: "Sömür",
  neutral: "Nötr",
  avoid: "Kaçın",
};

function pct(v: number): string {
  return (v * 100).toFixed(0) + "%";
}

const inputStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 10px",
  borderRadius: "7px",
  width: "130px",
  fontFamily: "inherit",
};

export default function OpponentConsolePage() {
  const [team, setTeam] = React.useState("");
  const [opp, setOpp] = React.useState("");
  const [q, setQ] = React.useState<{ t: string; o: string } | null>(null);

  const { data, isLoading, error } = useSWR<GridResp>(
    q ? `/admin/teams/${q.t}/matchup-grid?opponent_id=${q.o}&last_n=5` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const v = data?.value;

  const right = v ? (
    <div className="rc">
      <h3>Koridor Önerisi <span className="tiny">{v.matches_analyzed} maç</span></h3>
      <div className="stat"><span style={{ color: "var(--low)", fontWeight: 700 }}>En iyi</span><span className="sv">{CHANNEL_LABEL[v.best_channel] ?? v.best_channel}</span></div>
      <div className="stat"><span style={{ color: "var(--crit)", fontWeight: 700 }}>En zayıf</span><span className="sv">{CHANNEL_LABEL[v.worst_channel] ?? v.worst_channel}</span></div>
      <div style={{ fontSize: "12.5px", color: "var(--ink)", marginTop: 12, lineHeight: 1.5 }}>{v.recommendation}</div>
    </div>
  ) : (
    <div className="rc">
      <h3>Nasıl Çalışır?</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
        Kanal bazlı eşleşme: bizim güç (final üçte-bir girişleri) × rakip zaaf (savunma aksiyonu boşluğu). Sömürülecek koridoru bulur.
      </div>
    </div>
  );

  return (
    <ConsoleShell
      active="/opponent"
      title="Rakip Raporu"
      sub="Eşleşme grid"
      desc="Kanal bazlı eşleşme: bizim güç × rakip zaaf. Sömürülecek koridoru bulur."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Eşleşme</h2>
        <form onSubmit={(e) => { e.preventDefault(); if (team.trim() && opp.trim()) setQ({ t: team.trim(), o: opp.trim() }); }} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <input value={team} onChange={(e) => setTeam(e.target.value)} placeholder="Bizim takım ID" inputMode="numeric" style={inputStyle} />
          <span style={{ color: "var(--dim)" }}>vs</span>
          <input value={opp} onChange={(e) => setOpp(e.target.value)} placeholder="Rakip ID" inputMode="numeric" style={inputStyle} />
          <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Analiz et</button>
        </form>
      </div>

      {!q && <div className="pgdesc">İki takım ID gir (bizim + rakip).</div>}
      {q && isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {error && <div className="pgdesc">Analiz üretilemedi ya da yetki yok.</div>}
      {data?.note && <div className="pgdesc">{data.note}</div>}

      {v && (
        <>
          <div className="st"><h2>Kanal Analizi</h2><span className="ep">{v.matches_analyzed} maç</span></div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th>Kanal</th><th className="r">Bizim Güç</th><th className="r">Rakip Zaaf</th><th className="r">Skor</th><th className="c">Karar</th>
              </tr></thead>
              <tbody>
                {v.by_channel.map((c) => {
                  const vc = VERDICT_VAR[c.verdict] ?? "var(--muted)";
                  return (
                    <tr key={c.channel}>
                      <td><span className="nm">{CHANNEL_LABEL[c.channel] ?? c.channel}</span></td>
                      <td className="r" style={{ color: "var(--muted)" }}>{pct(c.our_strength)}</td>
                      <td className="r" style={{ color: "var(--muted)" }}>{pct(c.opp_weakness)}</td>
                      <td className="r" style={{ color: "var(--ink)" }}>{(c.matchup_score * 100).toFixed(0)}</td>
                      <td className="c"><span style={{ fontSize: "10px", textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: `1px solid ${vc}`, color: vc }}>{VERDICT_LABEL[c.verdict] ?? c.verdict}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
