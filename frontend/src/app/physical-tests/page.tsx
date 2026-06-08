"use client";

/**
 * Fiziksel Durum — açık tema (ConsoleShell) genel görünüm panosu.
 *
 * HRV + sprint + CMJ + ACWR yük göstergelerini kadro ısı-haritası olarak
 * birleştirir; takım HRV trendi + hazırlık dağılımı + kritik uyarılar.
 * Detaylı veri girişi / batarya: /physical-tests/entry (koyu panel).
 * Saha tableti: /test-session. DEMO_MODE'da demoSquad'dan deterministik üretim.
 */

import * as React from "react";
import Link from "next/link";
import { demoSquad } from "@/lib/demo-data";
import { ConsoleShell } from "../_console/shell";
import { RiskDonut, LegendRow } from "../_console/viz";

type Band = "Hazır" | "İzlenmeli" | "Riskli";
const BAND_META: Record<Band, { v: string; bg: string }> = {
  "Hazır": { v: "var(--low)", bg: "var(--low-bg)" },
  "İzlenmeli": { v: "var(--mid)", bg: "var(--mid-bg)" },
  "Riskli": { v: "var(--crit)", bg: "var(--crit-bg)" },
};

interface Status {
  shirt: number; name: string; pos: string;
  hrv: number;       // ms (yüksek iyi)
  sprint: number;    // 10m sn (düşük iyi)
  cmj: number;       // cm (yüksek iyi)
  acwr: number;      // akut/kronik
  load: number;      // haftalık iç yük 0..100
  band: Band;
  readiness: number; // 0..100
}

const STATUS: Status[] = demoSquad.slice(0, 16).map((p, i) => {
  const wave = Math.sin((p.player_id + i) * 1.4) * 0.5 + 0.5; // 0..1
  const cond = p.condition;
  const acwr = Math.round((0.85 + (p.risk_score / 100) * 0.78 + wave * 0.1) * 100) / 100;
  const band: Band = p.risk_label === "Kritik" ? "Riskli"
    : p.risk_label === "Yüksek" ? "İzlenmeli"
    : p.risk_label === "Orta" ? (cond >= 82 ? "Hazır" : "İzlenmeli")
    : "Hazır";
  return {
    shirt: p.shirt, name: p.player_name, pos: p.pos_detail,
    hrv: Math.round(58 + (cond - 70) * 0.8 + wave * 10),
    sprint: Math.round((1.70 + ((100 - cond) / 100) * 0.26 + wave * 0.04) * 100) / 100,
    cmj: Math.round(31 + (cond / 100) * 18 + wave * 4),
    acwr,
    load: Math.round(54 + (cond / 100) * 34 + wave * 6),
    band,
    readiness: cond,
  };
});

// Metrik yönüne duyarlı hücre derecesi → renk.
type Tone = "good" | "mid" | "bad";
const TONE: Record<Tone, { v: string; bg: string }> = {
  good: { v: "var(--low)", bg: "var(--low-bg)" },
  mid: { v: "var(--mid)", bg: "var(--mid-bg)" },
  bad: { v: "var(--crit)", bg: "var(--crit-bg)" },
};
function rate(metric: "hrv" | "sprint" | "cmj" | "acwr" | "load", v: number): Tone {
  switch (metric) {
    case "hrv": return v >= 80 ? "good" : v >= 68 ? "mid" : "bad";
    case "sprint": return v <= 1.78 ? "good" : v <= 1.88 ? "mid" : "bad";
    case "cmj": return v >= 42 ? "good" : v >= 35 ? "mid" : "bad";
    case "acwr": return v >= 0.8 && v <= 1.3 ? "good" : v <= 1.5 ? "mid" : "bad";
    case "load": return v <= 75 ? "good" : v <= 85 ? "mid" : "bad";
  }
}

