"use client";

/**
 * Hedef Takibi — oyuncu/protokol hedef değeri + "bu hızla kaç ölçüm sonra".
 *
 * İlerleme oyuncunun test geçmişinden (least-squares eğim) türetilir; hedef
 * yalnızca sayı + isteğe bağlı son tarih/not. Rotadan sapan üstte. DEMO:
 * localStorage + demoHistoryFor; production: /physical-tests/targets.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoSquad, demoProtocols } from "@/lib/demo-data";
import { PROTO_NAME } from "@/lib/derived-tests";
import {
  loadTargets, saveTargets, demoTargetRows, STATUS_LABEL, STATUS_VAR, TARGET_MIN_POINTS,
  type StoredTarget, type TargetRow,
} from "@/lib/targets";

const TARGET_PROTOCOLS = ["cmj", "sprint_10m", "sprint_30m", "yoyo_irl1", "vo2max"];

const field: React.CSSProperties = {
  fontFamily: "inherit", fontSize: 12.5, padding: "6px 8px", borderRadius: 8,
  border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)",
};
const btn: React.CSSProperties = {
  fontSize: 12, fontWeight: 700, padding: "7px 13px", borderRadius: 8, border: 0,
  background: "var(--besiktas)", color: "#fff", cursor: "pointer", fontFamily: "inherit",
};

const fmt = (x: number | null, unit: string) => (x == null ? "—" : `${x}${unit === "sn" ? "" : ""}`);

export function TargetTracker() {
  const [stored, setStored] = React.useState<StoredTarget[]>([]);
  const [pid, setPid] = React.useState(String(demoSquad[0].player_id));
  const [proto, setProto] = React.useState("cmj");
  const [value, setValue] = React.useState("");
  const [due, setDue] = React.useState("");
  const [note, setNote] = React.useState("");
  const [msg, setMsg] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => { setStored(loadTargets()); }, []);

  const api = useSWR<TargetRow[]>(DEMO_MODE ? null : "/physical-tests/targets", apiFetch);
  const rows: TargetRow[] = DEMO_MODE ? demoTargetRows(stored) : (api.data ?? []);
  const unit = demoProtocols.find((p) => p.key === proto)?.unit ?? "";

  async function add() {
    const player = demoSquad.find((s) => String(s.player_id) === pid);
    const v = Number(value);
    if (!player || !Number.isFinite(v) || value.trim() === "") { setMsg("Hedef değer gerekli."); return; }
    setBusy(true); setMsg(null);
    const payload = {
      player_id: pid, player_name: player.player_name, protocol: proto, target_value: v,
      due_date: due || null, note: note.trim() || null,
    };
    try {
      if (DEMO_MODE) {
        const next = [...loadTargets(), { id: Date.now(), ...payload }];
        saveTargets(next); setStored(next);
      } else {
        await apiFetch("/physical-tests/targets", { method: "POST", body: JSON.stringify(payload) });
        await api.mutate();
      }
      setValue(""); setNote(""); setMsg("Hedef kaydedildi.");
    } catch (e) {
      setMsg(`Kaydedilemedi: ${String(e).slice(0, 100)}`);
    } finally { setBusy(false); }
  }

  async function remove(id: number) {
    try {
      if (DEMO_MODE) {
        const next = loadTargets().filter((t) => t.id !== id);
        saveTargets(next); setStored(next);
      } else {
        await apiFetch(`/physical-tests/targets/${id}`, { method: "DELETE" });
        await api.mutate();
      }
    } catch (e) {
      setMsg(`Silinemedi: ${String(e).slice(0, 100)}`);
    }
  }

  return (
    <>
      <div className="st"><h2>Hedef Takibi</h2><span className="ep">hedef değer · mevcut eğimle kaç ölçüm sonra</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }} data-testid="target-panel">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
          <select value={pid} onChange={(e) => setPid(e.target.value)} style={field} aria-label="Oyuncu">
            {demoSquad.map((s) => <option key={s.player_id} value={String(s.player_id)}>{s.player_name}</option>)}
          </select>
          <select value={proto} onChange={(e) => setProto(e.target.value)} style={field} aria-label="Protokol">
            {TARGET_PROTOCOLS.map((k) => <option key={k} value={k}>{PROTO_NAME[k] ?? k}</option>)}
          </select>
          <input type="number" step="any" value={value} onChange={(e) => setValue(e.target.value)} placeholder={`hedef (${unit})`} style={{ ...field, width: 110 }} aria-label="Hedef değer" />
          <input type="date" value={due} onChange={(e) => setDue(e.target.value)} style={field} aria-label="Son tarih" />
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="not (isteğe bağlı)" style={{ ...field, width: 180 }} aria-label="Not" />
          <button type="button" onClick={add} disabled={busy} style={{ ...btn, opacity: busy ? 0.6 : 1 }}>
            <i className="ti ti-target-arrow" style={{ marginRight: 6 }} />Hedef koy
          </button>
          {msg && <span style={{ fontSize: 11.5, color: "var(--muted)" }}>{msg}</span>}
        </div>

        {!rows.length ? (
          <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
            {api.error ? `Yüklenemedi: ${String(api.error).slice(0, 80)}` : "Henüz hedef yok. Yukarıdan oyuncu + protokol + hedef değer gir."}
          </div>
        ) : (
          <>
            <div className="tbl">
              <table>
                <thead>
                  <tr>
                    <th>Oyuncu</th><th>Protokol</th><th className="r">Hedef</th><th className="r">Şimdi (n)</th>
                    <th className="r">Kalan</th><th>İlerleme</th><th>Durum</th><th>Son tarih</th><th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const v = STATUS_VAR[r.status];
                    return (
                      <tr key={r.id} data-status={r.status}>
                        <td className="nm">{r.player_name}</td>
                        <td>{PROTO_NAME[r.protocol] ?? r.protocol}</td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>{r.target_value} <span style={{ color: "var(--dim)", fontSize: 10.5 }}>{r.unit}</span></td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono" }}>{fmt(r.current, r.unit)} <span style={{ color: "var(--dim)" }}>({r.n_points})</span></td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono", color: r.gap != null && r.gap <= 0 ? "var(--low)" : "var(--ink)" }}>{r.gap == null ? "—" : r.gap <= 0 ? "0" : r.gap}</td>
                        <td style={{ minWidth: 140 }}>
                          <span className="mbar" style={{ display: "block", maxWidth: 160 }}>
                            <i style={{ width: `${r.progress_pct ?? 0}%`, background: v }} />
                          </span>
                          <span style={{ fontSize: 10.5, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>{r.progress_pct == null ? "—" : `%${r.progress_pct}`}</span>
                        </td>
                        <td>
                          <span className="risk" style={{ background: "transparent", color: v, fontSize: 10.5, textTransform: "uppercase", border: `1px solid ${v}`, borderRadius: 5, padding: "0 6px" }}>
                            {STATUS_LABEL[r.status]}
                          </span>
                          <div style={{ color: "var(--dim)", fontSize: 11, marginTop: 2 }}>{r.progress_note}</div>
                        </td>
                        <td style={{ fontSize: 11.5, color: "var(--dim)" }}>{r.due_date ?? "—"}{r.note ? ` · ${r.note}` : ""}</td>
                        <td className="r">
                          <button type="button" onClick={() => remove(r.id)} title="Hedefi sil" aria-label="Hedefi sil"
                            style={{ background: "transparent", border: 0, color: "var(--dim)", cursor: "pointer", fontSize: 14 }}>
                            <i className="ti ti-x" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 8 }}>
              İlerleme = ilk ölçümden hedefe kat edilen yol. "Kaç ölçüm sonra" = kalan ÷ ölçüm başına eğim (en küçük kareler, ≥{TARGET_MIN_POINTS} ölçüm);
              eğim ters yönde ya da 12 ölçümden uzun sürecekse "rotadan sapıyor". Tarih tahmini yapılmaz: test aralığı düzensiz olabilir.
            </div>
          </>
        )}
      </div>
    </>
  );
}
