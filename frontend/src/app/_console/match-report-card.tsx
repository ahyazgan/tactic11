"use client";

/**
 * Maç raporu — GET /tracking/matches/{id}/report.
 * Tüm maç dilimlere bölünür: özet, dilim tablosu, ortalamadan sapan dilimler ve
 * sunucunun bildirdiği sınırlar. Güvenilmez dilimler soluk gösterilir, özete girmez.
 */

import { useState } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

type Side = "home" | "away";
interface TeamSlice {
  reliable: boolean; frames_used: number; players_mean: number;
  width_m: number; depth_m: number; compactness_m: number;
  formation: string | null; press_index: number | null;
}
interface Summary { width_m: number; depth_m: number; compactness_m: number; press_index: number | null; reliable_slices: number }
interface Finding { side: Side; from_minute: number; to_minute: number; metric: string; delta: number; text: string }
interface ReportSlice { from_minute: number; to_minute: number; frames: number; home: TeamSlice; away: TeamSlice }
interface ReportResponse {
  teams: Record<Side, { team_external_id: number; summary: Summary | null }>;
  slices: ReportSlice[]; findings: Finding[]; limits: string[];
}

const SLICE_OPTIONS = [5, 10, 15] as const;
const MONO = "JetBrains Mono, monospace";
const US = "var(--accent)";
const THEM = "var(--high)";
const HEAD: React.CSSProperties = { fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 };
const CELL: React.CSSProperties = { padding: "5px 6px", textAlign: "right", fontFamily: MONO, fontSize: 11.5, whiteSpace: "nowrap" };

const num = (v: number | null | undefined, digits = 1) => (v == null ? "—" : v.toFixed(digits));
const unitOf = (metric: string) => (metric === "press_index" ? "" : " m");

function SummaryBlock({ name, color, summary }: { name: string; color: string; summary: Summary | null }) {
  return (
    <div style={{ flex: "1 1 220px", minWidth: 0 }}>
      <div style={{ ...HEAD, color }}>{name}</div>
      {summary ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 8, marginTop: 4 }}>
          {[["Genişlik", `${num(summary.width_m)} m`], ["Derinlik", `${num(summary.depth_m)} m`],
            ["Kompaktlık", `${num(summary.compactness_m)} m`], ["Pres", num(summary.press_index, 2)]].map(([label, value]) => (
            <div key={label}>
              <div style={{ fontFamily: MONO, fontSize: 15, fontWeight: 700, color: "var(--ink)" }}>{value}</div>
              <div style={{ fontSize: 10, color: "var(--muted)" }}>{label}</div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4 }}>Güvenilir dilim yok; özet verilmiyor.</div>
      )}
    </div>
  );
}

function TeamCells({ t }: { t: TeamSlice }) {
  const style = { ...CELL, color: t.reliable ? "var(--ink)" : "var(--dim)" };
  return (
    <>
      <td style={style}>{num(t.players_mean)}</td>
      <td style={style}>{num(t.width_m)}</td>
      <td style={style}>{num(t.depth_m)}</td>
      <td style={style}>{num(t.compactness_m)}</td>
      <td style={style}>{num(t.press_index, 2)}</td>
    </>
  );
}

