"use client";

import { useMemo, useState } from "react";
import { PerformanceTrajectoryChart } from "@/components/charts/PerformanceTrajectoryChart";
import { PlayerComparisonRadar } from "@/components/charts/PlayerComparisonRadar";
import { TeamHealthGauge } from "@/components/charts/TeamHealthGauge";
import { Panel, Pill, Sparkline, StatTile } from "@/components/ui";
import { apiFetch } from "@/lib/api";

interface ConsistencyResult {
  value: {
    sample_count: number;
    mean: number;
    sd: number;
    cv: number;
    best: number;
    worst: number;
    consistency_label: string;
    z_recent_5: number;
    reliability_score: number;
    summary: string;
    notes: string[];
  };
}

interface AnomalyEvent {
  type: string;
  match_id_seen: number;
  severity: string;
  z_or_factor: number;
  rationale: string;
  recommended_action: string;
  confidence: number;
}

interface AnomalyResult {
  value: {
    sample_count: number;
    baseline_mean: number;
    baseline_sd: number;
    events: AnomalyEvent[];
    summary: string;
    overall_risk: string;
  };
}

interface PlayerSnapshot {
  player_id: number;
  name: string;
  mean_rating: number;
  consistency_label: string;
  direction: string;
  reliability: number;
  z_recent_5: number;
}

interface TeamFormResult {
  value: {
    player_count: number;
    team_avg_rating: number;
    team_health_score: number;
    pct_improving: number;
    pct_declining: number;
    pct_stable: number;
    pct_high_consistency: number;
    pct_volatile: number;
    snapshots: PlayerSnapshot[];
    top_performers: PlayerSnapshot[];
    concerns: PlayerSnapshot[];
    summary: string;
  };
}

interface ComparisonResult {
  value: {
    player_count: number;
    kpis_compared: string[];
    per_player: {
      player_id: number;
      name: string;
      aggregate_score: number;
      strongest_kpi: string | null;
      weakest_kpi: string | null;
      overall_rank: number;
    }[];
    per_kpi: {
      kpi: string;
      values: Record<string, number>;
      normalized: Record<string, number>;
      rank: Record<string, number>;
      best_player_id: number;
      worst_player_id: number;
    }[];
    winner_id: number | null;
    winner_name: string | null;
    reasoning: string;
    summary: string;
  };
}

interface TrajectoryResult {
  value: {
    sample_count: number;
    slope: number;
    intercept: number;
    direction: string;
    confidence: number;
    peak_index: number;
    dip_index: number;
    last_value: number;
    projection_next_3: number[];
    smoothed_series: number[];
    rtm_warning: string | null;
    summary: string;
    notes: string[];
  };
}

const LABEL_VARIANT: Record<string, "win" | "warn" | "loss" | "neutral"> = {
  high: "win",
  medium: "neutral",
  volatile: "warn",
  insufficient: "neutral",
};

const DIRECTION_VARIANT: Record<string, "win" | "warn" | "loss" | "neutral"> = {
  improving: "win",
  stable: "neutral",
  declining: "loss",
  insufficient: "neutral",
};

const DIRECTION_LABEL: Record<string, string> = {
  improving: "Yükseliyor",
  declining: "Düşüyor",
  stable: "Sabit",
  insufficient: "Yetersiz",
};

const SAMPLE_PRESETS: Record<string, string> = {
  consistent_high: "7.0, 7.2, 6.9, 7.1, 7.0, 7.3, 7.1, 7.0, 7.2, 7.1",
  improving: "5.5, 6.0, 6.2, 6.8, 7.0, 7.2, 7.5, 7.8, 8.0, 8.2",
  declining: "8.2, 8.0, 7.7, 7.5, 7.0, 6.8, 6.3, 6.0, 5.7, 5.5",
  volatile: "5.0, 8.5, 4.0, 9.0, 5.5, 8.0, 4.5, 9.2, 5.0, 8.8",
  flat_low: "5.0, 5.1, 4.9, 5.0, 5.2, 4.8, 5.1, 5.0, 4.9, 5.1",
};

function parseSeries(input: string): number[] {
  return input
    .split(/[,;\s\n]+/)
    .map((s) => parseFloat(s.trim()))
    .filter((v) => !Number.isNaN(v));
}

