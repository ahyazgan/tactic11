"use client";

import * as React from "react";
import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel, Pill, StatTile } from "@/components/ui";

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

function confidencePill(c: string) {
  if (c === "high") return <Pill variant="win">{c}</Pill>;
  if (c === "medium") return <Pill variant="warn">{c}</Pill>;
  return <Pill variant="neutral">{c}</Pill>;
}

export default function SubChessPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const matchId = params.id;
  const myTeamId = search.get("my_team_id");
  const initialMinute = Number(search.get("current_minute") ?? "60");
  const [minute, setMinute] = React.useState<number>(initialMinute);

  const url =
    myTeamId && minute
      ? `/admin/matches/${matchId}/substitution-chess` +
        `?my_team_id=${myTeamId}&current_minute=${minute}`
      : null;

  const { data, error, isLoading } = useSWR<SubChessResponse>(url, apiFetch);

  if (!myTeamId) {
    return (
      <div className="max-w-5xl">
        <Panel>
          <p className="text-textmut text-[13px]">
            <code className="font-mono">?my_team_id=&lt;N&gt;</code> gerek.
          </p>
        </Panel>
      </div>
    );
  }

  const isEvent0 = data?.events_loaded === 0;

  return (
    <div className="max-w-6xl space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-text">
          Sub Chess — Maç #{matchId}
        </h1>
        <p className="text-[12px] text-textmut">
          Takım #{myTeamId} · {minute}. dakika
        </p>
      </div>

      <Panel title="Dakika">
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={5}
            max={90}
            step={5}
            value={minute}
            onChange={(e) => setMinute(Number(e.target.value))}
            className="flex-1"
            aria-label="Maç dakikası"
          />
          <span className="font-mono text-lg w-12 text-right">{minute}'</span>
        </div>
        <p className="text-[11px] text-textmut mt-2">
          Slider'ı oynat → senaryolar yeniden hesaplanır.
        </p>
      </Panel>

      {error && (
        <p className="text-danger text-[13px]">Yüklenemedi: {String(error)}</p>
      )}
      {isLoading && (
        <p className="text-textmut text-[13px]">Hesaplanıyor...</p>
      )}
      {isEvent0 && (
        <Panel>
          <p className="text-textmut text-[13px]">{data?.note}</p>
        </Panel>
      )}

      {data?.value && data.value.scenarios.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-text mb-2">
            Top 3 Senaryo (kalan {data.value.minutes_remaining.toFixed(0)} dk)
          </h2>
          <div className="grid md:grid-cols-3 gap-3">
            {data.value.scenarios.map((s, i) => {
              const isBest = i === data.value!.best_scenario_index;
              return (
                <div
                  key={i}
                  className={`bg-surface border border-border rounded-md p-3 ${
                    isBest ? "border-l-2 border-l-win" : ""
                  }`}
                >
                  <div className="flex items-baseline justify-between mb-2">
                    <span className="text-sm font-semibold text-text">
                      Senaryo {i + 1}
                    </span>
                    {confidencePill(s.confidence)}
                  </div>
                  <div className="text-[13px] text-text mb-2">
                    Player #{s.out_player_id} →{" "}
                    {s.in_player_id ? `#${s.in_player_id}` : "TD seçer"}
                  </div>
                  <StatTile
                    label="Projected Δ dominance"
                    value={
                      (s.projected_dominance_delta > 0 ? "+" : "") +
                      s.projected_dominance_delta.toFixed(3)
                    }
                  />
                  <div className="text-[11px] text-textmut mt-3 space-y-0.5">
                    <div>
                      Out fatigue (şimdi):{" "}
                      <span className="font-mono">
                        {s.out_player_current_fatigue.toFixed(2)}
                      </span>
                    </div>
                    <div>
                      Out projected (FT):{" "}
                      <span className="font-mono text-loss">
                        {s.out_player_projected_fatigue_at_full_time.toFixed(2)}
                      </span>
                    </div>
                    <div>
                      In projected (FT):{" "}
                      <span className="font-mono text-win">
                        {s.in_player_projected_fatigue_at_full_time.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
