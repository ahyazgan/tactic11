"use client";

/**
 * Performans Testi — batarya & sezon performansı. ConsoleShell çatısında.
 *
 * DEMO_MODE: canlı API'ye hiç dokunmaz. Beşiktaş kadrosunun fiziksel-test
 * bataryası, sezon trendleri ve kadro karşılaştırması demo-data.ts'ten gösterilir
 * (boş protokol listesi / "veri yok" olmaz). Öne çıkan oyuncu = kritik riskli
 * Orkun Kökçü (#10); ölçümler demoHistoryFor + demoRiskFor'dan türetilir.
 *
 * DEMO kapalı: eski tablet veri-giriş ekranı (kalıcı kayıt + batarya + PDF).
 *   GET  /admin/performance/protocols
 *   POST /physical-tests/
 *   POST /admin/performance/battery
 *   POST /reports/performance/pdf
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch, getAccessToken } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoSquad, demoHistoryFor, demoRiskFor } from "@/lib/demo-data";
import { SourceMark } from "@/lib/data-source";
import { ConsoleShell } from "../_console/shell";
import { Gauge } from "../_console/viz";

interface Protocol {
  key: string;
  name: string;
  unit: string;
  higher_is_better: boolean;
  description: string;
}
interface TestScore {
  protocol_key: string;
  protocol_name: string;
  raw_value: number;
  unit: string;
  rating: string;
  squad_percentile: number | null;
  note: string;
}
interface BatteryReport {
  player_external_id: number;
  scores: TestScore[];
  weak_areas: string[];
  strong_areas: string[];
}
interface Row {
  id: number;
  protocol_key: string;
  raw_value: string;
}

const RATING_VAR: Record<string, string> = {
  elit: "var(--low)",
  iyi: "var(--low)",
  ortalama: "var(--mid)",
  zayıf: "var(--crit)",
};

const fieldStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "14px",
  padding: "0 10px",
  height: "42px",
  borderRadius: "7px",
  fontFamily: "inherit",
};
const labelStyle: React.CSSProperties = { display: "block", fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--muted)", marginBottom: 4 };

let _rowSeq = 1;

export default function PerformancePage() {
  // Demo modunda canlı API/giriş yok — dolu sezon-performansı panelini göster.
  if (DEMO_MODE) return <PerformanceDemoConsole />;
  return <PerformanceFormConsole />;
}

/* ═══════════════════════════════════════════════════════════════════════════
   DEMO — Sezon Performansı & Batarya (backend yok, Beşiktaş evreni)
═══════════════════════════════════════════════════════════════════════════ */

// Protokol kataloğu — demoHistoryFor'un ürettiği anahtarlarla birebir.
// better: "low" → düşük değer daha iyi (sprint), "high" → yüksek değer daha iyi.
// name: anlaşılır ad (futbol diliyle); short: teknik test adı; plain: tek cümle
// "bu test ne işe yarar" açıklaması (tabloda adın altında görünür).
interface ProtoMeta { key: string; name: string; short: string; unit: string; better: "low" | "high"; plain: string }
const DEMO_PROTOCOLS: ProtoMeta[] = [
  { key: "sprint_10m", name: "Çıkış Hızı", short: "10 m sprint", unit: "sn", better: "low",
    plain: "İlk adım patlayıcılığı — kısa mesafede topa rakipten önce ulaşma." },
  { key: "sprint_30m", name: "Düz Hız", short: "30 m sprint", unit: "sn", better: "low",
    plain: "Maksimum koşu hızı — kontratak ve geri koşularda fark yaratır." },
  { key: "yoyo_irl1", name: "Dayanıklılık", short: "Yo-Yo testi", unit: "seviye", better: "high",
    plain: "Tekrarlı yüksek tempo koşu kapasitesi — 90 dakika pres gücü." },
  { key: "cmj", name: "Sıçrama Gücü", short: "dikey sıçrama", unit: "cm", better: "high",
    plain: "Bacak gücü — hava toplarında ve ani yön değişimlerinde belirleyici." },
  { key: "vo2max", name: "Kondisyon Motoru", short: "VO2max", unit: "ml/kg/dk", better: "high",
    plain: "Aerobik kapasite — maç boyu tempoyu taşıyabilme." },
];

