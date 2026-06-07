"use client";

/**
 * xG Performans — sezon beklenen gol (xG) farkı + overperformance.
 *
 * Backend: GET /admin/teams/{team_id}/xg-difference?days={7..365}
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel, EndpointTag } from "@/components/ui";

interface XgResp {
  team_id: number;
  days: number;
  matches_analyzed: number;
  xg_for: number;
  xg_against: number;
  xg_difference: number;
  goals_for: number;
  goals_against: number;
  actual_goal_difference: number;
  overperformance: number;
  note?: string;
}

const inputCls = "bg-surface2 border border-border text-text text-[13px] px-2 py-1.5 rounded";
const DAYS = [30, 90, 180];

function signed(v: number, d = 2): string {
  return (v >= 0 ? "+" : "") + v.toFixed(d);
}
function signColor(v: number): string {
  return v > 0.05 ? "text-ok" : v < -0.05 ? "text-danger" : "text-textmut";
}

function Tile({ label, value, cls, hint }: { label: string; value: string; cls?: string; hint?: string }) {
  return (
    <div className="bg-surface2 border border-border rounded-md px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-textmut">{label}</div>
      <div className={`text-xl font-bold font-mono ${cls ?? "text-text"}`}>{value}</div>
      {hint && <div className="text-[10px] text-textdim mt-0.5">{hint}</div>}
    </div>
  );
}

export default function XgPage() {
  const [team, setTeam] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [days, setDays] = React.useState(90);

  const { data, isLoading, error } = useSWR<XgResp>(
    team ? `/admin/teams/${team}/xg-difference?days=${days}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  const op = data?.overperformance ?? 0;
  const opHint =
    op > 0.05 ? "Klinik bitiricilik / şans (xG üstü)" : op < -0.05 ? "İsraf / şanssızlık (xG altı)" : "Beklentiyle uyumlu";

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">xG Performans</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Beklenen gol üretimi (xG) vs gerçek — over/underperformance ile gerçek
            verimliliği gösterir.
          </p>
        </div>
        <EndpointTag method="GET" path="/admin/teams/{id}/xg-difference" />
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
      {error && <p className="text-[12px] text-textmut">xG verisi üretilemedi ya da yetki yok.</p>}
      {data?.note && <p className="text-[12px] text-textmut">{data.note}</p>}

      {data && data.matches_analyzed > 0 && (
        <>
          <Panel title="Özet" actions={<span className="font-mono text-[11px] text-textmut">{data.matches_analyzed} maç · {data.days}g</span>}>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <Tile label="xG (lehte)" value={data.xg_for.toFixed(2)} />
              <Tile label="xGA (aleyhte)" value={data.xg_against.toFixed(2)} />
              <Tile label="xG farkı" value={signed(data.xg_difference)} cls={signColor(data.xg_difference)} />
              <Tile label="Gerçek averaj" value={signed(data.actual_goal_difference, 0)} cls={signColor(data.actual_goal_difference)} />
            </div>
          </Panel>

          <Panel title="Overperformance">
            <div className="flex items-baseline gap-3">
              <span className={`text-3xl font-extrabold font-mono ${signColor(op)}`}>{signed(op)}</span>
              <span className="text-[13px] text-textmut">{opHint}</span>
            </div>
            <p className="text-[12px] text-textmut mt-2">
              Gerçek averaj − xG farkı. Pozitif = xG'nin üstünde skor (klinik/şanslı),
              negatif = altında (israf/şanssız). Sürdürülebilirlik için 0'a yakınlık beklenir.
            </p>
            <div className="mt-2 flex gap-4 text-[12px] font-mono text-textmut">
              <span>Attığı: <span className="text-text">{data.goals_for}</span></span>
              <span>Yediği: <span className="text-text">{data.goals_against}</span></span>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
