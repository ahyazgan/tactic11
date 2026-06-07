"use client";

/**
 * Kafa Kafaya (H2H) — iki takımın geçmiş karşılaşma özeti. ConsoleShell çatısında.
 * Lig → takım kademeli seçim. Veri: /leagues, /teams/{lig}, /teams/{a}/vs/{b}.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

interface League { external_id: number; name: string }
interface Team { external_id: number; name: string }
interface H2HResult {
  value?: {
    team_a_external_id: number;
    team_b_external_id: number;
    matches_played: number;
    team_a_wins: number;
    draws: number;
    team_b_wins: number;
    team_a_goals: number;
    team_b_goals: number;
  };
  commentary?: string;
}

const selStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 9px",
  borderRadius: "7px",
  fontFamily: "inherit",
  minWidth: "140px",
};

function Sel({ value, onChange, options, placeholder, disabled }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; placeholder: string; disabled?: boolean;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} style={{ ...selStyle, opacity: disabled ? 0.5 : 1 }}>
      <option value="">{placeholder}</option>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export default function H2HConsolePage() {
  const [leagueA, setLeagueA] = React.useState("");
  const [leagueB, setLeagueB] = React.useState("");
  const [teamA, setTeamA] = React.useState("");
  const [teamB, setTeamB] = React.useState("");
  const [go, setGo] = React.useState(false);

  const { data: leagues } = useSWR<League[]>("/leagues", apiFetch, { shouldRetryOnError: false });
  const { data: teamsA } = useSWR<Team[]>(leagueA ? `/teams/${leagueA}` : null, apiFetch, { shouldRetryOnError: false });
  const { data: teamsB } = useSWR<Team[]>(leagueB ? `/teams/${leagueB}` : null, apiFetch, { shouldRetryOnError: false });
  const { data: h2h, error, isLoading } = useSWR<H2HResult>(
    go && teamA && teamB ? `/teams/${teamA}/vs/${teamB}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  const teamAName = teamsA?.find((t) => String(t.external_id) === teamA)?.name ?? "Takım A";
  const teamBName = teamsB?.find((t) => String(t.external_id) === teamB)?.name ?? "Takım B";
  const lgOpts = leagues?.map((l) => ({ value: String(l.external_id), label: l.name })) ?? [];
  const v = h2h?.value;

  const right = (
    <div className="rc">
      <h3>Nasıl Kullanılır?</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
        Her iki takım için önce lig, sonra takım seç; ardından <b style={{ color: "var(--ink)" }}>Karşılaştır</b>.
        Geçmiş karşılaşmaların galibiyet/beraberlik/gol dökümünü gösterir.
      </div>
      {v && h2h?.commentary && (
        <div style={{ fontSize: "12px", color: "var(--ink)", marginTop: 12, lineHeight: 1.5, borderTop: "1px solid var(--line)", paddingTop: 10 }}>{h2h.commentary}</div>
      )}
    </div>
  );

  return (
    <ConsoleShell
      active="/h2h"
      title="Kafa Kafaya"
      sub="Geçmiş karşılaşmalar"
      desc="İki takımın tarihsel karşılaşma özeti — galibiyet, beraberlik, gol dağılımı."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}><h2>Takım Seç</h2></div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--muted)", marginBottom: 6 }}>Takım A</div>
          <div style={{ display: "flex", gap: 6 }}>
            <Sel value={leagueA} onChange={(x) => { setLeagueA(x); setTeamA(""); }} options={lgOpts} placeholder="Lig" />
            <Sel value={teamA} onChange={setTeamA} options={teamsA?.map((t) => ({ value: String(t.external_id), label: t.name })) ?? []} placeholder="Takım" disabled={!leagueA} />
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--muted)", marginBottom: 6 }}>Takım B</div>
          <div style={{ display: "flex", gap: 6 }}>
            <Sel value={leagueB} onChange={(x) => { setLeagueB(x); setTeamB(""); }} options={lgOpts} placeholder="Lig" />
            <Sel value={teamB} onChange={setTeamB} options={teamsB?.map((t) => ({ value: String(t.external_id), label: t.name })) ?? []} placeholder="Takım" disabled={!leagueB} />
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "flex-end" }}>
          <button type="button" onClick={() => setGo(true)} disabled={!teamA || !teamB || teamA === teamB} style={{ ...selStyle, minWidth: 0, cursor: "pointer", color: "var(--ink)", background: "var(--panel3)", opacity: !teamA || !teamB || teamA === teamB ? 0.5 : 1 }}>Karşılaştır</button>
        </div>
      </div>

      {go && isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {error && <div className="pgdesc">Yüklenemedi ya da yetki yok.</div>}

      {v && (
        <>
          <div className="st"><h2>{teamAName} vs {teamBName}</h2><span className="ep">{v.matches_played} maç</span></div>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
            <div className="kpi"><div className="kl">{teamAName}</div><div className="kn" style={{ color: "var(--low)" }}>{v.team_a_wins}</div><div className="kd">{v.team_a_goals} gol</div></div>
            <div className="kpi"><div className="kl">Beraberlik</div><div className="kn" style={{ color: "var(--mid)" }}>{v.draws}</div><div className="kd">eşit</div></div>
            <div className="kpi"><div className="kl">{teamBName}</div><div className="kn" style={{ color: "var(--high)" }}>{v.team_b_wins}</div><div className="kd">{v.team_b_goals} gol</div></div>
          </div>
          <div className="pgdesc">Toplam {v.matches_played} maç oynandı.</div>
        </>
      )}
    </ConsoleShell>
  );
}
