"use client";

import useSWR from "swr";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { DataTable, type Column } from "@/components/ui";

interface League {
  sport: string;
  external_id: number;
  name: string;
  season: number;
  country: string | null;
}

const COLUMNS: Column<League>[] = [
  { key: "name", header: "Lig", sortable: true,
    sortValue: (r) => r.name },
  { key: "country", header: "Ülke", sortable: true,
    sortValue: (r) => r.country ?? "",
    render: (r) => r.country ?? "—" },
  { key: "season", header: "Sezon", align: "right", sortable: true,
    sortValue: (r) => r.season,
    render: (r) => `${r.season}/${r.season + 1}` },
  { key: "external_id", header: "ID", align: "right",
    sortable: true, sortValue: (r) => r.external_id,
    width: "5rem" },
];

export default function LeaguesPage() {
  const router = useRouter();
  const { data, error, isLoading } = useSWR<League[]>(
    "/leagues",
    apiFetch,
  );

  return (
    <div className="max-w-6xl">
      <h1 className="text-lg font-semibold text-text mb-3">Ligler</h1>

      {isLoading && (
        <p className="text-textmut text-[13px]">Yükleniyor...</p>
      )}
      {error && (
        <p className="text-danger text-[13px]">
          Yüklenemedi: {String(error)}
        </p>
      )}
      {data && (
        <DataTable<League>
          columns={COLUMNS}
          rows={data}
          rowKey={(r) => r.external_id}
          onRowClick={(r) => router.push(`/leagues/${r.external_id}/teams`)}
          emptyMessage="Henüz lig sync edilmedi. python -m scripts.sync_league --league N --season Y"
        />
      )}
    </div>
  );
}
