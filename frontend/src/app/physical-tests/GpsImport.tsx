"use client";

/**
 * GPS Yük Import (Catapult/STATSports) — Faz 2.
 *
 * Vendor CSV satırlarını compute_gps_load aynasıyla iç-yüke (AU) çevirir ve
 * AYNI yük serisine (source="gps") yazar — sRPE ile tek seri, ACWR motoru
 * değişmez. Cihaz `player_load` varsa o kullanılır, yoksa mesafe/HSR/sprint/
 * ivmeden tahmin. DEMO: localStorage; production: POST /session-load (ham
 * metrikler gider, AU backend'de compute_gps_load ile hesaplanır = tek doğruluk).
 *
 * Sütun düzeni: player_id, date, total_distance, hsr, sprint, accel, decel, player_load
 */

import * as React from "react";
import { demoSquad } from "@/lib/demo-data";
import { DEMO_MODE } from "@/lib/demo-mode";
import { apiFetch } from "@/lib/api";
import {
  gpsSessionLoad, loadSessions, saveSessions, type LoadSession,
} from "@/lib/load";

const today = () => new Date().toISOString().slice(0, 10);

const SAMPLE = `player_id,date,total_distance,hsr,sprint,accel,decel,player_load
8,2026-06-08,9800,820,210,28,24,
9,2026-06-08,10500,900,260,31,27,640`;

interface GRow {
  line: number;
  playerId: string;
  playerName: string;
  date: string;
  metrics: { total_distance_m: number; hsr_distance_m: number; sprint_distance_m: number; accelerations: number; decelerations: number; player_load: number | null };
  au: number;
  ok: boolean;
  warn?: string;
  error?: string;
}

const numOr = (s: string | undefined, d = 0): number => {
  if (s == null || s.trim() === "") return d;
  const v = parseFloat(s.replace(",", "."));
  return Number.isNaN(v) ? d : v;
};

function parse(text: string): GRow[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return [];
  const first = lines[0].toLowerCase();
  const start = first.includes("player") || first.includes("distance") ? 1 : 0;
  const rows: GRow[] = [];
  for (let i = start; i < lines.length; i++) {
    const p = lines[i].split(",").map((s) => s.trim());
    const [pid, dateRaw, dist, hsr, sprint, accel, decel, pl] = p;
    const lineNo = i + 1;
    if (!pid || (dist == null && pl == null)) {
      rows.push({ line: lineNo, playerId: pid ?? "", playerName: "", date: "", metrics: { total_distance_m: 0, hsr_distance_m: 0, sprint_distance_m: 0, accelerations: 0, decelerations: 0, player_load: null }, au: 0, ok: false, error: "eksik sütun (player_id + total_distance ya da player_load)" });
      continue;
    }
    const player = demoSquad.find((s) => String(s.player_id) === pid);
    const playerLoad = pl != null && pl.trim() !== "" ? numOr(pl) : null;
    const metrics = {
      total_distance_m: numOr(dist), hsr_distance_m: numOr(hsr), sprint_distance_m: numOr(sprint),
      accelerations: Math.round(numOr(accel)), decelerations: Math.round(numOr(decel)),
      player_load: playerLoad,
    };
    const au = gpsSessionLoad(metrics);
    if (au <= 0) {
      rows.push({ line: lineNo, playerId: pid, playerName: player?.player_name ?? "", date: dateRaw || today(), metrics, au, ok: false, error: "yük 0 — metrikleri kontrol et" });
      continue;
    }
    rows.push({
      line: lineNo, playerId: pid, playerName: player?.player_name ?? `#${pid}`,
      date: dateRaw || today(), metrics, au, ok: true,
      warn: player ? undefined : "kadroda yok (eklenir, panoya yansımaz)",
    });
  }
  return rows;
}

const btn: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, padding: "7px 13px", borderRadius: 8,
  border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)",
  cursor: "pointer", fontFamily: "inherit",
};

