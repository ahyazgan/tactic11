"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

interface SubRecommendation {
  player_external_id: number;
  urgency_score: number;
  urgency_label: string;
  reasons: string[];
}

interface PlayerShift {
  player_external_id: number;
  drift_distance: number;
}

interface Snapshot {
  match_id?: number;
  my_team_id?: number;
  opponent_id?: number;
  current_minute?: number;
  events_so_far?: number;
  score?: string;
  ppda?: { ppda?: number };
  field_tilt?: { team_a_tilt?: number };
  match_dominance?: {
    dominance_score?: number;
    label?: string;
    xg_diff?: number;
    possession_share?: number;
  };
  live_sub_recommendation?: {
    recommendations: SubRecommendation[];
    score_state: string;
  };
  opponent_shape_drift?: {
    shape_changed: boolean;
    n_players_significant_drift: number;
    alert_text: string;
    player_shifts?: PlayerShift[];
  };
  type?: string;
  error?: string;
  note?: string;
}

function StatCard({
  label, value, badge, accent = "default",
}: {
  label: string;
  value: string;
  badge?: string;
  accent?: "default" | "green" | "red" | "amber";
}) {
  const accentColors = {
    default: "border-muted",
    green: "border-green-500/40",
    red: "border-red-500/40",
    amber: "border-yellow-500/40",
  };
  return (
    <div className={`card border-l-2 ${accentColors[accent]}`}>
      <h3 className="text-xs uppercase text-muted mb-1">{label}</h3>
      <div className="text-2xl font-mono">{value}</div>
      {badge && (
        <div className="inline-block mt-1 px-2 py-0.5 rounded bg-accent/20 text-xs uppercase">
          {badge}
        </div>
      )}
    </div>
  );
}

