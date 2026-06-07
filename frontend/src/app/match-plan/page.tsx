"use client";

/**
 * Maç Planı — pre-match planın canlı senaryo takibi. ConsoleShell çatısında.
 * Maç seç → aktif senaryo (önde/eşit/geride), eşleşme reçetesi, duran top, notlar.
 * Backend: GET /matches/{match_id}/plan/vs-live.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

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

  const plan = useSWR<PlanVsLive>(query ? `/matches/${query}/plan/vs-live` : null, apiFetch, { shouldRetryOnError: false });
  const d = plan.data;
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
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Maç Seç</h2>
        <form onSubmit={(e) => { e.preventDefault(); setQuery(search.trim()); }} style={{ display: "flex", gap: 6 }}>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Maç ID" inputMode="numeric" style={inputStyle} />
          <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Getir</button>
        </form>
      </div>

      {!query && <div className="pgdesc">Canlı senaryo için bir maç ID gir.</div>}
      {query && plan.isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {query && plan.error && <div className="pgdesc">Bu maç için kayıtlı plan yok ya da maç bulunamadı.</div>}

      {d && scen && (
        <>
          <div className="rc" style={{ margin: "0 0 12px" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
              <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "var(--dim)" }}>Aktif senaryo</span>
              <span style={{ fontSize: 22, fontWeight: 800, color: scen.v }}>{scen.label}</span>
            </div>
            <div style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.5 }}>{d.summary}</div>
          </div>

          <div className="st"><h2>Eşleşme Reçetesi</h2></div>
          <div className="rc" style={{ margin: "0 0 12px", fontSize: 13, color: "var(--ink)" }}>{d.matchup_recommendation ?? "—"}</div>

          <div className="st"><h2>Duran Top İpucu</h2></div>
          <div className="rc" style={{ margin: "0 0 12px", fontSize: 13, color: "var(--ink)" }}>{d.set_piece_hint ?? "—"}</div>

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
