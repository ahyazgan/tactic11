"use client";

/**
 * Admin Paneli — API kullanımı/kota + job geçmişi + DB istatistikleri.
 * ConsoleShell çatısında, admin rolü gerektirir.
 * Veri: /admin/jobs, /admin/usage, /admin/db-stats.
 */

import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { RequireRole } from "@/lib/auth";
import { DEMO_MODE } from "@/lib/demo-mode";
import { jobLabel } from "@/lib/labels";
import { useSort, SortableTh, sortCompare } from "@/lib/sortable";
import { ConsoleShell } from "../_console/shell";
import { ErrorState } from "@/components/ui";

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
type DbStats = Record<string, number>;

const STATUS_VAR: Record<string, string> = {
  success: "var(--low)",
  failed: "var(--crit)",
  running: "var(--mid)",
};

function pct(used: number | undefined, limit: number | undefined): number {
  if (!used || !limit) return 0;
  return Math.round((used / limit) * 100);
}
function quotaVar(p: number): string {
  return p >= 95 ? "var(--crit)" : p >= 80 ? "var(--mid)" : "var(--low)";
}

// Demo: backend'siz, dolu sistem paneli (job geçmişi / kota / DB sayaçları).
const DEMO_USAGE: UsageSummary = {
  anthropic_tokens_today: 2_840_000, anthropic_token_limit: 5_000_000,
  api_football_calls_today: 312, api_football_daily_limit: 1000,
};
const DEMO_DB: DbStats = {
  "Maçlar": 1284, "Oyuncular": 642, "Fiziksel Testler": 5120,
  "Olaylar (events)": 1_840_322, "Takımlar": 38, "Ligler": 6, "Karar Kayıtları": 894,
};
const DEMO_JOBS: JobRow[] = [
  { id: 1, job_name: "statsbomb_ingest",      status: "success", started_at: "2026-06-08T06:00:12", ended_at: "2026-06-08T06:04:38", attempts: 1, error: null },
  { id: 2, job_name: "xg_model_recompute",    status: "success", started_at: "2026-06-08T06:05:00", ended_at: "2026-06-08T06:07:21", attempts: 1, error: null },
  { id: 3, job_name: "load_risk_recalc",      status: "success", started_at: "2026-06-08T06:10:00", ended_at: "2026-06-08T06:10:54", attempts: 1, error: null },
  { id: 4, job_name: "opponent_report_build", status: "running", started_at: "2026-06-08T14:20:03", ended_at: null,                  attempts: 1, error: null },
  { id: 5, job_name: "api_football_sync",     status: "failed",  started_at: "2026-06-08T05:30:00", ended_at: "2026-06-08T05:30:42", attempts: 3, error: "429 rate limit — retry zamanlandı" },
  { id: 6, job_name: "decision_engine_warm",  status: "success", started_at: "2026-06-08T06:12:00", ended_at: "2026-06-08T06:12:19", attempts: 1, error: null },
  { id: 7, job_name: "physical_test_etl",     status: "success", started_at: "2026-06-08T03:00:00", ended_at: "2026-06-08T03:02:47", attempts: 1, error: null },
  { id: 8, job_name: "calibration_nightly",   status: "success", started_at: "2026-06-08T02:00:00", ended_at: "2026-06-08T02:18:05", attempts: 1, error: null },
  { id: 9, job_name: "h2h_aggregate",         status: "success", started_at: "2026-06-07T23:40:00", ended_at: "2026-06-07T23:41:12", attempts: 1, error: null },
  { id: 10, job_name: "notification_dispatch", status: "success", started_at: "2026-06-08T07:00:00", ended_at: "2026-06-08T07:00:08", attempts: 1, error: null },
];

export default function AdminPage() {
  // Demo modunda rol kapısını baypas et (login yok) — paneli direkt göster.
  if (DEMO_MODE) return <AdminConsoleContent />;
  return (
    <RequireRole roles={["admin"]}>
      <AdminConsoleContent />
    </RequireRole>
  );
}

