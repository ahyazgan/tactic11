"use client";

import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import {
  DataTable,
  Panel,
  Pill,
  StatTile,
  type Column,
} from "@/components/ui";
import { RequireRole } from "@/lib/auth";

interface JobRow {
  id: number;
  job_name: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  attempts: number;
  error: string | null;
}

interface UsageSummary {
  anthropic_tokens_today?: number;
  api_football_calls_today?: number;
  anthropic_token_limit?: number;
  api_football_daily_limit?: number;
}

interface DbStats {
  [key: string]: number;
}

const JOB_COLUMNS: Column<JobRow>[] = [
  { key: "started_at", header: "Başladı", sortable: true,
    sortValue: (r) => r.started_at,
    render: (r) => new Date(r.started_at).toLocaleString("tr-TR") },
  { key: "job_name", header: "Job", sortable: true,
    sortValue: (r) => r.job_name },
  { key: "status", header: "Durum", sortable: true,
    sortValue: (r) => r.status,
    render: (r) => <StatusPill status={r.status} /> },
  { key: "attempts", header: "Deneme", align: "right",
    sortable: true, sortValue: (r) => r.attempts,
    width: "5rem" },
  { key: "error", header: "Hata",
    render: (r) => r.error
      ? <span className="text-danger">{r.error.slice(0, 60)}</span>
      : "—" },
];

function StatusPill({ status }: { status: string }) {
  const variant =
    status === "success" ? "win"
      : status === "failed" ? "danger"
      : status === "running" ? "warn"
      : "neutral";
  return <Pill variant={variant}>{status}</Pill>;
}

function pct(used: number | undefined, limit: number | undefined): number {
  if (!used || !limit) return 0;
  return Math.round((used / limit) * 100);
}

export default function AdminPage() {
  return (
    <RequireRole roles={["admin"]}>
      <AdminPanelContent />
    </RequireRole>
  );
}

function AdminPanelContent() {
  const { data: jobs, error: jobsError } = useSWR<JobRow[]>(
    "/admin/jobs",
    apiFetch,
    { refreshInterval: 30_000 },
  );
  const { data: usage } = useSWR<UsageSummary>(
    "/admin/usage",
    apiFetch,
    { refreshInterval: 60_000 },
  );
  const { data: dbStats } = useSWR<DbStats>(
    "/admin/db-stats",
    apiFetch,
    { refreshInterval: 5 * 60 * 1000 },
  );

  const tokensPct = pct(
    usage?.anthropic_tokens_today,
    usage?.anthropic_token_limit,
  );
  const callsPct = pct(
    usage?.api_football_calls_today,
    usage?.api_football_daily_limit,
  );

  return (
    <div className="max-w-6xl space-y-4">
      <h1 className="text-lg font-semibold text-text">Admin Paneli</h1>

      {/* Kullanım */}
      <section>
        <h2 className="text-sm font-semibold text-text mb-2">
          Bugünkü API Kullanımı
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatTile
            label="Anthropic token"
            value={usage?.anthropic_tokens_today?.toLocaleString() ?? "—"}
            delta={
              usage?.anthropic_token_limit
                ? `${tokensPct}% / ${usage.anthropic_token_limit.toLocaleString()}`
                : undefined
            }
          />
          <StatTile
            label="API-Football call"
            value={usage?.api_football_calls_today ?? "—"}
            delta={
              usage?.api_football_daily_limit
                ? `${callsPct}% / ${usage.api_football_daily_limit}`
                : undefined
            }
          />
          <div className="bg-surface border border-border rounded-md p-3">
            <span className="text-[10px] uppercase tracking-wider text-textdim">
              Anthropic Kota
            </span>
            <div className="mt-1">
              {tokensPct >= 95 && <Pill variant="danger">Kota %{tokensPct}</Pill>}
              {tokensPct >= 80 && tokensPct < 95
                && <Pill variant="warn">Kota %{tokensPct}</Pill>}
              {tokensPct < 80 && <Pill variant="win">Normal</Pill>}
            </div>
          </div>
          <div className="bg-surface border border-border rounded-md p-3">
            <span className="text-[10px] uppercase tracking-wider text-textdim">
              API-Football Kota
            </span>
            <div className="mt-1">
              {callsPct >= 95 && <Pill variant="danger">Kota %{callsPct}</Pill>}
              {callsPct >= 80 && callsPct < 95
                && <Pill variant="warn">Kota %{callsPct}</Pill>}
              {callsPct < 80 && <Pill variant="win">Normal</Pill>}
            </div>
          </div>
        </div>
      </section>

      {/* Jobs */}
      <section>
        <h2 className="text-sm font-semibold text-text mb-2">
          Son Job Geçmişi
        </h2>
        {jobsError && (
          <p className="text-danger text-[13px]">
            {String(jobsError)}
          </p>
        )}
        {jobs && (
          <DataTable<JobRow>
            columns={JOB_COLUMNS}
            rows={jobs.slice(0, 30)}
            rowKey={(r) => r.id}
            emptyMessage="Hiç job çalışmamış"
          />
        )}
      </section>

      {/* DB stats */}
      <section>
        <h2 className="text-sm font-semibold text-text mb-2">
          DB İstatistikleri
        </h2>
        <Panel>
          {dbStats ? (
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1 text-[12px]">
              {Object.entries(dbStats).map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-border py-1">
                  <dt className="text-textmut">{k}</dt>
                  <dd className="font-mono tabular-nums text-text">
                    {v.toLocaleString()}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-textmut text-[13px]">Yükleniyor...</p>
          )}
        </Panel>
      </section>
    </div>
  );
}
