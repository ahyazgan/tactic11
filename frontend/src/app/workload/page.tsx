"use client";

/**
 * Yük Takibi — ACWR (akut:kronik iş yükü oranı) + GPS yük göstergeleri.
 *
 * ConsoleShell çatısında, FM26 açık tema. DEMO_MODE'da inline mock veriyle
 * kadronun haftalık GPS yükü + ACWR bandı + aşırı yüklenme riskini gösterir.
 * Backend bağlanınca app/engine/gps_load + injury_risk motorlarına (ACWR)
 * bağlanacak.
 */

import * as React from "react";
import { demoSquad } from "@/lib/demo-data";
import { ConsoleShell } from "../_console/shell";
import { RiskDonut, LegendRow } from "../_console/viz";

interface Load {
  shirt: number;
  name: string;
  pos: string;
  acute: number;    // 7 günlük iç yük (AU)
  chronic: number;  // 28 günlük ort. (AU)
  acwr: number;     // akut / kronik
  gpsKm: number;    // son maç toplam mesafe (km)
  hir: number;      // yüksek-şiddet koşu mesafesi (m)
}

// demoSquad'dan deterministik üret (Math.random YOK — tekrarlanabilir).
const LOADS: Load[] = demoSquad.slice(0, 16).map((p, i) => {
  const wave = Math.sin((p.player_id + i) * 1.3) * 0.5 + 0.5; // 0..1
  const chronic = 380 + Math.round(wave * 140);
  // Riskli oyuncuda akut yük kronik'in üstüne çıkar.
  const ratio = 0.82 + (p.risk_score / 100) * 0.95 + wave * 0.12;
  const acwr = Math.round(ratio * 100) / 100;
  const acute = Math.round(chronic * acwr);
  return {
    shirt: p.shirt, name: p.player_name, pos: p.pos_detail,
    acute, chronic, acwr,
    gpsKm: Math.round((9.4 + wave * 2.4) * 10) / 10,
    hir: 720 + Math.round(wave * 520),
  };
});

function acwrColor(v: number): string {
  if (v > 1.5) return "var(--crit)";
  if (v > 1.3) return "var(--high)";
  if (v < 0.8) return "var(--mid)";
  return "var(--low)";
}
function acwrLabel(v: number): string {
  if (v > 1.5) return "Tehlike";
  if (v > 1.3) return "Yüksek";
  if (v < 0.8) return "Düşük yük";
  return "İdeal";
}

const AVG_ACWR = Math.round((LOADS.reduce((a, p) => a + p.acwr, 0) / LOADS.length) * 100) / 100;
const IDEAL = LOADS.filter((p) => p.acwr >= 0.8 && p.acwr <= 1.3).length;
const RISKY = LOADS.filter((p) => p.acwr > 1.3);
const TOTAL_KM = Math.round(LOADS.reduce((a, p) => a + p.gpsKm, 0) * 10) / 10;
const TOP = LOADS.reduce((b, p) => (p.gpsKm > b.gpsKm ? p : b), LOADS[0]);

/** ACWR bant göstergesi — 0.5..2.0 ekseninde "tatlı nokta" 0.8-1.3 yeşil. */
function AcwrScale({ value }: { value: number }) {
  const min = 0.5, max = 2.0;
  const pct = (v: number) => Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
  return (
    <div style={{ position: "relative", height: 10, borderRadius: 6, overflow: "hidden", background: "var(--surface2)" }}>
      <div style={{ position: "absolute", left: `${pct(0.8)}%`, width: `${pct(1.3) - pct(0.8)}%`, top: 0, bottom: 0, background: "var(--low-bg)" }} />
      <div style={{ position: "absolute", left: `${pct(1.3)}%`, width: `${pct(1.5) - pct(1.3)}%`, top: 0, bottom: 0, background: "var(--high-bg)" }} />
      <div style={{ position: "absolute", left: `${pct(1.5)}%`, right: 0, top: 0, bottom: 0, background: "var(--crit-bg)" }} />
      <div style={{ position: "absolute", left: `calc(${pct(value)}% - 1px)`, top: -2, bottom: -2, width: 2, background: "var(--ink)" }} />
    </div>
  );
}

