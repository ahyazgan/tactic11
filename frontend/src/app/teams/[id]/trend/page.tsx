"use client";

import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { TrendLineChart } from "@/components/charts/TrendLineChart";

interface TrendData {
  series: number[];
  mean: number;
  slope: number;
  direction: string;
  biggest_shift: number;
  biggest_shift_match_idx: number;
  biggest_shift_match_id: number | null;
}

interface TacticalTrendResponse {
  team_id: number;
  last_n: number;
  matches_analyzed: number;
  matches?: { match_id: number; kickoff: string | null; opp_id: number; score: string }[];
  trends?: Record<string, TrendData>;
  note?: string;
}

const METRIC_CONFIG: { key: string; title: string; higherBetter: boolean }[] = [
  { key: "ppda", title: "PPDA (Pres Yoğunluğu)", higherBetter: false },
  { key: "field_tilt", title: "Field Tilt (Bizim Pay)", higherBetter: true },
  { key: "team_xt", title: "Takım xT", higherBetter: true },
  { key: "possession_share", title: "Possession %", higherBetter: true },
  { key: "dominance_score", title: "Match Dominance", higherBetter: true },
];

export default function TacticalTrendPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const teamId = params.id;
  const lastN = search.get("last_n") ?? "10";
  const { data, error, isLoading } = useSWR<TacticalTrendResponse>(
    `/admin/teams/${teamId}/tactical-trend?last_n=${lastN}`,
    apiFetch,
  );

  if (error)
    return (
      <main className="max-w-6xl mx-auto p-6">
        <p className="text-red-400">Yüklenemedi: {String(error)}</p>
      </main>
    );
  if (isLoading || !data)
    return (
      <main className="max-w-6xl mx-auto p-6">
        <p className="text-muted">Yükleniyor...</p>
      </main>
    );

  if (data.matches_analyzed === 0)
    return (
      <main className="max-w-6xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-3">
          Takım #{teamId} — Sezon Trendi
        </h1>
        <div className="card">
          <p className="text-muted">{data.note || "Veri yok"}</p>
        </div>
      </main>
    );

  const matches = data.matches || [];

  return (
    <main className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-1">
        Takım #{teamId} — Sezon Trendi
      </h1>
      <p className="text-sm text-muted mb-6">
        Son {data.matches_analyzed} maç · kronolojik sıra (eski → yeni)
      </p>

      <h2 className="text-lg font-semibold mb-3">Maç Listesi</h2>
      <div className="card mb-6">
        <div className="grid md:grid-cols-3 lg:grid-cols-5 gap-2 text-xs">
          {matches.map((m, i) => (
            <div key={m.match_id} className="font-mono">
              <span className="text-muted">M{i + 1}:</span>{" "}
              #{m.match_id}{" "}
              <span className="text-muted">vs #{m.opp_id}</span>{" "}
              <span>{m.score}</span>
            </div>
          ))}
        </div>
      </div>

      <h2 className="text-lg font-semibold mb-3">Metrik Trendleri</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
        {METRIC_CONFIG.map((m) => {
          const t = data.trends?.[m.key];
          if (!t) return null;
          return (
            <TrendLineChart
              key={m.key}
              title={m.title}
              trend={t}
              matches={matches}
              higherIsBetter={m.higherBetter}
            />
          );
        })}
      </div>

      <h2 className="text-lg font-semibold mb-3">En Büyük Tek-Maç Sıçramaları</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
        {METRIC_CONFIG.map((m) => {
          const t = data.trends?.[m.key];
          if (!t || t.biggest_shift_match_id === null) return null;
          const targetMatch = matches[t.biggest_shift_match_idx];
          return (
            <div key={m.key} className="card">
              <h3 className="text-xs uppercase text-muted mb-1">{m.title}</h3>
              <div className="text-lg font-mono">
                Δ {t.biggest_shift > 0 ? "+" : ""}
                {t.biggest_shift.toFixed(2)}
              </div>
              <div className="text-xs text-muted mt-1">
                Maç #{t.biggest_shift_match_id}
                {targetMatch && ` (${targetMatch.score} vs #${targetMatch.opp_id})`}
              </div>
            </div>
          );
        })}
      </div>
    </main>
  );
}
