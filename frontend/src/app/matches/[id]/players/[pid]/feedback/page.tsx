"use client";

/**
 * Oyuncu Maç Feedback — metrikler + alt-optimal pas örnekleri + AI brief.
 * ConsoleShell çatısında. MiniPitch görseli korunur.
 * Backend: GET /admin/matches/{id}/players/{pid}/feedback.
 */

import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { MiniPitch } from "@/components/charts/MiniPitch";
import { ConsoleShell } from "../../../../../_console/shell";

interface SuboptimalPass {
  minute: number;
  start: [number, number];
  actual_end: [number, number];
  best_alternative: { x: number; y: number; delta: number };
  completed: boolean;
}
interface FeedbackResponse {
  match_external_id?: number;
  player_external_id?: number;
  minutes_played?: number;
  events_loaded?: number;
  metrics?: {
    xt_per_90: number | null;
    xa_per_90: number | null;
    vaep_per_90: number | null;
    progressive_per_90: number | null;
    press_resistance_under_press: number;
    overperformance_total: number;
    overperformance_label: string;
  };
  pass_alternatives_summary?: {
    passes_analyzed: number;
    mean_best_delta: number;
    suboptimal_share: number;
    top_suboptimal: SuboptimalPass[];
  };
  ai_brief?: string;
  note?: string;
}

function opVar(label?: string): string {
  if (label === "clinical") return "var(--low)";
  if (label === "underperforming") return "var(--crit)";
  return "var(--muted)";
}

export default function PlayerFeedbackConsolePage() {
  const params = useParams<{ id: string; pid: string }>();
  const matchId = params.id;
  const playerId = params.pid;

  const { data, error, isLoading } = useSWR<FeedbackResponse>(
    `/admin/matches/${matchId}/players/${playerId}/feedback`,
    apiFetch,
    { shouldRetryOnError: false },
  );

  const title = `Oyuncu #${playerId} — Maç #${matchId}`;
  const m = data?.metrics;
  const sub = data?.pass_alternatives_summary;

  const right = (
    <div className="rc">
      <h3>Maç-Sonu Brief</h3>
      {data?.ai_brief ? (
        <div style={{ fontSize: 12.5, color: "var(--ink)", whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{data.ai_brief}</div>
      ) : (
        <div style={{ fontSize: "12px", color: "var(--dim)" }}>Brief yok.</div>
      )}
    </div>
  );

  return (
    <ConsoleShell active="/matches" title={title} sub="Maç feedback" desc={data ? `${data.minutes_played ?? 0} dk · ${data.events_loaded ?? 0} event` : "Oyuncu maç-sonu analizi."} right={right}>
      {error && <div className="pgdesc">Yüklenemedi: {String(error)}</div>}
      {isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {data?.events_loaded === 0 && <div className="pgdesc">{data.note ?? "Bu maç için event ingest yok."}</div>}

      {m && (
        <>
          <div className="st" style={{ marginTop: 0 }}><h2>Metrikler</h2></div>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(6,1fr)" }}>
            <div className="kpi"><div className="kl">xT/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.xt_per_90 ?? 0).toFixed(2)}</div></div>
            <div className="kpi"><div className="kl">xA/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.xa_per_90 ?? 0).toFixed(2)}</div></div>
            <div className="kpi"><div className="kl">VAEP/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.vaep_per_90 ?? 0).toFixed(2)}</div></div>
            <div className="kpi"><div className="kl">Prog/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.progressive_per_90 ?? 0).toFixed(2)}</div></div>
            <div className="kpi"><div className="kl">Pres Altı</div><div className="kn" style={{ fontSize: 20 }}>%{Math.round(m.press_resistance_under_press * 100)}</div></div>
            <div className="kpi"><div className="kl">Overperf.</div><div className="kn" style={{ fontSize: 20, color: opVar(m.overperformance_label) }}>{m.overperformance_total > 0 ? "+" : ""}{m.overperformance_total.toFixed(2)}</div><div className="kd">{m.overperformance_label}</div></div>
          </div>
        </>
      )}

      {sub && sub.top_suboptimal.length > 0 && (
        <>
          <div className="st"><h2>Alt-optimal Pas Örnekleri</h2><span className="ep">{sub.passes_analyzed} pas · %{Math.round(sub.suboptimal_share * 100)} alt-optimal</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            {sub.top_suboptimal.map((p, i) => (
              <div className="rc" key={i} style={{ margin: 0 }}>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>{p.minute.toFixed(0)}. dakika{p.completed ? "" : <span style={{ color: "var(--crit)", marginLeft: 8 }}>(başarısız)</span>}</div>
                <MiniPitch start={p.start} actualEnd={p.actual_end} suggestedEnd={[p.best_alternative.x, p.best_alternative.y]} label={`xT Δ +${p.best_alternative.delta.toFixed(2)}`} />
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, fontFamily: "JetBrains Mono", lineHeight: 1.6 }}>
                  <div>Actual: <span style={{ color: "var(--crit)" }}>({p.actual_end[0].toFixed(0)},{p.actual_end[1].toFixed(0)})</span></div>
                  <div>Önerilen: <span style={{ color: "var(--low)" }}>({p.best_alternative.x.toFixed(0)},{p.best_alternative.y.toFixed(0)})</span></div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
