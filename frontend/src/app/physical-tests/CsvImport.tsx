"use client";

/**
 * Toplu Veri Girişi (CSV) — kadro-geneli fiziksel test import.
 *
 * Uzun format: `player_id, protocol, value, date` (date opsiyonel → bugün).
 * Aynı demo deposunu (localStorage LS_KEY) besler; böylece Hazırlık Kararı panosu
 * + "Test Hesaplayıcı Kayıtları" anında güncellenir. H:Q için isokinetic_ham +
 * isokinetic_quad aynı oyuncuya girilirse karar verici otomatik eşler.
 *
 * DEMO_MODE: localStorage'a yaz. Production: satır başına POST /physical-tests/.
 */

import * as React from "react";
import { demoSquad } from "@/lib/demo-data";
import { DEMO_MODE } from "@/lib/demo-mode";
import { apiFetch } from "@/lib/api";
import {
  PROTO_NAME, PROTO_UNIT, loadDerivedRecords, saveDerivedRecords, type SavedRecord,
} from "@/lib/derived-tests";

const KNOWN = new Set(Object.keys(PROTO_NAME));
const today = () => new Date().toISOString().slice(0, 10);

const SAMPLE = `player_id,protocol,value,date
8,isokinetic_ham,1.4,2026-06-08
8,isokinetic_quad,3.2,2026-06-08
3,sprint_10m,1.92,2026-06-08
9,cmj,47,2026-06-08`;

interface Row {
  line: number;
  playerId: string;
  playerName: string;
  protocol: string;
  value: number;
  date: string;
  ok: boolean;
  warn?: string;
  error?: string;
}

function parseCsv(text: string): Row[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return [];
  const first = lines[0].toLowerCase();
  const start = first.includes("player") || first.includes("protocol") ? 1 : 0;
  const rows: Row[] = [];
  for (let i = start; i < lines.length; i++) {
    const parts = lines[i].split(",").map((s) => s.trim());
    const [pid, proto, valRaw, dateRaw] = parts;
    const lineNo = i + 1;
    if (!pid || !proto || valRaw === undefined || valRaw === "") {
      rows.push({ line: lineNo, playerId: pid ?? "", playerName: "", protocol: proto ?? "", value: NaN, date: "", ok: false, error: "eksik sütun (player_id, protocol, value)" });
      continue;
    }
    const value = parseFloat(valRaw.replace(",", "."));
    const player = demoSquad.find((s) => String(s.player_id) === pid);
    if (Number.isNaN(value)) {
      rows.push({ line: lineNo, playerId: pid, playerName: player?.player_name ?? "", protocol: proto, value: NaN, date: "", ok: false, error: `geçersiz değer "${valRaw}"` });
      continue;
    }
    let warn: string | undefined;
    if (!player) warn = "kadroda yok (eklenir, panoya yansımaz)";
    else if (!KNOWN.has(proto)) warn = `bilinmeyen protokol "${proto}"`;
    rows.push({
      line: lineNo, playerId: pid, playerName: player?.player_name ?? `#${pid}`,
      protocol: proto, value, date: dateRaw || today(), ok: true, warn,
    });
  }
  return rows;
}

const btn: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, padding: "7px 13px", borderRadius: 8,
  border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)",
  cursor: "pointer", fontFamily: "inherit",
};

