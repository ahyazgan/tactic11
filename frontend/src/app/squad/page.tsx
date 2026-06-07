"use client";

/**
 * Kadro — yük & uygunluk panosu. Tüm oyuncular risk seviyesine göre.
 *
 * Backend: GET /physical-tests/players → [{player_id, player_name, test_count,
 *          latest_test_date, risk_label, risk_score}]  (riskli üstte)
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel, EndpointTag, RiskPill } from "@/components/ui";

interface PlayerRow {
  player_id: string;
  player_name: string;
  test_count: number;
  latest_test_date: string | null;
  risk_label: string;
  risk_score: number;
}

const RISK_BAR: Record<string, string> = {
  Kritik: "bg-danger",
  Yüksek: "bg-high",
  Orta: "bg-warn",
  Düşük: "bg-ok",
};
const ORDER = ["Kritik", "Yüksek", "Orta", "Düşük", "Veri Yok"];

function Kpi({ label, value, cls }: { label: string; value: number; cls?: string }) {
  return (
    <div className="bg-surface2 border border-border rounded-md px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-textmut">{label}</div>
      <div className={`text-2xl font-bold font-mono ${cls ?? "text-text"}`}>{value}</div>
    </div>
  );
}

export default function SquadPage() {
  const { data, isLoading, error } = useSWR<PlayerRow[]>(
    "/physical-tests/players",
    apiFetch,
    { shouldRetryOnError: false },
  );
  const players = data ?? [];

  const counts = players.reduce<Record<string, number>>((acc, p) => {
    acc[p.risk_label] = (acc[p.risk_label] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="max-w-6xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Kadro — Yük & Uygunluk</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Tüm oyuncular fiziksel yük riskine göre. Kritik olanlar üstte; rotasyon
            ve antrenman yükü kararları için.
          </p>
        </div>
        <EndpointTag method="GET" path="/physical-tests/players" />
      </div>

      {data && (
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
          <Kpi label="Toplam" value={players.length} />
          <Kpi label="Kritik" value={counts["Kritik"] ?? 0} cls="text-danger" />
          <Kpi label="Yüksek" value={counts["Yüksek"] ?? 0} cls="text-high" />
          <Kpi label="Orta" value={counts["Orta"] ?? 0} cls="text-warn" />
          <Kpi label="Düşük" value={counts["Düşük"] ?? 0} cls="text-ok" />
        </div>
      )}

      <Panel title={`Oyuncular (${players.length})`}>
        {isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
        {error && (
          <p className="text-[12px] text-textmut">
            Veri yok ya da yetki yok. (Önce performans testi girilmiş olmalı.)
          </p>
        )}
        {data && players.length === 0 && (
          <p className="text-[12px] text-textmut">Kayıtlı test verisi olan oyuncu yok.</p>
        )}
        {players.length > 0 && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {players.map((p) => (
              <Link
                key={p.player_id}
                href={`/players/${p.player_id}`}
                className="block bg-surface2 border border-border rounded-md p-3 hover:border-borderlt transition-colors"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold text-text truncate">
                      {p.player_name}
                    </div>
                    <div className="text-[10px] font-mono text-textdim">
                      #{p.player_id} · {p.test_count} test
                    </div>
                  </div>
                  <RiskPill label={p.risk_label} />
                </div>
                <div className="mt-2 h-1.5 rounded bg-elevated overflow-hidden">
                  <div
                    className={`h-full rounded ${RISK_BAR[p.risk_label] ?? "bg-textdim"}`}
                    style={{ width: `${Math.max(4, Math.min(100, p.risk_score * 100))}%` }}
                  />
                </div>
                <div className="mt-1 flex items-center justify-between text-[10px] font-mono text-textmut">
                  <span>risk {(p.risk_score * 100).toFixed(0)}/100</span>
                  <span>{p.latest_test_date ?? "—"}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
