"use client";

/**
 * Genel Bakış (Ana Konsol) — rol bazlı "bugün ne yapmalıyım" özeti.
 *
 * Backend: GET /admin/daily-briefing?team_id={id}&role={coach|admin|analyst}
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel } from "@/components/ui";

interface AlertItem {
  player_external_id?: number;
  message?: string;
  level?: string;
}
interface Briefing {
  team_id: number;
  role: string;
  alerts?: { critical_count: number; warning_count: number; top: AlertItem[] };
  ops?: { total_jobs: number };
  data?: { matches_with_events: number };
  todo: string[];
}

const ROLES = ["coach", "admin", "analyst"] as const;
const ROLE_LABEL: Record<string, string> = {
  coach: "Teknik",
  admin: "Yönetim",
  analyst: "Analist",
};

const inputCls =
  "bg-surface2 border border-border text-text text-[13px] px-2 py-1.5 rounded";

export default function OverviewPage() {
  const [team, setTeam] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [role, setRole] = React.useState<string>("coach");

  const { data, isLoading, error } = useSWR<Briefing>(
    team ? `/admin/daily-briefing?team_id=${team}&role=${role}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Genel Bakış</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Role göre günün öncelikleri, uyarılar ve yapılacaklar.
          </p>
        </div>
        <span className="font-mono text-[10px] text-textdim bg-surface2 border border-border rounded px-2 py-0.5">
          GET /admin/daily-briefing
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setTeam(search.trim());
          }}
          className="flex items-center gap-2"
        >
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Takım ID"
            inputMode="numeric"
            className={`${inputCls} h-8 w-28`}
          />
          <button
            type="submit"
            className="text-[11px] uppercase px-2 py-1.5 rounded border border-borderlt text-textmut hover:text-text"
          >
            Getir
          </button>
        </form>
        <div className="flex items-center gap-1 ml-2">
          {ROLES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRole(r)}
              className={`text-[11px] px-2 py-1.5 rounded border ${
                role === r
                  ? "border-accent text-accent"
                  : "border-borderlt text-textmut hover:text-text"
              }`}
            >
              {ROLE_LABEL[r]}
            </button>
          ))}
        </div>
      </div>

      {!team && <p className="text-[12px] text-textmut">Bir takım ID gir.</p>}
      {team && isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
      {error && <p className="text-[12px] text-textmut">Brief üretilemedi ya da yetki yok.</p>}

      {data && (
        <div className="grid md:grid-cols-3 gap-4">
          <Panel title="Bugün Yapılacaklar" className="md:col-span-2">
            {data.todo.length === 0 ? (
              <p className="text-[12px] text-ok">Acil bir şey yok.</p>
            ) : (
              <ul className="space-y-2">
                {data.todo.map((t, i) => (
                  <li key={i} className="flex items-start gap-2 text-[13px] text-text">
                    <span className="mt-1 w-1.5 h-1.5 rounded-full bg-accent shrink-0" />
                    {t}
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <div className="space-y-4">
            {data.alerts && (
              <Panel title="Uyarılar">
                <div className="flex gap-3">
                  <div>
                    <div className="text-2xl font-bold font-mono text-danger">
                      {data.alerts.critical_count}
                    </div>
                    <div className="text-[10px] uppercase text-textmut">Kritik</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold font-mono text-high">
                      {data.alerts.warning_count}
                    </div>
                    <div className="text-[10px] uppercase text-textmut">Uyarı</div>
                  </div>
                </div>
                {data.alerts.top.length > 0 && (
                  <ul className="mt-2 text-[11px] text-textmut space-y-1">
                    {data.alerts.top.slice(0, 5).map((a, i) => (
                      <li key={i} className="border-t border-border/40 pt-1">
                        {a.player_external_id && (
                          <Link
                            href={`/players/${a.player_external_id}`}
                            className="font-mono text-accent mr-1"
                          >
                            #{a.player_external_id}
                          </Link>
                        )}
                        {a.message ?? a.level ?? ""}
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            )}
            {(data.ops || data.data) && (
              <Panel title="Sistem">
                {data.ops && (
                  <div className="text-[12px] text-textmut">
                    Toplam job: <span className="font-mono text-text">{data.ops.total_jobs}</span>
                  </div>
                )}
                {data.data && (
                  <div className="text-[12px] text-textmut">
                    Event'li maç:{" "}
                    <span className="font-mono text-text">{data.data.matches_with_events}</span>
                  </div>
                )}
              </Panel>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
