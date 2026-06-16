"use client";

/**
 * Günlük Yük (sRPE) & ACWR — antrenman yükü girişi.
 *
 * Foster sRPE (RPE × süre = AU) → günlük seri → ACWR (acute 7g / chronic 28g).
 * GPS donanımı olmayan kulüpler için evrensel yöntem; sonuç Hazırlık Kararı
 * panosunun ACWR bayrağını besler. DEMO: localStorage (LS_LOAD_KEY); production:
 * POST /physical-tests/session-load. "28 günlük örnek seri" demoda ACWR'yi anında
 * gösterir (≥7 gün gerekir).
 */

import * as React from "react";
import { demoSquad } from "@/lib/demo-data";
import { DEMO_MODE } from "@/lib/demo-mode";
import { apiFetch } from "@/lib/api";
import {
  srpeLoad, loadSessions, saveSessions, acwrResultFor, demoSeedSeriesFor,
  ZONE_VAR, type LoadSession,
} from "@/lib/load";

const today = () => new Date().toISOString().slice(0, 10);

const btn: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, padding: "8px 13px", borderRadius: 8,
  border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)",
  cursor: "pointer", fontFamily: "inherit",
};
const fld: React.CSSProperties = {
  background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8,
  padding: "8px 10px", fontSize: 13, color: "var(--ink)", fontFamily: "inherit",
};

export function LoadEntry({ onChanged }: { onChanged: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [pid, setPid] = React.useState(String(demoSquad[0].player_id));
  const [date, setDate] = React.useState(today());
  const [rpe, setRpe] = React.useState("6");
  const [dur, setDur] = React.useState("60");
  const [sessions, setSessions] = React.useState<LoadSession[]>([]);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => { setSessions(loadSessions()); }, []);

  const player = demoSquad.find((s) => String(s.player_id) === pid);
  const acwr = acwrResultFor(pid, sessions);
  const mineCount = sessions.filter((s) => String(s.player_id) === pid).length;

  function refresh() { setSessions(loadSessions()); onChanged(); }

  async function addOne() {
    const r = parseFloat(rpe);
    const d = parseFloat(dur);
    if (!player || Number.isNaN(r) || Number.isNaN(d) || r <= 0 || r > 10 || d <= 0) {
      setMsg("Oyuncu + RPE (1-10) + süre (dk) gerekli."); return;
    }
    setBusy(true); setMsg(null);
    try {
      if (DEMO_MODE) {
        const rec: LoadSession = {
          id: Date.now(), player_id: pid, player_name: player.player_name,
          session_date: date, source: "srpe", rpe: r, duration_min: d, load_au: srpeLoad(r, d),
        };
        saveSessions([rec, ...loadSessions()]);
        setMsg(`✓ ${player.player_name}: ${srpeLoad(r, d)} AU eklendi (demo).`);
      } else {
        await apiFetch("/physical-tests/session-load", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            player_id: pid, player_name: player.player_name, session_date: date,
            source: "srpe", rpe: r, duration_min: d,
          }),
        });
        setMsg("✓ Yük kaydedildi.");
      }
      refresh();
    } catch (e) {
      setMsg(`Hata: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  function seed() {
    if (!player) return;
    const others = loadSessions().filter((s) => String(s.player_id) !== pid);
    saveSessions([...demoSeedSeriesFor(player.player_id), ...others]);
    setMsg(`✓ ${player.player_name}: 28 günlük örnek seri yüklendi → ACWR hesaplandı.`);
    refresh();
  }

  return (
    <>
      <div className="st"><h2>Günlük Yük (sRPE) & ACWR</h2><span className="ep">akut:kronik yük → karar verici</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }}>
        <button type="button" onClick={() => setOpen(!open)} style={{ ...btn, width: "100%", textAlign: "left", borderStyle: "dashed" }}>
          {open ? "▲ Yük girişini gizle" : "▼ Antrenman yükü gir (RPE × süre → ACWR)"}
        </button>
        {open && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 10, lineHeight: 1.55 }}>
              Foster sRPE: <b>RPE (1-10) × süre (dk) = iç-yük (AU)</b>. Günlük seri 7+ güne
              ulaşınca ACWR (akut 7g / kronik 28g) hesaplanır ve Hazırlık Kararı panosuna işlenir.
              GPS donanımı yoksa evrensel yöntem.
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <select value={pid} onChange={(e) => setPid(e.target.value)} style={{ ...fld, minWidth: 180 }}>
                {demoSquad.map((p) => (
                  <option key={p.player_id} value={String(p.player_id)}>{p.shirt}. {p.player_name}</option>
                ))}
              </select>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} style={fld} />
              <input type="number" min="1" max="10" step="0.5" value={rpe} onChange={(e) => setRpe(e.target.value)} placeholder="RPE" style={{ ...fld, width: 80 }} title="RPE 1-10" />
              <input type="number" min="1" step="5" value={dur} onChange={(e) => setDur(e.target.value)} placeholder="dk" style={{ ...fld, width: 80 }} title="Süre (dk)" />
              <button type="button" onClick={addOne} disabled={busy} style={{ ...btn, background: "var(--besiktas)", color: "#fff", border: 0, fontWeight: 700 }}>
                {busy ? "…" : `Yük Ekle (${srpeLoad(parseFloat(rpe) || 0, parseFloat(dur) || 0)} AU)`}
              </button>
              {DEMO_MODE && (
                <button type="button" onClick={seed} style={btn} title="Demo: bu oyuncuya 28 günlük gerçekçi seri üret">
                  28 günlük örnek seri
                </button>
              )}
            </div>

            <div style={{ display: "flex", gap: 16, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
              <span style={{ fontSize: 12, color: "var(--muted)" }}>
                {player?.player_name} · <b style={{ color: "var(--ink)", fontFamily: "JetBrains Mono" }}>{mineCount}</b> seans
              </span>
              {acwr.acwr != null ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 13, fontWeight: 700 }}>
                  <span style={{ width: 9, height: 9, borderRadius: "50%", background: ZONE_VAR[acwr.zone] }} />
                  ACWR <span style={{ fontFamily: "JetBrains Mono", color: ZONE_VAR[acwr.zone] }}>{acwr.acwr}</span>
                  <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase" }}>({acwr.zone})</span>
                  <span style={{ fontSize: 11, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>akut {acwr.acute} / kronik {acwr.chronic}</span>
                </span>
              ) : (
                <span style={{ fontSize: 12, color: "var(--dim)" }}>ACWR için ≥7 günlük seri gerekli ({acwr.days}/7 gün){DEMO_MODE ? " — “28 günlük örnek seri”ye bas" : ""}</span>
              )}
            </div>
            {msg && <div style={{ fontSize: 12.5, color: "var(--low)", marginTop: 10 }}>{msg}</div>}
            {!DEMO_MODE && <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 8 }}>Production: kayıt DB'ye (POST /session-load) yazılır; ACWR rozeti yalnız demo'da yereldir, pano API'den gerçeği gösterir.</div>}
          </div>
        )}
      </div>
    </>
  );
}
