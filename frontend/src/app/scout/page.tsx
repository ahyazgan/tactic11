"use client";

/**
 * Scout — Oyuncu Benzerliği. ConsoleShell çatısını kullanır.
 * Hedef oyuncu → cosine similarity ile top-N benzer oyuncu + izleme listesi.
 * Backend:
 *   GET    /admin/scout/similar/{player_external_id}
 *   GET    /admin/scout/watchlist
 *   POST   /admin/scout/watchlist
 *   DELETE /admin/scout/watchlist/{id}
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

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

function simColor(sim: number): string {
  if (sim >= 0.85) return "var(--low)";
  if (sim >= 0.7) return "var(--mid)";
  return "var(--muted)";
}

const inputStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 10px",
  borderRadius: "7px",
  width: "130px",
  fontFamily: "inherit",
};

export default function ScoutConsolePage() {
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
  const entries = watch.data?.entries ?? [];
  const watched = new Set(entries.map((e) => e.player_external_id));

  async function addWatch(pid: number) {
    try {
      await apiFetch("/admin/scout/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_external_id: pid, notes: `Scout: ${query} ile benzer` }),
      });
      watch.mutate();
    } catch {
      /* sessizce yut */
    }
  }

  async function removeWatch(pid: number) {
    try {
      await apiFetch(`/admin/scout/watchlist/${pid}`, { method: "DELETE" });
      watch.mutate();
    } catch {
      /* sessizce yut */
    }
  }

  const right = (
    <div className="rc">
      <h3>İzleme Listesi <span className="tiny">{entries.length}</span></h3>
      {entries.length === 0 && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Liste boş. Soldan oyuncu ekle.</div>}
      {entries.map((e) => (
        <div className="alrt" key={e.id}>
          <span className="ai" style={{ background: "var(--low)" }} />
          <div className="am" style={{ flex: 1 }}>
            <b style={{ fontFamily: "JetBrains Mono" }}>#{e.player_external_id}</b>
            <span className="tm">{e.notes ?? "—"}</span>
          </div>
          <button
            type="button"
            onClick={() => removeWatch(e.player_external_id)}
            title="İzleme listesinden çıkar"
            style={{ background: "transparent", border: "1px solid var(--line)", color: "var(--crit)", fontSize: "10px", padding: "2px 7px", borderRadius: 5, cursor: "pointer" }}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );

  return (
    <ConsoleShell
      active="/scout"
      title="Scout — Benzerlik"
      sub="Oyuncu profil eşleştirme"
      desc="Per-90 stat vektörü + cosine similarity ile hedef oyuncuya en yakın profiller. Aday havuzu mevcut kadrodur."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Hedef Oyuncu</h2>
        <form onSubmit={(e) => { e.preventDefault(); setQuery(search.trim()); }} style={{ display: "flex", gap: 6 }}>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Oyuncu ID" inputMode="numeric" style={inputStyle} />
          <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Analiz et</button>
        </form>
      </div>

      {!query && <div className="pgdesc">Benzerlik analizi için bir hedef oyuncu ID gir.</div>}
      {query && sim.isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {query && sim.error && <div className="pgdesc">Bu oyuncu için maç verisi yok ya da aday havuzu yetersiz.</div>}
      {sim.data && matches.length === 0 && !sim.isLoading && <div className="pgdesc">Yeterli benzer aday bulunamadı.</div>}

      {sim.data && matches.length > 0 && (
        <>
          <div className="st">
            <h2>Benzer Oyuncular</h2>
            <span className="ep">hedef #{sim.data.value.target_player_id} · {sim.data.value.candidates_eligible}/{sim.data.value.candidates_considered} aday</span>
          </div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th className="c">#</th><th>Oyuncu</th><th className="r">Benzerlik</th><th className="r">Dakika</th><th className="c">İzle</th>
              </tr></thead>
              <tbody>
                {matches.map((m, i) => (
                  <tr key={m.player_external_id}>
                    <td className="pnum c">{i + 1}</td>
                    <td><span className="nm" style={{ fontFamily: "JetBrains Mono" }}>#{m.player_external_id}</span></td>
                    <td className="r" style={{ color: simColor(m.similarity) }}>{(m.similarity * 100).toFixed(1)}%</td>
                    <td className="r" style={{ color: "var(--muted)" }}>{m.total_minutes}</td>
                    <td className="c">
                      {watched.has(m.player_external_id) ? (
                        <span style={{ fontSize: "10px", color: "var(--low)", textTransform: "uppercase" }}>✓ listede</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => addWatch(m.player_external_id)}
                          style={{ fontSize: "10px", textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: "1px solid var(--line)", color: "var(--ink)", background: "var(--panel3)", cursor: "pointer" }}
                        >
                          + izle
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