function AdminConsoleContent() {
  const { data: jobsData, error: jobsErrorRaw } = useSWR<JobRow[]>(DEMO_MODE ? null : "/admin/jobs", apiFetch, { refreshInterval: 30_000, shouldRetryOnError: false });
  const { data: usageData } = useSWR<UsageSummary>(DEMO_MODE ? null : "/admin/usage", apiFetch, { refreshInterval: 60_000, shouldRetryOnError: false });
  const { data: dbStatsData } = useSWR<DbStats>(DEMO_MODE ? null : "/admin/db-stats", apiFetch, { refreshInterval: 300_000, shouldRetryOnError: false });

  const jobs = DEMO_MODE ? DEMO_JOBS : jobsData;
  const usage = DEMO_MODE ? DEMO_USAGE : usageData;
  const dbStats = DEMO_MODE ? DEMO_DB : dbStatsData;
  const jobsError = DEMO_MODE ? undefined : jobsErrorRaw;

  const tokensPct = pct(usage?.anthropic_tokens_today, usage?.anthropic_token_limit);
  const callsPct = pct(usage?.api_football_calls_today, usage?.api_football_daily_limit);
  const rows = jobs ?? [];

  const jobSort = useSort<"started_at" | "job_name" | "status" | "attempts">("started_at");
  const sortedRows = [...rows].sort((a, b) =>
    sortCompare(a[jobSort.key], b[jobSort.key], jobSort.dir),
  );
  const failed = rows.filter((r) => r.status === "failed").length;

  const right = (
    <div className="rc">
      <h3>DB İstatistikleri</h3>
      {!dbStats && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yükleniyor…</div>}
      {dbStats && Object.entries(dbStats).map(([k, v]) => (
        <div className="stat" key={k}>
          <span style={{ fontSize: 11.5, color: "var(--muted)" }}>{k}</span>
          <span className="sv">{v.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );

  return (
    <ConsoleShell
      active="/admin"
      title="Admin Paneli"
      sub="Sistem & kullanım"
      desc="API kullanımı/kota, arka plan job geçmişi ve veritabanı istatistikleri."
      navBadge={failed}
      right={right}
    >
      <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        <div className="kpi"><div className="kl">Anthropic Token</div><div className="kn" style={{ fontSize: 20 }}>{usage?.anthropic_tokens_today?.toLocaleString() ?? "—"}</div><div className="kd">{usage?.anthropic_token_limit ? `%${tokensPct} / ${usage.anthropic_token_limit.toLocaleString()}` : "bugün"}</div></div>
        <div className="kpi"><div className="kl">Anthropic Kota</div><div className="kn" style={{ color: quotaVar(tokensPct) }}>%{tokensPct}</div><div className="kd">{tokensPct >= 95 ? "kritik" : tokensPct >= 80 ? "uyarı" : "normal"}</div></div>
        <div className="kpi"><div className="kl">API-Football Call</div><div className="kn" style={{ fontSize: 20 }}>{usage?.api_football_calls_today ?? "—"}</div><div className="kd">{usage?.api_football_daily_limit ? `%${callsPct} / ${usage.api_football_daily_limit}` : "bugün"}</div></div>
        <div className="kpi"><div className="kl">API-Football Kota</div><div className="kn" style={{ color: quotaVar(callsPct) }}>%{callsPct}</div><div className="kd">{callsPct >= 95 ? "kritik" : callsPct >= 80 ? "uyarı" : "normal"}</div></div>
      </div>

      <div className="st"><h2>Son Job Geçmişi</h2><span className="ep">GET /admin/jobs</span></div>
      {jobsError && <ErrorState title="Job geçmişi alınamadı ya da yetki yok." />}
      <div className="tbl">
        <table>
          <thead><tr>
            <SortableTh active={jobSort.key === "started_at"} dir={jobSort.dir} label="Başladı" onClick={() => jobSort.onSort("started_at")} />
            <SortableTh active={jobSort.key === "job_name"} dir={jobSort.dir} label="Görev" onClick={() => jobSort.onSort("job_name")} />
            <SortableTh active={jobSort.key === "status"} dir={jobSort.dir} label="Durum" align="c" onClick={() => jobSort.onSort("status")} />
            <SortableTh active={jobSort.key === "attempts"} dir={jobSort.dir} label="Deneme" align="c" onClick={() => jobSort.onSort("attempts")} />
            <th>Hata</th>
          </tr></thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>Hiç görev çalışmamış.</td></tr>
            )}
            {sortedRows.slice(0, 30).map((r) => {
              const v = STATUS_VAR[r.status] ?? "var(--muted)";
              return (
                <tr key={r.id}>
                  <td style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11, whiteSpace: "nowrap" }}>{new Date(r.started_at).toLocaleString("tr-TR")}</td>
                  <td><span className="nm" title={r.job_name}>{jobLabel(r.job_name)}</span></td>
                  <td className="c"><span className="risk" style={{ color: v }}><span className="rd" style={{ background: v, boxShadow: `0 0 7px ${v}` }} />{r.status}</span></td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{r.attempts}</td>
                  <td style={{ color: r.error ? "var(--crit)" : "var(--dim)", fontSize: 11.5 }}>{r.error ? r.error.slice(0, 60) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