/** Bir oyuncunun bir protokoldeki son ölçüm + trend (5 ölçüm) zinciri. */
function latestSeries(playerId: number, protoKey: string): number[] {
  return demoHistoryFor(playerId)
    .filter((t) => t.protocol === protoKey)
    .map((t) => t.value);
}

/** Kadro genelinde bir protokol için tüm oyuncuların son değeri. */
function squadLatest(protoKey: string): number[] {
  return demoSquad.map((p) => {
    const s = latestSeries(p.player_id, protoKey);
    return s.length ? s[s.length - 1] : NaN;
  }).filter((v) => !Number.isNaN(v));
}

/** Yüzde sıralaması (0..100): better'a göre yön. */
function percentileOf(value: number, pool: number[], better: "low" | "high"): number {
  if (pool.length === 0) return 50;
  const betterCount = pool.filter((v) => (better === "low" ? v <= value : v >= value)).length;
  // value'dan "daha iyi ya da eşit" olanların oranı → yüksek = elit
  return Math.round((betterCount / pool.length) * 100);
}

function ratingFromPct(pct: number): { txt: string; cls: string } {
  if (pct >= 80) return { txt: "elit", cls: "risk-low" };
  if (pct >= 55) return { txt: "iyi", cls: "risk-low" };
  if (pct >= 30) return { txt: "ortalama", cls: "risk-mid" };
  return { txt: "zayıf", cls: "risk-crit" };
}

const RISK_CLS: Record<string, string> = {
  Kritik: "risk-crit",
  Yüksek: "risk-high",
  Orta: "risk-mid",
  Düşük: "risk-low",
};

/** Mini sparkline — bir protokolün 5 ölçümlük trendi. */
function Spark({ values, better, width = 88, height = 26 }: { values: number[]; better: "low" | "high"; width?: number; height?: number }) {
  if (values.length < 2) return <span style={{ color: "var(--dim)" }}>—</span>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 3;
  const stepX = (width - pad * 2) / (values.length - 1);
  const pts = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = pad + (height - pad * 2) * (1 - (v - min) / span);
    return [x, y] as const;
  });
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  // İyiye gidiş yönü: son − ilk; better'a göre renk.
  const delta = values[values.length - 1] - values[0];
  const improving = better === "low" ? delta < 0 : delta > 0;
  const col = Math.abs(delta) < span * 0.05 ? "var(--mid)" : improving ? "var(--low)" : "var(--crit)";
  const last = pts[pts.length - 1];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      <polyline points={pts.map((p) => `${p[0]},${p[1]}`).join(" ")} fill="none" stroke={col} strokeOpacity={0.18} strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" />
      <path d={d} fill="none" stroke={col} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r={2.4} fill={col} />
    </svg>
  );
}