const READY = STATUS.filter((s) => s.band === "Hazır").length;
const WATCH = STATUS.filter((s) => s.band === "İzlenmeli").length;
const RISKY = STATUS.filter((s) => s.band === "Riskli").length;
const AVG_HRV = Math.round(STATUS.reduce((a, s) => a + s.hrv, 0) / STATUS.length);
const AVG_ACWR = Math.round((STATUS.reduce((a, s) => a + s.acwr, 0) / STATUS.length) * 100) / 100;
const FASTEST = STATUS.reduce((b, s) => (s.sprint < b.sprint ? s : b), STATUS[0]);

// Takım ortalama HRV trendi (14 gün) — maç sonrası dip + toparlanma.
const HRV_TREND = [82, 80, 79, 76, 71, 73, 78, 81, 80, 77, 72, 75, 79, AVG_HRV];

function HrvTrend({ data }: { data: number[] }) {
  const W = 560, H = 130, padX = 24, padY = 16;
  const n = data.length, iw = W - padX * 2, ih = H - padY * 2;
  const lo = Math.min(...data) - 4, hi = Math.max(...data) + 4;
  const x = (i: number) => padX + (iw * i) / (n - 1);
  const y = (v: number) => padY + ih - (ih * (v - lo)) / (hi - lo);
  const pts = data.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const area = `${padX},${padY + ih} ${pts} ${padX + iw},${padY + ih}`;
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }} preserveAspectRatio="none">
      {[lo, (lo + hi) / 2, hi].map((g, i) => (
        <line key={i} x1={padX} x2={padX + iw} y1={y(g)} y2={y(g)} stroke="var(--line)" strokeWidth={1} strokeDasharray={i === 0 ? "0" : "3 4"} />
      ))}
      <polygon points={area} fill="var(--accent)" opacity={0.08} />
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      {data.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={i === n - 1 ? 4 : 2.5} fill={i === n - 1 ? "var(--accent)" : "var(--accent)"} stroke="var(--white)" strokeWidth={1.5} />)}
    </svg>
  );
}

function Cell({ metric, value, unit }: { metric: "hrv" | "sprint" | "cmj" | "acwr" | "load"; value: number; unit?: string }) {
  const t = TONE[rate(metric, value)];
  return (
    <td className="c">
      <span style={{ display: "inline-block", minWidth: 52, padding: "3px 8px", borderRadius: 7, background: t.bg, color: t.v, fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 12 }}>
        {value}{unit ? ` ${unit}` : ""}
      </span>
    </td>
  );
}

