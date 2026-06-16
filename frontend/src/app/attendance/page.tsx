"use client";

/**
 * Yoklama — antrenman katılım kaydı + özür/izin takibi. ConsoleShell, FM26 açık tema.
 * DEMO_MODE'da inline mock; backend bağlanınca antrenman oturumlarına bağlanır.
 */

import * as React from "react";
import { demoSquad } from "@/lib/demo-data";
import { ConsoleShell } from "../_console/shell";

type Status = "Katıldı" | "İzinli" | "Sakat" | "Geç";
const STATUS_META: Record<Status, { v: string; bg: string; dot: string }> = {
  "Katıldı": { v: "var(--low)", bg: "var(--low-bg)", dot: "var(--low)" },
  "İzinli": { v: "var(--mid)", bg: "var(--mid-bg)", dot: "var(--mid)" },
  "Sakat": { v: "var(--crit)", bg: "var(--crit-bg)", dot: "var(--crit)" },
  "Geç": { v: "var(--high)", bg: "var(--high-bg)", dot: "var(--high)" },
};
const STATUSES: Status[] = ["Katıldı", "İzinli", "Sakat", "Geç"];
const DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Bugün"];

// Deterministik durum üretimi (Math.random YOK).
function statusFor(seed: number, day: number): Status {
  const r = (Math.sin(seed * 2.3 + day * 1.7) + 1) / 2; // 0..1
  if (r > 0.86) return "İzinli";
  if (r > 0.78) return "Geç";
  if (r > 0.72) return "Sakat";
  return "Katıldı";
}

interface Row { shirt: number; name: string; pos: string; week: Status[]; today: Status; note: string }
const ROWS: Row[] = demoSquad.slice(0, 16).map((p) => {
  const week = DAYS.map((_, d) => statusFor(p.player_id, d));
  // Sakat oyuncular (yüksek risk) tüm hafta sakat.
  if (p.risk_label === "Kritik") week.forEach((_, i) => (week[i] = "Sakat"));
  const today = week[week.length - 1];
  const note = today === "Sakat" ? "Tedavi sürüyor" : today === "İzinli" ? "Onaylı izin" : today === "Geç" ? "10 dk geç" : "—";
  return { shirt: p.shirt, name: p.player_name, pos: p.pos_detail, week, today, note };
});

const COUNT = (s: Status) => ROWS.filter((r) => r.today === s).length;
const PRESENT = COUNT("Katıldı") + COUNT("Geç");
const RATE = Math.round((PRESENT / ROWS.length) * 100);

export default function AttendancePage() {
  const right = (
    <>
      <div className="rc">
        <h3>Bugünün Özeti <span className="tiny">{ROWS.length} oyuncu</span></h3>
        {STATUSES.map((s) => {
          const m = STATUS_META[s];
          return (
            <div className="stat" key={s}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: m.dot }} />{s}
              </span>
              <span className="sv" style={{ color: m.v }}>{COUNT(s)}</span>
            </div>
          );
        })}
      </div>
      <div className="rc">
        <h3>İzin & Sakatlık <span className="tiny">{COUNT("İzinli") + COUNT("Sakat")}</span></h3>
        {ROWS.filter((r) => r.today === "İzinli" || r.today === "Sakat").map((r) => {
          const m = STATUS_META[r.today];
          return (
            <div className="alrt" key={r.shirt}>
              <span className="ai" style={{ background: m.dot }} />
              <div className="am"><b>{r.name}</b> ({r.shirt}) · {r.today.toLowerCase()}
                <span className="tm">{r.note}</span>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/attendance"
      title="Yoklama"
      sub="Katılım · özür takibi"
      desc="Günlük antrenman katılımı, geç kalma ve onaylı izin/sakatlık kaydı."
      right={right}
    >
      <div className="kpis">
        <div className="kpi"><div className="kl">Bugünkü Katılım</div><div className="kn" style={{ color: RATE >= 85 ? "var(--low)" : "var(--mid)" }}>{RATE}<span className="pct">%</span></div><div className="kd">{PRESENT}/{ROWS.length} sahada</div></div>
        <div className="kpi"><div className="kl">Mevcut</div><div className="kn" style={{ color: "var(--low)" }}>{COUNT("Katıldı")}</div><div className="kd">tam katılım</div></div>
        <div className="kpi"><div className="kl">İzinli</div><div className="kn" style={{ color: "var(--mid)" }}>{COUNT("İzinli")}</div><div className="kd">onaylı</div></div>
        <div className="kpi"><div className="kl">Sakat</div><div className="kn" style={{ color: "var(--crit)" }}>{COUNT("Sakat")}</div><div className="kd">tedavide</div></div>
        <div className="kpi"><div className="kl">Geç Kalan</div><div className="kn" style={{ color: "var(--high)" }}>{COUNT("Geç")}</div><div className="kd">bugün</div></div>
      </div>

      <div className="st" style={{ marginTop: 0 }}><h2>Haftalık Katılım</h2><span className="ep">son 7 antrenman</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th><th>Oyuncu</th>
            {DAYS.map((d) => <th key={d} className="c">{d}</th>)}
            <th className="c">Durum</th>
          </tr></thead>
          <tbody>
            {ROWS.map((r) => {
              const m = STATUS_META[r.today];
              return (
                <tr key={r.shirt}>
                  <td className="pnum c">{r.shirt}</td>
                  <td><span className="nm">{r.name}</span> <span style={{ color: "var(--dim)", fontSize: 11 }}>· {r.pos}</span></td>
                  {r.week.map((s, i) => {
                    const dm = STATUS_META[s];
                    return (
                      <td key={i} className="c" title={s}>
                        <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: 3, background: dm.dot, opacity: s === "Katıldı" ? 0.85 : 1 }} />
                      </td>
                    );
                  })}
                  <td className="c">
                    <span className="risk" style={{ background: m.bg, color: m.v }}>
                      <span className="rd" style={{ background: m.v }} />{r.today}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", gap: 16, marginTop: 10, flexWrap: "wrap" }}>
        {STATUSES.map((s) => (
          <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--muted)" }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: STATUS_META[s].dot }} /> {s}
          </span>
        ))}
      </div>
    </ConsoleShell>
  );
}
