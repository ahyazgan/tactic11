"use client";

/**
 * Admin Paneli — API kullanımı/kota + job geçmişi + DB istatistikleri.
 * ConsoleShell çatısında, admin rolü gerektirir.
 * Veri: /admin/jobs, /admin/usage, /admin/db-stats.
 */

import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { RequireRole } from "@/lib/auth";
import { ConsoleShell } from "../_console/shell";

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

export default function AdminPage() {
  return (
    <RequireRole roles={["admin"]}>
      <AdminConsoleContent />
    </RequireRole>
  );
}

function AdminConsoleContent() {
  const { data: jobs, error: jobsError } = useSWR<JobRow[]>("/admin/jobs", apiFetch, { refreshInterval: 30_000, shouldRetryOnError: false });
  const { data: usage } = useSWR<UsageSummary>("/admin/usage", apiFetch, { refreshInterval: 60_000, shouldRetryOnError: false });
  const { data: dbStats } = useSWR<DbStats>("/admin/db-stats", apiFetch, { refreshInterval: 300_000, shouldRetryOnError: false });

  const tokensPct = pct(usage?.anthropic_tokens_today, usage?.anthropic_token_limit);
  const callsPct = pct(usage?.api_football_calls_today, usage?.api_football_daily_limit);
  const rows = jobs ?? [];
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
      {jobsError && <div className="pgdesc">Job geçmişi alınamadı ya da yetki yok.</div>}
      <div className="tbl">
        <table>
          <thead><tr><th>Başladı</th><th>Job</th><th className="c">Durum</th><th className="c">Deneme</th><th>Hata</th></tr></thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>Hiç job çalışmamış.</td></tr>
            )}
            {rows.slice(0, 30).map((r) => {
              const v = STATUS_VAR[r.status] ?? "var(--muted)";
              return (
                <tr key={r.id}>
                  <td style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11, whiteSpace: "nowrap" }}>{new Date(r.started_at).toLocaleString("tr-TR")}</td>
                  <td><span className="nm" style={{ fontFamily: "JetBrains Mono", fontSize: 11.5 }}>{r.job_name}</span></td>
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
