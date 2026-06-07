"use client";

/**
 * Sözleşmeler — biten/geçmiş sözleşme uyarı panosu (FM Contracts).
 *
 * Backend: GET /players/contract-alerts?horizon_days=365[&team_external_id=]
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel } from "@/components/ui";

interface Alert {
  player_external_id: number;
  contract_end: string;
  days_remaining: number;
  level: string;
  annual_salary_eur: number | null;
  message: string;
}
interface AlertsResp {
  total_contracts: number;
  in_horizon: number;
  critical_count: number;
  warning_count: number;
  notice_count: number;
  expired_count: number;
  alerts: Alert[];
}

const LEVEL_STYLE: Record<string, string> = {
  critical: "text-danger",
  expired: "text-danger",
  warning: "text-high",
  notice: "text-warn",
};
const LEVEL_LABEL: Record<string, string> = {
  critical: "Kritik",
  expired: "Bitti",
  warning: "Uyarı",
  notice: "Bilgi",
};

function euro(v: number | null): string {
  if (v === null) return "—";
  return "€" + v.toLocaleString("tr-TR");
}

function Kpi({ label, value, cls }: { label: string; value: number; cls?: string }) {
  return (
    <div className="bg-surface2 border border-border rounded-md px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-textmut">{label}</div>
      <div className={`text-xl font-bold font-mono ${cls ?? "text-text"}`}>{value}</div>
    </div>
  );
}

const HORIZONS = [180, 365, 730];

export default function ContractsPage() {
  const [horizon, setHorizon] = React.useState(365);
  const { data, isLoading, error } = useSWR<AlertsResp>(
    `/players/contract-alerts?horizon_days=${horizon}`,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const alerts = data?.alerts ?? [];

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Sözleşmeler</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Belirlenen ufuk içinde biten veya süresi geçmiş sözleşmeler.
          </p>
        </div>
        <span className="font-mono text-[10px] text-textdim bg-surface2 border border-border rounded px-2 py-0.5">
          GET /players/contract-alerts
        </span>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-[11px] text-textmut uppercase">Ufuk:</span>
        {HORIZONS.map((h) => (
          <button
            key={h}
            type="button"
            onClick={() => setHorizon(h)}
            className={`text-[11px] px-2 py-1 rounded border ${
              horizon === h
                ? "border-accent text-accent"
                : "border-borderlt text-textmut hover:text-text"
            }`}
          >
            {h} gün
          </button>
        ))}
      </div>

      {data && (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          <Kpi label="Toplam" value={data.total_contracts} />
          <Kpi label="Ufukta" value={data.in_horizon} />
          <Kpi label="Kritik" value={data.critical_count} cls="text-danger" />
          <Kpi label="Uyarı" value={data.warning_count} cls="text-high" />
          <Kpi label="Bilgi" value={data.notice_count} cls="text-warn" />
          <Kpi label="Bitti" value={data.expired_count} cls="text-danger" />
        </div>
      )}

      <Panel title="Uyarılar">
        {isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
        {error && <p className="text-[12px] text-textmut">Sözleşme verisi yok ya da yetki yok.</p>}
        {data && alerts.length === 0 && (
          <p className="text-[12px] text-ok">Bu ufukta biten sözleşme yok.</p>
        )}
        {alerts.length > 0 && (
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-textmut text-left border-b border-border uppercase text-[10.5px]">
                <th className="py-1 pr-2">Oyuncu</th>
                <th className="py-1 pr-2">Bitiş</th>
                <th className="py-1 pr-2 text-right">Kalan</th>
                <th className="py-1 pr-2 text-right">Yıllık ücret</th>
                <th className="py-1 pr-2">Durum</th>
                <th className="py-1">Not</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.player_external_id} className="border-b border-border/50">
                  <td className="py-1 pr-2">
                    <Link href={`/players/${a.player_external_id}`} className="font-mono text-accent">
                      #{a.player_external_id}
                    </Link>
                  </td>
                  <td className="py-1 pr-2 font-mono text-textmut">{a.contract_end}</td>
                  <td className={`py-1 pr-2 text-right font-mono ${LEVEL_STYLE[a.level] ?? "text-textmut"}`}>
                    {a.days_remaining}g
                  </td>
                  <td className="py-1 pr-2 text-right font-mono text-textmut">
                    {euro(a.annual_salary_eur)}
                  </td>
                  <td className={`py-1 pr-2 font-semibold ${LEVEL_STYLE[a.level] ?? "text-textmut"}`}>
                    {LEVEL_LABEL[a.level] ?? a.level}
                  </td>
                  <td className="py-1 text-textmut">{a.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
