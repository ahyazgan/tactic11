"use client";

/**
 * Sözleşmeler — biten/geçmiş sözleşme uyarı panosu. ConsoleShell çatısında.
 * Backend: GET /players/contract-alerts?horizon_days=365.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { useSort, SortableTh, sortCompare } from "@/lib/sortable";
import { DemoLiveBanner } from "@/lib/demo-live-banner";
import { ConsoleShell } from "../_console/shell";

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

const LEVEL_VAR: Record<string, string> = {
  critical: "var(--crit)",
  expired: "var(--crit)",
  warning: "var(--high)",
  notice: "var(--mid)",
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

const HORIZONS = [180, 365, 730];

export default function ContractsConsolePage() {
  const [horizon, setHorizon] = React.useState(365);
  const { data, isLoading, error } = useSWR<AlertsResp>(
    `/players/contract-alerts?horizon_days=${horizon}`,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const alerts = data?.alerts ?? [];

  const sort = useSort<"contract_end" | "days_remaining" | "annual_salary_eur" | "level">("days_remaining", "asc");
  const sortedAlerts = [...alerts].sort((a, b) => sortCompare(a[sort.key], b[sort.key], sort.dir));

  const breakdown = [
    { label: "Kritik", n: data?.critical_count ?? 0, v: "var(--crit)" },
    { label: "Uyarı", n: data?.warning_count ?? 0, v: "var(--high)" },
    { label: "Bilgi", n: data?.notice_count ?? 0, v: "var(--mid)" },
    { label: "Bitti", n: data?.expired_count ?? 0, v: "var(--crit)" },
  ];

  const right = (
    <div className="rc">
      <h3>Seviye Dağılımı <span className="tiny">{data?.in_horizon ?? 0} ufukta</span></h3>
      {breakdown.map((b) => (
        <div className="stat" key={b.label}>
          <span style={{ color: b.v, fontWeight: 700 }}>{b.label}</span>
          <span className="sv">{b.n}</span>
        </div>
      ))}
      <div className="stat"><span>Toplam sözleşme</span><span className="sv">{data?.total_contracts ?? 0}</span></div>
    </div>
  );

  return (
    <ConsoleShell
      active="/contracts"
      title="Sözleşmeler"
      sub="Bitiş uyarıları"
      desc="Belirlenen ufuk içinde biten veya süresi geçmiş sözleşmeler. Erken aksiyon için öncelik panosu."
      navBadge={data?.critical_count}
      right={right}
    >
      <DemoLiveBanner />
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Ufuk</h2>
        <div className="seg">
          {HORIZONS.map((h) => (
            <button key={h} className={horizon === h ? "on" : ""} onClick={() => setHorizon(h)}>{h} gün</button>
          ))}
        </div>
      </div>

      <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
        <div className="kpi"><div className="kl">Toplam</div><div className="kn">{data?.total_contracts ?? 0}</div><div className="kd">sözleşme</div></div>
        <div className="kpi"><div className="kl">Ufukta</div><div className="kn">{data?.in_horizon ?? 0}</div><div className="kd">{horizon} gün içinde</div></div>
        <div className="kpi"><div className="kl">Kritik</div><div className="kn" style={{ color: "var(--crit)" }}>{data?.critical_count ?? 0}</div><div className="kd">acil</div></div>
        <div className="kpi"><div className="kl">Uyarı</div><div className="kn" style={{ color: "var(--high)" }}>{data?.warning_count ?? 0}</div><div className="kd">yaklaşan</div></div>
        <div className="kpi"><div className="kl">Bitti</div><div className="kn" style={{ color: "var(--crit)" }}>{data?.expired_count ?? 0}</div><div className="kd">süresi geçmiş</div></div>
      </div>

      <div className="st"><h2>Uyarılar</h2><span className="ep">GET /players/contract-alerts</span></div>
      {isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {error && <div className="pgdesc">Sözleşme verisi yok ya da yetki yok.</div>}
      <div className="tbl">
        <table>
          <thead><tr>
            <th>Oyuncu</th>
            <SortableTh active={sort.key === "contract_end"} dir={sort.dir} label="Bitiş" align="c" onClick={() => sort.onSort("contract_end")} />
            <SortableTh active={sort.key === "days_remaining"} dir={sort.dir} label="Kalan" align="r" onClick={() => sort.onSort("days_remaining")} />
            <SortableTh active={sort.key === "annual_salary_eur"} dir={sort.dir} label="Yıllık Ücret" align="r" onClick={() => sort.onSort("annual_salary_eur")} />
            <SortableTh active={sort.key === "level"} dir={sort.dir} label="Durum" align="c" onClick={() => sort.onSort("level")} />
            <th>Not</th>
          </tr></thead>
          <tbody>
            {sortedAlerts.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                {data ? "Bu ufukta biten sözleşme yok." : "Veri yok (backend bağlı değilse boş gelir)."}
              </td></tr>
            )}
            {sortedAlerts.map((a) => {
              const v = LEVEL_VAR[a.level] ?? "var(--muted)";
              return (
                <tr key={a.player_external_id}>
                  <td><span className="nm" style={{ fontFamily: "JetBrains Mono" }}>#{a.player_external_id}</span></td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11 }}>{a.contract_end}</td>
                  <td className="r" style={{ color: v }}>{a.days_remaining}g</td>
                  <td className="r" style={{ color: "var(--muted)" }}>{euro(a.annual_salary_eur)}</td>
                  <td className="c"><span className="risk" style={{ color: v }}><span className="rd" style={{ background: v, boxShadow: `0 0 7px ${v}` }} />{LEVEL_LABEL[a.level] ?? a.level}</span></td>
                  <td style={{ color: "var(--muted)", fontSize: 11.5 }}>{a.message}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
