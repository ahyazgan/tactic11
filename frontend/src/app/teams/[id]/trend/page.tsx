"use client";

/**
 * Takım — Taktik Trend (detay). ConsoleShell çatısını kullanır.
 * Son N maçın taktik metrikleri (PPDA, Field Tilt, Takım xT, Possession,
 * Match Dominance) çizgi grafiği + yön/eğim + en büyük tek-maç sıçraması.
 *
 * DEMO_MODE açıkken canlı API'ye / role kapısına hiç dokunmaz; "Beşiktaş"
 * evreni için dolu, inandırıcı taktik trend gösterir (boş-state / spinner /
 * "veri yok" yok). [id] parametresi yalnızca başlıkta kullanılır; tek demo
 * evreni (Beşiktaş vs lig rakipleri) yeterlidir.
 * Backend: GET /admin/teams/{team_id}/tactical-trend?last_n={N}.
 */

import * as React from "react";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { DEMO_CLUB, DEMO_OPPONENT } from "@/lib/demo-data";
import { ConsoleShell } from "../../../_console/shell";
import { LoadingState, ErrorState, EmptyState } from "@/components/ui";

// --------------------------------------------------------------------------- //
// Canlı-API tipleri (DEMO kapalıyken korunur)
// --------------------------------------------------------------------------- //

interface TrendData {
  series: number[];
  mean: number;
  slope: number;
  direction: string;
  biggest_shift: number;
  biggest_shift_match_idx: number;
  biggest_shift_match_id: number | null;
}

interface MatchMeta {
  match_id: number;
  kickoff: string | null;
  opp_id: number;
  score: string;
}

interface TacticalTrendResponse {
  team_id: number;
  last_n: number;
  matches_analyzed: number;
  matches?: MatchMeta[];
  trends?: Record<string, TrendData>;
  note?: string;
}

// --------------------------------------------------------------------------- //
// Metrik kataloğu
// --------------------------------------------------------------------------- //

type MetricKey = "ppda" | "field_tilt" | "team_xt" | "possession_share" | "dominance_score";

interface MetricDef {
  key: MetricKey;
  title: string;
  short: string;
  unit: string;
  higherBetter: boolean;
  decimals: number;
  desc: string;
}

const METRICS: MetricDef[] = [
  { key: "ppda", title: "PPDA — Pres Yoğunluğu", short: "PPDA", unit: "", higherBetter: false, decimals: 1, desc: "Rakibe izin verilen pas / savunma aksiyonu. Düşük = daha agresif pres." },
  { key: "field_tilt", title: "Field Tilt — Saha Hâkimiyeti", short: "Field Tilt", unit: "%", higherBetter: true, decimals: 0, desc: "Son üçte birde topla geçirilen zaman payımız. Yüksek = oyun rakip yarı alanda." },
  { key: "team_xt", title: "Takım xT — Tehdit Üretimi", short: "Takım xT", unit: "", higherBetter: true, decimals: 2, desc: "Pas/taşıma zincirinden üretilen beklenen tehdit (expected threat)." },
  { key: "possession_share", title: "Topla Oynama %", short: "Possession", unit: "%", higherBetter: true, decimals: 0, desc: "Maç boyunca topa sahip olma yüzdesi." },
  { key: "dominance_score", title: "Maç Hâkimiyeti", short: "Dominance", unit: "", higherBetter: true, decimals: 1, desc: "xT, field tilt ve şut kalitesini birleştiren 0–100 bileşik hâkimiyet skoru." },
];

// --------------------------------------------------------------------------- //
// DEMO VERİSİ — "Beşiktaş" son 10 maç taktik dökümü (inline, paylaşılan dosya değil).
// Kronolojik (eski → yeni); en yenisi maç günü Beşiktaş vs Antalyaspor.
// --------------------------------------------------------------------------- //

interface DemoTrendMatch {
  match_id: number;
  date: string;
  opp: string;
  ha: "İ" | "D";        // İç saha / Deplasman
  res: "G" | "B" | "M"; // Galibiyet / Berabere / Mağlubiyet
  score: string;        // "2-0"
  ppda: number;
  field_tilt: number;
  team_xt: number;
  possession_share: number;
  dominance_score: number;
}