export default function LiveMatchPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const matchId = params.id;
  const myTeam = search.get("my_team_id");
  const interval = search.get("interval_seconds") ?? "10";
  const maxMinute = search.get("max_minute") ?? "90";
  const tenantId = search.get("tenant_id") ?? "t-default";

  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [ended, setEnded] = useState(false);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!myTeam) return;
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url =
      `${proto}//${host}/api/ws/matches/${matchId}/live` +
      `?my_team_id=${myTeam}&interval_seconds=${interval}` +
      `&max_minute=${maxMinute}&tenant_id=${tenantId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as Snapshot;
        if (data.type === "match_ended") {
          setEnded(true);
          return;
        }
        setSnapshot(data);
        setHistory((h) => [...h.slice(-19), data]);
      } catch {
        // ignore
      }
    };
    ws.onclose = () => setConnected(false);
    return () => ws.close();
  }, [matchId, myTeam, interval, maxMinute, tenantId]);

  if (!myTeam) {
    return (
      <main className="max-w-5xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-3">Canlı Maç Dashboard</h1>
        <div className="card">
          <p className="text-muted">
            <code className="font-mono">?my_team_id=&lt;N&gt;</code> parametresi gerek.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-6xl mx-auto p-6">
      <div className="flex items-baseline justify-between mb-4">
        <h1 className="text-2xl font-bold">
          Canlı — Maç #{matchId}
        </h1>
        <div className="text-xs uppercase">
          {ended ? (
            <span className="px-2 py-0.5 rounded bg-muted/30">Maç bitti</span>
          ) : connected ? (
            <span className="px-2 py-0.5 rounded bg-green-500/20 text-green-400">
              ● Canlı
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400">
              Bağlanıyor...
            </span>
          )}
        </div>
      </div>

      {snapshot?.note && (
        <div className="card mb-4 text-muted">{snapshot.note}</div>
      )}
      {snapshot?.error && (
        <div className="card border-l-2 border-red-500/40 mb-4">
          <p className="text-red-400 text-sm">{snapshot.error}</p>
        </div>
      )}

      {snapshot && !snapshot.error && (
        <>
          <h2 className="text-sm uppercase text-muted mb-3">Maç Durumu</h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            <StatCard label="Dakika"
              value={snapshot.current_minute?.toFixed(0) ?? "—"} />
            <StatCard label="Skor"
              value={snapshot.score ?? "—"}
              badge={snapshot.live_sub_recommendation?.score_state} />
            <StatCard label="Olay sayısı"
              value={String(snapshot.events_so_far ?? 0)} />
            <StatCard label="Dominance"
              value={snapshot.match_dominance?.dominance_score?.toFixed(2) ?? "—"}
              badge={snapshot.match_dominance?.label}
              accent={
                (snapshot.match_dominance?.dominance_score ?? 0) > 1
                  ? "green"
                  : (snapshot.match_dominance?.dominance_score ?? 0) < -1
                  ? "red"
                  : "default"
              } />
          </div>

          <div className="grid md:grid-cols-3 gap-3 mb-6">
            <StatCard label="PPDA"
              value={snapshot.ppda?.ppda?.toFixed(2) ?? "—"} />
            <StatCard label="Field Tilt (biz)"
              value={
                snapshot.field_tilt
                  ? `%${Math.round((snapshot.field_tilt.team_a_tilt ?? 0) * 100)}`
                  : "—"
              } />
            <StatCard label="xG Farkı"
              value={snapshot.match_dominance?.xg_diff?.toFixed(2) ?? "—"} />
          </div>

          {snapshot.live_sub_recommendation
            && snapshot.live_sub_recommendation.recommendations.length > 0 && (
            <>
              <h2 className="text-sm uppercase text-muted mb-3">
                Oyuncu Değişikliği Önerileri (Top 3)
              </h2>
              <div className="grid md:grid-cols-3 gap-3 mb-6">
                {snapshot.live_sub_recommendation.recommendations.map((rec) => (
                  <div
                    key={rec.player_external_id}
                    className={`card border-l-2 ${
                      rec.urgency_label === "high"
                        ? "border-red-500/50"
                        : rec.urgency_label === "medium"
                        ? "border-yellow-500/50"
                        : "border-muted"
                    }`}
                  >
                    <div className="flex justify-between mb-1">
                      <span className="font-mono">
                        Player #{rec.player_external_id}
                      </span>
                      <span className="text-xs uppercase px-2 py-0.5 rounded bg-accent/20">
                        {rec.urgency_label}
                      </span>
                    </div>
                    <div className="text-sm text-muted mb-2">
                      Aciliyet:{" "}
                      <span className="font-mono">{rec.urgency_score.toFixed(2)}</span>
                    </div>
                    <ul className="text-xs space-y-1">
                      {rec.reasons.map((r, i) => (
                        <li key={i} className="text-muted">
                          · {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </>
          )}

          {snapshot.opponent_shape_drift && (
            <>
              <h2 className="text-sm uppercase text-muted mb-3">
                Rakip Formasyon Takibi
              </h2>
              <div
                className={`card mb-6 ${
                  snapshot.opponent_shape_drift.shape_changed
                    ? "border-l-2 border-red-500/50"
                    : ""
                }`}
              >
                <div className="text-sm">
                  {snapshot.opponent_shape_drift.alert_text}
                </div>
                {snapshot.opponent_shape_drift.player_shifts
                  && snapshot.opponent_shape_drift.player_shifts.length > 0 && (
                  <div className="text-xs text-muted mt-2">
                    Drift olan oyuncular:{" "}
                    {snapshot.opponent_shape_drift.player_shifts
                      .slice(0, 5)
                      .map(
                        (p) =>
                          `#${p.player_external_id} (${p.drift_distance.toFixed(1)})`,
                      )
                      .join(", ")}
                  </div>
                )}
              </div>
            </>
          )}

          <div className="text-xs text-muted">
            Snapshot geçmişi: {history.length} kayıt · Interval {interval}sn
          </div>
        </>
      )}
    </main>
  );
}
