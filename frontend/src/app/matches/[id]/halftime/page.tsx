"use client";

import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface HalftimeBrief {
  match_external_id: number;
  my_team_external_id: number;
  opponent_team_external_id: number;
  my_side: "home" | "away";
  halftime_score: string;
  events_loaded: number;
  first_half_event_counts?: {
    passes: number;
    carries: number;
    defensive_actions: number;
    shots: number;
  };
  stats?: {
    ppda: number;
    pressing_style: string;
    field_tilt_my_share: number;
    team_xt_total: number;
    match_dominance_score: number;
    match_dominance_label: string;
  };
  opponent_weakness?: {
    most_vulnerable_channel: string;
    recommendation: string;
    by_channel: { channel: string; score: number; our_attacks: number; opp_def_actions: number }[];
  };
  fatigue_alerts?: {
    player_id: number;
    fatigue_score: number;
    recommendation: string;
    pass_completion_drop: number;
  }[];
  opponent_set_piece_pattern?: {
    most_frequent_zone?: string;
    most_dangerous_zone?: string;
    alert_text?: string;
    total_shots?: number;
  };
  sub_recommendations?: {
    recommendations: {
      player_external_id: number;
      urgency_score: number;
      urgency_label: string;
      reasons: string[];
    }[];
    score_state?: string;
  };
  ai_brief?: string;
  note?: string;
}