export default function WorkloadPage() {
  const dist = [
    { label: "İdeal (0.8–1.3)", v: "var(--low)", n: LOADS.filter((p) => p.acwr >= 0.8 && p.acwr <= 1.3).length },
    { label: "Yüksek (1.3–1.5)", v: "var(--high)", n: LOADS.filter((p) => p.acwr > 1.3 && p.acwr <= 1.5).length },
    { label: "Tehlike (>1.5)", v: "var(--crit)", n: LOADS.filter((p) => p.acwr > 1.5).length },
    { label: "Düşük (<0.8)", v: "var(--mid)", n: LOADS.filter((p) => p.acwr < 0.8).length },
  ];

  const right = (
    <>
      <div className="rc">
        <h3>ACWR Dağılımı <span className="tiny">{LOADS.length} oyuncu</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut segments={dist.map((d) => ({ value: d.n, color: d.v }))} centerLabel={IDEAL} centerSub="ideal" />
          <div style={{ flex: 1, minWidth: 0 }}>
            {dist.map((d) => <LegendRow key={d.label} color={d.v} label={d.label} value={d.n} />)}
          </div>
        </div>
      </div>
      <div className="rc">
        <h3>Aşırı Yüklenme Uyarısı <span className="tiny">{RISKY.length} oyuncu</span></h3>
        {RISKY.length === 0 && <div style={{ fontSize: 12, color: "var(--dim)" }}>ACWR eşiği aşan yok.</div>}
        {RISKY.map((p) => {
          const c = acwrColor(p.acwr);
          return (
            <div className="alrt" key={p.shirt}>
              <span className="ai" style={{ background: c }} />
              <div className="am"><b>{p.name}</b> ({p.shirt})
                <span className="tm">ACWR {p.acwr.toFixed(2)} · {acwrLabel(p.acwr)} — yük %{Math.round((p.acwr - 1) * 100)} fazla</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="rc">
        <h3>ACWR Nedir?</h3>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55 }}>
          Akut (7 gün) / kronik (28 gün) iş yükü oranı. <b style={{ color: "var(--low)" }}>0.8–1.3</b> tatlı nokta;
          <b style={{ color: "var(--high)" }}> 1.3 üstü</b> sakatlık riski belirgin artar. GPS iç-yükten (AU) hesaplanır.
        </div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/workload"
      title="Yük Takibi"
      sub="ACWR · GPS iş yükü"
      desc="Kadronun akut:kronik iş yükü oranı ve GPS yük göstergeleri — aşırı yüklenme erken uyarısı."
      right={right}
    >
      <div className="kpis">
        <div className="kpi"><div className="kl">Ort. ACWR</div><div className="kn" style={{ color: acwrColor(AVG_ACWR) }}>{AVG_ACWR.toFixed(2)}</div><div className="kd">akut/kronik</div></div>
        <div className="kpi"><div className="kl">İdeal Bantta</div><div className="kn" style={{ color: "var(--low)" }}>{IDEAL}<span className="pct">/{LOADS.length}</span></div><div className="kd">0.8–1.3</div></div>
        <div className="kpi"><div className="kl">Riskli</div><div className="kn" style={{ color: "var(--high)" }}>{RISKY.length}</div><div className="kd">ACWR &gt; 1.3</div></div>
        <div className="kpi"><div className="kl">Haftalık GPS</div><div className="kn">{TOTAL_KM}<span className="pct"> km</span></div><div className="kd">toplam mesafe</div></div>
        <div className="kpi"><div className="kl">En Yüklü</div><div className="kn" style={{ fontSize: 18 }}>{TOP.name.split(" ")[0]}</div><div className="kd">{TOP.gpsKm} km maç</div></div>
      </div>

      <div className="st" style={{ marginTop: 0 }}><h2>Oyuncu Yük Tablosu</h2><span className="ep">son 7 gün · AU = arbitrary unit</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th><th>Oyuncu</th><th>Mevki</th>
            <th className="r">Akut</th><th className="r">Kronik</th>
            <th style={{ width: 170 }}>ACWR</th><th className="r">GPS</th><th className="r">YŞK</th>
          </tr></thead>
          <tbody>
            {LOADS.map((p) => {
              const c = acwrColor(p.acwr);
              return (
                <tr key={p.shirt}>
                  <td className="pnum c">{p.shirt}</td>
                  <td><span className="nm">{p.name}</span></td>
                  <td style={{ color: "var(--muted)" }}>{p.pos}</td>
                  <td className="r" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{p.acute}</td>
                  <td className="r" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)" }}>{p.chronic}</td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: c, minWidth: 34 }}>{p.acwr.toFixed(2)}</span>
                      <span style={{ flex: 1 }}><AcwrScale value={p.acwr} /></span>
                    </div>
                  </td>
                  <td className="r" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{p.gpsKm} km</td>
                  <td className="r" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)" }}>{p.hir} m</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 8 }}>
        YŞK = yüksek-şiddet koşu mesafesi (&gt;19.8 km/s). ACWR bandı: <span style={{ color: "var(--low)" }}>yeşil ideal</span> · <span style={{ color: "var(--high)" }}>turuncu yüksek</span> · <span style={{ color: "var(--crit)" }}>kırmızı tehlike</span>.
      </div>
    </ConsoleShell>
  );
}
