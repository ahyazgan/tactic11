"use client";

/**
 * Sub Chess — değişiklik senaryoları (forward-projection). ConsoleShell çatısında.
 * Dakika slider → top-3 senaryo (yorgunluk projeksiyonu + dominance Δ).
 * Backend: GET /admin/matches/{id}/substitution-chess?my_team_id&current_minute.
 */

import * as React from "react";
import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../../../_console/shell";

interface Scenario {
  out_player_id: number;
  out_player_current_fatigue: number;
  out_player_projected_fatigue_at_full_time: number;
  in_player_id: number | null;
  in_player_projected_fatigue_at_full_time: number;
  minutes_remaining: number;
  projected_dominance_delta: number;
  confidence: string;
}
interface SubChessResponse {
  value?: {
    team_external_id: number;
    current_minute: number;
    minutes_remaining: number;
    scenarios: Scenario[];
    best_scenario_index: number;
    no_action_baseline: number;
  };
  events_loaded?: number;
  note?: string;
}

export default function SubChessConsolePage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const matchId = params.id;
  const myTeamId = search.get("my_team_id");
  const initialMinute = Number(search.get("current_minute") ?? "60");
  const [minute, setMinute] = React.useState<number>(initialMinute);

  const url = myTeamId && minute
    ? `/admin/matches/${matchId}/substitution-chess?my_team_id=${myTeamId}&current_minute=${minute}`
    : null;
  const { data, error, isLoading } = useSWR<SubChessResponse>(url, apiFetch, { shouldRetryOnError: false });
  const isEvent0 = data?.events_loaded === 0;

  const right = (
    <div className="rc">
      <h3>Dakika</h3>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <input type="range" min={5} max={90} step={5} value={minute} onChange={(e) => setMinute(Number(e.target.value))} style={{ flex: 1 }} aria-label="Maç dakikası" />
        <span style={{ fontFamily: "JetBrains Mono", fontSize: 16, width: 40, textAlign: "right" }}>{minute}&apos;</span>
      </div>
      <div style={{ fontSize: "11.5px", color: "var(--dim)", lineHeight: 1.5 }}>Slider&apos;ı oynat → senaryolar yeniden hesaplanır.</div>
    </div>
  );

  if (!myTeamId) {
    return (
      <ConsoleShell active="/matches" title={`Sub Chess — Maç #${matchId}`} sub="Değişiklik senaryoları">
        <div className="pgdesc"><code style={{ fontFamily: "JetBrains Mono" }}>?my_team_id=&lt;N&gt;</code> parametresi gerekli (Maç detayından gel).</div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell
      active="/matches"
      title={`Sub Chess — Maç #${matchId}`}
      sub={`Takım #${myTeamId} · ${minute}. dakika`}
      desc="Forward-projection ile en iyi 3 değişiklik senaryosu — yorgunluk ve dominance etkisi."
      right={right}
    >
      {error && <div className="pgdesc">Yüklenemedi: {String(error)}</div>}
      {isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {isEvent0 && <div className="pgdesc">{data?.note}</div>}

      {data?.value && data.value.scenarios.length > 0 && (
        <>
          <div className="st" style={{ marginTop: 0 }}><h2>Top 3 Senaryo</h2><span className="ep">kalan {data.value.minutes_remaining.toFixed(0)} dk</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            {data.value.scenarios.map((s, i) => {
              const isBest = i === data.value!.best_scenario_index;
              return (
                <div className="rc" key={i} style={{ margin: 0, borderLeft: isBest ? "2px solid var(--low)" : undefined }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)" }}>Senaryo {i + 1}{isBest ? " ★" : ""}</span>
                    <span style={{ fontSize: 10, textTransform: "uppercase", color: "var(--muted)", fontFamily: "JetBrains Mono" }}>{s.confidence}</span>
                  </div>
                  <div style={{ fontSize: 13, color: "var(--ink)", marginBottom: 8 }}>#{s.out_player_id} → {s.in_player_id ? `#${s.in_player_id}` : "TD seçer"}</div>
                  <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "JetBrains Mono", color: s.projected_dominance_delta > 0 ? "var(--low)" : "var(--crit)", marginBottom: 8 }}>
                    {(s.projected_dominance_delta > 0 ? "+" : "") + s.projected_dominance_delta.toFixed(3)}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.6, fontFamily: "JetBrains Mono" }}>
                    <div>Out şimdi: {s.out_player_current_fatigue.toFixed(2)}</div>
                    <div>Out FT: <span style={{ color: "var(--crit)" }}>{s.out_player_projected_fatigue_at_full_time.toFixed(2)}</span></div>
                    <div>In FT: <span style={{ color: "var(--low)" }}>{s.in_player_projected_fatigue_at_full_time.toFixed(2)}</span></div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
