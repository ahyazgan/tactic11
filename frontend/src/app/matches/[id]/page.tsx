"use client";

import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConfidenceBadge } from "@/components/ui";

interface PredictResponse {
  value: {
    prob_home_win: number;
    prob_draw: number;
    prob_away_win: number;
    expected_home_goals: number;
    expected_away_goals: number;
    most_likely_score: [number, number];
  };
  audit: any;
  confidence: { score: number; label: string; drivers: string[] } | null;
}

interface MatchInfo {
  match_id: number;
  kickoff: string;
  status: string;
  home_team_id: number;
  away_team_id: number;
  home_score: number | null;
  away_score: number | null;
}

function ProbBar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round(value * 100);
  return (
    <div className="mb-2">
      <div className="flex justify-between text-xs text-muted mb-1">
        <span>{label}</span>
        <span className="font-mono">{pct}%</span>
      </div>
      <div className="h-2 bg-bg rounded overflow-hidden">
        <div
          className="h-full"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

export default function MatchDetailPage() {
  const params = useParams<{ id: string }>();
  const matchId = params.id;

  const { data: predict, error: predictError } = useSWR<PredictResponse>(
    `/matches/${matchId}/predict?use_ml=true`,
    apiFetch,
  );

  // /matches/{id}/info benzeri yok; predict response'unda match info çıkarılabilir
  // Real product: /matches/{id} ekle (mevcut endpoint listesinde yok)
  if (predictError) {
    return (
      <main className="p-8">
        <p className="text-bad">Hata: {String(predictError)}</p>
      </main>
    );
  }

  return (
    <main className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Maç #{matchId}</h1>
      <div className="grid lg:grid-cols-2 gap-4">
        {/* Sol: tahmin + brief */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm uppercase text-muted">Tahmin (engine.predict_ml)</h2>
            {predict?.confidence && (
              <ConfidenceBadge
                score={predict.confidence.score}
                label={predict.confidence.label}
                drivers={predict.confidence.drivers}
              />
            )}
          </div>
          {predict ? (
            <>
              <ProbBar label="Ev galibiyet" value={predict.value.prob_home_win} color="var(--good, #3fb950)" />
              <ProbBar label="Beraberlik" value={predict.value.prob_draw} color="var(--muted, #8b949e)" />
              <ProbBar label="Dep galibiyet" value={predict.value.prob_away_win} color="var(--bad, #f85149)" />
              <div className="mt-4 text-sm">
                <div>Beklenen skor: <span className="font-mono">{predict.value.expected_home_goals.toFixed(2)} - {predict.value.expected_away_goals.toFixed(2)}</span></div>
                <div>En olası skor: <span className="font-mono">{predict.value.most_likely_score[0]}-{predict.value.most_likely_score[1]}</span></div>
              </div>
            </>
          ) : (
            <p className="text-muted">Yükleniyor...</p>
          )}
        </div>

        {/* Sağ: form / load / H2H */}
        <div className="card">
          <h2 className="text-sm uppercase text-muted mb-3">Takım analizi</h2>
          <p className="text-muted text-sm">
            TODO: form/rating/H2H widget'ları. Endpoint: <span className="font-mono">/teams/{"{id}"}/form</span>,{" "}
            <span className="font-mono">/teams/{"{id}"}/rating</span>.
          </p>
        </div>
      </div>
    </main>
  );
}