const TEAM_PRESET = JSON.stringify(
  [
    { player_id: 1, name: "Forvet A", ratings: [7.4, 7.6, 7.8, 8.0, 8.2] },
    { player_id: 2, name: "Forvet B", ratings: [6.5, 6.7, 6.9, 7.0, 7.0] },
    { player_id: 3, name: "Orta saha", ratings: [7.0, 7.0, 7.0, 7.0, 7.0] },
    { player_id: 4, name: "Defans A", ratings: [7.5, 7.3, 7.0, 6.7, 6.4] },
    { player_id: 5, name: "Defans B", ratings: [5.8, 5.6, 5.4, 5.2, 5.0] },
    { player_id: 6, name: "Kanat", ratings: [6.0, 8.0, 5.0, 9.0, 6.0] },
  ],
  null,
  2,
);

const COMPARE_PRESET = JSON.stringify(
  [
    { player_id: 1, name: "Striker A",
      kpis: { rating: 7.4, xt_per_90: 0.35, goals_per_90: 0.55, xa_per_90: 0.20 } },
    { player_id: 2, name: "Striker B",
      kpis: { rating: 7.1, xt_per_90: 0.48, goals_per_90: 0.40, xa_per_90: 0.30 } },
    { player_id: 3, name: "Striker C",
      kpis: { rating: 6.8, xt_per_90: 0.20, goals_per_90: 0.65, xa_per_90: 0.10 } },
  ],
  null,
  2,
);