export function GpsImport({ onChanged }: { onChanged: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState("");
  const [rows, setRows] = React.useState<GRow[] | null>(null);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const valid = rows?.filter((r) => r.ok) ?? [];
  const invalid = rows?.filter((r) => !r.ok) ?? [];

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => { const t = String(reader.result ?? ""); setText(t); setRows(parse(t)); setMsg(null); };
    reader.readAsText(f);
  }

  async function doImport() {
    if (!valid.length) return;
    setBusy(true);
    setMsg(null);
    try {
      if (DEMO_MODE) {
        const now = Date.now();
        const recs: LoadSession[] = valid.map((r, i) => ({
          id: now + i, player_id: r.playerId, player_name: r.playerName,
          session_date: r.date, source: "gps", load_au: r.au,
        }));
        saveSessions([...recs, ...loadSessions()]);
        setMsg(`✓ ${recs.length} GPS seansı içe aktarıldı (demo). Aynı seriye yazıldı → ACWR güncellendi.`);
      } else {
        let ok = 0, fail = 0;
        await Promise.all(valid.map(async (r) => {
          try {
            await apiFetch("/physical-tests/session-load", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                player_id: r.playerId, player_name: r.playerName, session_date: r.date,
                source: "gps", ...r.metrics,
              }),
            });
            ok++;
          } catch { fail++; }
        }));
        setMsg(`✓ ${ok} GPS seansı yazıldı${fail ? `, ${fail} başarısız` : ""}.`);
      }
      setRows(null);
      setText("");
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="st"><h2>GPS Yük Import</h2><span className="ep">Catapult/STATSports → aynı seri (Faz 2)</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }}>
        <button type="button" onClick={() => setOpen(!open)} style={{ ...btn, width: "100%", textAlign: "left", borderStyle: "dashed" }}>
          {open ? "▲ GPS importu gizle" : "▼ GPS vendor CSV yükle (mesafe/HSR/sprint → AU)"}
        </button>
        {open && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8, lineHeight: 1.55 }}>
              Sütun: <code>player_id, date, total_distance, hsr, sprint, accel, decel, player_load</code>.
              Cihaz <code>player_load</code> varsa o (AU) kullanılır; yoksa mesafe/HSR/sprint/ivmeden tahmin.
              sRPE ile <b>aynı seriye</b> (source=gps) yazılır — ACWR motoru değişmez.
            </div>
            <textarea
              value={text} onChange={(e) => setText(e.target.value)} placeholder={SAMPLE} rows={5}
              style={{ width: "100%", boxSizing: "border-box", background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "10px 12px", fontSize: 12.5, fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: "var(--ink)", resize: "vertical" }}
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
              <input type="file" accept=".csv,text/csv" onChange={onFile} style={{ fontSize: 12, color: "var(--muted)" }} />
              <button type="button" onClick={() => { setRows(parse(text)); setMsg(null); }} style={btn} disabled={!text.trim()}>Önizle</button>
              <button type="button" onClick={() => { setText(SAMPLE); setRows(null); setMsg(null); }} style={btn}>Örnek doldur</button>
            </div>

            {rows && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12, marginBottom: 6, fontFamily: "JetBrains Mono" }}>
                  <span style={{ color: "var(--low)" }}>{valid.length} geçerli</span>
                  {invalid.length > 0 && <span style={{ color: "var(--crit)" }}> · {invalid.length} hatalı</span>}
                </div>
                <div className="tbl">
                  <table>
                    <thead><tr>
                      <th className="c">Satır</th><th>Oyuncu</th><th className="c">Tarih</th>
                      <th className="r">Mesafe</th><th className="r">Yük (AU)</th><th>Durum</th>
                    </tr></thead>
                    <tbody>
                      {rows.slice(0, 30).map((r) => (
                        <tr key={r.line} style={{ opacity: r.ok ? 1 : 0.65 }}>
                          <td className="pnum c">{r.line}</td>
                          <td><span className="nm">{r.playerName || "—"}</span> <span style={{ color: "var(--dim)" }}>#{r.playerId}</span></td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)" }}>{r.date || "—"}</td>
                          <td className="r" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{r.metrics.total_distance_m || (r.metrics.player_load != null ? "PL" : "—")}</td>
                          <td className="r" style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>{r.au || "—"}</td>
                          <td style={{ fontSize: 11.5, color: r.ok ? (r.warn ? "var(--mid)" : "var(--low)") : "var(--crit)" }}>{r.error ?? r.warn ?? "geçerli"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {rows.length > 30 && <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 6 }}>… +{rows.length - 30} satır daha (hepsi içe aktarılır)</div>}
                <button
                  type="button" onClick={doImport} disabled={!valid.length || busy}
                  style={{ ...btn, marginTop: 10, background: valid.length ? "var(--besiktas)" : "var(--panel)", color: valid.length ? "#fff" : "var(--dim)", border: 0, fontWeight: 700, padding: "10px 16px", cursor: valid.length && !busy ? "pointer" : "default" }}
                >
                  {busy ? "Aktarılıyor…" : `İçe Aktar (${valid.length} GPS seansı)`}
                </button>
              </div>
            )}
            {msg && <div style={{ fontSize: 12.5, color: "var(--low)", marginTop: 10, lineHeight: 1.5 }}>{msg}</div>}
          </div>
        )}
      </div>
    </>
  );
}
