"use client";

import useSWR from "swr";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { DataTable, type Column } from "@/components/ui";

interface League {
  external_id: number;
  name: string;
  season: number;
  country: string | null;
}

interface Team {
  sport: string;
  external_id: number;
  name: string;
  country: string | null;
  founded: number | null;
}

const TEAM_COLUMNS: Column<Team>[] = [
  { key: "name", header: "Takım", sortable: true,
    sortValue: (r) => r.name },
  { key: "country", header: "Ülke", sortable: true,
    sortValue: (r) => r.country ?? "",
    render: (r) => r.country ?? "—" },
  { key: "founded", header: "Kuruluş", align: "right",
    sortable: true, sortValue: (r) => r.founded ?? 0,
    render: (r) => r.founded ?? "—",
    width: "6rem" },
  { key: "external_id", header: "ID", align: "right",
    sortable: true, sortValue: (r) => r.external_id,
    width: "5rem" },
];

export default function LeagueTeamsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const leagueId = params.id;

  const { data: leagues } = useSWR<League[]>("/leagues", apiFetch);
  const league = leagues?.find((l) => l.external_id === Number(leagueId));

  const { data: teams, error, isLoading } = useSWR<Team[]>(
    `/teams/${leagueId}`,
    apiFetch,
  );

  return (
    <div className="max-w-6xl">
      <nav className="text-[11px] text-textmut mb-2">
        <Link href="/leagues" className="hover:text-text">Ligler</Link>
        <span className="mx-1">/</span>
        <span className="text-text">{league?.name ?? `#${leagueId}`}</span>
      </nav>

      <h1 className="text-lg font-semibold text-text mb-1">
        {league?.name ?? `Lig #${leagueId}`} — Takımlar
      </h1>
      {league && (
        <p className="text-[12px] text-textmut mb-3">
          {league.country ?? "—"} · {league.season}/{league.season + 1}
        </p>
      )}

      {isLoading && (
        <p className="text-textmut text-[13px]">Yükleniyor...</p>
      )}
      {error && (
        <p className="text-danger text-[13px]">
          Yüklenemedi: {String(error)}
        </p>
      )}
      {teams && (
        <DataTable<Team>
          columns={TEAM_COLUMNS}
          rows={teams}
          rowKey={(r) => r.external_id}
          onRowClick={(r) => router.push(`/teams/${r.external_id}`)}
          emptyMessage="Bu ligde takım yok"
        />
      )}
    </div>
  );
}