// 10 maç, eskiden yeniye. Eğilim: sezon ortasında pres çözüldü (PPDA yükseldi),
// son 4 maçta toparlanma var (PPDA düşüyor, xT/dominance artıyor).
const DEMO_TREND_MATCHES: DemoTrendMatch[] = [
  { match_id: 4101, date: "03-23", opp: "Çaykur Rizespor", ha: "D", res: "M", score: "0-1", ppda: 9.8,  field_tilt: 47, team_xt: 1.04, possession_share: 49, dominance_score: 44 },
  { match_id: 4108, date: "03-30", opp: "Galatasaray",    ha: "İ", res: "G", score: "3-0", ppda: 8.6,  field_tilt: 61, team_xt: 1.71, possession_share: 58, dominance_score: 67 },
  { match_id: 4115, date: "04-06", opp: "Samsunspor",     ha: "D", res: "B", score: "2-2", ppda: 11.2, field_tilt: 52, team_xt: 1.28, possession_share: 51, dominance_score: 53 },
  { match_id: 4122, date: "04-13", opp: "Alanyaspor",     ha: "İ", res: "G", score: "2-0", ppda: 10.4, field_tilt: 56, team_xt: 1.49, possession_share: 55, dominance_score: 59 },
  { match_id: 4129, date: "04-20", opp: "Eyüpspor",       ha: "D", res: "M", score: "1-3", ppda: 13.1, field_tilt: 44, team_xt: 1.12, possession_share: 47, dominance_score: 41 },
  { match_id: 4136, date: "04-27", opp: "Başakşehir",     ha: "İ", res: "G", score: "1-0", ppda: 11.6, field_tilt: 58, team_xt: 1.36, possession_share: 56, dominance_score: 58 },
  { match_id: 4143, date: "05-04", opp: "Sivasspor",      ha: "D", res: "B", score: "1-1", ppda: 12.4, field_tilt: 41, team_xt: 0.97, possession_share: 45, dominance_score: 47 },
  { match_id: 4150, date: "05-11", opp: "Kasımpaşa",      ha: "İ", res: "G", score: "2-1", ppda: 9.9,  field_tilt: 60, team_xt: 1.58, possession_share: 57, dominance_score: 63 },
  { match_id: 4157, date: "05-18", opp: "Trabzonspor",    ha: "D", res: "M", score: "0-2", ppda: 10.8, field_tilt: 49, team_xt: 1.21, possession_share: 50, dominance_score: 49 },
  { match_id: 4164, date: "06-01", opp: "Konyaspor",      ha: "D", res: "G", score: "2-0", ppda: 8.9,  field_tilt: 63, team_xt: 1.84, possession_share: 59, dominance_score: 68 },
];

/** En son (maç günü) Beşiktaş vs Antalyaspor — listeye ekleyerek tam N maç yapar. */
const DEMO_TODAY_MATCH: DemoTrendMatch = {
  match_id: 4171, date: "06-08", opp: DEMO_OPPONENT, ha: "İ", res: "B", score: "1-1",
  ppda: 9.4, field_tilt: 57, team_xt: 1.43, possession_share: 54, dominance_score: 58,
};

const RES_LABEL: Record<DemoTrendMatch["res"], { txt: string; cls: string }> = {
  G: { txt: "G", cls: "risk-low" },
  B: { txt: "B", cls: "risk-mid" },
  M: { txt: "M", cls: "risk-crit" },
};

/** Basit lineer regresyon eğimi (en küçük kareler). */
function slopeOf(values: number[]): number {
  const n = values.length;
  if (n < 2) return 0;
  const xs = values.map((_, i) => i);
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = values.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (values[i] - my);
    den += (xs[i] - mx) ** 2;
  }
  return den === 0 ? 0 : num / den;
}

/** En büyük ardışık tek-maç değişimi (|Δ|), yönü işaretiyle. */
function biggestShift(values: number[]): { delta: number; idx: number } {
  let best = 0;
  let idx = 0;
  for (let i = 1; i < values.length; i++) {
    const d = values[i] - values[i - 1];
    if (Math.abs(d) > Math.abs(best)) {
      best = d;
      idx = i;
    }
  }
  return { delta: best, idx };
}

