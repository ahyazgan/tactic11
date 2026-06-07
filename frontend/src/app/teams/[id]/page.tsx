"use client";

/**
 * Takım Detayı — son form + rating. ConsoleShell çatısında.
 * Veri: GET /teams/{id}/form, GET /teams/{id}/rating.
 */

import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../../_console/shell";

interface Confidence { score: number; label: string; drivers: string[] }
interface FormResponse {
  value: {
    matches_played: number;
    wins: number;
    draws: number;
    losses: number;
    goals_for: number;
    goals_against: number;
    points_per_game: number;
    last_results: ("W" | "D" | "L")[];
  };
  confidence: Confidence | null;
}
interface RatingResponse {
  value: { rating: number; home_rating: number | null; away_rating: number | null; matches_considered: number };
  confidence: Confidence | null;
}

function ResultDot({ r }: { r: "W" | "D" | "L" }) {
  const bg = r === "W" ? "var(--low)" : r === "L" ? "var(--crit)" : "var(--dim)";
  return <span style={{ display: "inline-flex", width: 24, height: 24, borderRadius: 5, alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#fff", background: bg }}>{r}</span>;
}

export default function TeamDetailConsolePage() {
  const params = useParams<{ id: string }>();
  const teamId = params.id;

  const { data: form } = useSWR<FormResponse>(`/teams/${teamId}/form`, apiFetch, { shouldRetryOnError: false });
  const { data: rating } = useSWR<RatingResponse>(`/teams/${teamId}/rating`, apiFetch, { shouldRetryOnError: false });
  const f = form?.value;
  const rt = rating?.value;

  const right = (
    <div className="rc">
      <h3>Rating</h3>
      {rt ? (
        <>
          <div style={{ fontSize: 30, fontWeight: 800, fontFamily: "JetBrains Mono", marginBottom: 8 }}>{rt.rating.toFixed(2)}</div>
          <div className="stat"><span>Ev</span><span className="sv">{rt.home_rating?.toFixed(2) ?? "—"}</span></div>
          <div className="stat"><span>Deplasman</span><span className="sv">{rt.away_rating?.toFixed(2) ?? "—"}</span></div>
          <div className="stat"><span>Değerlendirilen</span><span className="sv">{rt.matches_considered} maç</span></div>
        </>
      ) : <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yükleniyor…</div>}
    </div>
  );

  return (
    <ConsoleShell
      active="/teams"
      title={`Takım #${teamId}`}
      sub="Form & rating"
      desc="Takımın son form dökümü ve model rating'i."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}><h2>Son Form</h2>{form?.confidence && <span className="ep">güven: {form.confidence.label}</span>}</div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        {f ? (
          <>
            <div style={{ fontSize: 30, fontWeight: 800, fontFamily: "JetBrains Mono", marginBottom: 8 }}>{f.wins}-{f.draws}-{f.losses}</div>
            <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 12 }}>
              PPG: <b style={{ color: "var(--ink)", fontFamily: "JetBrains Mono" }}>{f.points_per_game}</b> · GF/GA: <b style={{ color: "var(--ink)", fontFamily: "JetBrains Mono" }}>{f.goals_for}/{f.goals_against}</b>
            </div>
            <div style={{ display: "flex", gap: 5 }}>
              {f.last_results.slice(0, 10).map((r, i) => <ResultDot key={i} r={r} />)}
            </div>
          </>
        ) : <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yükleniyor…</div>}
      </div>

      <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        <div className="kpi"><div className="kl">Oynanan</div><div className="kn">{f?.matches_played ?? "—"}</div><div className="kd">maç</div></div>
        <div className="kpi"><div className="kl">Galibiyet</div><div className="kn" style={{ color: "var(--low)" }}>{f?.wins ?? "—"}</div><div className="kd">W</div></div>
        <div className="kpi"><div className="kl">Beraberlik</div><div className="kn" style={{ color: "var(--mid)" }}>{f?.draws ?? "—"}</div><div className="kd">D</div></div>
        <div className="kpi"><div className="kl">Mağlubiyet</div><div className="kn" style={{ color: "var(--crit)" }}>{f?.losses ?? "—"}</div><div className="kd">L</div></div>
      </div>
    </ConsoleShell>
  );
}
