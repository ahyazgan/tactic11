"use client";

/**
 * Maç Planı — pre-match planın canlı senaryo takibi. ConsoleShell çatısında.
 * Maç seç → aktif senaryo (önde/eşit/geride), eşleşme reçetesi, duran top, notlar.
 * Backend: GET /matches/{match_id}/plan/vs-live.
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoPlan, demoWeaknesses, demoMatchups, demoScenarios, DEMO_OPPONENT } from "@/lib/demo-data";
import { demoNextMatchSimulation } from "@/lib/match-simulation";
import { demoTrackRecord } from "@/lib/track-record";
import { ConsoleShell } from "../_console/shell";
import { MatchSimBody } from "../_console/match-sim";
import { TrackRecordBadge } from "../_console/track-record";

interface PlanVsLive {
  summary: string;
  updated_at: string;
  plan_age_seconds: number;
  status: string | null;
  active_scenario: string;
  matchup_recommendation: string | null;
  set_piece_hint: string | null;
  notes: string[];
}

const SCENARIO: Record<string, { label: string; v: string }> = {
  leading: { label: "ÖNDE", v: "var(--low)" },
  level: { label: "EŞİT", v: "var(--mid)" },
  trailing: { label: "GERİDE", v: "var(--crit)" },
  unknown: { label: "BİLİNMİYOR", v: "var(--muted)" },
};

interface PreMatchIntel {
  opponent_fingerprint?: {
    top_archetype: string; label: string; description: string;
    confidence: string; summary: string; second_archetype?: string | null;
  };
  our_fingerprint?: { top_archetype: string; label: string } | null;
  counter_playbook?: { text: string; focus: string; tags: string[] }[];
  summary?: string;
}

function PreMatchIntelCard({
  ourTeamId, oppTeamId,
}: { ourTeamId: string; oppTeamId: string }): React.ReactElement | null {
  const path = `/admin/teams/${ourTeamId}/pre-match-intel`
    + `?opponent_team_id=${oppTeamId}&our_team_id=${ourTeamId}&last_n=6`;
  const { data } = useSWR<PreMatchIntel>(
    path, apiFetch, { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  if (!data?.opponent_fingerprint) return null;
  const opp = data.opponent_fingerprint;
  return (
    <div className="rc" style={{
      margin: "12px 0", padding: "12px 16px",
      borderLeft: "3px solid var(--accent)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8,
        marginBottom: 8 }}>
        <span style={{ fontSize: 14 }}>🧠</span>
        <h3 style={{ fontSize: 11.5, textTransform: "uppercase",
          letterSpacing: 0.7, color: "var(--muted)", margin: 0,
          fontWeight: 700 }}>Rakip stili + counter playbook</h3>
        <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--dim)",
          textTransform: "uppercase" }}>{opp.confidence}</span>
      </div>
      <div style={{ marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)" }}>
          {opp.label}
        </span>
        <span style={{ marginLeft: 8, fontSize: 11.5, color: "var(--muted)" }}>
          — {opp.description}
        </span>
      </div>
      {data.counter_playbook && data.counter_playbook.length > 0 && (
        <div>
          <div style={{ fontSize: 10.5, textTransform: "uppercase",
            color: "var(--muted)", letterSpacing: 0.5, marginBottom: 6,
            fontWeight: 700 }}>Counter Playbook ({data.counter_playbook.length})</div>
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {data.counter_playbook.slice(0, 4).map((a, i) => (
              <li key={i} style={{ fontSize: 12, color: "var(--ink)",
                lineHeight: 1.55, marginBottom: 4,
                paddingLeft: 14, position: "relative" }}>
                <span style={{ position: "absolute", left: 0,
                  color: "var(--accent)" }}>•</span>
                {a.text}
                <span style={{ marginLeft: 6, fontSize: 9.5,
                  color: "var(--dim)", textTransform: "uppercase" }}>
                  [{a.focus}]
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

interface PreMatchBrief {
  summary: string;
  output: {
    match_external_id: number;
    ai_brief: string;
    home_team_external_id?: number;
    away_team_external_id?: number;
    [k: string]: unknown;
  };
}

function PreMatchBriefCard({ matchId }: { matchId: string }): React.ReactElement | null {
  const { data, error, isLoading } = useSWR<PreMatchBrief>(
    `/admin/matches/${matchId}/pre-match-brief?last_n=5`, apiFetch,
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  if (isLoading) {
    return (
      <div className="rc" style={{ margin: "12px 0", padding: "10px 14px" }}>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>
          PreMatchReportAgent brief yükleniyor…
        </span>
      </div>
    );
  }
  if (error || !data) return null;
  const isStub = data.output.ai_brief?.startsWith("[stub:");
  return (
    <div className="rc" style={{
      margin: "12px 0", padding: "12px 16px",
      borderLeft: "3px solid var(--accent)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8,
        marginBottom: 6 }}>
        <span style={{ fontSize: 14 }}>🤖</span>
        <h3 style={{ fontSize: 11.5, textTransform: "uppercase",
          letterSpacing: 0.7, color: "var(--muted)", margin: 0,
          fontWeight: 700 }}>Maç-öncesi AI brief</h3>
        {isStub && (
          <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--dim)",
            textTransform: "uppercase", letterSpacing: 0.5 }}>stub</span>
        )}
      </div>
      <div style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.6,
        fontStyle: isStub ? "italic" : "normal",
        opacity: isStub ? 0.85 : 1 }}>
        {data.output.ai_brief}
      </div>
    </div>
  );
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

export default function MatchPlanConsolePage() {
  const [query, setQuery] = React.useState("");
  const [search, setSearch] = React.useState("");

  const plan = useSWR<PlanVsLive>(DEMO_MODE || !query ? null : `/matches/${query}/plan/vs-live`, apiFetch, { shouldRetryOnError: false });
  const d = DEMO_MODE ? (demoPlan as PlanVsLive) : plan.data;
  const scen = d ? SCENARIO[d.active_scenario] ?? SCENARIO.unknown : null;

  const right = (
    <div className="rc">
      <h3>Canlı Senaryo</h3>
      {d && scen ? (
        <>
          <div style={{ fontSize: 26, fontWeight: 800, color: scen.v, marginBottom: 8 }}>{scen.label}</div>
          {d.status && <div className="stat"><span>Durum</span><span className="sv">{d.status}</span></div>}
          <div className="stat"><span>Plan yaşı</span><span className="sv">{Math.round(d.plan_age_seconds)}s</span></div>
        </>
      ) : (
        <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
          Maç ID gir → planın hangi senaryosunun (önde/eşit/geride) aktif olduğunu, eşleşme reçetesini ve duran top ipucunu gösterir.
        </div>
      )}
    </div>
  );

  return (
    <ConsoleShell
      active="/match-plan"
      title="Maç Planı"
      sub="Canlı senaryo takibi"
      desc="Pre-match planın hangi senaryosu şimdi aktif, eşleşme reçetesi ve duran top ipucu."
      right={right}
    >
      {!DEMO_MODE && (
        <div className="st" style={{ marginTop: 0 }}>
          <h2>Maç Seç</h2>
          <form onSubmit={(e) => { e.preventDefault(); setQuery(search.trim()); }} style={{ display: "flex", gap: 6 }}>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Maç ID" inputMode="numeric" style={inputStyle} />
            <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Getir</button>
          </form>
        </div>
      )}

      {!DEMO_MODE && !query && <div className="pgdesc">Canlı senaryo için bir maç ID gir.</div>}
      {!DEMO_MODE && query && plan.isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {!DEMO_MODE && query && plan.error && <div className="pgdesc">Bu maç için kayıtlı plan yok ya da maç bulunamadı.</div>}
      {!DEMO_MODE && query && <PreMatchBriefCard matchId={query} />}
      {!DEMO_MODE && query && <PreMatchIntelCard ourTeamId="217" oppTeamId="206" />}

      {d && scen && (
        <>
          <div className="rc" style={{ margin: "0 0 12px" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
              <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "var(--dim)" }}>Aktif senaryo</span>
              <span style={{ fontSize: 22, fontWeight: 800, color: scen.v }}>{scen.label}</span>
            </div>
            <div style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.5 }}>{d.summary}</div>
          </div>

          {DEMO_MODE && (
            <>
              <div className="st">
                <h2>Maç Simülasyonu</h2>
                <span className="ep">Poisson · Dixon-Coles olasılık modeli</span>
              </div>
              <div className="rc" style={{ margin: "0 0 12px" }}>
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
                  <Link href="/calibration" style={{ textDecoration: "none" }}>
                    <TrackRecordBadge tr={demoTrackRecord()} type="match" />
                  </Link>
                </div>
                <MatchSimBody sim={demoNextMatchSimulation()} />
              </div>
            </>
          )}

          <div className="st"><h2>Eşleşme Reçetesi</h2></div>
          <div className="rc" style={{ margin: "0 0 12px", fontSize: 13, color: "var(--ink)" }}>{d.matchup_recommendation ?? "—"}</div>

          <div className="st"><h2>Duran Top İpucu</h2></div>
          <div className="rc" style={{ margin: "0 0 12px", fontSize: 13, color: "var(--ink)" }}>{d.set_piece_hint ?? "—"}</div>

          {DEMO_MODE && (
            <>
              <div className="st"><h2>Rakip Zaafları</h2><span className="ep">{DEMO_OPPONENT}</span></div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 12 }}>
                {demoWeaknesses.map((w, i) => {
                  const sv = w.severity === "yüksek" ? "var(--crit)" : w.severity === "orta" ? "var(--mid)" : "var(--muted)";
                  return (
                    <div className="rc" key={i} style={{ margin: 0, borderTop: `2px solid ${sv}` }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                        <b style={{ fontSize: 12.5 }}>{w.title}</b>
                        <span style={{ fontSize: 9.5, textTransform: "uppercase", color: sv }}>{w.severity}</span>
                      </div>
                      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{w.detail}</div>
                    </div>
                  );
                })}
              </div>

              <div className="st"><h2>Eşleşme Avantajı</h2></div>
              <div className="rc" style={{ margin: "0 0 12px", padding: 0, overflow: "hidden" }}>
                {demoMatchups.map((m, i) => {
                  const adv = m.advantage;
                  const c = adv >= 65 ? "var(--low)" : adv >= 50 ? "var(--mid)" : "var(--high)";
                  return (
                    <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 12, alignItems: "center", padding: "10px 14px", borderTop: i ? "1px solid var(--line)" : undefined }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 12.5, fontWeight: 600 }}>{m.ours} <span style={{ color: "var(--dim)" }}>vs</span> {m.theirs}</div>
                        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{m.note}</div>
                        <div style={{ height: 6, borderRadius: 4, background: "var(--panel3)", overflow: "hidden", marginTop: 6 }}>
                          <i style={{ display: "block", height: "100%", width: `${adv}%`, background: c }} />
                        </div>
                      </div>
                      <div style={{ fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 18, color: c }}>%{adv}</div>
                    </div>
                  );
                })}
              </div>

              <div className="st"><h2>Senaryo Planı</h2></div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 12 }}>
                {demoScenarios.map((s, i) => {
                  const sv = s.state === "Öndeyiz" ? "var(--low)" : s.state === "Berabere" ? "var(--mid)" : "var(--crit)";
                  return (
                    <div className="rc" key={i} style={{ margin: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 800, color: sv, marginBottom: 6 }}>{s.state}</div>
                      <div style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.5, marginBottom: 8 }}>{s.plan}</div>
                      <div style={{ fontSize: 11, color: "var(--muted)", borderTop: "1px solid var(--line)", paddingTop: 6 }}>
                        <span style={{ color: "var(--dim)", textTransform: "uppercase", fontSize: 9.5, letterSpacing: 0.5 }}>Değişiklik · </span>{s.subs}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          <div className="st"><h2>Notlar</h2><span className="ep">güncellendi {d.updated_at}</span></div>
          <div className="rc" style={{ margin: 0 }}>
            {d.notes.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--muted)" }}>Not yok.</div>
            ) : (
              <ul style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.7, paddingLeft: 18, margin: 0 }}>
                {d.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            )}
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
