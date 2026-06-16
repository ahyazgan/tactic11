"use client";

/**
 * Sözleşmeler — biten/geçmiş sözleşme uyarı panosu. ConsoleShell çatısında.
 * Backend: GET /players/contract-alerts?horizon_days=365.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoSquad } from "@/lib/demo-data";
import { useSort, SortableTh, sortCompare } from "@/lib/sortable";
import { DemoLiveBanner } from "@/lib/demo-live-banner";
import { ConsoleShell } from "../_console/shell";
import { LoadingState, ErrorState } from "@/components/ui";

interface Alert {
  player_external_id: number;
  player_name?: string;          // demo örnek verisinde dolu; canlıda #id gösterilir
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

// ── Demo örnek verisi ─────────────────────────────────────────────────────────
// Backend'te sözleşme kaydı yokken sayfa boş kalmasın: kadrodan deterministik
// bitiş tarihleri üret (demo evreni "bugün"ü: 2026-06-08). Yalnız DEMO_MODE'da
// ve canlı veri boşken devreye girer — canlı kayıt varsa daima o gösterilir.
const DEMO_TODAY = new Date("2026-06-08T00:00:00");
// Kadro sırasına göre bitişe kalan ay şablonu (kritik→uzun karışık, gerçekçi).
const MONTH_PATTERN = [1, 13, 25, 3, 19, 37, 8, 28, -1, 16, 49, 5];

function demoAlerts(horizon: number): AlertsResp {
  const all: Alert[] = demoSquad.map((p, i) => {
    const months = MONTH_PATTERN[i % MONTH_PATTERN.length];
    const end = new Date(DEMO_TODAY);
    end.setMonth(end.getMonth() + months);
    end.setDate(30);
    const days = Math.round((end.getTime() - DEMO_TODAY.getTime()) / 86_400_000);
    const level = days < 0 ? "expired" : days <= 90 ? "critical" : days <= 180 ? "warning" : "notice";
    // Maaş: yaş+kondisyondan deterministik (1.0M–3.6M bandı).
    const salary = Math.round((1_000_000 + (32 - Math.min(32, p.age)) * 120_000 + p.condition * 14_000) / 50_000) * 50_000;
    const msg = days < 0
      ? "Sözleşme süresi doldu — yeni sözleşme ya da ayrılık kararı bekliyor."
      : days <= 90
        ? "Bonservissiz ayrılık riski — uzatma görüşmesi öncelikli."
        : days <= 180
          ? "Sezon sonu opsiyonu için görüşme penceresi açık."
          : "Takip listesinde — acil aksiyon gerekmiyor.";
    return {
      player_external_id: Number(String(p.player_id).replace(/\D/g, "")) || i + 1,
      player_name: p.player_name,
      contract_end: end.toISOString().slice(0, 10),
      days_remaining: days,
      level,
      annual_salary_eur: salary,
      message: msg,
    };
  });
  const inHorizon = all.filter((a) => a.days_remaining <= horizon);
  return {
    total_contracts: all.length,
    in_horizon: inHorizon.length,
    critical_count: inHorizon.filter((a) => a.level === "critical").length,
    warning_count: inHorizon.filter((a) => a.level === "warning").length,
    notice_count: inHorizon.filter((a) => a.level === "notice").length,
    expired_count: inHorizon.filter((a) => a.level === "expired").length,
    alerts: inHorizon,
  };
}

export default function ContractsConsolePage() {
  const [horizon, setHorizon] = React.useState(365);
  const { data: liveData, isLoading, error } = useSWR<AlertsResp>(
    `/players/contract-alerts?horizon_days=${horizon}`,
    apiFetch,
    { shouldRetryOnError: false },
  );
  // Demo modunda canlı kayıt yoksa örnek veri (sayfa asla boş kalmaz).
  const useDemo = DEMO_MODE && (!liveData || liveData.total_contracts === 0);
  const data = useDemo ? demoAlerts(horizon) : liveData;
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

      <div className="st"><h2>Uyarılar</h2><span className="ep">{useDemo ? "örnek veri (backend'te kayıt yok)" : "GET /players/contract-alerts"}</span></div>
      {isLoading && !useDemo && <LoadingState />}
      {error && !useDemo && <ErrorState title="Sözleşme verisi yok ya da yetki yok." />}
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
                  <td>{a.player_name
                    ? <span className="nm">{a.player_name}</span>
                    : <span className="nm" style={{ fontFamily: "JetBrains Mono" }}>#{a.player_external_id}</span>}</td>
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
