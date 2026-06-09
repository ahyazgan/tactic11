"use client";

/**
 * Wellness (öznel günlük hazırlık) — 5 madde anket (1-7).
 *
 * Uyku/dinçlik/ağrısızlık/sakinlik/ruh hali → readiness (compute_wellness aynası).
 * ACWR (objektif yük) ile birlikte Hazırlık Kararı'nın öznel yarısı. DEMO:
 * localStorage; production: POST /physical-tests/wellness. squad-readiness
 * her oyuncunun EN SON anketini kullanır.
 */

import * as React from "react";
import { demoSquad } from "@/lib/demo-data";
import { DEMO_MODE } from "@/lib/demo-mode";
import { apiFetch } from "@/lib/api";
import {
  wellnessReadiness, wellnessZone, WZONE_VAR, loadWellness, saveWellness,
  demoSeedWellnessAll, latestWellnessFor, type WellnessEntry as WEntry, type WellnessFields,
} from "@/lib/wellness";

const today = () => new Date().toISOString().slice(0, 10);

const ITEMS: { key: keyof WellnessFields; label: string }[] = [
  { key: "sleep_quality", label: "Uyku" },
  { key: "fatigue", label: "Dinçlik" },
  { key: "muscle_soreness", label: "Ağrısızlık" },
  { key: "stress", label: "Sakinlik" },
  { key: "mood", label: "Ruh hali" },
];

const btn: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, padding: "8px 13px", borderRadius: 8,
  border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)",
  cursor: "pointer", fontFamily: "inherit",
};

export function WellnessEntry({ onChanged }: { onChanged: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [pid, setPid] = React.useState(String(demoSquad[0].player_id));
  const [vals, setVals] = React.useState<WellnessFields>({
    sleep_quality: 6, fatigue: 6, muscle_soreness: 6, stress: 6, mood: 6,
  });
  const [entries, setEntries] = React.useState<WEntry[]>([]);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => { setEntries(loadWellness()); }, []);

  const player = demoSquad.find((s) => String(s.player_id) === pid);
  const readiness = wellnessReadiness(vals);
  const zone = wellnessZone(readiness);
  const latest = latestWellnessFor(pid, entries);

  function refresh() { setEntries(loadWellness()); onChanged(); }
  const setItem = (k: keyof WellnessFields, v: number) =>
    setVals((prev) => ({ ...prev, [k]: Math.max(1, Math.min(7, v)) }));

  async function addOne() {
    if (!player) return;
    setBusy(true); setMsg(null);
    try {
      if (DEMO_MODE) {
        const rec: WEntry = {
          id: Date.now(), player_id: pid, player_name: player.player_name,
          entry_date: today(), ...vals, readiness,
        };
        saveWellness([rec, ...loadWellness()]);
        setMsg(`✓ ${player.player_name}: hazırlık %${Math.round(readiness * 100)} (${zone}).`);
      } else {
        await apiFetch("/physical-tests/wellness", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ player_id: pid, player_name: player.player_name, entry_date: today(), ...vals }),
        });
        setMsg("✓ Anket kaydedildi.");
      }
      refresh();
    } catch (e) {
      setMsg(`Hata: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  function seedAll() {
    saveWellness(demoSeedWellnessAll(today()));
    setMsg("✓ Tüm kadroya demo anket üretildi → pano öznel readiness'le güncellendi.");
    refresh();
  }

  return (
    <>
      <div className="st"><h2>Wellness (Öznel Hazırlık)</h2><span className="ep">uyku/yorgunluk/ağrı → karar verici</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }}>
        <button type="button" onClick={() => setOpen(!open)} style={{ ...btn, width: "100%", textAlign: "left", borderStyle: "dashed" }}>
          {open ? "▲ Wellness anketini gizle" : "▼ Günlük hazırlık anketi gir (5 madde, 1-7)"}
        </button>
        {open && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 10, lineHeight: 1.55 }}>
              Her madde <b>1-7</b> (7 = en iyi). 5 maddenin ortalaması readiness'i verir
              (≥%70 hazır · &lt;%55 dikkat). ACWR (objektif) ile birlikte Hazırlık Kararı'nın öznel yarısı.
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, color: "var(--dim)" }}>
                oyuncu
                <select value={pid} onChange={(e) => setPid(e.target.value)} style={{ ...btn, fontWeight: 400, cursor: "pointer", minWidth: 170 }}>
                  {demoSquad.map((p) => <option key={p.player_id} value={String(p.player_id)}>{p.shirt}. {p.player_name}</option>)}
                </select>
              </label>
              {ITEMS.map((it) => (
                <label key={it.key} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, color: "var(--dim)" }}>
                  {it.label}
                  <input type="number" min={1} max={7} value={vals[it.key]} onChange={(e) => setItem(it.key, parseInt(e.target.value, 10) || 1)}
                    style={{ width: 58, background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "8px 10px", fontSize: 13, color: "var(--ink)", fontFamily: "JetBrains Mono" }} />
                </label>
              ))}
              <button type="button" onClick={addOne} disabled={busy} style={{ ...btn, background: "var(--besiktas)", color: "#fff", border: 0, fontWeight: 700 }}>
                {busy ? "…" : "Anket Kaydet"}
              </button>
              {DEMO_MODE && <button type="button" onClick={seedAll} style={btn} title="Demo: tüm kadroya bir günlük anket üret">Tüm kadroya demo anket</button>}
            </div>

            <div style={{ display: "flex", gap: 16, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 13, fontWeight: 700 }}>
                <span style={{ width: 9, height: 9, borderRadius: "50%", background: WZONE_VAR[zone] }} />
                Girilen: <span style={{ fontFamily: "JetBrains Mono", color: WZONE_VAR[zone] }}>%{Math.round(readiness * 100)}</span>
                <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase" }}>({zone})</span>
              </span>
              {latest && (
                <span style={{ fontSize: 11.5, color: "var(--dim)" }}>
                  {player?.player_name} son kayıt: %{Math.round(latest.readiness * 100)} · {latest.entry_date}
                </span>
              )}
            </div>
            {msg && <div style={{ fontSize: 12.5, color: "var(--low)", marginTop: 10 }}>{msg}</div>}
          </div>
        )}
      </div>
    </>
  );
}
