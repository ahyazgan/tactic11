"use client";

/**
 * Antrenman Planı (detay) — rakip profili + önerilen drill'ler + hafta briefi.
 * ConsoleShell çatısında.
 * Backend: GET /admin/teams/{id}/training-plan?opponent_id.
 */

import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../../../_console/shell";

interface Drill { name: string; focus: string; rationale: string; duration_min: string }
interface TrainingPlanResponse {
  my_team_external_id?: number;
  opponent_external_id?: number;
  events_loaded?: number;
  matches_analyzed?: number;
  opponent_profile?: {
    ppda: number;
    pressing_style: string;
    recovery_style: string;
    archetype: string;
    dominant_channel: string;
  };
  drills?: Drill[];
  ai_brief?: string;
  note?: string;
}

export default function TrainingPlanConsolePage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const teamId = params.id;
  const opponentId = search.get("opponent_id");

  const { data, error, isLoading } = useSWR<TrainingPlanResponse>(
    opponentId ? `/admin/teams/${teamId}/training-plan?opponent_id=${opponentId}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  if (!opponentId) {
    return (
      <ConsoleShell active="/training" title={`Antrenman — Takım #${teamId}`} sub="Maça özel plan">
        <div className="pgdesc"><code style={{ fontFamily: "JetBrains Mono" }}>?opponent_id=&lt;N&gt;</code> parametresi gerekli (Antrenman ekranından gel).</div>
      </ConsoleShell>
    );
  }

  const op = data?.opponent_profile;
  const drills = data?.drills ?? [];

  const right = (
    <div className="rc">
      <h3>Hafta Briefi</h3>
      {data?.ai_brief ? (
        <div style={{ fontSize: 12.5, color: "var(--ink)", whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{data.ai_brief}</div>
      ) : <div style={{ fontSize: "12px", color: "var(--dim)" }}>Brief yok.</div>}
    </div>
  );

  return (
    <ConsoleShell
      active="/training"
      title={`Antrenman — Takım #${teamId}`}
      sub={`vs Rakip #${opponentId}`}
      desc={data?.matches_analyzed != null ? `${data.matches_analyzed} rakip maç · ${data.events_loaded ?? 0} event` : "Rakibe özel haftalık antrenman planı."}
      right={right}
    >
      {error && <div className="pgdesc">Yüklenemedi: {String(error)}</div>}
      {isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {data && (data.events_loaded ?? 0) === 0 && <div className="pgdesc">{data.note ?? "Veri yok."}</div>}

      {op && (
        <>
          <div className="st" style={{ marginTop: 0 }}><h2>Rakip Profili</h2></div>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
            <div className="kpi"><div className="kl">PPDA</div><div className="kn" style={{ fontSize: 20 }}>{op.ppda.toFixed(2)}</div></div>
            <div className="kpi"><div className="kl">Pres Tarzı</div><div className="kn" style={{ fontSize: 14 }}>{op.pressing_style}</div></div>
            <div className="kpi"><div className="kl">Kazanım</div><div className="kn" style={{ fontSize: 14 }}>{op.recovery_style}</div></div>
            <div className="kpi"><div className="kl">Arketip</div><div className="kn" style={{ fontSize: 14 }}>{op.archetype}</div></div>
            <div className="kpi"><div className="kl">Kanal</div><div className="kn" style={{ fontSize: 14 }}>{op.dominant_channel}</div></div>
          </div>
        </>
      )}

      {drills.length > 0 && (
        <>
          <div className="st"><h2>Önerilen Drill&apos;ler</h2><span className="ep">{drills.length} drill</span></div>
          <div className="tbl">
            <table>
              <thead><tr><th>Drill</th><th>Odak</th><th className="c">Süre</th><th>Gerekçe</th></tr></thead>
              <tbody>
                {drills.map((d) => (
                  <tr key={d.name}>
                    <td><span className="nm">{d.name}</span></td>
                    <td style={{ color: "var(--muted)" }}>{d.focus}</td>
                    <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{d.duration_min}&apos;</td>
                    <td style={{ color: "var(--muted)", fontSize: 11.5 }} title={d.rationale}>{d.rationale.length > 80 ? d.rationale.slice(0, 80) + "…" : d.rationale}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
