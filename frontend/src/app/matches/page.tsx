"use client";

import useSWR from "swr";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

interface MatchSummary {
  match_id: number;
  home_team_id: number;
  away_team_id: number;
  kickoff: string;
}

export default function MatchesPage() {
  // Backend `/teams` endpoint var; maç listesi için /admin/leagues-summary
  // veya per-team /teams/{id}/schedule kullanılabilir. Bu skeleton tek bir
  // takımın yaklaşan maçlarını gösterir.
  const { data, error, isLoading } = useSWR<MatchSummary[]>(
    "/teams/611/schedule",  // TODO: dinamik team
    async (path: string) => {
      const sched = await apiFetch<any>(path);
      return (sched?.value?.next_kickoffs ?? []).map((iso: string, i: number) => ({
        match_id: 1000 + i, home_team_id: 611, away_team_id: 0, kickoff: iso,
      }));
    },
  );

  if (isLoading) return <p className="p-8 text-muted">Yükleniyor...</p>;
  if (error) return <p className="p-8 text-bad">Hata: {String(error)}</p>;

  return (
    <main className="max-w-5xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">Yaklaşan maçlar</h1>
      <ul className="space-y-2">
        {(data ?? []).map((m) => (
          <li key={m.match_id} className="card flex items-center justify-between">
            <div>
              <span className="font-mono text-sm text-muted">{m.kickoff.slice(0, 16)}</span>
              <span className="ml-4">Team {m.home_team_id} vs Team {m.away_team_id}</span>
            </div>
            <Link href={`/matches/${m.match_id}`} className="text-accent text-sm">Detay →</Link>
          </li>
        ))}
        {(!data || data.length === 0) && (
          <li className="text-muted">Maç yok. Backend'de sync_league çalıştırıldı mı?</li>
        )}
      </ul>
    </main>
  );
}
