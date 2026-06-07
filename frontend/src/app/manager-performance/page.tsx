"use client";

/**
 * TD Performansı — beklenen puan (xPts) vs gerçek puan + maç bazlı olasılıklar.
 *
 * Backend: GET /admin/manager-performance?team_external_id={id}&days={n}
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel, EndpointTag, ProbBar } from "@/components/ui";

interface PerMatch {
  match_id: number;
  is_home: boolean;
  xpts: number;
  actual_pts: number;
  delta: number;
  p_win: number;
  p_draw: number;
  p_loss: number;
}
interface MgrResp {
  team_id: number;
  days: number;
  matches_considered: number;
  xpts: number;
  actual_points: number;
  overperformance: number;
  per_match: PerMatch[];
}

const inputCls = "bg-surface2 border border-border text-text text-[13px] px-2 py-1.5 rounded";
const DAYS = [30, 90, 180];

function signed(v: number, d = 2): string {
  return (v >= 0 ? "+" : "") + v.toFixed(d);
}
function signColor(v: number): string {
  return v > 0.05 ? "text-ok" : v < -0.05 ? "text-danger" : "text-textmut";
}

export default function ManagerPerfPage() {
  const [team, setTeam] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [days, setDays] = React.useState(90);

  const { data, isLoading, error } = useSWR<MgrResp>(
    team ? `/admin/manager-performance?team_external_id=${team}&days=${days}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const rows = data?.per_match ?? [];

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">TD Performansı</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Beklenen puan (xPts) vs gerçek puan. Pozitif fark = modelin üstünde
            sonuç (iyi yönetim/şans), negatif = altında.
          </p>
        </div>
        <EndpointTag method="GET" path="/admin/manager-performance" />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setTeam(search.trim());
          }}
          className="flex items-center gap-2"
        >
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Takım ID" inputMode="numeric" className={`${inputCls} h-8 w-28`} />
          <button type="submit" className="text-[11px] uppercase px-2 py-1.5 rounded border border-borderlt text-textmut hover:text-text">
            Getir
          </button>
        </form>
        <div className="flex items-center gap-1 ml-2">
          {DAYS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={`text-[11px] px-2 py-1.5 rounded border ${
                days === d ? "border-accent text-accent" : "border-borderlt text-textmut hover:text-text"
              }`}
            >
              {d}g
            </button>
          ))}
        </div>
      </div>

      {!team && <p className="text-[12px] text-textmut">Bir takım ID gir.</p>}
      {team && isLoading && <p className="text-[12px] text-textmut">Hesaplanıyor…</p>}
      {error && <p className="text-[12px] text-textmut">Veri üretilemedi ya da yetki yok.</p>}

      {data && data.matches_considered > 0 && (
        <>
          <Panel title="Özet" actions={<span className="font-mono text-[11px] text-textmut">{data.matches_considered} maç · {data.days}g</span>}>
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-surface2 border border-border rounded-md px-3 py-2">
                <div className="text-[10px] uppercase text-textmut">xPts (beklenen)</div>
                <div className="text-xl font-bold font-mono text-text">{data.xpts.toFixed(1)}</div>
              </div>
              <div className="bg-surface2 border border-border rounded-md px-3 py-2">
                <div className="text-[10px] uppercase text-textmut">Gerçek puan</div>
                <div className="text-xl font-bold font-mono text-text">{data.actual_points}</div>
              </div>
              <div className="bg-surface2 border border-border rounded-md px-3 py-2">
                <div className="text-[10px] uppercase text-textmut">Fark</div>
                <div className={`text-xl font-bold font-mono ${signColor(data.overperformance)}`}>
                  {signed(data.overperformance, 1)}
                </div>
              </div>
            </div>
          </Panel>

          <Panel title="Maç Bazlı">
            <div className="space-y-2">
              {rows.map((m) => (
                <div key={m.match_id} className="flex items-center gap-3 text-[12px]">
                  <span className="font-mono text-textmut w-20 shrink-0">
                    #{m.match_id}
                  </span>
                  <span className="text-[10px] uppercase text-textdim w-8 shrink-0">
                    {m.is_home ? "Ev" : "Dep"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <ProbBar home={m.p_win} draw={m.p_draw} away={m.p_loss} />
                  </div>
                  <span className="font-mono text-textmut w-24 text-right shrink-0">
                    xP {m.xpts.toFixed(1)} · {m.actual_pts}p
                  </span>
                  <span className={`font-mono w-12 text-right shrink-0 ${signColor(m.delta)}`}>
                    {signed(m.delta, 1)}
                  </span>
                </div>
              ))}
            </div>
            <p className="text-[10px] text-textdim mt-2">
              Çubuk: galibiyet / beraberlik / mağlubiyet olasılığı. xP = beklenen
              puan, son sütun = gerçek − beklenen.
            </p>
          </Panel>
        </>
      )}
    </div>
  );
}
