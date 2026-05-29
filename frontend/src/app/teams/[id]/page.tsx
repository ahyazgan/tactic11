"use client";

import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConfidenceBadge } from "@/components/ui";

interface Confidence {
  score: number;
  label: string;
  drivers: string[];
}

interface FormResponse {
  value: {
    matches_played: number;
    wins: number;
    draws: number;
    losses: number;
    goals_for: number;
    goals_against: number;
    points_per_game: number;
    last_results: ("W" | "D" | "L")[];
  };
  confidence: Confidence | null;
}

interface RatingResponse {
  value: {
    rating: number;
    home_rating: number | null;
    away_rating: number | null;
    matches_considered: number;
  };
  confidence: Confidence | null;
}

function ResultDot({ r }: { r: "W" | "D" | "L" }) {
  const color = r === "W" ? "bg-good" : r === "L" ? "bg-bad" : "bg-muted";
  return (
    <span className={`inline-block w-6 h-6 rounded text-center text-xs leading-6 font-bold text-white ${color}`}>
      {r}
    </span>
  );
}

export default function TeamDetailPage() {
  const params = useParams<{ id: string }>();
  const teamId = params.id;

  const { data: form } = useSWR<FormResponse>(`/teams/${teamId}/form`, apiFetch);
  const { data: rating } = useSWR<RatingResponse>(`/teams/${teamId}/rating`, apiFetch);

  return (
    <main className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Takım #{teamId}</h1>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm uppercase text-muted">Son form</h2>
            {form?.confidence && (
              <ConfidenceBadge
                score={form.confidence.score}
                label={form.confidence.label}
                drivers={form.confidence.drivers}
              />
            )}
          </div>
          {form ? (
            <>
              <div className="text-3xl font-mono mb-2">
                {form.value.wins}-{form.value.draws}-{form.value.losses}
              </div>
              <div className="text-sm text-muted mb-3">
                PPG: <span className="font-mono">{form.value.points_per_game}</span> ·{" "}
                GF/GA: <span className="font-mono">{form.value.goals_for}/{form.value.goals_against}</span>
              </div>
              <div className="flex gap-1">
                {form.value.last_results.slice(0, 10).map((r, i) => (
                  <ResultDot key={i} r={r} />
                ))}
              </div>
            </>
          ) : (
            <p className="text-muted">Yükleniyor...</p>
          )}
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm uppercase text-muted">Rating</h2>
            {rating?.confidence && (
              <ConfidenceBadge
                score={rating.confidence.score}
                label={rating.confidence.label}
                drivers={rating.confidence.drivers}
              />
            )}
          </div>
          {rating ? (
            <>
              <div className="text-3xl font-mono mb-2">{rating.value.rating.toFixed(2)}</div>
              <div className="text-sm text-muted">
                Ev: <span className="font-mono">{rating.value.home_rating?.toFixed(2) ?? "—"}</span> ·{" "}
                Dep: <span className="font-mono">{rating.value.away_rating?.toFixed(2) ?? "—"}</span>
              </div>
              <div className="text-xs text-muted mt-2">{rating.value.matches_considered} maç değerlendirildi</div>
            </>
          ) : (
            <p className="text-muted">Yükleniyor...</p>
          )}
        </div>
      </div>
    </main>
  );
}
