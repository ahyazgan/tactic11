"use client";

import { useMemo, useState } from "react";
import { Panel, Pill, StatTile, Sparkline } from "@/components/ui";
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

  const values = useMemo(() => parseSeries(seriesText), [seriesText]);

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
    try {
      const samples = values.map((v, i) => ({ match_id: i + 1, value: v }));
      const points = values.map((v, i) => ({
        match_id: i + 1, value: v, game_index: i,
      }));
      const [c, t] = await Promise.all([
        apiFetch<ConsistencyResult>("/admin/performance/consistency", {
          method: "POST", body: JSON.stringify({ samples }),
        }),
        apiFetch<TrajectoryResult>("/admin/performance/trajectory", {
          method: "POST", body: JSON.stringify({ points }),
        }),
      ]);
      setConsistency(c);
      setTrajectory(t);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
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
              <div className="text-xs uppercase text-muted mb-1">Smoothed (3-game MA)</div>
              <Sparkline
                data={trajectory.value.smoothed_series}
                width={320}
                height={48}
              />
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

      <Panel title="4. Karşılaştırma (engine.player_comparison)">
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
