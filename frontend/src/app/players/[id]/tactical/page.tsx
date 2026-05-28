"use client";

import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface EngineValue {
  value: Record<string, unknown>;
}

interface PlayerTactical {
  player_id: number;
  events_loaded: number;
  meta: {
    team_external_id: number | null;
    minutes_played: number;
    matches_analyzed: number;
  };
  tactical_profile: Record<string, EngineValue | { error: string }>;
  note?: string;
}

function fmt(v: unknown): string {
  if (typeof v === "number") return v.toFixed(2);
  if (v === null || v === undefined) return "—";
  return String(v);
}

function MetricRow({
  label,
  metric,
  primary,
  secondary,
  badge,
}: {
  label: string;
  metric?: EngineValue | { error: string };
  primary: string;
  secondary?: string;
  badge?: string;
}) {
  if (!metric || "error" in metric) {
    return (
      <div className="card">
        <h3 className="text-xs uppercase text-muted mb-1">{label}</h3>
        <p className="text-muted text-sm">—</p>
      </div>
    );
  }
  const v = metric.value;
  return (
    <div className="card">
      <h3 className="text-xs uppercase text-muted mb-1">{label}</h3>
      <div className="text-2xl font-mono mb-1">{fmt(v[primary])}</div>
      {secondary && (
        <div className="text-xs text-muted">
          {secondary}: <span className="font-mono">{fmt(v[secondary])}</span>
        </div>
      )}
      {badge && v[badge] !== undefined && (
        <div className="inline-block mt-2 px-2 py-0.5 rounded bg-accent/20 text-xs uppercase">
          {String(v[badge])}
        </div>
      )}
    </div>
  );
}

export default function PlayerTacticalPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const playerId = params.id;
  const lastN = search.get("last_n") ?? "10";
  const { data, error, isLoading } = useSWR<PlayerTactical>(
    `/admin/players/${playerId}/tactical-profile?last_n=${lastN}`,
    apiFetch,
  );

  if (error)
    return (
      <main className="max-w-5xl mx-auto p-6">
        <p className="text-red-400">Yüklenemedi: {String(error)}</p>
      </main>
    );
  if (isLoading || !data)
    return (
      <main className="max-w-5xl mx-auto p-6">
        <p className="text-muted">Yükleniyor...</p>
      </main>
    );
  if (data.events_loaded === 0)
    return (
      <main className="max-w-5xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-3">
          Oyuncu #{playerId} — Taktiksel Profil
        </h1>
        <div className="card">
          <p className="text-muted">Bu oyuncu için events tablosunda kayıt yok.</p>
        </div>
      </main>
    );

  const tp = data.tactical_profile;
  return (
    <main className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-1">
        Oyuncu #{playerId} — Taktiksel Profil
      </h1>
      <p className="text-sm text-muted mb-5">
        Son {data.meta.matches_analyzed} maç · {data.meta.minutes_played} dk ·
        takım #{data.meta.team_external_id ?? "—"}
      </p>

      <h2 className="text-lg font-semibold mb-2">Yaratıcı Katkı</h2>
      <div className="grid md:grid-cols-3 gap-3 mb-6">
        <MetricRow label="Player xT" metric={tp.player_xt}
          primary="player_xt_added" secondary="contributions" />
        <MetricRow label="Player xA" metric={tp.player_xa}
          primary="xa_total" secondary="key_passes" />
        <MetricRow label="Overperformance" metric={tp.overperformance}
          primary="total_overperformance" secondary="goals" badge="label" />
      </div>

      <h2 className="text-lg font-semibold mb-2">Top Ataağı</h2>
      <div className="grid md:grid-cols-3 gap-3 mb-6">
        <MetricRow label="Progressive Passes" metric={tp.progressive_passes}
          primary="progressive_per_90" secondary="progressive_share" />
        <MetricRow label="Carries into Final 1/3"
          metric={tp.carries_into_final_third}
          primary="per_90" secondary="deep_to_final_third" />
        <MetricRow label="Off-ball Runs" metric={tp.off_ball_runs}
          primary="forward_runs_per_90" secondary="runs_per_possession" />
      </div>

      <h2 className="text-lg font-semibold mb-2">Pres & Tehdit</h2>
      <div className="grid md:grid-cols-2 gap-3 mb-6">
        <MetricRow label="Press Resistance" metric={tp.press_resistance}
          primary="completion_rate_under_press"
          secondary="completion_rate_unpressed" />
        <MetricRow label="VAEP (Possession Value)" metric={tp.vaep}
          primary="vaep_per_90" secondary="vaep_value" badge="model_version" />
      </div>

      <p className="text-xs text-muted mt-3">
        VAEP = ΔP(score) − ΔP(concede). Şu an heuristic baseline; v2 ML.
      </p>
    </main>
  );
}
