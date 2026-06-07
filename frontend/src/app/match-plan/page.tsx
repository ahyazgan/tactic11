"use client";

/**
 * Maç Planı — pre-match planın canlı senaryo takibi.
 *
 * Maç seç → planın hangi senaryosu (önde/eşit/geride) şimdi aktif, eşleşme
 * reçetesi, duran top ipucu, notlar. (Önerilen 11 + tam rakip brifing referans
 * HTML ile genişletilecek.)
 *
 * Backend: GET /matches/{match_id}/plan/vs-live
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel } from "@/components/ui";

interface PlanVsLive {
  summary: string;
  updated_at: string;
  plan_age_seconds: number;
  status: string | null;
  active_scenario: string; // leading | level | trailing | unknown
  matchup_recommendation: string | null;
  set_piece_hint: string | null;
  notes: string[];
}

const SCENARIO: Record<string, { label: string; cls: string }> = {
  leading: { label: "ÖNDE", cls: "text-ok" },
  level: { label: "EŞİT", cls: "text-warn" },
  trailing: { label: "GERİDE", cls: "text-danger" },
  unknown: { label: "BİLİNMİYOR", cls: "text-textmut" },
};

const inputCls =
  "w-full bg-surface2 border border-border text-text text-[13px] px-2 py-1.5 rounded";

export default function MatchPlanPage() {
  const [query, setQuery] = React.useState("");
  const [search, setSearch] = React.useState("");

  const plan = useSWR<PlanVsLive>(
    query ? `/matches/${query}/plan/vs-live` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const d = plan.data;
  const scen = d ? SCENARIO[d.active_scenario] ?? SCENARIO.unknown : null;

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Maç Planı — Canlı Senaryo</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Pre-match planın hangi senaryosu şimdi aktif, eşleşme reçetesi ve duran
            top ipucu. Açık oyun (OP) ağırlıklı taktik takibi.
          </p>
        </div>
        <span className="font-mono text-[10px] text-textdim bg-surface2 border border-border rounded px-2 py-0.5">
          GET /matches/&#123;id&#125;/plan/vs-live
        </span>
      </div>

      <Panel
        title="Maç"
        actions={
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(search.trim());
            }}
            className="flex items-center gap-2"
          >
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Maç ID"
              inputMode="numeric"
              className={`${inputCls} h-7 w-32`}
            />
            <button
              type="submit"
              className="text-[11px] uppercase px-2 py-1 rounded border border-borderlt text-textmut hover:text-text"
            >
              Getir
            </button>
          </form>
        }
      >
        {!query && <p className="text-[12px] text-textmut">Bir maç ID gir.</p>}
        {query && plan.isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
        {query && plan.error && (
          <p className="text-[12px] text-textmut">
            Bu maç için kayıtlı plan yok ya da maç bulunamadı.
          </p>
        )}
        {d && scen && (
          <div className="space-y-3">
            <div className="flex items-baseline gap-3">
              <span className="text-[10px] uppercase tracking-wider text-textdim">
                Aktif senaryo
              </span>
              <span className={`text-2xl font-extrabold ${scen.cls}`}>{scen.label}</span>
              {d.status && (
                <span className="font-mono text-[11px] text-textmut">{d.status}</span>
              )}
            </div>
            <p className="text-[13px] text-text">{d.summary}</p>
          </div>
        )}
      </Panel>

      {d && scen && (
        <div className="grid sm:grid-cols-2 gap-4">
          <Panel title="Eşleşme Reçetesi">
            <p className="text-[13px] text-text">
              {d.matchup_recommendation ?? "—"}
            </p>
          </Panel>
          <Panel title="Duran Top İpucu">
            <p className="text-[13px] text-text">{d.set_piece_hint ?? "—"}</p>
          </Panel>
          <Panel title="Notlar" className="sm:col-span-2">
            {d.notes.length === 0 ? (
              <p className="text-[12px] text-textmut">Not yok.</p>
            ) : (
              <ul className="text-[13px] text-text space-y-1 list-disc pl-4">
                {d.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            )}
            <p className="font-mono text-[10px] text-textdim mt-2">
              plan yaşı: {Math.round(d.plan_age_seconds)}s · güncellendi {d.updated_at}
            </p>
          </Panel>
        </div>
      )}
    </div>
  );
}