/** Demo maç listesinden canlı-API şekline uyumlu trend yanıtı üret. */
function demoTrendResponse(lastN: number): { resp: TacticalTrendResponse; rows: DemoTrendMatch[] } {
  const all = [...DEMO_TREND_MATCHES, DEMO_TODAY_MATCH];
  const rows = all.slice(Math.max(0, all.length - lastN));
  const matches: MatchMeta[] = rows.map((m) => ({
    match_id: m.match_id,
    kickoff: `2026-${m.date}T20:00:00Z`,
    opp_id: m.match_id % 100,
    score: m.score,
  }));

  const trends: Record<string, TrendData> = {};
  for (const def of METRICS) {
    const series = rows.map((m) => m[def.key]);
    const mean = series.reduce((a, b) => a + b, 0) / series.length;
    const slope = slopeOf(series);
    const { delta, idx } = biggestShift(series);
    // Yön: eğim işareti + metrik "yüksek iyi mi" birleşik değerlendirme.
    const eff = def.higherBetter ? slope : -slope;
    const direction = Math.abs(slope) < 1e-6 ? "stable" : eff > 0 ? "improving" : "worsening";
    trends[def.key] = {
      series,
      mean,
      slope,
      direction,
      biggest_shift: delta,
      biggest_shift_match_idx: idx,
      biggest_shift_match_id: rows[idx]?.match_id ?? null,
    };
  }

  return {
    resp: {
      team_id: 0,
      last_n: lastN,
      matches_analyzed: rows.length,
      matches,
      trends,
    },
    rows,
  };
}

// --------------------------------------------------------------------------- //
// İnline SVG çizgi grafiği — tek metrik, son N maç, yön rengi + alan dolgusu.
// --------------------------------------------------------------------------- //

const DIR_COLOR: Record<string, string> = {
  improving: "var(--low)",
  worsening: "var(--crit)",
  stable: "var(--muted)",
};

function TrendChart({
  series,
  labels,
  direction,
  mean,
  decimals,
  highlightIdx,
}: {
  series: number[];
  labels: string[];
  direction: string;
  mean: number;
  decimals: number;
  highlightIdx: number;
}) {
  const W = 640;
  const H = 220;
  const PAD = { t: 18, r: 16, b: 28, l: 38 };
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const color = DIR_COLOR[direction] ?? "var(--muted)";

  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min || 1;
  const lo = min - span * 0.18;
  const hi = max + span * 0.18;
  const range = hi - lo || 1;

  const x = (i: number) => PAD.l + (series.length <= 1 ? iw / 2 : (i / (series.length - 1)) * iw);
  const y = (v: number) => PAD.t + ih - ((v - lo) / range) * ih;

  const line = series.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const areaPath = `${line} L${x(series.length - 1).toFixed(1)},${(PAD.t + ih).toFixed(1)} L${x(0).toFixed(1)},${(PAD.t + ih).toFixed(1)} Z`;

  const yTicks = [lo + range * 0.15, lo + range * 0.5, lo + range * 0.85];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }} role="img" aria-label="Taktik trend çizgisi">
      <defs>
        <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.18" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Izgara + y eksen etiketleri */}
      {yTicks.map((t, i) => (
        <g key={`y${i}`}>
          <line x1={PAD.l} y1={y(t)} x2={W - PAD.r} y2={y(t)} stroke="var(--line)" strokeWidth={1} />
          <text x={PAD.l - 7} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--dim)" style={{ fontSize: 10, fontFamily: "JetBrains Mono" }}>
            {t.toFixed(decimals)}
          </text>
        </g>
      ))}

      {/* Ortalama referans çizgisi */}
      <line x1={PAD.l} y1={y(mean)} x2={W - PAD.r} y2={y(mean)} stroke="var(--dim)" strokeWidth={1} strokeDasharray="4 4" opacity={0.7} />
      <text x={W - PAD.r} y={y(mean) - 4} textAnchor="end" fill="var(--dim)" style={{ fontSize: 9.5, fontFamily: "JetBrains Mono" }}>
        ort {mean.toFixed(decimals)}
      </text>

      {/* x eksen etiketleri (maç sırası) */}
      {labels.map((lab, i) => (
        <text key={`x${i}`} x={x(i)} y={H - 9} textAnchor="middle" fill="var(--dim)" style={{ fontSize: 9.5, fontFamily: "JetBrains Mono" }}>
          {lab}
        </text>
      ))}

      {/* Alan + çizgi */}
      <path d={areaPath} fill="url(#trendFill)" />
      <path d={line} fill="none" stroke={color} strokeWidth={2.4} strokeLinejoin="round" strokeLinecap="round" />

      {/* Noktalar; en büyük sıçrama vurgulu */}
      {series.map((v, i) => (
        <circle
          key={`d${i}`}
          cx={x(i)}
          cy={y(v)}
          r={i === highlightIdx ? 5 : 3}
          fill={i === highlightIdx ? color : "var(--surface)"}
          stroke={color}
          strokeWidth={i === highlightIdx ? 0 : 2}
        />
      ))}
    </svg>
  );
}

