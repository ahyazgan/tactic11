"use client";

/**
 * Genel Bakış (Ana Konsol) — çok kaynaklı FM konsolu. Günün öncelikleri +
 * kadro sağlığı + sözleşmeler tek ekranda. Hepsi gerçek veri.
 *
 * Backend:
 *   GET /admin/daily-briefing?team_id=&role=   — todo + uyarılar
 *   GET /physical-tests/players                 — kadro yük riski
 *   GET /players/contract-alerts?horizon_days=  — sözleşme uyarıları
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel, EndpointTag, RiskPill } from "@/components/ui";

interface AlertItem {
  player_external_id?: number;
  message?: string;
}
interface Briefing {
  todo: string[];
  alerts?: { critical_count: number; warning_count: number; top: AlertItem[] };
}
interface PlayerRow {
  player_id: string;
  player_name: string;
  risk_label: string;
  risk_score: number;
}
interface ContractAlert {
  player_external_id: number;
  days_remaining: number;
  level: string;
  message: string;
}
interface ContractsResp {
  critical_count: number;
  warning_count: number;
  alerts: ContractAlert[];
}

const ROLES = ["coach", "admin", "analyst"] as const;
const ROLE_LABEL: Record<string, string> = { coach: "Teknik", admin: "Yönetim", analyst: "Analist" };
const inputCls = "bg-surface2 border border-border text-text text-[13px] px-2 py-1.5 rounded";

export default function OverviewPage() {
  const [team, setTeam] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [role, setRole] = React.useState<string>("coach");

  const brief = useSWR<Briefing>(
    team ? `/admin/daily-briefing?team_id=${team}&role=${role}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const squad = useSWR<PlayerRow[]>("/physical-tests/players", apiFetch, { shouldRetryOnError: false });
  const contracts = useSWR<ContractsResp>("/players/contract-alerts?horizon_days=365", apiFetch, {
    shouldRetryOnError: false,
  });

  const players = squad.data ?? [];
  const critical = players.filter((p) => p.risk_label === "Kritik" || p.risk_label === "Yüksek");
  const todo = brief.data?.todo ?? [];

  return (
    <div className="max-w-6xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Genel Bakış</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Günün öncelikleri, kadro sağlığı ve sözleşmeler — tek konsolda.
          </p>
        </div>
        <EndpointTag method="GET" path="/admin/daily-briefing" />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setTeam(search.trim());
          }}
          className="flex items-center gap-2"
        >
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Takım ID (brief için)" inputMode="numeric" className={`${inputCls} h-8 w-40`} />
          <button type="submit" className="text-[11px] uppercase px-2 py-1.5 rounded border border-borderlt text-textmut hover:text-text">Getir</button>
        </form>
        <div className="flex items-center gap-1 ml-2">
          {ROLES.map((r) => (
            <button key={r} type="button" onClick={() => setRole(r)} className={`text-[11px] px-2 py-1.5 rounded border ${role === r ? "border-accent text-accent" : "border-borderlt text-textmut hover:text-text"}`}>
              {ROLE_LABEL[r]}
            </button>
          ))}
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        {/* Bugün */}
        <Panel title="Bugün" className="lg:col-span-1">
          {!team && <p className="text-[12px] text-textmut">Brief için takım ID gir.</p>}
          {team && brief.isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
          {team && brief.error && <p className="text-[12px] text-textmut">Brief üretilemedi.</p>}
          {todo.length > 0 ? (
            <ul className="space-y-2">
              {todo.map((t, i) => (
                <li key={i} className="flex items-start gap-2 text-[13px] text-text">
                  <span className="mt-1 w-1.5 h-1.5 rounded-full bg-accent shrink-0" />
                  {t}
                </li>
              ))}
            </ul>
          ) : (
            team && !brief.isLoading && !brief.error && <p className="text-[12px] text-ok">Acil bir şey yok.</p>
          )}
          {brief.data?.alerts && (
            <div className="mt-3 flex gap-3 pt-3 border-t border-border/50">
              <span className="text-[12px]"><b className="font-mono text-danger">{brief.data.alerts.critical_count}</b> <span className="text-textmut">kritik</span></span>
              <span className="text-[12px]"><b className="font-mono text-high">{brief.data.alerts.warning_count}</b> <span className="text-textmut">uyarı</span></span>
            </div>
          )}
        </Panel>

        {/* Kadro sağlığı */}
        <Panel
          title="Kadro Sağlığı"
          actions={<Link href="/squad" className="text-[11px] text-accent">tümü →</Link>}
        >
          {squad.isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
          {squad.data && critical.length === 0 && <p className="text-[12px] text-ok">Kritik/yüksek riskli oyuncu yok.</p>}
          {critical.length > 0 && (
            <ul className="space-y-1.5">
              {critical.slice(0, 6).map((p) => (
                <li key={p.player_id} className="flex items-center justify-between gap-2">
                  <Link href={`/players/${p.player_id}`} className="text-[13px] text-text truncate hover:text-accent">
                    {p.player_name}
                  </Link>
                  <RiskPill label={p.risk_label} score={Math.round(p.risk_score * 100)} />
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* Sözleşmeler */}
        <Panel
          title="Sözleşmeler"
          actions={<Link href="/contracts" className="text-[11px] text-accent">tümü →</Link>}
        >
          {contracts.isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
          {contracts.data && (
            <>
              <div className="flex gap-3 mb-2">
                <span className="text-[12px]"><b className="font-mono text-danger">{contracts.data.critical_count}</b> <span className="text-textmut">kritik</span></span>
                <span className="text-[12px]"><b className="font-mono text-high">{contracts.data.warning_count}</b> <span className="text-textmut">uyarı</span></span>
              </div>
              {contracts.data.alerts.length === 0 ? (
                <p className="text-[12px] text-ok">Yaklaşan sözleşme yok.</p>
              ) : (
                <ul className="space-y-1.5">
                  {contracts.data.alerts.slice(0, 6).map((a) => (
                    <li key={a.player_external_id} className="flex items-center justify-between gap-2 text-[12px]">
                      <Link href={`/players/${a.player_external_id}`} className="font-mono text-accent">#{a.player_external_id}</Link>
                      <span className="font-mono text-textmut">{a.days_remaining}g</span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}