function Stat({ label, value, badge }: {
  label: string; value: string | number; badge?: string;
}) {
  return (
    <div className="card">
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

export default function HalftimePage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const matchId = params.id;
  const myTeam = search.get("my_team_id");
  const { data, error, isLoading } = useSWR<HalftimeBrief>(
    myTeam ? `/admin/matches/${matchId}/halftime-brief?my_team_id=${myTeam}` : null,
    apiFetch,
  );

  if (!myTeam) {
    return (
      <main className="max-w-4xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-3">Devre Arası Brief</h1>
        <div className="card">
          <p className="text-muted">
            Bu sayfa için <code className="font-mono">?my_team_id=&lt;TEAM_ID&gt;</code>{" "}
            parametresi gerek (kendi takımın hangisi).
          </p>
          <p className="text-xs text-muted mt-2">
            Örnek:{" "}
            <code className="font-mono">/matches/{matchId}/halftime?my_team_id=11</code>
          </p>
        </div>
      </main>
    );
  }

  if (error)
    return (
      <main className="max-w-4xl mx-auto p-6">
        <p className="text-red-400">Yüklenemedi: {String(error)}</p>
      </main>
    );
  if (isLoading || !data)
    return (
      <main className="max-w-4xl mx-auto p-6">
        <p className="text-muted">Yükleniyor...</p>
      </main>
    );

  if (data.events_loaded === 0) {
    return (
      <main className="max-w-4xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-3">Devre Arası Brief</h1>
        <div className="card">
          <p className="text-muted">
            Bu maç için events tablosunda kayıt yok. Önce event ingest çağrısı:
          </p>
          <p className="text-xs text-muted mt-2">
            <code className="font-mono">
              python -m scripts.ingest_statsbomb_events --tenant t-default
              --match {matchId}
            </code>
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-1">Devre Arası — Takım #{data.my_team_external_id}</h1>
      <p className="text-sm text-muted mb-5">
        Maç #{data.match_external_id} · vs #{data.opponent_team_external_id} (
        {data.my_side === "home" ? "ev" : "dep"}) · İY skor{" "}
        <span className="font-mono">{data.halftime_score}</span> ·{" "}
        {data.events_loaded} event
      </p>

      <h2 className="text-lg font-semibold mb-2">1. Yarı Sayılar</h2>
      <div className="grid md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <Stat label="PPDA" value={data.stats?.ppda.toFixed(2) ?? "—"} />
        <Stat label="Pres Tarzı" value="" badge={data.stats?.pressing_style} />
        <Stat label="Field Tilt"
          value={data.stats ? `%${Math.round(data.stats.field_tilt_my_share * 100)}` : "—"} />
        <Stat label="Team xT" value={data.stats?.team_xt_total.toFixed(2) ?? "—"} />
        <Stat label="Dominance"
          value={data.stats?.match_dominance_score.toFixed(2) ?? "—"}
          badge={data.stats?.match_dominance_label} />
        <Stat label="Şutlar" value={data.first_half_event_counts?.shots ?? 0} />
      </div>

      {data.opponent_weakness && (
        <>
          <h2 className="text-lg font-semibold mb-2">Rakibin Zayıf Kanalı</h2>
          <div className="card mb-6">
            <div className="text-xl font-mono mb-1">
              {data.opponent_weakness.most_vulnerable_channel.toUpperCase()}
            </div>
            <p className="text-sm text-muted mb-3">
              {data.opponent_weakness.recommendation}
            </p>
            <div className="grid grid-cols-3 gap-2">
              {data.opponent_weakness.by_channel.map((c) => (
                <div key={c.channel} className="text-xs text-muted">
                  <div className="font-mono text-base text-fg">{c.channel}</div>
                  bizim atak: {c.our_attacks} · rakip def: {c.opp_def_actions}
                  <br />score: <span className="font-mono">{c.score}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {data.fatigue_alerts && data.fatigue_alerts.length > 0 && (
        <>
          <h2 className="text-lg font-semibold mb-2">
            Yorgun Oyuncular ({data.fatigue_alerts.length})
          </h2>
          <div className="grid md:grid-cols-2 gap-3 mb-6">
            {data.fatigue_alerts.map((f) => (
              <div key={f.player_id} className="card">
                <div className="flex items-center justify-between mb-1">
                  <div className="font-mono">Player #{f.player_id}</div>
                  <span
                    className={
                      f.recommendation === "urgent_sub"
                        ? "px-2 py-0.5 rounded bg-red-500/20 text-xs uppercase"
                        : "px-2 py-0.5 rounded bg-yellow-500/20 text-xs uppercase"
                    }
                  >
                    {f.recommendation}
                  </span>
                </div>
                <div className="text-sm text-muted">
                  Fatigue:{" "}
                  <span className="font-mono">{f.fatigue_score.toFixed(2)}</span>
                  {" · "}
                  Pas kaybı:{" "}
                  <span className="font-mono">
                    %{Math.round(f.pass_completion_drop * 100)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {data.opponent_set_piece_pattern
        && (data.opponent_set_piece_pattern.total_shots ?? 0) > 0 && (
        <>
          <h2 className="text-lg font-semibold mb-2">Rakip Set-Piece Pattern</h2>
          <div className="card mb-6">
            <div className="text-sm mb-2">
              {data.opponent_set_piece_pattern.alert_text}
            </div>
            <div className="text-xs text-muted">
              Toplam set-piece şutu:{" "}
              <span className="font-mono">
                {data.opponent_set_piece_pattern.total_shots}
              </span>{" "}
              · En sık:{" "}
              <span className="font-mono">
                {data.opponent_set_piece_pattern.most_frequent_zone}
              </span>{" "}
              · En tehlikeli:{" "}
              <span className="font-mono">
                {data.opponent_set_piece_pattern.most_dangerous_zone}
              </span>
            </div>
          </div>
        </>
      )}

      {data.sub_recommendations
        && data.sub_recommendations.recommendations.length > 0 && (
        <>
          <h2 className="text-lg font-semibold mb-2">
            45. dk Oyuncu Değişikliği Önerileri
          </h2>
          <div className="grid md:grid-cols-3 gap-3 mb-6">
            {data.sub_recommendations.recommendations.map((rec) => (
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
                <div className="flex items-baseline justify-between mb-1">
                  <span className="font-mono">
                    Player #{rec.player_external_id}
                  </span>
                  <span className="text-xs uppercase px-2 py-0.5 rounded bg-accent/20">
                    {rec.urgency_label}
                  </span>
                </div>
                <div className="text-xs text-muted mb-2">
                  Aciliyet{" "}
                  <span className="font-mono">{rec.urgency_score.toFixed(2)}</span>
                </div>
                <ul className="text-xs space-y-1">
                  {rec.reasons.slice(0, 3).map((r, i) => (
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

      {data.ai_brief && (
        <>
          <h2 className="text-lg font-semibold mb-2">AI Brief — TD için 2. yarı önerisi</h2>
          <div className="card whitespace-pre-wrap text-sm leading-relaxed">
            {data.ai_brief}
          </div>
        </>
      )}
    </main>
  );
}