// --------------------------------------------------------------------------- //
// Yardımcılar
// --------------------------------------------------------------------------- //

const LAST_N_OPTS = [5, 10] as const;

function signed(v: number, d = 2): string {
  return (v >= 0 ? "+" : "") + v.toFixed(d);
}

function dirText(direction: string): string {
  return direction === "improving" ? "yükselişte" : direction === "worsening" ? "düşüşte" : "stabil";
}

function dirVar(direction: string): string {
  return DIR_COLOR[direction] ?? "var(--muted)";
}

const inputStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 10px",
  borderRadius: "7px",
  width: "120px",
  fontFamily: "inherit",
};

// --------------------------------------------------------------------------- //
// Sayfa
// --------------------------------------------------------------------------- //

export default function TacticalTrendPage() {
  const params = useParams<{ id: string }>();
  const teamId = params?.id ?? "demo";

  const [lastN, setLastN] = React.useState<number>(10);
  const [metricKey, setMetricKey] = React.useState<MetricKey>("dominance_score");

  // Demo modunda canlı API'ye dokunma; dolu mock trendi göster (spinner olmaz).
  const { data, error, isLoading } = useSWR<TacticalTrendResponse>(
    DEMO_MODE ? null : `/admin/teams/${teamId}/tactical-trend?last_n=${lastN}`,
    apiFetch,
    { shouldRetryOnError: false },
  );

  // Demo seti her render'da ucuz (≤10 satır) — memo gerekmez, xg sayfası deseni.
  const demo = DEMO_MODE ? demoTrendResponse(lastN) : null;
  const resp: TacticalTrendResponse | undefined = DEMO_MODE ? demo!.resp : data;
  const demoRows = demo?.rows ?? [];

  const matches = resp?.matches ?? [];
  const trends = resp?.trends ?? {};
  const activeDef = METRICS.find((m) => m.key === metricKey)!;
  const activeTrend = trends[metricKey];

  // Maç etiketleri (eski → yeni). Demo'da rakip kısaltması, canlıda M#.
  const xLabels = DEMO_MODE
    ? demoRows.map((m) => m.opp.split(" ")[0].slice(0, 6))
    : matches.map((m) => `#${m.match_id}`);

  // KPI: aktif metrik özeti + en iyi/en kötü yönlenen metrik.
  const improvingCount = METRICS.filter((m) => trends[m.key]?.direction === "improving").length;
  const worseningCount = METRICS.filter((m) => trends[m.key]?.direction === "worsening").length;
  const formW = demoRows.filter((m) => m.res === "G").length;
  const formD = demoRows.filter((m) => m.res === "B").length;
  const formL = demoRows.filter((m) => m.res === "M").length;

  // Sağ kolon — tüm metriklerin yönü + en büyük tek-maç sıçramaları.
  const right = (
    <>
      <div className="rc">
        <h3>Metrik Yönleri <span className="tiny">son {resp?.matches_analyzed ?? 0} maç</span></h3>
        {METRICS.map((m) => {
          const t = trends[m.key];
          if (!t) return null;
          const v = dirVar(t.direction);
          return (
            <button
              key={m.key}
              onClick={() => setMetricKey(m.key)}
              className="alrt"
              style={{
                width: "100%", background: "none", border: 0, textAlign: "left",
                cursor: "pointer", font: "inherit", padding: "8px 0",
                opacity: m.key === metricKey ? 1 : 0.82,
              }}
            >
              <span className="ai" style={{ background: v }} />
              <div className="am">
                <b style={{ color: m.key === metricKey ? "var(--accent)" : "var(--ink)" }}>{m.short}</b> · {dirText(t.direction)}
                <span className="tm">ort {t.mean.toFixed(m.decimals)}{m.unit} · eğim {signed(t.slope, 3)}</span>
              </div>
            </button>
          );
        })}
      </div>

      <div className="rc">
        <h3>En Büyük Sıçrama <span className="tiny">tek maç</span></h3>
        {METRICS.map((m) => {
          const t = trends[m.key];
          if (!t || t.biggest_shift_match_id === null) return null;
          const tgt = DEMO_MODE ? demoRows[t.biggest_shift_match_idx] : undefined;
          const good = (m.higherBetter ? t.biggest_shift : -t.biggest_shift) > 0;
          return (
            <div className="stat" key={m.key}>
              <span style={{ color: "var(--muted)" }}>
                {m.short}
                {tgt && <span style={{ color: "var(--dim)", marginLeft: 6, fontSize: 11 }}>vs {tgt.opp.split(" ")[0]}</span>}
              </span>
              <span className="sv" style={{ color: good ? "var(--low)" : "var(--crit)" }}>
                {signed(t.biggest_shift, m.decimals)}{m.unit}
              </span>
            </div>
          );
        })}
      </div>

      <div className="rc">
        <h3>{activeDef.short} Nedir?</h3>
        <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
          {activeDef.desc}
          <div style={{ marginTop: 8, color: "var(--dim)" }}>
            {activeDef.higherBetter ? "Yüksek = iyi." : "Düşük = iyi."}
          </div>
        </div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/teams"
      title="Taktik Trend"
      sub={DEMO_MODE ? DEMO_CLUB : `Takım #${teamId}`}
      desc="Son maçların taktik kimliği — pres yoğunluğu, saha hâkimiyeti ve tehdit üretimi maç maç nasıl değişti."
      right={right}
    >
      {/* DEMO kapalı: yükleme / hata / boş durumları */}
      {!DEMO_MODE && isLoading && <LoadingState label="Trend hesaplanıyor…" />}
      {!DEMO_MODE && error && <ErrorState title="Trend verisi alınamadı ya da yetki yok." />}
      {!DEMO_MODE && resp && resp.matches_analyzed === 0 && (
        <EmptyState title={resp.note || "Yeterli maç verisi yok."} />
      )}

      {resp && resp.matches_analyzed > 0 && (
        <>
          {/* Başlık + kontroller */}
          <div className="st" style={{ marginTop: 0 }}>
            <h2>{DEMO_MODE ? `${DEMO_CLUB} — Süper Lig` : `Takım #${teamId}`}</h2>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11.5, color: "var(--dim)" }}>maç sayısı</span>
              <div className="seg">
                {LAST_N_OPTS.map((n) => (
                  <button key={n} className={lastN === n ? "on" : ""} onClick={() => setLastN(n)}>{n}</button>
                ))}
              </div>
            </div>
          </div>

          {/* KPI şeridi */}
          <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
            <div className="kpi">
              <div className="kl">Analiz Edilen</div>
              <div className="kn">{resp.matches_analyzed}</div>
              <div className="kd">maç · kronolojik</div>
            </div>
            <div className="kpi">
              <div className="kl">İyileşen Metrik</div>
              <div className="kn" style={{ color: "var(--low)" }}>{improvingCount}</div>
              <div className="kd">/ {METRICS.length} metrik</div>
            </div>
            <div className="kpi">
              <div className="kl">Kötüleşen Metrik</div>
              <div className="kn" style={{ color: worseningCount ? "var(--crit)" : "var(--low)" }}>{worseningCount}</div>
              <div className="kd">/ {METRICS.length} metrik</div>
            </div>
            <div className="kpi">
              <div className="kl">{activeDef.short} Ort.</div>
              <div className="kn">{activeTrend ? activeTrend.mean.toFixed(activeDef.decimals) : "—"}<span className="pct">{activeDef.unit}</span></div>
              <div className="kd" style={{ color: activeTrend ? dirVar(activeTrend.direction) : "var(--dim)" }}>
                {activeTrend ? dirText(activeTrend.direction) : "—"}
              </div>
            </div>
            <div className="kpi">
              <div className="kl">Form (Son {resp.matches_analyzed})</div>
              <div className="kn" style={{ fontSize: 20 }}>
                {DEMO_MODE ? `${formW}G ${formD}B ${formL}M` : "—"}
              </div>
              <div className="kd">galip / berabere / mağlup</div>
            </div>
          </div>

          {/* Aktif metrik seçimi (seg) */}
          <div className="st">
            <h2>Metrik Trendi</h2>
            <div className="seg">
              {METRICS.map((m) => (
                <button key={m.key} className={metricKey === m.key ? "on" : ""} onClick={() => setMetricKey(m.key)}>{m.short}</button>
              ))}
            </div>
          </div>

          {/* Aktif metrik grafiği */}
          {activeTrend && (
            <div className="rc" style={{ margin: 0, padding: "12px 14px 6px" }}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", margin: "2px 4px 8px", flexWrap: "wrap", gap: 8 }}>
                <div>
                  <span style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)" }}>{activeDef.title}</span>
                  <span style={{ fontSize: 11.5, color: "var(--dim)", marginLeft: 8 }}>
                    {activeDef.higherBetter ? "yüksek = iyi" : "düşük = iyi"}
                  </span>
                </div>
                <span className={`risk ${activeTrend.direction === "improving" ? "risk-low" : activeTrend.direction === "worsening" ? "risk-crit" : "risk-mid"}`}>
                  <span className="rd" style={{ background: dirVar(activeTrend.direction) }} />
                  {dirText(activeTrend.direction)} · eğim {signed(activeTrend.slope, 3)}
                </span>
              </div>
              <TrendChart
                series={activeTrend.series}
                labels={xLabels}
                direction={activeTrend.direction}
                mean={activeTrend.mean}
                decimals={activeDef.decimals}
                highlightIdx={activeTrend.biggest_shift_match_idx}
              />
              <p style={{ fontSize: "11.5px", color: "var(--muted)", margin: "6px 4px 8px", lineHeight: 1.5 }}>
                {DEMO_MODE ? (
                  <>
                    {activeDef.short} son {resp.matches_analyzed} maçta ortalama <b>{activeTrend.mean.toFixed(activeDef.decimals)}{activeDef.unit}</b>;
                    yön <b style={{ color: dirVar(activeTrend.direction) }}>{dirText(activeTrend.direction)}</b>.
                    En sert tek-maç değişimi <b>{signed(activeTrend.biggest_shift, activeDef.decimals)}{activeDef.unit}</b>
                    {demoRows[activeTrend.biggest_shift_match_idx] && ` (${demoRows[activeTrend.biggest_shift_match_idx].opp} — ${demoRows[activeTrend.biggest_shift_match_idx].score})`}.
                    Vurgulu nokta o maçı işaret ediyor.
                  </>
                ) : (
                  <>Ortalama {activeTrend.mean.toFixed(activeDef.decimals)}{activeDef.unit}, eğim {signed(activeTrend.slope, 3)}. Kesikli çizgi dönem ortalamasıdır.</>
                )}
              </p>
            </div>
          )}

          {/* Maç maç döküm tablosu */}
          <div className="st">
            <h2>Maç Maç Döküm</h2>
            <span className="ep">{DEMO_MODE ? `${matches.length} maç · son ${lastN}` : "GET /admin/teams/{id}/tactical-trend"}</span>
          </div>
          <div className="tbl">
            <table>
              <thead>
                <tr>
                  <th>Tarih</th>
                  <th>Rakip</th>
                  <th className="c">S</th>
                  <th className="c">Skor</th>
                  <th className="c">PPDA</th>
                  <th className="c">Field Tilt</th>
                  <th className="c">xT</th>
                  <th className="c">Poss%</th>
                  <th className="r">Hâkimiyet</th>
                </tr>
              </thead>
              <tbody>
                {DEMO_MODE
                  ? demoRows.map((m, i) => {
                      const rl = RES_LABEL[m.res];
                      const isShift = activeTrend?.biggest_shift_match_idx === i;
                      return (
                        <tr key={m.match_id} style={isShift ? { background: "var(--accent-lt)" } : undefined}>
                          <td style={{ color: "var(--dim)", fontFamily: "JetBrains Mono", fontSize: "11px" }}>{m.date}</td>
                          <td>
                            <span className="nm">{m.opp}</span>{" "}
                            <span className="nat">{m.ha === "İ" ? "iç saha" : "deplasman"}</span>
                          </td>
                          <td className="c"><span className={`risk ${rl.cls}`}>{rl.txt}</span></td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 600 }}>{m.score}</td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{m.ppda.toFixed(1)}</td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{m.field_tilt}%</td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{m.team_xt.toFixed(2)}</td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{m.possession_share}%</td>
                          <td className="r">{m.dominance_score.toFixed(0)}</td>
                        </tr>
                      );
                    })
                  : matches.map((m) => (
                      <tr key={m.match_id}>
                        <td style={{ color: "var(--dim)", fontFamily: "JetBrains Mono", fontSize: "11px" }}>
                          {m.kickoff ? m.kickoff.slice(5, 10) : "—"}
                        </td>
                        <td><span className="nm">#{m.match_id}</span> <span className="nat">vs #{m.opp_id}</span></td>
                        <td className="c">—</td>
                        <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 600 }}>{m.score}</td>
                        <td className="c">{trends.ppda?.series[matches.indexOf(m)]?.toFixed(1) ?? "—"}</td>
                        <td className="c">{trends.field_tilt?.series[matches.indexOf(m)]?.toFixed(0) ?? "—"}</td>
                        <td className="c">{trends.team_xt?.series[matches.indexOf(m)]?.toFixed(2) ?? "—"}</td>
                        <td className="c">{trends.possession_share?.series[matches.indexOf(m)]?.toFixed(0) ?? "—"}</td>
                        <td className="r">{trends.dominance_score?.series[matches.indexOf(m)]?.toFixed(0) ?? "—"}</td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>

          {/* Taktik yorum */}
          <div className="st"><h2>Taktik Okuma</h2><span className="ep">{resp.matches_analyzed} maç</span></div>
          <div className="rc" style={{ margin: 0 }}>
            <p style={{ fontSize: "12px", color: "var(--muted)", margin: 0, lineHeight: 1.6 }}>
              {DEMO_MODE ? (
                <>
                  {DEMO_CLUB} son {resp.matches_analyzed} maçta <b>{improvingCount}</b> metrikte yükseliş, <b>{worseningCount}</b> metrikte düşüş gösterdi.
                  Sezon ortasındaki tempo düşüşünün (PPDA {trends.ppda?.mean.toFixed(1)} bandına çıkmıştı) ardından son dört maçta pres
                  yeniden agresifleşti ve maç hâkimiyeti <b style={{ color: dirVar(trends.dominance_score?.direction ?? "stable") }}>{dirText(trends.dominance_score?.direction ?? "stable")}</b>.
                  Bugünkü {DEMO_OPPONENT} maçında saha hâkimiyeti %{DEMO_TODAY_MATCH.field_tilt} ve xT {DEMO_TODAY_MATCH.team_xt.toFixed(2)} ile
                  takım kimliğine uygun başladı; skor 1–1 olsa da üretim trendi olumlu yönde.
                </>
              ) : (
                <>
                  Son {resp.matches_analyzed} maçta {improvingCount} metrik iyileşti, {worseningCount} metrik kötüleşti.
                  Her grafikteki kesikli çizgi dönem ortalamasını, vurgulu nokta ise en büyük tek-maç sıçramasını gösterir.
                </>
              )}
            </p>
          </div>

          {/* DEMO kapalı + canlı arama: takım id girişi (yalnızca info) */}
          {!DEMO_MODE && (
            <div className="st" style={{ marginBottom: 0 }}>
              <span style={{ fontSize: 11.5, color: "var(--dim)" }}>
                Aktif takım: <span style={{ fontFamily: "JetBrains Mono" }}>#{teamId}</span> · son {lastN} maç
              </span>
              <span style={{ ...inputStyle, width: "auto", color: "var(--dim)" }}>read-only</span>
            </div>
          )}
        </>
      )}
    </ConsoleShell>
  );
}
