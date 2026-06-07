"use client";

/**
 * Antrenman Planı — takım + rakip seç → maça özel plan. ConsoleShell çatısında.
 * Lig→takım kademeli seçim. Veri: /leagues, /teams/{lig}.
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

interface League { external_id: number; name: string }
interface Team { external_id: number; name: string }

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

export default function TrainingConsolePage() {
  const [leagueA, setLeagueA] = React.useState("");
  const [leagueB, setLeagueB] = React.useState("");
  const [teamA, setTeamA] = React.useState("");
  const [teamB, setTeamB] = React.useState("");

  const { data: leagues } = useSWR<League[]>("/leagues", apiFetch, { shouldRetryOnError: false });
  const { data: teamsA } = useSWR<Team[]>(leagueA ? `/teams/${leagueA}` : null, apiFetch, { shouldRetryOnError: false });
  const { data: teamsB } = useSWR<Team[]>(leagueB ? `/teams/${leagueB}` : null, apiFetch, { shouldRetryOnError: false });
  const lgOpts = leagues?.map((l) => ({ value: String(l.external_id), label: l.name })) ?? [];
  const ready = teamA && teamB && teamA !== teamB;

  return (
    <ConsoleShell
      active="/training"
      title="Antrenman Planı"
      sub="Maça özel hazırlık"
      desc="Bizim takım + rakip seç → maça özel antrenman planı oluştur."
      right={
        <div className="rc">
          <h3>Nasıl Çalışır?</h3>
          <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
            Her iki taraf için lig→takım seç. Plan, rakibin zaaflarına göre haftalık antrenman odağını önerir.
          </div>
        </div>
      }
    >
      <div className="st" style={{ marginTop: 0 }}><h2>Takım + Rakip Seç</h2></div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--muted)", marginBottom: 6 }}>Bizim takım</div>
          <div style={{ display: "flex", gap: 6 }}>
            <Sel value={leagueA} onChange={(x) => { setLeagueA(x); setTeamA(""); }} options={lgOpts} placeholder="Lig" />
            <Sel value={teamA} onChange={setTeamA} options={teamsA?.map((t) => ({ value: String(t.external_id), label: t.name })) ?? []} placeholder="Takım" disabled={!leagueA} />
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--muted)", marginBottom: 6 }}>Rakip</div>
          <div style={{ display: "flex", gap: 6 }}>
            <Sel value={leagueB} onChange={(x) => { setLeagueB(x); setTeamB(""); }} options={lgOpts} placeholder="Lig" />
            <Sel value={teamB} onChange={setTeamB} options={teamsB?.map((t) => ({ value: String(t.external_id), label: t.name })) ?? []} placeholder="Takım" disabled={!leagueB} />
          </div>
        </div>
      </div>

      <div className="rc" style={{ margin: 0 }}>
        {ready ? (
          <Link href={`/teams/${teamA}/training-plan?opponent_id=${teamB}`} style={{ display: "inline-block", fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.5, padding: "8px 16px", borderRadius: 7, border: "1px solid var(--line)", color: "#fff", background: "var(--besiktas)", textDecoration: "none", fontWeight: 600 }}>
            Plan oluştur →
          </Link>
        ) : (
          <span style={{ display: "inline-block", fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.5, padding: "8px 16px", borderRadius: 7, border: "1px solid var(--line)", color: "var(--dim)", opacity: 0.6 }}>
            Plan oluştur → (iki farklı takım seç)
          </span>
        )}
      </div>
    </ConsoleShell>
  );
}