export function CsvImport({ onImported }: { onImported: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState("");
  const [rows, setRows] = React.useState<Row[] | null>(null);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const valid = rows?.filter((r) => r.ok) ?? [];
  const invalid = rows?.filter((r) => !r.ok) ?? [];
  const warned = valid.filter((r) => r.warn);

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => { const t = String(reader.result ?? ""); setText(t); setRows(parseCsv(t)); setMsg(null); };
    reader.readAsText(f);
  }

  async function doImport() {
    if (!valid.length) return;
    setBusy(true);
    setMsg(null);
    try {
      if (DEMO_MODE) {
        const now = Date.now();
        const recs: SavedRecord[] = valid.map((r, i) => ({
          id: now + i, player_id: r.playerId, player_name: r.playerName,
          test_date: r.date, protocol: r.protocol, value: r.value, components: {},
          label: `${r.value}${PROTO_UNIT[r.protocol] ? " " + PROTO_UNIT[r.protocol] : ""} (CSV)`,
        }));
        saveDerivedRecords([...recs, ...loadDerivedRecords()]);
        setMsg(`✓ ${recs.length} kayıt içe aktarıldı (demo: tarayıcıda saklandı). Hazırlık Kararı panosu güncellendi.`);
      } else {
        let ok = 0, fail = 0;
        await Promise.all(valid.map(async (r) => {
          try {
            await apiFetch("/physical-tests/", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                player_id: r.playerId, player_name: r.playerName, test_date: r.date,
                protocol: r.protocol, value: r.value, recorded_by: "CSV import",
              }),
            });
            ok++;
          } catch { fail++; }
        }));
        setMsg(`✓ ${ok} kayıt yazıldı${fail ? `, ${fail} başarısız` : ""}.`);
      }
      setRows(null);
      setText("");
      onImported();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="st"><h2>Toplu Veri Girişi (CSV)</h2><span className="ep">kadro-geneli test import</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }}>
        <button type="button" onClick={() => setOpen(!open)} style={{ ...btn, width: "100%", textAlign: "left", borderStyle: "dashed" }}>
          {open ? "▲ CSV importu gizle" : "▼ CSV ile toplu test yükle (kadro geneli)"}
        </button>
        {open && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8, lineHeight: 1.55 }}>
              Sütun düzeni: <code>player_id, protocol, value, date</code> — date opsiyonel (boşsa bugün).
              H:Q kararı için aynı oyuncuya <code>isokinetic_ham</code> + <code>isokinetic_quad</code> gir;
              karar verici ikisini otomatik eşler.
            </div>
            <textarea
              value={text} onChange={(e) => setText(e.target.value)} placeholder={SAMPLE} rows={6}
              style={{ width: "100%", boxSizing: "border-box", background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "10px 12px", fontSize: 12.5, fontFamily: "'JetBrains Mono', ui-monospace, monospace", color: "var(--ink)", resize: "vertical" }}
            />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
              <input type="file" accept=".csv,text/csv" onChange={onFile} style={{ fontSize: 12, color: "var(--muted)" }} />
              <button type="button" onClick={() => { setRows(parseCsv(text)); setMsg(null); }} style={btn} disabled={!text.trim()}>Önizle</button>
              <button type="button" onClick={() => { setText(SAMPLE); setRows(null); setMsg(null); }} style={btn}>Örnek doldur</button>
            </div>

            {rows && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12, marginBottom: 6, fontFamily: "JetBrains Mono" }}>
                  <span style={{ color: "var(--low)" }}>{valid.length} geçerli</span>
                  {warned.length > 0 && <span style={{ color: "var(--mid)" }}> · {warned.length} uyarı</span>}
                  {invalid.length > 0 && <span style={{ color: "var(--crit)" }}> · {invalid.length} hatalı</span>}
                </div>
                <div className="tbl">
                  <table>
                    <thead><tr>
                      <th className="c">Satır</th><th>Oyuncu</th><th>Protokol</th>
                      <th className="r">Değer</th><th className="c">Tarih</th><th>Durum</th>
                    </tr></thead>
                    <tbody>
                      {rows.slice(0, 30).map((r) => (
                        <tr key={r.line} style={{ opacity: r.ok ? 1 : 0.65 }}>
                          <td className="pnum c">{r.line}</td>
                          <td><span className="nm">{r.playerName || "—"}</span> <span style={{ color: "var(--dim)" }}>#{r.playerId}</span></td>
                          <td style={{ color: "var(--muted)" }}>{PROTO_NAME[r.protocol] ?? r.protocol}</td>
                          <td className="r" style={{ fontFamily: "JetBrains Mono" }}>{Number.isNaN(r.value) ? "—" : r.value}</td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)" }}>{r.date || "—"}</td>
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
                  {busy ? "Aktarılıyor…" : `İçe Aktar (${valid.length} satır)`}
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
