"use client";

/**
 * Set-piece Routine — duran top rutini önerileri + zone haritası. ConsoleShell çatısında.
 * SetPieceZoneMap görseli korunur.
 * Backend: GET /admin/teams/{id}/set-piece-routine?opponent_id&set_piece_type.
 */

import * as React from "react";
import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { SetPieceZoneMap } from "@/components/charts/SetPieceZoneMap";
import { ConsoleShell } from "../../../_console/shell";

interface Recommendation {
  target_zone: string;
  technique: string;
  rationale: string;
  opponent_weakness_score: number;
  our_strength_score: number;
  routine_score: number;
}
interface RoutineResponse {
  value?: {
    my_team_external_id: number;
    opponent_team_external_id: number;
    set_piece_type: string;
    top_recommendations: Recommendation[];
    avoid_zone: string;
    matches_analyzed: number;
  };
  note?: string;
}

const SET_PIECE_TYPES = ["all", "corner_kick", "free_kick", "set_piece"];
const ZONE_TR: Record<string, string> = {
  near_post: "Yakın direk",
  central_6yd: "Kale ağzı (6 yd)",
  far_post: "Uzak direk",
  penalty_arc: "Ceza yayı",
  outside_box: "Ceza dışı",
};

export default function SetPieceRoutineConsolePage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const teamId = params.id;
  const opponentId = search.get("opponent_id");
  const [spType, setSpType] = React.useState<string>("all");
  const [selectedZone, setSelectedZone] = React.useState<string | undefined>();

  const url = opponentId ? `/admin/teams/${teamId}/set-piece-routine?opponent_id=${opponentId}&set_piece_type=${spType}` : null;
  const { data, error, isLoading } = useSWR<RoutineResponse>(url, apiFetch, { shouldRetryOnError: false });

  const scoresByZone: Record<string, number> = {};
  data?.value?.top_recommendations.forEach((r) => { scoresByZone[r.target_zone] = Math.min(1, r.routine_score); });

  if (!opponentId) {
    return (
      <ConsoleShell active="/teams" title={`Set-piece — Takım #${teamId}`} sub="Duran top rutini">
        <div className="pgdesc"><code style={{ fontFamily: "JetBrains Mono" }}>?opponent_id=&lt;N&gt;</code> parametresi gerekli.</div>
      </ConsoleShell>
    );
  }

  const right = (
    <div className="rc">
      <h3>Zone Haritası</h3>
      {data?.value ? (
        <>
          <SetPieceZoneMap scoresByZone={scoresByZone} avoidZone={data.value.avoid_zone} selectedZone={selectedZone} onSelectZone={setSelectedZone} />
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>✕ işareti: rakibin saldırgan pattern&apos;i — burayı bekler, defansif yığınak yapar.</div>
        </>
      ) : <div style={{ fontSize: "12px", color: "var(--dim)" }}>Veri bekleniyor…</div>}
    </div>
  );

  return (
    <ConsoleShell
      active="/teams"
      title={`Set-piece — Takım #${teamId}`}
      sub={`vs Rakip #${opponentId}`}
      desc={data?.value ? `${data.value.matches_analyzed} maç incelendi · tip ${data.value.set_piece_type}` : "Rakibe karşı duran top rutini önerileri."}
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Set-piece Tipi</h2>
        <div className="seg">
          {SET_PIECE_TYPES.map((t) => (
            <button key={t} className={spType === t ? "on" : ""} onClick={() => setSpType(t)}>{t}</button>
          ))}
        </div>
      </div>

      {error && <div className="pgdesc">Yüklenemedi: {String(error)}</div>}
      {isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {data?.note && <div className="pgdesc">{data.note}</div>}

      {data?.value && (
        <>
          <div className="st"><h2>Top Öneriler</h2><span className="ep">{data.value.top_recommendations.length} öneri</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {data.value.top_recommendations.map((r, i) => (
              <div className="rc" key={i} style={{ margin: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)" }}>{ZONE_TR[r.target_zone] ?? r.target_zone}</span>
                  <span style={{ fontSize: 10, textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: "1px solid var(--low)", color: "var(--low)" }}>score {r.routine_score.toFixed(2)}</span>
                </div>
                <div style={{ fontSize: 12, color: "var(--ink)", marginBottom: 6 }}>Teknik: <span style={{ fontFamily: "JetBrains Mono" }}>{r.technique}</span></div>
                <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{r.rationale}</div>
                <div style={{ display: "flex", gap: 12, fontSize: 11, color: "var(--dim)", marginTop: 8, fontFamily: "JetBrains Mono" }}>
                  <span>rakip zayıflığı <span style={{ color: "var(--crit)" }}>{(r.opponent_weakness_score * 100).toFixed(0)}%</span></span>
                  <span>bizim güç <span style={{ color: "var(--low)" }}>{(r.our_strength_score * 100).toFixed(0)}%</span></span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
