"use client";

/**
 * Scout / Rakip Dosyası — oyuncu benzerliği + izleme listesi.
 *
 * Hedef oyuncu → cosine similarity ile top-N benzer oyuncu (per-90 stat
 * vektörü), + scout izleme listesi (watchlist) ekle/gör.
 *
 * Backend:
 *   GET  /admin/scout/similar/{player_external_id}   — benzer oyuncular
 *   GET  /admin/scout/watchlist                      — izleme listesi
 *   POST /admin/scout/watchlist                      — listeye ekle
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel } from "@/components/ui";

interface SimMatch {
  player_external_id: number;
  similarity: number; // -1..1 cosine
  total_minutes: number;
}
interface SimResp {
  value: {
    target_player_id: number;
    candidates_considered: number;
    candidates_eligible: number;
    top_matches: SimMatch[];
  };
}
interface WatchEntry {
  id: number;
  player_external_id: number;
  notes: string | null;
}
interface WatchResp {
  entries: WatchEntry[];
}

const inputCls =
  "w-full bg-surface2 border border-border text-text text-[13px] px-2 py-1.5 rounded";

function simColor(sim: number): string {
  if (sim >= 0.85) return "text-ok";
  if (sim >= 0.7) return "text-warn";
  return "text-textmut";
}

export default function ScoutPage() {
  const [query, setQuery] = React.useState("");
  const [search, setSearch] = React.useState("");

  const sim = useSWR<SimResp>(
    query ? `/admin/scout/similar/${query}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const watch = useSWR<WatchResp>("/admin/scout/watchlist", apiFetch, {
    shouldRetryOnError: false,
  });

  const matches = sim.data?.value.top_matches ?? [];
  const watched = new Set(
    (watch.data?.entries ?? []).map((e) => e.player_external_id),
  );

  async function addWatch(pid: number) {
    try {
      await apiFetch("/admin/scout/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          player_external_id: pid,
          notes: `Scout: ${query} ile benzer`,
        }),
      });
      watch.mutate();
    } catch {
      /* sessizce yut — UI watchlist'i yeniden çeker */
    }
  }

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Scout — Oyuncu Benzerliği</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Per-90 stat vektörü + cosine similarity ile hedef oyuncuya en yakın
            profiller. Rol/profil eşleştirme için aday havuzu mevcut kadrodur.
          </p>
        </div>
        <span className="font-mono text-[10px] text-textdim bg-surface2 border border-border rounded px-2 py-0.5">
          GET /admin/scout/similar/&#123;id&#125;
        </span>
      </div>

      <Panel
        title="Hedef oyuncu"
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
              placeholder="Oyuncu ID"
              inputMode="numeric"
              className={`${inputCls} h-7 w-32`}
            />
            <button
              type="submit"
              className="text-[11px] uppercase px-2 py-1 rounded border border-borderlt text-textmut hover:text-text"
            >
              Analiz et
            </button>
          </form>
        }
      >
        {!query && <p className="text-[12px] text-textmut">Bir hedef oyuncu ID gir.</p>}
        {query && sim.isLoading && <p className="text-[12px] text-textmut">Hesaplanıyor…</p>}
        {query && sim.error && (
          <p className="text-[12px] text-textmut">
            Bu oyuncu için maç verisi (appearance) yok ya da aday havuzu yetersiz.
          </p>
        )}
        {sim.data && matches.length > 0 && (
          <>
            <div className="text-[11px] text-textmut font-mono mb-2">
              hedef #{sim.data.value.target_player_id} ·{" "}
              {sim.data.value.candidates_eligible}/{sim.data.value.candidates_considered} uygun aday
            </div>
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-textmut text-left border-b border-border uppercase text-[10.5px]">
                  <th className="py-1 pr-2 w-8">#</th>
                  <th className="py-1 pr-2">Oyuncu</th>
                  <th className="py-1 pr-2 text-right">Benzerlik</th>
                  <th className="py-1 pr-2 text-right">Dakika</th>
                  <th className="py-1 text-right">İzle</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m, i) => (
                  <tr key={m.player_external_id} className="border-b border-border/50">
                    <td className="py-1 pr-2 font-mono text-textdim">{i + 1}</td>
                    <td className="py-1 pr-2 font-mono">#{m.player_external_id}</td>
                    <td className={`py-1 pr-2 text-right font-mono font-semibold ${simColor(m.similarity)}`}>
                      {(m.similarity * 100).toFixed(1)}%
                    </td>
                    <td className="py-1 pr-2 text-right font-mono text-textmut">
                      {m.total_minutes}
                    </td>
                    <td className="py-1 text-right">
                      {watched.has(m.player_external_id) ? (
                        <span className="text-[10px] text-ok uppercase">✓ listede</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => addWatch(m.player_external_id)}
                          className="text-[10px] uppercase px-2 py-0.5 rounded border border-borderlt text-accent hover:bg-surface2"
                        >
                          + izle
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {sim.data && matches.length === 0 && !sim.isLoading && (
          <p className="text-[12px] text-textmut">Yeterli benzer aday bulunamadı.</p>
        )}
      </Panel>

      <Panel title={`İzleme Listesi (${watch.data?.entries.length ?? 0})`}>
        {(watch.data?.entries ?? []).length === 0 ? (
          <p className="text-[12px] text-textmut">Liste boş. Yukarıdan oyuncu ekle.</p>
        ) : (
          <ul className="text-[12px] space-y-1">
            {(watch.data?.entries ?? []).map((e) => (
              <li key={e.id} className="flex items-center gap-3 border-b border-border/40 py-1">
                <span className="font-mono">#{e.player_external_id}</span>
                <span className="text-textmut flex-1">{e.notes ?? "—"}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="font-mono text-[10px] text-textdim mt-2">GET /admin/scout/watchlist</p>
      </Panel>
    </div>
  );
}
