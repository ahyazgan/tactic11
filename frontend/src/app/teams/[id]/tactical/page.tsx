"use client";

import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface EngineValue {
  value: Record<string, unknown>;
  audit?: {
    engine: string;
    metric: string;
    formula: string;
  };
}

interface TacticalProfile {
  team_id: number;
  last_n: number;
  matches_analyzed: number[];
  events_loaded: number;
  event_counts?: {
    passes: number;
    carries: number;
    defensive_actions: number;
    shots: number;
  };
  tactical_profile: Record<string, EngineValue | { error: string }>;
  note?: string;
}

function MetricCard({
  title,
  metric,
  primary,
  secondary,
  badge,
}: {
  title: string;
  metric?: EngineValue | { error: string };
  primary: string;
  secondary?: string;
  badge?: string | null;
}) {
  if (!metric) {
    return (
      <div className="card">
        <h3 className="text-xs uppercase text-muted mb-2">{title}</h3>
        <p className="text-muted text-sm">—</p>
      </div>
    );
  }
  if ("error" in metric) {
    return (
      <div className="card border-red-500/30">
        <h3 className="text-xs uppercase text-muted mb-2">{title}</h3>
        <p className="text-xs text-red-400">{metric.error.slice(0, 80)}</p>
      </div>
    );
  }
  const v = metric.value as Record<string, unknown>;
  const primaryVal = v[primary];
  const secondaryVal = secondary ? v[secondary] : null;
  const badgeVal = badge ? v[badge] : null;
  return (
    <div className="card">
      <h3 className="text-xs uppercase text-muted mb-2">{title}</h3>
      <div className="text-2xl font-mono mb-1">
        {typeof primaryVal === "number" ? primaryVal.toFixed(2) : String(primaryVal ?? "—")}
      </div>
      {secondaryVal !== null && secondaryVal !== undefined && (
        <div className="text-xs text-muted">
          {secondary}: <span className="font-mono">{String(secondaryVal)}</span>
        </div>
      )}
      {badgeVal !== null && badgeVal !== undefined && (
        <div className="inline-block mt-2 px-2 py-0.5 rounded bg-accent/20 text-xs uppercase">
          {String(badgeVal)}
        </div>
      )}
    </div>
  );
}

export default function TacticalProfilePage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const teamId = params.id;
  const lastN = search.get("last_n") ?? "10";
  const opponentId = search.get("opponent_id");
  const qs = opponentId
    ? `?last_n=${lastN}&opponent_id=${opponentId}`
    : `?last_n=${lastN}`;

  const { data, error, isLoading } = useSWR<TacticalProfile>(
    `/admin/teams/${teamId}/tactical-profile${qs}`,
    apiFetch,
  );

  if (error) {
    return (
      <main className="max-w-6xl mx-auto p-6">
        <p className="text-red-400">Yüklenemedi: {String(error)}</p>
      </main>
    );
  }
  if (isLoading || !data) {
    return (
      <main className="max-w-6xl mx-auto p-6">
        <p className="text-muted">Yükleniyor...</p>
      </main>
    );
  }
  if (data.events_loaded === 0) {
    return (
      <main className="max-w-6xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-4">
          Takım #{teamId} — Taktiksel Profil
        </h1>
        <div className="card">
          <p className="text-muted">
            events tablosunda bu takım için kayıt yok.
          </p>
          <p className="text-xs text-muted mt-2">
            Ingest çağırın: <code className="font-mono">python -m
            scripts.ingest_statsbomb_events --tenant t-default --team {teamId}</code>
          </p>
        </div>
      </main>
    );
  }

  const tp = data.tactical_profile;
  return (
    <main className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-2">
        Takım #{teamId} — Taktiksel Profil
      </h1>
      <p className="text-sm text-muted mb-6">
        Son {data.matches_analyzed.length} maç ({data.events_loaded} event)
        {opponentId && ` · vs #${opponentId}`}
      </p>

      <h2 className="text-lg font-semibold mt-2 mb-3">Pres & Savunma</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <MetricCard title="PPDA"
          metric={tp.ppda} primary="ppda" secondary="opp_passes_in_press_zone" />
        <MetricCard title="Pressing Trigger"
          metric={tp.pressing_trigger} primary="avg_recovery_time_min"
          secondary="fast_recovery_ratio" badge="style_label" />
        <MetricCard title="Savunma Hattı"
          metric={tp.defensive_line} primary="avg_x"
          secondary="actions_counted" badge="line_label" />
        <MetricCard title="Recovery Zone"
          metric={tp.recovery_zone_heat} primary="attacking_share"
          secondary="defensive_share" badge="style_label" />
        <MetricCard title="Compactness"
          metric={tp.compactness} primary="overall_stdev" badge="label" />
        <MetricCard title="Defensive Duels"
          metric={tp.defensive_duels} primary="win_rate"
          secondary="duels_won" />
        <MetricCard title="Counter-Press"
          metric={tp.counter_press_triggers} primary="pressure_responses"
          badge="dominant_trigger" />
        <MetricCard title="Set-piece Zones"
          metric={tp.set_piece_zones} primary="total_shots"
          badge="most_threatening_zone" />
      </div>

      <h2 className="text-lg font-semibold mt-2 mb-3">Hücum & Geçiş</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <MetricCard title="Tempo"
          metric={tp.tempo} primary="passes_per_minute" badge="label" />
        <MetricCard title="Direct Play"
          metric={tp.direct_play} primary="avg_directness" badge="style_label" />
        <MetricCard title="Transition Speed"
          metric={tp.transition} primary="avg_time_to_shot_min"
          secondary="fast_counter_ratio" badge="style_label" />
        <MetricCard title="Possession Quality"
          metric={tp.possession_quality} primary="quality_score"
          secondary="avg_passes_per_sequence" badge="label" />
        <MetricCard title="Channel Pref."
          metric={tp.channel_preference} primary="left_share"
          secondary="right_share" badge="dominant_channel" />
        <MetricCard title="Final 3rd Entries"
          metric={tp.final_third_entries} primary="total_entries"
          secondary="pass_share" badge="dominant_entry_channel" />
        <MetricCard title="Cross Effectiveness"
          metric={tp.cross_effectiveness} primary="total_crosses"
          secondary="shots_from_crosses" badge="most_effective_zone" />
        <MetricCard title="Cutback Frequency"
          metric={tp.cutback_frequency} primary="cutbacks_per_match"
          secondary="goals_from_cutbacks" />
      </div>

      <h2 className="text-lg font-semibold mt-2 mb-3">Toplam Tehdit</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <MetricCard title="Team xT"
          metric={tp.team_xt} primary="total_xt" />
        <MetricCard title="Build-up"
          metric={tp.build_up_pattern} primary="long_ball_ratio"
          secondary="counter_attack_share" badge="dominant_start_zone" />
        <MetricCard title="Press Resistance"
          metric={tp.press_resistance} primary="completion_rate_under_press"
          secondary="passes_under_press" />
        {tp.field_tilt && (
          <MetricCard title="Field Tilt"
            metric={tp.field_tilt} primary="team_a_tilt"
            secondary="team_b_tilt" />
        )}
        {tp.coaching_identity && (
          <MetricCard title="Coaching Identity"
            metric={tp.coaching_identity} primary="archetype"
            secondary="top_features" />
        )}
      </div>

      <p className="text-xs text-muted mt-4">
        Audit: tüm metriklerin formülü{" "}
        <code className="font-mono">/admin/teams/{teamId}/tactical-profile</code>{" "}
        endpoint yanıtının <code>audit.formula</code> alanında.
      </p>
    </main>
  );
}