export default function PerformansPage() {
  const [seriesText, setSeriesText] = useState(SAMPLE_PRESETS.improving);
  const [consistency, setConsistency] = useState<ConsistencyResult | null>(null);
  const [trajectory, setTrajectory] = useState<TrajectoryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [compareJson, setCompareJson] = useState(COMPARE_PRESET);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareErr, setCompareErr] = useState<string | null>(null);

  const [teamJson, setTeamJson] = useState(TEAM_PRESET);
  const [teamForm, setTeamForm] = useState<TeamFormResult | null>(null);
  const [teamLoading, setTeamLoading] = useState(false);
  const [teamErr, setTeamErr] = useState<string | null>(null);

  const [anomaly, setAnomaly] = useState<AnomalyResult | null>(null);
  const [anomalyLoading, setAnomalyLoading] = useState(false);

  const values = useMemo(() => parseSeries(seriesText), [seriesText]);

  async function runTeamForm() {
    setTeamErr(null);
    setTeamLoading(true);
    try {
      const players = JSON.parse(teamJson);
      const res = await apiFetch<TeamFormResult>("/admin/performance/team-form-health", {
        method: "POST", body: JSON.stringify({ players }),
      });
      setTeamForm(res);
    } catch (e) {
      setTeamErr(String(e));
    } finally {
      setTeamLoading(false);
    }
  }

  async function runComparison() {
    setCompareErr(null);
    setCompareLoading(true);
    try {
      const players = JSON.parse(compareJson);
      const res = await apiFetch<ComparisonResult>("/admin/performance/comparison", {
        method: "POST", body: JSON.stringify({ players }),
      });
      setComparison(res);
    } catch (e) {
      setCompareErr(String(e));
    } finally {
      setCompareLoading(false);
    }
  }

  async function runAnalysis() {
    if (values.length < 2) {
      setErr("En az 2 değer girin (örn: 6.5, 7.0, 7.2)");
      return;
    }
    setErr(null);
    setLoading(true);
    setAnomalyLoading(true);
    try {
      const samples = values.map((v, i) => ({ match_id: i + 1, value: v }));
      const points = values.map((v, i) => ({
        match_id: i + 1, value: v, game_index: i,
      }));
      const anomalyPoints = values.map((v, i) => ({
        match_id: i + 1, rating: v,
      }));
      const [c, t, a] = await Promise.all([
        apiFetch<ConsistencyResult>("/admin/performance/consistency", {
          method: "POST", body: JSON.stringify({ samples }),
        }),
        apiFetch<TrajectoryResult>("/admin/performance/trajectory", {
          method: "POST", body: JSON.stringify({ points }),
        }),
        apiFetch<AnomalyResult>("/admin/performance/anomaly", {
          method: "POST", body: JSON.stringify({ points: anomalyPoints }),
        }),
      ]);
      setConsistency(c);
      setTrajectory(t);
      setAnomaly(a);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
      setAnomalyLoading(false);
    }
  }

  return (
    <main className="max-w-6xl mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-1">Performans Analizi</h1>
        <p className="text-sm text-muted">
          Oyuncu rating serisinden tutarlılık (O) + yön/projeksiyon (P).
          Maç-maç rating'leri yapıştır → reliability + trajectory + RTM uyarısı.
        </p>
      </div>

      <Panel title="Rating serisi (maç-maç)">
        <div className="mb-3 flex flex-wrap gap-2">
          {Object.entries(SAMPLE_PRESETS).map(([k, v]) => (
            <button
              key={k}
              className="text-xs px-2 py-1 border border-border rounded hover:bg-surface2"
              onClick={() => setSeriesText(v)}
            >
              {k}
            </button>
          ))}
        </div>
        <textarea
          rows={3}
          className="w-full bg-bg border border-border rounded px-2 py-1 text-sm font-mono"
          placeholder="6.5, 7.0, 7.2, 6.8, 7.5 (virgül veya yeni satır ayır)"
          value={seriesText}
          onChange={(e) => setSeriesText(e.target.value)}
        />
        <div className="mt-2 flex items-center gap-3">
          <button
            className="px-3 py-1.5 bg-accent text-white text-sm rounded"
            onClick={runAnalysis}
            disabled={loading}
          >
            {loading ? "Analiz…" : "Analiz et"}
          </button>
          <span className="text-xs text-muted">{values.length} değer parse edildi</span>
          {values.length > 0 && (
            <Sparkline data={values} width={120} height={24} />
          )}
        </div>
        {err && <p className="text-bad text-sm mt-2">{err}</p>}
      </Panel>

      {consistency && (
        <Panel title="1. Tutarlılık (engine.performance_consistency)">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            <StatTile label="Mean" value={consistency.value.mean.toFixed(2)} />
            <StatTile label="SD" value={consistency.value.sd.toFixed(2)} />
            <StatTile label="CV" value={consistency.value.cv.toFixed(2)} />
            <StatTile
              label="Reliability"
              value={`${consistency.value.reliability_score.toFixed(0)}`}
            />
            <StatTile label="Best" value={consistency.value.best.toFixed(2)} />
            <StatTile label="Worst" value={consistency.value.worst.toFixed(2)} />
            <StatTile
              label="Son 5 z"
              value={consistency.value.z_recent_5.toFixed(2)}
              delta={consistency.value.z_recent_5}
            />
            <StatTile
              label="Örnek"
              value={String(consistency.value.sample_count)}
            />
          </div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs uppercase text-muted">Tutarlılık:</span>
            <Pill variant={LABEL_VARIANT[consistency.value.consistency_label] || "neutral"}>
              {consistency.value.consistency_label}
            </Pill>
          </div>
          <p className="text-sm">{consistency.value.summary}</p>
          {consistency.value.notes.length > 0 && (
            <ul className="text-xs text-muted mt-2 space-y-0.5">
              {consistency.value.notes.map((n, i) => (
                <li key={i}>• {n}</li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      {trajectory && (
        <Panel title="2. Yön ve Projeksiyon (engine.performance_trajectory)">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            <StatTile
              label="Yön"
              value={DIRECTION_LABEL[trajectory.value.direction] || trajectory.value.direction}
            />
            <StatTile
              label="Slope/maç"
              value={trajectory.value.slope.toFixed(3)}
              delta={trajectory.value.slope}
            />
            <StatTile label="Conf" value={trajectory.value.confidence.toFixed(2)} />
            <StatTile label="Son değer" value={trajectory.value.last_value.toFixed(2)} />
            <StatTile
              label="Peak idx"
              value={String(trajectory.value.peak_index)}
            />
            <StatTile
              label="Dip idx"
              value={String(trajectory.value.dip_index)}
            />
            <StatTile
              label="Proj +1"
              value={trajectory.value.projection_next_3[0]?.toFixed(2) || "—"}
            />
            <StatTile
              label="Proj +3"
              value={trajectory.value.projection_next_3[2]?.toFixed(2) || "—"}
            />
          </div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs uppercase text-muted">Yön:</span>
            <Pill variant={DIRECTION_VARIANT[trajectory.value.direction] || "neutral"}>
              {trajectory.value.direction}
            </Pill>
          </div>

          {trajectory.value.smoothed_series.length > 0 && (
            <div className="mb-3">
              <div className="text-xs uppercase text-muted mb-1">
                Trajectory (ham + smoothed + projeksiyon)
              </div>
              <PerformanceTrajectoryChart
                raw={values}
                smoothed={trajectory.value.smoothed_series}
                projection={trajectory.value.projection_next_3}
                peakIndex={trajectory.value.peak_index}
                dipIndex={trajectory.value.dip_index}
                direction={trajectory.value.direction}
              />
              <div className="text-[10px] text-muted mt-1">
                Yeşil = peak, kırmızı = dip; kesik çizgi = next-3 projeksiyon
              </div>
            </div>
          )}

          <p className="text-sm">{trajectory.value.summary}</p>

          {trajectory.value.rtm_warning && (
            <div className="mt-3 p-2 border border-warn/40 bg-warn/10 rounded text-xs">
              <span className="font-semibold">RTM Uyarısı:</span>{" "}
              {trajectory.value.rtm_warning}
            </div>
          )}

          {trajectory.value.notes.length > 0 && (
            <ul className="text-xs text-muted mt-2 space-y-0.5">
              {trajectory.value.notes.map((n, i) => (
                <li key={i}>• {n}</li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      {anomaly && (
        <Panel title="4. Anomali Tespiti (engine.performance_anomaly — S)">
          {anomalyLoading && <p className="text-xs text-muted">Tarama…</p>}
          <div className="flex items-center gap-3 mb-3">
            <span className="text-xs uppercase text-muted">Genel risk:</span>
            <Pill
              variant={
                anomaly.value.overall_risk === "high"
                  ? "loss"
                  : anomaly.value.overall_risk === "medium"
                  ? "warn"
                  : "win"
              }
            >
              {anomaly.value.overall_risk.toUpperCase()}
            </Pill>
            <span className="text-xs text-muted">
              baseline μ={anomaly.value.baseline_mean.toFixed(2)} σ={anomaly.value.baseline_sd.toFixed(2)}
            </span>
          </div>
          <p className="text-sm mb-3">{anomaly.value.summary}</p>

          {anomaly.value.events.length === 0 ? (
            <p className="text-xs text-muted">Anomali bulunamadı — baseline'da kalıyor.</p>
          ) : (
            <div className="space-y-2">
              {anomaly.value.events.map((ev, i) => (
                <div key={i} className="border border-border rounded p-2">
                  <div className="flex items-center gap-2 mb-1">
                    <Pill
                      variant={
                        ev.severity === "high"
                          ? "loss"
                          : ev.severity === "medium"
                          ? "warn"
                          : "neutral"
                      }
                    >
                      {ev.severity.toUpperCase()}
                    </Pill>
                    <span className="text-xs uppercase text-accent font-mono">{ev.type}</span>
                    <span className="text-xs text-muted">
                      match #{ev.match_id_seen} · conf {ev.confidence.toFixed(2)}
                    </span>
                  </div>
                  <div className="text-xs text-muted mb-1">{ev.rationale}</div>
                  <div className="text-sm">{ev.recommended_action}</div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      <Panel title="5. Kadro Formu (engine.team_form_health — R)">
        <label className="flex flex-col text-xs mb-3">
          <span className="text-muted mb-1">
            Oyuncular (JSON — her oyuncunun rating serisi)
          </span>
          <textarea
            rows={10}
            className="bg-bg border border-border rounded px-2 py-1 text-xs font-mono"
            value={teamJson}
            onChange={(e) => setTeamJson(e.target.value)}
          />
        </label>
        <button
          className="px-3 py-1.5 bg-accent text-white text-sm rounded mb-3"
          onClick={runTeamForm}
          disabled={teamLoading}
        >
          {teamLoading ? "Hesaplanıyor…" : "Kadro formu hesapla"}
        </button>
        {teamErr && <p className="text-bad text-sm mt-2">{teamErr}</p>}

        {teamForm && (
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] gap-3 items-start">
              <TeamHealthGauge
                score={teamForm.value.team_health_score}
                label="Kadro Sağlık Skoru"
              />
              <p className="text-sm self-center">{teamForm.value.summary}</p>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <StatTile
                label="Health"
                value={`${teamForm.value.team_health_score.toFixed(0)}/100`}
              />
              <StatTile label="Avg rating" value={teamForm.value.team_avg_rating.toFixed(2)} />
              <StatTile label="Oyuncu" value={String(teamForm.value.player_count)} />
              <StatTile
                label="% Yükselişte"
                value={`${teamForm.value.pct_improving.toFixed(0)}%`}
              />
              <StatTile
                label="% Düşüşte"
                value={`${teamForm.value.pct_declining.toFixed(0)}%`}
              />
              <StatTile
                label="% Sabit"
                value={`${teamForm.value.pct_stable.toFixed(0)}%`}
              />
              <StatTile
                label="% Tutarlı"
                value={`${teamForm.value.pct_high_consistency.toFixed(0)}%`}
              />
              <StatTile
                label="% Değişken"
                value={`${teamForm.value.pct_volatile.toFixed(0)}%`}
              />
            </div>

            {teamForm.value.top_performers.length > 0 && (
              <div>
                <div className="text-xs uppercase text-muted mb-1">Top Performans</div>
                <div className="flex flex-wrap gap-2">
                  {teamForm.value.top_performers.map((p) => (
                    <Pill key={p.player_id} variant="win">
                      {p.name} · {p.reliability.toFixed(0)}
                    </Pill>
                  ))}
                </div>
              </div>
            )}

            {teamForm.value.concerns.length > 0 && (
              <div>
                <div className="text-xs uppercase text-muted mb-1">Endişeli oyuncular</div>
                <div className="flex flex-wrap gap-2">
                  {teamForm.value.concerns.map((p) => (
                    <Pill key={p.player_id} variant="loss">
                      {p.name} · düşüşte ({p.reliability.toFixed(0)})
                    </Pill>
                  ))}
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-xs border border-border">
                <thead className="bg-surface2">
                  <tr>
                    <th className="p-2 text-left">Oyuncu</th>
                    <th className="p-2 text-right">Mean</th>
                    <th className="p-2 text-left">Tutarlılık</th>
                    <th className="p-2 text-left">Yön</th>
                    <th className="p-2 text-right">Reliability</th>
                    <th className="p-2 text-right">Son 5 z</th>
                  </tr>
                </thead>
                <tbody>
                  {teamForm.value.snapshots.map((s) => (
                    <tr key={s.player_id} className="border-t border-border">
                      <td className="p-2 font-semibold">{s.name}</td>
                      <td className="p-2 text-right tabular-nums">{s.mean_rating.toFixed(2)}</td>
                      <td className="p-2">
                        <Pill variant={LABEL_VARIANT[s.consistency_label] || "neutral"}>
                          {s.consistency_label}
                        </Pill>
                      </td>
                      <td className="p-2">
                        <Pill variant={DIRECTION_VARIANT[s.direction] || "neutral"}>
                          {s.direction}
                        </Pill>
                      </td>
                      <td className="p-2 text-right tabular-nums">{s.reliability.toFixed(0)}</td>
                      <td className="p-2 text-right tabular-nums">{s.z_recent_5.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Panel>

      <Panel title="6. Karşılaştırma (engine.player_comparison)">
        <label className="flex flex-col text-xs mb-3">
          <span className="text-muted mb-1">Oyuncular (JSON — 2-6 oyuncu)</span>
          <textarea
            rows={10}
            className="bg-bg border border-border rounded px-2 py-1 text-xs font-mono"
            value={compareJson}
            onChange={(e) => setCompareJson(e.target.value)}
          />
        </label>
        <button
          className="px-3 py-1.5 bg-accent text-white text-sm rounded mb-3"
          onClick={runComparison}
          disabled={compareLoading}
        >
          {compareLoading ? "Karşılaştırma…" : "Karşılaştır"}
        </button>
        {compareErr && <p className="text-bad text-sm mt-2">{compareErr}</p>}

        {comparison && (
          <div className="space-y-3">
            <p className="text-sm">{comparison.value.summary}</p>
            {comparison.value.winner_name && (
              <p className="text-sm">
                <Pill variant="win">Kazanan</Pill>{" "}
                <span className="font-semibold">{comparison.value.winner_name}</span> —{" "}
                <span className="text-muted">{comparison.value.reasoning}</span>
              </p>
            )}

            {comparison.value.per_kpi.length > 0 && comparison.value.per_player.length > 0 && (
              <div>
                <div className="text-xs uppercase text-muted mb-1">
                  Radar (normalize KPI'lar)
                </div>
                <PlayerComparisonRadar
                  kpis={comparison.value.kpis_compared}
                  perKpi={comparison.value.per_kpi}
                  perPlayer={comparison.value.per_player}
                />
              </div>
            )}

            {/* Per-player ranking */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-border">
                <thead className="bg-surface2">
                  <tr>
                    <th className="p-2 text-left">#</th>
                    <th className="p-2 text-left">Oyuncu</th>
                    <th className="p-2 text-right">Aggregate</th>
                    <th className="p-2 text-left">Strongest</th>
                    <th className="p-2 text-left">Weakest</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.value.per_player.map((p) => (
                    <tr key={p.player_id} className="border-t border-border">
                      <td className="p-2">{p.overall_rank}</td>
                      <td className="p-2 font-semibold">{p.name}</td>
                      <td className="p-2 text-right tabular-nums">{p.aggregate_score.toFixed(3)}</td>
                      <td className="p-2 text-xs text-good">{p.strongest_kpi || "—"}</td>
                      <td className="p-2 text-xs text-bad">{p.weakest_kpi || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Per-KPI breakdown */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs border border-border">
                <thead className="bg-surface2">
                  <tr>
                    <th className="p-2 text-left">KPI</th>
                    {comparison.value.per_player.map((p) => (
                      <th key={p.player_id} className="p-2 text-right">{p.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {comparison.value.per_kpi.map((k) => (
                    <tr key={k.kpi} className="border-t border-border">
                      <td className="p-2 font-mono">{k.kpi}</td>
                      {comparison.value.per_player.map((p) => {
                        const raw = k.values[p.player_id];
                        const rank = k.rank[p.player_id];
                        const isBest = k.best_player_id === p.player_id;
                        return (
                          <td
                            key={p.player_id}
                            className={`p-2 text-right tabular-nums ${isBest ? "text-good font-semibold" : ""}`}
                          >
                            {raw?.toFixed(2)} <span className="text-muted">#{rank}</span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Panel>

      {consistency && trajectory && (
        <Panel title="3. Sentez (kompozit yorum)">
          <p className="text-sm">
            {synthesize(consistency.value, trajectory.value)}
          </p>
        </Panel>
      )}
    </main>
  );
}

function synthesize(
  c: ConsistencyResult["value"],
  t: TrajectoryResult["value"],
): string {
  const parts: string[] = [];
  if (c.consistency_label === "high") {
    parts.push("Bu oyuncu çok tutarlı bir performans çiziyor.");
  } else if (c.consistency_label === "volatile") {
    parts.push("Bu oyuncu çok değişken — bir maçta 9, sonrakinde 4 olabilir.");
  } else if (c.consistency_label === "medium") {
    parts.push("Performans orta düzeyde tutarlı, küçük dalgalanmalar normal.");
  } else {
    parts.push("Az örnek var — tutarlılık değerlendirmesi sınırlı.");
  }

  if (t.direction === "improving" && t.confidence > 0.6) {
    parts.push(`Yön net yükseliyor (slope ${t.slope.toFixed(3)}/maç, conf ${t.confidence.toFixed(2)}) — sonraki maçta ~${t.projection_next_3[0].toFixed(2)} beklenir.`);
  } else if (t.direction === "declining" && t.confidence > 0.6) {
    parts.push(`Yön net düşüyor — dikkat, sonraki maçta ~${t.projection_next_3[0].toFixed(2)}.`);
  } else if (t.direction === "stable") {
    parts.push("Performans yönü stabil, sürpriz beklenmez.");
  } else {
    parts.push("Yön belirsiz — slope düşük conf'ta, gürültü olabilir.");
  }

  if (t.rtm_warning) {
    parts.push("Ancak: anormal sapma var, ortalamaya dönme beklenebilir.");
  }

  if (c.reliability_score >= 70) {
    parts.push(`Reliability skoru ${c.reliability_score.toFixed(0)}/100 — güvenle ilk 11 oyuncusu.`);
  } else if (c.reliability_score >= 40) {
    parts.push(`Reliability skoru ${c.reliability_score.toFixed(0)}/100 — rotasyon adayı.`);
  } else {
    parts.push(`Reliability skoru ${c.reliability_score.toFixed(0)}/100 — yedek/yetiştirme.`);
  }

  return parts.join(" ");
}