export function MatchReportCard({ matchId, ourSide }: { matchId: number | null; ourSide: Side }) {
  const [sliceMinutes, setSliceMinutes] = useState<number>(15);
  const key = matchId != null ? `/tracking/matches/${matchId}/report?slice_minutes=${sliceMinutes}` : null;
  const { data, error, isLoading } = useSWR<ReportResponse>(key, apiFetch, { revalidateOnFocus: false, shouldRetryOnError: false, keepPreviousData: true });
  if (!matchId) return null;
  const theirSide: Side = ourSide === "home" ? "away" : "home";
  const label = (side: Side) => (side === ourSide ? "Biz" : "Rakip");
  const columns = ["Oyuncu", "Gen.", "Der.", "Komp.", "Pres"];
  return (
    <div className="rc" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Maç raporu <span style={{ fontWeight: 400, color: "var(--muted)", fontSize: 11 }}>· tüm maç, dilim dilim</span></h3>
        <label style={{ fontSize: 11, color: "var(--muted)", display: "flex", alignItems: "center", gap: 6 }}>
          Dilim
          <select value={sliceMinutes} onChange={(e) => setSliceMinutes(Number(e.target.value))}
            style={{ padding: "4px 6px", background: "var(--panel2)", color: "var(--ink)", border: "1px solid var(--line)", borderRadius: 4, fontSize: 11.5 }}>
            {SLICE_OPTIONS.map((m) => <option key={m} value={m}>{m} dk</option>)}
          </select>
        </label>
      </div>
      {error && <div style={{ fontSize: 11, color: "var(--crit)", marginTop: 6 }}>Rapor yüklenemedi: {String(error).slice(0, 120)}</div>}
      {!error && !data && isLoading && <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>Rapor hesaplanıyor…</div>}
      {data && (
        <>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginTop: 10 }}>
            <SummaryBlock name="Biz · maç ortalaması" color={US} summary={data.teams[ourSide].summary} />
            <SummaryBlock name="Rakip · maç ortalaması" color={THEM} summary={data.teams[theirSide].summary} />
          </div>

          <div style={{ ...HEAD, marginTop: 14 }}>Öne çıkanlar</div>
          {data.findings.length === 0 ? (
            <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4 }}>Hiçbir dilim maç ortalamasından eşik kadar sapmadı.</div>
          ) : (
            <ul style={{ margin: "4px 0 0", padding: 0, listStyle: "none" }}>
              {data.findings.map((f) => (
                <li key={`${f.side}-${f.from_minute}-${f.metric}`} style={{ fontSize: 12, color: "var(--ink)", padding: "3px 0" }}>
                  <span style={{ fontFamily: MONO, color: "var(--muted)" }}>{f.from_minute}–{f.to_minute}&apos;</span>{" "}
                  <span style={{ color: f.side === ourSide ? US : THEM, fontWeight: 700 }}>{label(f.side)}</span>{" "}
                  {f.text}{" "}
                  <span style={{ fontFamily: MONO, color: "var(--muted)" }}>({f.delta > 0 ? "+" : ""}{f.delta}{unitOf(f.metric)})</span>
                </li>
              ))}
            </ul>
          )}

          <div style={{ overflowX: "auto", marginTop: 14 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 560 }}>
              <thead>
                <tr>
                  <th style={{ ...HEAD, textAlign: "left", padding: "4px 6px" }} rowSpan={2}>Dakika</th>
                  <th style={{ ...HEAD, color: US, textAlign: "center", padding: "4px 6px" }} colSpan={5}>Biz</th>
                  <th style={{ ...HEAD, color: THEM, textAlign: "center", padding: "4px 6px", borderLeft: "1px solid var(--line)" }} colSpan={5}>Rakip</th>
                </tr>
                <tr>
                  {[ourSide, theirSide].flatMap((side) => columns.map((c) => (
                    <th key={`${side}-${c}`} style={{ ...HEAD, textAlign: "right", padding: "2px 6px" }}>{c}</th>
                  )))}
                </tr>
              </thead>
              <tbody>
                {data.slices.map((s) => (
                  <tr key={s.from_minute} style={{ borderTop: "1px solid var(--line)" }}>
                    <td style={{ ...CELL, textAlign: "left", color: "var(--muted)" }}>
                      {s.from_minute}–{s.to_minute}&apos;
                      {!(s[ourSide].reliable && s[theirSide].reliable) && <span title="Az kare ya da az görünür oyuncu" style={{ color: "var(--high)", marginLeft: 6 }}>güvenilmez</span>}
                    </td>
                    <TeamCells t={s[ourSide]} />
                    <TeamCells t={s[theirSide]} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ ...HEAD, marginTop: 14 }}>Bu raporu okurken</div>
          <ul style={{ margin: "4px 0 0", paddingLeft: 16, fontSize: 10.5, color: "var(--muted)", lineHeight: 1.6 }}>
            {data.limits.map((limit) => <li key={limit}>{limit}</li>)}
          </ul>
        </>
      )}
    </div>
  );
}
