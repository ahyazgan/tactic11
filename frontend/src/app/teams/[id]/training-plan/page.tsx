"use client";

import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DataTable, Panel, Pill, StatTile, type Column } from "@/components/ui";

interface Drill {
  name: string;
  focus: string;
  rationale: string;
  duration_min: string;
}

interface TrainingPlanResponse {
  my_team_external_id?: number;
  opponent_external_id?: number;
  events_loaded?: number;
  matches_analyzed?: number;
  opponent_profile?: {
    ppda: number;
    pressing_style: string;
    recovery_style: string;
    archetype: string;
    dominant_channel: string;
  };
  drills?: Drill[];
  ai_brief?: string;
  note?: string;
}

const DRILL_COLUMNS: Column<Drill>[] = [
  {
    key: "name",
    header: "Drill",
    sortable: true,
    sortValue: (r) => r.name,
    width: "20rem",
  },
  {
    key: "focus",
    header: "Odak",
    sortable: true,
    sortValue: (r) => r.focus,
    width: "14rem",
  },
  {
    key: "duration_min",
    header: "Süre",
    align: "right",
    sortable: true,
    sortValue: (r) => Number(r.duration_min) || 0,
    render: (r) => `${r.duration_min}'`,
    width: "4rem",
  },
  {
    key: "rationale",
    header: "Gerekçe",
    render: (r) => (
      <span title={r.rationale} className="text-textmut">
        {r.rationale.length > 80
          ? r.rationale.slice(0, 80) + "..."
          : r.rationale}
      </span>
    ),
  },
];

export default function TrainingPlanPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const teamId = params.id;
  const opponentId = search.get("opponent_id");

  const { data, error, isLoading } = useSWR<TrainingPlanResponse>(
    opponentId
      ? `/admin/teams/${teamId}/training-plan?opponent_id=${opponentId}`
      : null,
    apiFetch,
  );

  if (!opponentId) {
    return (
      <div className="max-w-5xl">
        <h1 className="text-lg font-semibold text-text mb-3">
          Takım #{teamId} — Antrenman Planı
        </h1>
        <Panel>
          <p className="text-textmut text-[13px]">
            <code className="font-mono">?opponent_id=&lt;N&gt;</code>{" "}
            parametresi gerek.
          </p>
        </Panel>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-5xl">
        <p className="text-danger text-[13px]">Yüklenemedi: {String(error)}</p>
      </div>
    );
  }
  if (isLoading || !data) {
    return (
      <div className="max-w-5xl">
        <p className="text-textmut text-[13px]">Yükleniyor...</p>
      </div>
    );
  }
  if ((data.events_loaded ?? 0) === 0) {
    return (
      <div className="max-w-5xl">
        <h1 className="text-lg font-semibold text-text mb-3">
          Takım #{teamId} vs Rakip #{opponentId}
        </h1>
        <Panel>
          <p className="text-textmut text-[13px]">{data.note ?? "Veri yok."}</p>
        </Panel>
      </div>
    );
  }

  const op = data.opponent_profile;

  return (
    <div className="max-w-6xl space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-text">
          Antrenman Planı — Takım #{teamId} vs Rakip #{opponentId}
        </h1>
        <p className="text-[12px] text-textmut">
          {data.matches_analyzed} rakip maç incelendi · {data.events_loaded} event
        </p>
      </div>

      {op && (
        <section>
          <h2 className="text-sm font-semibold text-text mb-2">Rakip Profili</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <StatTile label="PPDA" value={op.ppda.toFixed(2)} />
            <div className="bg-surface border border-border rounded-md p-3">
              <span className="text-[10px] uppercase tracking-wider text-textdim">
                Pres tarzı
              </span>
              <div className="mt-1">
                <Pill variant="neutral">{op.pressing_style}</Pill>
              </div>
            </div>
            <div className="bg-surface border border-border rounded-md p-3">
              <span className="text-[10px] uppercase tracking-wider text-textdim">
                Kazanım
              </span>
              <div className="mt-1">
                <Pill variant="neutral">{op.recovery_style}</Pill>
              </div>
            </div>
            <div className="bg-surface border border-border rounded-md p-3">
              <span className="text-[10px] uppercase tracking-wider text-textdim">
                Arketip
              </span>
              <div className="mt-1">
                <Pill variant="neutral">{op.archetype}</Pill>
              </div>
            </div>
            <div className="bg-surface border border-border rounded-md p-3">
              <span className="text-[10px] uppercase tracking-wider text-textdim">
                Kanal
              </span>
              <div className="mt-1">
                <Pill variant="neutral">{op.dominant_channel}</Pill>
              </div>
            </div>
          </div>
        </section>
      )}

      {data.drills && data.drills.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-text mb-2">
            Önerilen Drill'ler
          </h2>
          <DataTable<Drill>
            columns={DRILL_COLUMNS}
            rows={data.drills}
            rowKey={(r) => r.name}
            emptyMessage="Drill yok"
          />
        </section>
      )}

      {data.ai_brief && (
        <section>
          <h2 className="text-sm font-semibold text-text mb-2">Hafta Briefi</h2>
          <Panel>
            <p className="text-[13px] text-text whitespace-pre-wrap leading-[18px]">
              {data.ai_brief}
            </p>
          </Panel>
        </section>
      )}
    </div>
  );
}