function PerformanceDemoConsole() {
  // Öne çıkan oyuncu: kritik riskli 10 numara (id=8), demoSquad'da garanti var.
  const FEATURED_ID = 8;
  const [focusId, setFocusId] = React.useState<number>(FEATURED_ID);
  const focus = demoSquad.find((p) => p.player_id === focusId) ?? demoSquad[0];
  const risk = demoRiskFor(focus.player_id);

  // Sezon KPI'ları
  const totalTests = demoSquad.length * DEMO_PROTOCOLS.length * 5; // 24 × 5 protokol × 5 ölçüm
  const avgCond = Math.round(demoSquad.reduce((a, p) => a + p.condition, 0) / demoSquad.length);
  const criticalCount = demoSquad.filter((p) => p.risk_label === "Kritik").length;
  const monitored = demoSquad.filter((p) => p.risk_label === "Yüksek" || p.risk_label === "Orta").length;
  const elitCount = demoSquad.filter((p) => p.condition >= 88).length;

  // Öne çıkan oyuncu bataryası (5 protokol)
  const focusBattery: TestScore[] = DEMO_PROTOCOLS.map((pr) => {
    const series = latestSeries(focus.player_id, pr.key);
    const raw = series.length ? series[series.length - 1] : 0;
    const pct = percentileOf(raw, squadLatest(pr.key), pr.better);
    const r = ratingFromPct(pct);
    return {
      protocol_key: pr.key,
      protocol_name: pr.name,
      raw_value: raw,
      unit: pr.unit,
      rating: r.txt,
      squad_percentile: pct,
      note: "",
    };
  });

  // Kadro protokol kıyası: her protokol için en iyi & en zayıf oyuncu + kadro ort.
  const benchmarks = DEMO_PROTOCOLS.map((pr) => {
    const rows = demoSquad.map((p) => {
      const s = latestSeries(p.player_id, pr.key);
      return { p, v: s.length ? s[s.length - 1] : NaN };
    }).filter((r) => !Number.isNaN(r.v));
    const sorted = [...rows].sort((a, b) => (pr.better === "low" ? a.v - b.v : b.v - a.v));
    const avg = rows.reduce((a, r) => a + r.v, 0) / rows.length;
    return {
      meta: pr,
      best: sorted[0],
      worst: sorted[sorted.length - 1],
      avg,
    };
  });

  // En iyi atletik profil (kondisyon) — sağ kolon
  const topPerformers = [...demoSquad].sort((a, b) => b.condition - a.condition).slice(0, 5);

  // Odak oyuncu için trend tablosu satırları (protokol bazında spark + delta)
  const focusTrends = DEMO_PROTOCOLS.map((pr) => {
    const series = latestSeries(focus.player_id, pr.key);
    return { meta: pr, series };
  });

  const focusRiskCls = RISK_CLS[focus.risk_label] ?? "risk-mid";
  const gaugeColor = focus.condition >= 85 ? "var(--low)" : focus.condition >= 72 ? "var(--mid)" : "var(--crit)";

  const right = (
    <>
      <div className="rc">
        <h3>Odak Oyuncu <span className="tiny">#{focus.shirt}</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 10 }}>
          <Gauge value={focus.condition} color={gaugeColor} label="kondisyon" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)" }}>{focus.player_name}</div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 2 }}>{focus.pos_detail} · {focus.age} yaş</div>
            <div style={{ marginTop: 8 }}>
              <span className={`risk ${focusRiskCls}`}><span className="rd" style={{ background: "currentColor" }} />{focus.risk_label} risk · {focus.risk_score}/100</span>
            </div>
          </div>
        </div>
        <div style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
            <SourceMark id="claude" height={12} />
            <span style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: ".4px", color: "var(--dim)" }}>AI değerlendirme</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{risk.summary}</div>
        </div>
      </div>

      <div className="rc">
        <h3>Güçlü / Gelişim Alanları</h3>
        <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--low)", marginBottom: 4 }}>Güçlü</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
          {focusBattery.filter((s) => (s.squad_percentile ?? 0) >= 55).map((s) => (
            <span key={s.protocol_key} style={{ fontSize: 11, padding: "3px 9px", borderRadius: 20, background: "var(--low-bg)", color: "var(--low)", fontWeight: 600 }}>{s.protocol_name}</span>
          ))}
          {focusBattery.filter((s) => (s.squad_percentile ?? 0) >= 55).length === 0 && (
            <span style={{ fontSize: 12, color: "var(--dim)" }}>Belirgin güçlü alan yok.</span>
          )}
        </div>
        <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--crit)", marginBottom: 4 }}>Gelişim</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {focusBattery.filter((s) => (s.squad_percentile ?? 0) < 30).map((s) => (
            <span key={s.protocol_key} style={{ fontSize: 11, padding: "3px 9px", borderRadius: 20, background: "var(--crit-bg)", color: "var(--crit)", fontWeight: 600 }}>{s.protocol_name}</span>
          ))}
          {focusBattery.filter((s) => (s.squad_percentile ?? 0) < 30).length === 0 && (
            <span style={{ fontSize: 12, color: "var(--dim)" }}>Kritik gelişim alanı yok.</span>
          )}
        </div>
      </div>

      <div className="rc">
        <h3>Formda Olanlar <span className="tiny">kondisyon ilk 5</span></h3>
        {topPerformers.map((p) => (
          <div className="alrt" key={p.player_id}>
            <span className="ai" style={{ background: "var(--low)" }} />
            <div className="am"><b>{p.player_name}</b> · {p.pos_detail}
              <span className="tm">kondisyon {p.condition} · risk {p.risk_score}/100</span>
            </div>
          </div>
        ))}
      </div>

      <div className="rc">
        <Link href="/physical-tests" style={{ display: "inline-block", fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.5, padding: "8px 14px", borderRadius: 7, background: "var(--accent)", color: "#fff", fontWeight: 600, textDecoration: "none" }}>
          Yük riski paneli →
        </Link>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/performance"
      title="Performans"
      sub="Test karnesi & sezon gidişatı"
      desc="Kadronun saha/lab test karnesi: her oyuncunun takım içindeki yeri, son 5 testteki gidişatı ve seviyesi. Sağlık/performans verisi KVKK'da özel niteliklidir."
      source={["perf_lab", "claude"]}
      navBadge={criticalCount}
      right={right}
    >
      <div className="kpis">
        <div className="kpi"><div className="kl">Test Kaydı</div><div className="kn">{totalTests.toLocaleString("tr-TR")}</div><div className="kd">{DEMO_PROTOCOLS.length} test türü × son 5 ölçüm</div></div>
        <div className="kpi"><div className="kl">Ort. Kondisyon</div><div className="kn">{avgCond}<span className="pct">%</span></div><div className="kd">{demoSquad.length} oyuncu</div></div>
        <div className="kpi"><div className="kl">Zirve Formda</div><div className="kn" style={{ color: "var(--low)" }}>{elitCount}</div><div className="kd">kondisyon 88 ve üstü</div></div>
        <div className="kpi"><div className="kl">Takipte</div><div className="kn" style={{ color: "var(--mid)" }}>{monitored}</div><div className="kd">yükü artmış — izleniyor</div></div>
        <div className="kpi"><div className="kl">Kritik Risk</div><div className="kn" style={{ color: criticalCount ? "var(--crit)" : "var(--low)" }}>{criticalCount}</div><div className="kd">hemen dinlendirilmeli</div></div>
      </div>

      {/* ── Odak oyuncu test karnesi ── */}
      <div className="st">
        <h2>Test Karnesi — {focus.player_name}</h2>
        <div className="seg">
          {demoSquad.filter((p) => p.risk_label === "Kritik" || p.condition >= 90).slice(0, 4).map((p) => (
            <button key={p.player_id} className={p.player_id === focusId ? "on" : ""} onClick={() => setFocusId(p.player_id)}>
              {p.player_name.split(" ")[0]}
            </button>
          ))}
        </div>
      </div>
      {/* Nasıl okunur — tek satır lejant */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", margin: "0 0 10px", fontSize: 11.5, color: "var(--dim)" }}>
        <span><b style={{ color: "var(--muted)" }}>Kadro Sırası:</b> %82 = takım arkadaşlarının %82&apos;sinden daha iyi sonuç</span>
        <span><b style={{ color: "var(--muted)" }}>Gidişat:</b> <i style={{ display: "inline-block", width: 9, height: 9, borderRadius: 3, background: "var(--low)", verticalAlign: "middle" }} /> iyiye gidiyor · <i style={{ display: "inline-block", width: 9, height: 9, borderRadius: 3, background: "var(--crit)", verticalAlign: "middle" }} /> geriliyor</span>
        <span><b style={{ color: "var(--muted)" }}>Seviye:</b> elit %80+ · iyi %55+ · ortalama %30+ · zayıf altı</span>
      </div>
      <div className="tbl" style={{ marginBottom: 14 }}>
        <table>
          <thead><tr>
            <th>Test</th><th className="r">Son Sonuç</th><th className="c">Gidişat (son 5)</th><th className="c">Kadro Sırası</th><th className="c">Seviye</th>
          </tr></thead>
          <tbody>
            {focusBattery.map((s, i) => {
              const meta = DEMO_PROTOCOLS[i];
              const series = focusTrends[i].series;
              const r = ratingFromPct(s.squad_percentile ?? 0);
              return (
                <tr key={s.protocol_key}>
                  <td>
                    <span className="nm">{s.protocol_name}</span> <span className="nat">{meta.short} · {meta.better === "low" ? "düşük sonuç iyi" : "yüksek sonuç iyi"}</span>
                    <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 2, lineHeight: 1.4 }}>{meta.plain}</div>
                  </td>
                  <td className="r" style={{ color: "var(--muted)" }}>{s.raw_value} <span style={{ color: "var(--dim)", fontWeight: 400 }}>{s.unit}</span></td>
                  <td className="c"><div style={{ display: "inline-block" }}><Spark values={series} better={meta.better} /></div></td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }} title={`Takım arkadaşlarının %${s.squad_percentile}'inden daha iyi`}>%{s.squad_percentile}</td>
                  <td className="c"><span className={`risk ${r.cls}`}><span className="rd" style={{ background: "currentColor" }} />{r.txt}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {risk.flags.length > 0 && (
        <>
          <div className="st"><h2>Yük & Sakatlık Uyarıları</h2><span className="ep" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><SourceMark id="claude" height={12} /> risk motoru</span></div>
          <div className="rc" style={{ margin: "0 0 14px" }}>
            {risk.flags.map((f, i) => (
              <div className="alrt" key={i}>
                <span className="ai" style={{ background: "var(--crit)" }} />
                <div className="am"><b>{f.message}</b>
                  <span className="tm">{DEMO_PROTOCOLS.find((p) => p.key === f.protocol)?.name ?? f.protocol} · {f.value} {f.unit}</span>
                </div>
              </div>
            ))}
            {risk.recommendations.length > 0 && (
              <div style={{ marginTop: 12, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--muted)", marginBottom: 6 }}>Öneriler</div>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "var(--muted)", lineHeight: 1.7 }}>
                  {risk.recommendations.map((rec, i) => <li key={i}>{rec}</li>)}
                </ul>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Kadro karşılaştırması ── */}
      <div className="st"><h2>Kadro Karşılaştırması — hangi testte kim önde?</h2><span className="ep" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><SourceMark id="perf_lab" height={12} /> {demoSquad.length} oyuncu · son ölçüm</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th>Test</th><th className="c">Takım Ort.</th><th>Takımın En İyisi</th><th>En Geride Olan</th><th className="c">Makas</th>
          </tr></thead>
          <tbody>
            {benchmarks.map((b) => {
              const fmt = (v: number) => `${Math.round(v * 100) / 100} ${b.meta.unit}`;
              const range = Math.abs(b.best.v - b.worst.v);
              return (
                <tr key={b.meta.key}>
                  <td><span className="nm">{b.meta.name}</span> <span className="nat">{b.meta.short} · {b.meta.better === "low" ? "düşük sonuç iyi" : "yüksek sonuç iyi"}</span></td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{fmt(b.avg)}</td>
                  <td><span className="nm" style={{ color: "var(--low)" }}>{b.best.p.player_name}</span> <span className="nat">{fmt(b.best.v)}</span></td>
                  <td><span style={{ color: "var(--muted)" }}>{b.worst.p.player_name}</span> <span className="nat">{fmt(b.worst.v)}</span></td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)" }} title="Takımın en iyisi ile en gerisi arasındaki fark">±{Math.round(range * 100) / 100}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   CANLI — Tablet veri-giriş ekranı (DEMO_MODE kapalıyken)
═══════════════════════════════════════════════════════════════════════════ */

function PerformanceFormConsole() {
  const { data: lib } = useSWR<{ protocols: Protocol[] }>("/admin/performance/protocols", apiFetch, { shouldRetryOnError: false });
  const protocols = lib?.protocols ?? [];

  const [playerName, setPlayerName] = React.useState("");
  const [playerId, setPlayerId] = React.useState("");
  const [testDate, setTestDate] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [rows, setRows] = React.useState<Row[]>([{ id: _rowSeq++, protocol_key: "", raw_value: "" }]);
  const [report, setReport] = React.useState<BatteryReport | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [savedCount, setSavedCount] = React.useState<number | null>(null);

  function updateRow(id: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setRows((rs) => [...rs, { id: _rowSeq++, protocol_key: "", raw_value: "" }]);
  }
  function removeRow(id: number) {
    setRows((rs) => (rs.length > 1 ? rs.filter((r) => r.id !== id) : rs));
  }

  function validResults(): [string, number][] {
    return rows
      .filter((r) => r.protocol_key && r.raw_value.trim() !== "")
      .map((r) => [r.protocol_key, Number(r.raw_value)] as [string, number])
      .filter(([, v]) => !Number.isNaN(v));
  }

  async function persistResults(): Promise<number> {
    let ok = 0;
    for (const [protocol, value] of validResults()) {
      try {
        await apiFetch("/physical-tests/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            player_id: playerId || "0",
            player_name: playerName || `Oyuncu #${playerId || 0}`,
            test_date: testDate,
            protocol,
            value,
          }),
        });
        ok++;
      } catch {
        /* best-effort */
      }
    }
    return ok;
  }

  async function evaluate() {
    setError(null);
    setBusy(true);
    setSavedCount(null);
    try {
      const saved = await persistResults();
      setSavedCount(saved);
      const res = await apiFetch<BatteryReport>("/admin/performance/battery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_id: Number(playerId) || 0, results: validResults() }),
      });
      setReport(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Değerlendirme başarısız");
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf() {
    setError(null);
    setBusy(true);
    try {
      const token = getAccessToken();
      const res = await fetch("/api/reports/performance/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({
          player_name: playerName || `Oyuncu #${playerId || 0}`,
          player_id: Number(playerId) || 0,
          results: validResults(),
          test_date: testDate,
        }),
      });
      if (!res.ok) {
        if (res.status === 503) throw new Error("PDF üretici sunucuda devre dışı (reportlab yok)");
        throw new Error(`PDF üretilemedi (HTTP ${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `performans_oyuncu_${playerId || 0}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "PDF indirme başarısız");
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = validResults().length > 0 && !busy;
  const activeProtocol = (key: string) => protocols.find((p) => p.key === key);

  const right = (
    <div className="rc">
      <h3>Yeni Panel</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5, marginBottom: 12 }}>
        Kalıcı kayıt + yük riski + trend + risk halkası artık <b style={{ color: "var(--ink)" }}>Performans (Yük Riski)</b> panelinde.
      </div>
      <Link href="/physical-tests" style={{ display: "inline-block", fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.5, padding: "8px 14px", borderRadius: 7, background: "var(--besiktas)", color: "#fff", fontWeight: 600, textDecoration: "none" }}>
        Yeni panele git →
      </Link>
      {report && (report.strong_areas.length > 0 || report.weak_areas.length > 0) && (
        <div style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          {report.strong_areas.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--low)", marginBottom: 3 }}>Güçlü yönler</div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>{report.strong_areas.join(", ")}</div>
            </div>
          )}
          {report.weak_areas.length > 0 && (
            <div>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--crit)", marginBottom: 3 }}>Gelişim alanları</div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>{report.weak_areas.join(", ")}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <ConsoleShell
      active="/performance"
      title="Performans Testi"
      sub="Veri girişi & test karnesi"
      desc="Saha/laboratuvar veri girişi. Sağlık/performans verisi KVKK'da özel niteliklidir; erişim ve dışa aktarım denetim kaydına yazılır."
      source="perf_lab"
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}><h2>Oyuncu</h2></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          <label><span style={labelStyle}>Ad</span><input value={playerName} onChange={(e) => setPlayerName(e.target.value)} placeholder="Oyuncu adı" style={fieldStyle} /></label>
          <label><span style={labelStyle}>Oyuncu ID</span><input value={playerId} onChange={(e) => setPlayerId(e.target.value.replace(/[^0-9]/g, ""))} inputMode="numeric" placeholder="örn. 42" style={fieldStyle} /></label>
          <label><span style={labelStyle}>Test tarihi</span><input type="date" value={testDate} onChange={(e) => setTestDate(e.target.value)} style={fieldStyle} /></label>
        </div>
      </div>

      <div className="st"><h2>Test Sonuçları</h2><button type="button" onClick={addRow} style={{ fontSize: 11, textTransform: "uppercase", padding: "4px 10px", borderRadius: 6, border: "1px solid var(--line)", color: "var(--ink)", background: "var(--panel3)", cursor: "pointer" }}>+ Test ekle</button></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        {rows.map((row) => {
          const proto = activeProtocol(row.protocol_key);
          return (
            <div key={row.id} style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
                <label style={{ flex: 1 }}>
                  <span style={labelStyle}>Protokol</span>
                  <select value={row.protocol_key} onChange={(e) => updateRow(row.id, { protocol_key: e.target.value })} style={fieldStyle}>
                    <option value="">Test seç…</option>
                    {protocols.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
                  </select>
                </label>
                <label style={{ width: 120 }}>
                  <span style={labelStyle}>Değer {proto ? `(${proto.unit})` : ""}</span>
                  <input value={row.raw_value} onChange={(e) => updateRow(row.id, { raw_value: e.target.value.replace(/[^0-9.]/g, "") })} inputMode="decimal" placeholder="0" style={{ ...fieldStyle, textAlign: "right" }} />
                </label>
                <button type="button" onClick={() => removeRow(row.id)} disabled={rows.length <= 1} aria-label="Satırı sil" style={{ height: 42, width: 42, flexShrink: 0, borderRadius: 7, border: "1px solid var(--line)", color: "var(--dim)", background: "transparent", cursor: rows.length <= 1 ? "default" : "pointer", opacity: rows.length <= 1 ? 0.3 : 1 }}>×</button>
              </div>
              {proto && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4, lineHeight: 1.4 }}>{proto.description}</div>}
            </div>
          );
        })}

        {error && <div style={{ marginTop: 10, fontSize: 12, color: "var(--crit)" }}>{error}</div>}
        {savedCount !== null && savedCount > 0 && <div style={{ marginTop: 10, fontSize: 12, color: "var(--low)" }}>{savedCount} sonuç kaydedildi — geçmiş, trend ve risk panellerine işlendi.</div>}

        <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 8 }}>
          <button type="button" onClick={evaluate} disabled={!canSubmit} style={{ padding: "0 16px", height: 42, borderRadius: 7, background: "var(--besiktas)", color: "#fff", fontWeight: 600, fontSize: 13, border: 0, cursor: canSubmit ? "pointer" : "default", opacity: canSubmit ? 1 : 0.4, fontFamily: "inherit" }}>{busy ? "İşleniyor…" : "Kaydet & Değerlendir"}</button>
          <button type="button" onClick={downloadPdf} disabled={!canSubmit} style={{ padding: "0 16px", height: 42, borderRadius: 7, background: "transparent", color: "var(--ink)", fontSize: 13, border: "1px solid var(--line)", cursor: canSubmit ? "pointer" : "default", opacity: canSubmit ? 1 : 0.4, fontFamily: "inherit" }}>PDF Rapor indir</button>
        </div>
      </div>

      {report && (
        <>
          <div className="st"><h2>Değerlendirme</h2><span className="ep">POST /admin/performance/battery</span></div>
          <div className="tbl">
            <table>
              <thead><tr><th>Protokol</th><th className="r">Değer</th><th className="c">Kadro %</th><th className="c">Değerlendirme</th></tr></thead>
              <tbody>
                {report.scores.map((s) => {
                  const v = RATING_VAR[s.rating] ?? "var(--muted)";
                  return (
                    <tr key={s.protocol_key}>
                      <td><span className="nm">{s.protocol_name}</span></td>
                      <td className="r" style={{ color: "var(--muted)" }}>{s.raw_value} {s.unit}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{s.squad_percentile != null ? `%${s.squad_percentile}` : "—"}</td>
                      <td className="c"><span style={{ fontSize: 10, textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: `1px solid ${v}`, color: v }}>{s.rating}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