export default function FizikselDurumPage() {
  const dist = [
    { label: "Hazır", v: "var(--low)", n: READY },
    { label: "İzlenmeli", v: "var(--mid)", n: WATCH },
    { label: "Riskli", v: "var(--crit)", n: RISKY },
  ];
  const flagged = STATUS.filter((s) => s.band !== "Hazır").sort((a, b) => a.readiness - b.readiness);

  const right = (
    <>
      <div className="rc">
        <h3>Hazırlık Dağılımı <span className="tiny">{STATUS.length} oyuncu</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut segments={dist.map((d) => ({ value: d.n, color: d.v }))} centerLabel={READY} centerSub="hazır" />
          <div style={{ flex: 1, minWidth: 0 }}>
            {dist.map((d) => <LegendRow key={d.label} color={d.v} label={d.label} value={d.n} />)}
          </div>
        </div>
      </div>
      <div className="rc">
        <h3>İzlenecekler <span className="tiny">{flagged.length}</span></h3>
        {flagged.map((s) => {
          const m = BAND_META[s.band];
          return (
            <div className="alrt" key={s.shirt}>
              <span className="ai" style={{ background: m.v }} />
              <div className="am"><b>{s.name}</b> ({s.shirt}) · {s.band.toLowerCase()}
                <span className="tm">HRV {s.hrv} · ACWR {s.acwr.toFixed(2)} · kondisyon {s.readiness}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="rc">
        <h3>Aksiyonlar</h3>
        <Link href="/physical-tests/entry" style={{ display: "block", textAlign: "center", padding: "9px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontWeight: 600, fontSize: 12.5, textDecoration: "none", marginBottom: 8 }}>
          <i className="ti ti-clipboard-data" style={{ marginRight: 6 }} />Detaylı giriş & batarya
        </Link>
        <Link href="/test-session" style={{ display: "block", textAlign: "center", padding: "9px", borderRadius: 9, border: 0, background: "var(--besiktas)", color: "#fff", fontWeight: 700, fontSize: 12.5, textDecoration: "none" }}>
          <i className="ti ti-run" style={{ marginRight: 6 }} />Saha testi başlat
        </Link>
        <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 10 }}>Son test oturumu: 2026-06-05</div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/physical-tests"
      title="Fiziksel Durum"
      sub="HRV · sprint · yük"
      desc="Kadronun HRV, sprint, sıçrama ve ACWR yük göstergeleri — tek bakışta hazırlık ve risk."
      navBadge={RISKY}
      right={right}
    >
      <div className="kpis">
        <div className="kpi"><div className="kl">Sahaya Hazır</div><div className="kn" style={{ color: "var(--low)" }}>{READY}<span className="pct">/{STATUS.length}</span></div><div className="kd">{WATCH} izlenmeli · {RISKY} riskli</div></div>
        <div className="kpi"><div className="kl">Ort. HRV</div><div className="kn" style={{ color: AVG_HRV >= 78 ? "var(--low)" : "var(--mid)" }}>{AVG_HRV}<span className="pct"> ms</span></div><div className="kd">kalp atış değişkenliği</div></div>
        <div className="kpi"><div className="kl">Ort. ACWR</div><div className="kn" style={{ color: AVG_ACWR > 1.3 ? "var(--high)" : "var(--low)" }}>{AVG_ACWR.toFixed(2)}</div><div className="kd">akut/kronik yük</div></div>
        <div className="kpi"><div className="kl">Kritik Risk</div><div className="kn" style={{ color: RISKY ? "var(--crit)" : "var(--low)" }}>{RISKY}</div><div className="kd">acil değerlendirme</div></div>
        <div className="kpi"><div className="kl">En Hızlı</div><div className="kn" style={{ fontSize: 18 }}>{FASTEST.name.split(" ")[0]}</div><div className="kd">10m {FASTEST.sprint.toFixed(2)}sn</div></div>
      </div>

      <div className="st" style={{ marginTop: 0 }}><h2>Takım HRV Trendi</h2><span className="ep">son 14 gün · maç sonrası dip</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }}>
        <HrvTrend data={HRV_TREND} />
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8 }}>
          Maç (5. gün) sonrası HRV düştü, toparlanma günleriyle yükseldi. Düşük HRV = yetersiz toparlanma / yüksek stres göstergesi.
        </div>
      </div>

      <div className="st"><h2>Kadro Isı Haritası</h2><span className="ep">yeşil iyi · sarı izle · kırmızı risk</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th><th>Oyuncu</th><th>Mevki</th>
            <th className="c">Hazırlık</th><th className="c">HRV</th><th className="c">Sprint 10m</th>
            <th className="c">CMJ</th><th className="c">ACWR</th><th className="c">Yük</th>
          </tr></thead>
          <tbody>
            {STATUS.map((s) => {
              const m = BAND_META[s.band];
              return (
                <tr key={s.shirt}>
                  <td className="pnum c">{s.shirt}</td>
                  <td><span className="nm">{s.name}</span></td>
                  <td style={{ color: "var(--muted)" }}>{s.pos}</td>
                  <td className="c">
                    <span className="risk" style={{ background: m.bg, color: m.v }}>
                      <span className="rd" style={{ background: m.v }} />{s.band}
                    </span>
                  </td>
                  <Cell metric="hrv" value={s.hrv} />
                  <Cell metric="sprint" value={s.sprint} />
                  <Cell metric="cmj" value={s.cmj} />
                  <Cell metric="acwr" value={s.acwr} />
                  <Cell metric="load" value={s.load} />
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 8 }}>
        HRV ms · Sprint 10m sn (düşük iyi) · CMJ cm · ACWR akut/kronik · Yük haftalık iç yük (0–100). Hücre rengi metriğin yönüne göre.
      </div>
    </ConsoleShell>
  );
}
