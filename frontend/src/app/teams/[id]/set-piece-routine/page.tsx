"use client";

import * as React from "react";
import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel, Pill } from "@/components/ui";
import { SetPieceZoneMap } from "@/components/charts/SetPieceZoneMap";

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
  my_events?: number;
  opp_events?: number;
}

const SET_PIECE_TYPES = ["all", "corner_kick", "free_kick", "set_piece"];

const ZONE_TR: Record<string, string> = {
  near_post: "Yakın direk",
  central_6yd: "Kale ağzı (6 yd)",
  far_post: "Uzak direk",
  penalty_arc: "Ceza yayı",
  outside_box: "Ceza dışı",
};

export default function SetPieceRoutinePage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const teamId = params.id;
  const opponentId = search.get("opponent_id");
  const [spType, setSpType] = React.useState<string>("all");
  const [selectedZone, setSelectedZone] = React.useState<string | undefined>();

  const url = opponentId
    ? `/admin/teams/${teamId}/set-piece-routine` +
      `?opponent_id=${opponentId}&set_piece_type=${spType}`
    : null;
  const { data, error, isLoading } = useSWR<RoutineResponse>(url, apiFetch);

  if (!opponentId) {
    return (
      <div className="max-w-5xl">
        <Panel>
          <p className="text-textmut text-[13px]">
            <code className="font-mono">?opponent_id=&lt;N&gt;</code> gerek.
          </p>
        </Panel>
      </div>
    );
  }

  const scoresByZone: Record<string, number> = {};
  data?.value?.top_recommendations.forEach((r) => {
    // routine_score zaten kompozit; 0-1 normalize varsay (clamp)
    scoresByZone[r.target_zone] = Math.min(1, r.routine_score);
  });

  return (
    <div className="max-w-6xl space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-text">
          Set-piece Routine — Takım #{teamId} vs Rakip #{opponentId}
        </h1>
        {data?.value && (
          <p className="text-[12px] text-textmut">
            {data.value.matches_analyzed} maç incelendi · tip{" "}
            <code className="font-mono">{data.value.set_piece_type}</code>
          </p>
        )}
      </div>

      <Panel title="Set-piece tipi">
        <div className="flex gap-2">
          {SET_PIECE_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setSpType(t)}
              className={`text-[11px] uppercase tracking-wide px-3 py-1 rounded border transition-colors ${
                spType === t
                  ? "bg-accent/15 border-accent text-accent"
                  : "border-borderlt text-textmut hover:text-text"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </Panel>

      {error && (
        <p className="text-danger text-[13px]">Yüklenemedi: {String(error)}</p>
      )}
      {isLoading && (
        <p className="text-textmut text-[13px]">Hesaplanıyor...</p>
      )}
      {data?.note && (
        <Panel>
          <p className="text-textmut text-[13px]">{data.note}</p>
        </Panel>
      )}

      {data?.value && (
        <div className="grid lg:grid-cols-2 gap-4">
          <section>
            <h2 className="text-sm font-semibold text-text mb-2">
              Zone Haritası
            </h2>
            <SetPieceZoneMap
              scoresByZone={scoresByZone}
              avoidZone={data.value.avoid_zone}
              selectedZone={selectedZone}
              onSelectZone={setSelectedZone}
            />
            <p className="text-[11px] text-textmut mt-2">
              ✕ işareti: rakibin saldırgan pattern'i — rakip burayı bekliyor,
              defansif yığınak yapar.
            </p>
          </section>

          <section>
            <h2 className="text-sm font-semibold text-text mb-2">
              Top Öneriler ({data.value.top_recommendations.length})
            </h2>
            <div className="space-y-3">
              {data.value.top_recommendations.map((r, i) => (
                <Panel key={i}>
                  <div className="flex items-baseline justify-between mb-2">
                    <h3 className="text-sm font-semibold text-text">
                      {ZONE_TR[r.target_zone] ?? r.target_zone}
                    </h3>
                    <Pill variant="win">
                      score {r.routine_score.toFixed(2)}
                    </Pill>
                  </div>
                  <div className="text-[12px] text-text mb-2">
                    Teknik: <span className="font-mono">{r.technique}</span>
                  </div>
                  <p className="text-[12px] text-textmut leading-[16px]">
                    {r.rationale}
                  </p>
                  <div className="mt-2 flex gap-3 text-[11px] text-textdim">
                    <span>
                      rakip zayıflığı{" "}
                      <span className="font-mono text-loss">
                        {(r.opponent_weakness_score * 100).toFixed(0)}%
                      </span>
                    </span>
                    <span>
                      bizim gücümüz{" "}
                      <span className="font-mono text-win">
                        {(r.our_strength_score * 100).toFixed(0)}%
                      </span>
                    </span>
                  </div>
                </Panel>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
