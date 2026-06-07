"use client";

/**
 * Rakip Raporu — eşleşme grid: bizim güç × rakip zaaf (kanal bazlı).
 *
 * Backend: GET /admin/teams/{team_id}/matchup-grid?opponent_id={id}&last_n=5
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel } from "@/components/ui";

interface ChannelM {
  channel: string;
  our_attacks: number;
  opp_def_actions: number;
  our_strength: number;
  opp_weakness: number;
  matchup_score: number;
  verdict: string;
}
interface GridResp {
  value?: {
    matches_analyzed: number;
    by_channel: ChannelM[];
    best_channel: string;
    worst_channel: string;
    recommendation: string;
  };
  note?: string;
}

const CHANNEL_LABEL: Record<string, string> = {
  left: "Sol kanat",
  center: "Merkez",
  right: "Sağ kanat",
  left_halfspace: "Sol yarı alan",
  right_halfspace: "Sağ yarı alan",
};
const VERDICT_STYLE: Record<string, string> = {
  exploit: "text-ok border-emerald-700",
  neutral: "text-textmut border-borderlt",
  avoid: "text-danger border-red-800",
};
const VERDICT_LABEL: Record<string, string> = {
  exploit: "Sömür",
  neutral: "Nötr",
  avoid: "Kaçın",
};

function pct(v: number): string {
  return (v * 100).toFixed(0) + "%";
}

const inputCls = "bg-surface2 border border-border text-text text-[13px] px-2 py-1.5 rounded";

export default function OpponentReportPage() {
  const [team, setTeam] = React.useState("");
  const [opp, setOpp] = React.useState("");
  const [q, setQ] = React.useState<{ t: string; o: string } | null>(null);

  const { data, isLoading, error } = useSWR<GridResp>(
    q ? `/admin/teams/${q.t}/matchup-grid?opponent_id=${q.o}&last_n=5` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const v = data?.value;

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Rakip Raporu — Eşleşme Grid</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Kanal bazlı eşleşme: bizim güç (final üçte-bir girişleri) × rakip zaaf
            (savunma aksiyonu boşluğu). Sömürülecek koridoru bulur.
          </p>
        </div>
        <span className="font-mono text-[10px] text-textdim bg-surface2 border border-border rounded px-2 py-0.5">
          GET /admin/teams/&#123;id&#125;/matchup-grid
        </span>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (team.trim() && opp.trim()) setQ({ t: team.trim(), o: opp.trim() });
        }}
        className="flex flex-wrap items-center gap-2"
      >
        <input value={team} onChange={(e) => setTeam(e.target.value)} placeholder="Bizim takım ID" inputMode="numeric" className={`${inputCls} h-8 w-36`} />
        <span className="text-textmut">vs</span>
        <input value={opp} onChange={(e) => setOpp(e.target.value)} placeholder="Rakip ID" inputMode="numeric" className={`${inputCls} h-8 w-32`} />
        <button type="submit" className="text-[11px] uppercase px-3 py-1.5 rounded border border-borderlt text-textmut hover:text-text">
          Analiz et
        </button>
      </form>

      {!q && <p className="text-[12px] text-textmut">İki takım ID gir.</p>}
      {q && isLoading && <p className="text-[12px] text-textmut">Hesaplanıyor…</p>}
      {error && <p className="text-[12px] text-textmut">Analiz üretilemedi ya da yetki yok.</p>}
      {data?.note && <p className="text-[12px] text-textmut">{data.note}</p>}

      {v && (
        <>
          <Panel title="Öneri">
            <p className="text-[14px] text-text">{v.recommendation}</p>
            <div className="mt-2 flex gap-4 text-[12px]">
              <span className="text-ok">
                En iyi: <b>{CHANNEL_LABEL[v.best_channel] ?? v.best_channel}</b>
              </span>
              <span className="text-danger">
                En zayıf: <b>{CHANNEL_LABEL[v.worst_channel] ?? v.worst_channel}</b>
              </span>
              <span className="text-textmut font-mono">{v.matches_analyzed} maç</span>
            </div>
          </Panel>

          <Panel title="Kanal Analizi">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-textmut text-left border-b border-border uppercase text-[10.5px]">
                  <th className="py-1 pr-2">Kanal</th>
                  <th className="py-1 pr-2 text-right">Bizim güç</th>
                  <th className="py-1 pr-2 text-right">Rakip zaaf</th>
                  <th className="py-1 pr-2 text-right">Skor</th>
                  <th className="py-1">Karar</th>
                </tr>
              </thead>
              <tbody>
                {v.by_channel.map((c) => (
                  <tr key={c.channel} className="border-b border-border/50">
                    <td className="py-1 pr-2 text-text">{CHANNEL_LABEL[c.channel] ?? c.channel}</td>
                    <td className="py-1 pr-2 text-right font-mono text-textmut">{pct(c.our_strength)}</td>
                    <td className="py-1 pr-2 text-right font-mono text-textmut">{pct(c.opp_weakness)}</td>
                    <td className="py-1 pr-2 text-right font-mono font-semibold text-text">
                      {(c.matchup_score * 100).toFixed(0)}
                    </td>
                    <td className="py-1">
                      <span className={`text-[10px] uppercase px-2 py-0.5 rounded border ${VERDICT_STYLE[c.verdict] ?? "text-textmut border-borderlt"}`}>
                        {VERDICT_LABEL[c.verdict] ?? c.verdict}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </>
      )}
    </div>
  );
}
