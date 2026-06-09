"use client";

/**
 * Analiz — xG Performans. ConsoleShell çatısını kullanır.
 * Beklenen gol (xG) farkı + over/underperformance.
 *
 * DEMO_MODE açıkken canlı API'ye hiç dokunmaz; "FK Demo" evreni için dolu,
 * inandırıcı xG içeriği gösterir (boş-state / ID-prompt / spinner yok):
 * kümülatif xG eğrisi (SVG), maç-içi xG akışı + son maç tablosu.
 * Backend: GET /admin/teams/{team_id}/xg-difference?days={30..180}.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoLive, DEMO_CLUB, DEMO_OPPONENT, type LivePlayerImpact } from "@/lib/demo-data";
import { useSort, SortableTh } from "@/lib/sortable";
import { ConsoleShell } from "../_console/shell";

interface XgResp {
  team_id: number;
  days: number;
  matches_analyzed: number;
  xg_for: number;
  xg_against: number;
  xg_difference: number;
  goals_for: number;
  goals_against: number;
  actual_goal_difference: number;
  overperformance: number;
  note?: string;
}

const DAYS = [30, 90, 180];

function signed(v: number, d = 2): string {
  return (v >= 0 ? "+" : "") + v.toFixed(d);
}
function signColor(v: number): string {
  return v > 0.05 ? "var(--low)" : v < -0.05 ? "var(--crit)" : "var(--muted)";
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
// DEMO VERİSİ — "FK Demo" son 12 maç xG dökümü (inline, paylaşılan dosya değil).
// xG/skor tutarlı; overperformance = (att−yed) − (xG−xGA).
// --------------------------------------------------------------------------- //

interface XgMatch {
  date: string;
  opp: string;
  ha: "İ" | "D";        // İç saha / Deplasman
  res: "G" | "B" | "M"; // Galibiyet / Berabere / Mağlubiyet
  gf: number;
  ga: number;
  xgf: number;
  xga: number;
}

const DEMO_MATCHES: XgMatch[] = [
  { date: "06-08", opp: DEMO_OPPONENT,    ha: "İ", res: "B", gf: 1, ga: 1, xgf: 1.22, xga: 1.35 },
  { date: "06-01", opp: "Yıldız FK",      ha: "D", res: "G", gf: 2, ga: 0, xgf: 1.84, xga: 0.71 },
  { date: "05-25", opp: "Demir SK",       ha: "İ", res: "G", gf: 3, ga: 1, xgf: 2.41, xga: 1.02 },
  { date: "05-18", opp: "Kartal Spor",    ha: "D", res: "M", gf: 0, ga: 2, xgf: 1.06, xga: 1.58 },
  { date: "05-11", opp: "Liman FK",       ha: "İ", res: "G", gf: 2, ga: 1, xgf: 1.63, xga: 0.94 },
  { date: "05-04", opp: "Şahin SK",       ha: "D", res: "B", gf: 1, ga: 1, xgf: 0.88, xga: 1.41 },
  { date: "04-27", opp: "Bora United",    ha: "İ", res: "G", gf: 1, ga: 0, xgf: 1.71, xga: 0.62 },
  { date: "04-20", opp: "Toros FK",       ha: "D", res: "M", gf: 1, ga: 3, xgf: 1.49, xga: 2.05 },
  { date: "04-13", opp: "Yeşil Spor",     ha: "İ", res: "G", gf: 2, ga: 0, xgf: 1.92, xga: 0.78 },
  { date: "04-06", opp: "Karadeniz FK",   ha: "D", res: "B", gf: 2, ga: 2, xgf: 1.55, xga: 1.49 },
  { date: "03-30", opp: "Anadolu SK",     ha: "İ", res: "G", gf: 3, ga: 0, xgf: 2.18, xga: 0.55 },
  { date: "03-23", opp: "Fırtına FK",     ha: "D", res: "M", gf: 0, ga: 1, xgf: 1.12, xga: 1.27 },
];

const RES_LABEL: Record<XgMatch["res"], { txt: string; cls: string }> = {
  G: { txt: "G", cls: "risk-low" },
  B: { txt: "B", cls: "risk-mid" },
  M: { txt: "M", cls: "risk-crit" },
};

// --------------------------------------------------------------------------- //
// PRES & TEMPO (PPDA) — faz faz son maç. PPDA = savunma aksiyonu başına rakibe
// izin verilen pas; DÜŞÜK = daha agresif pres. İlk yarı yoğun, 75' sonrası
// pres çözülüyor (tempo düşüşü) — bu hatırlatma sentezini görünür kılar.
// --------------------------------------------------------------------------- //
interface PpdaPhase { phase: string; team: number; opp: number }
const DEMO_PPDA: PpdaPhase[] = [
  { phase: "0–15", team: 8.1, opp: 11.6 },
  { phase: "16–30", team: 8.9, opp: 10.9 },
  { phase: "31–45", team: 9.7, opp: 10.4 },
  { phase: "46–60", team: 10.3, opp: 9.7 },
  { phase: "61–75", team: 11.4, opp: 9.0 },
  { phase: "76–90", team: 13.8, opp: 8.6 },
];
const PPDA_SEASON_AVG = 11.0; // takım sezon ortalaması (referans çizgi)

// --------------------------------------------------------------------------- //
// ŞUT HARİTASI — son maç (FK Demo 1–1 Rakip SK) şut dökümü. Koordinatlar 0..100:
// x = hücum ekseni (100 = rakip kale çizgisi), y = genişlik (0 sol, 100 sağ).
// xG toplamları demoLive ile tutarlı: home 1.22, away 1.35.
// --------------------------------------------------------------------------- //
interface Shot { x: number; y: number; xg: number; goal: boolean; team: "home" | "away"; player: string; minute: number }
const DEMO_SHOTS: Shot[] = [
  // FK Demo (home) — toplam xG 1.22
  { x: 88, y: 42, xg: 0.31, goal: false, team: "home", player: "Milot Rashica", minute: 12 },
  { x: 92, y: 52, xg: 0.46, goal: true, team: "home", player: "Oh Hyeon-Gyu", minute: 23 },
  { x: 78, y: 30, xg: 0.08, goal: false, team: "home", player: "Salih Uçan", minute: 34 },
  { x: 84, y: 60, xg: 0.12, goal: false, team: "home", player: "Orkun Kökçü", minute: 41 },
  { x: 90, y: 48, xg: 0.19, goal: false, team: "home", player: "Jota Silva", minute: 55 },
  { x: 73, y: 38, xg: 0.06, goal: false, team: "home", player: "Oh Hyeon-Gyu", minute: 62 },
  // Rakip SK (away) — toplam xG 1.35
  { x: 86, y: 55, xg: 0.24, goal: false, team: "away", player: "Rakip #9", minute: 38 },
  { x: 94, y: 50, xg: 0.41, goal: true, team: "away", player: "Rakip #4", minute: 45 },
  { x: 80, y: 44, xg: 0.14, goal: false, team: "away", player: "Rakip #23", minute: 60 },
  { x: 88, y: 36, xg: 0.33, goal: false, team: "away", player: "Rakip #23", minute: 64 },
  { x: 76, y: 58, xg: 0.23, goal: false, team: "away", player: "Rakip #11", minute: 66 },
];

/** Son N maçtan demo xG özeti üret (canlı API şekliyle uyumlu). */
function demoXgFromMatches(days: number): XgResp {
  // Dönem → kabaca maç sayısı (90g ≈ tüm liste, 30g ≈ son 4, 180g ≈ liste).
  const n = days <= 30 ? 4 : days <= 90 ? 8 : DEMO_MATCHES.length;
  const m = DEMO_MATCHES.slice(0, n);
  const xgf = m.reduce((a, x) => a + x.xgf, 0);
  const xga = m.reduce((a, x) => a + x.xga, 0);
  const gf = m.reduce((a, x) => a + x.gf, 0);
  const ga = m.reduce((a, x) => a + x.ga, 0);
  const xgDiff = xgf - xga;
  const goalDiff = gf - ga;
  return {
    team_id: 0,
    days,
    matches_analyzed: m.length,
    xg_for: xgf,
    xg_against: xga,
    xg_difference: xgDiff,
    goals_for: gf,
    goals_against: ga,
    actual_goal_difference: goalDiff,
    overperformance: goalDiff - xgDiff,
  };
}

// --------------------------------------------------------------------------- //
// xG EĞRİSİ (inline SVG) — kümülatif xG, lehte vs aleyhte, dakika ekseni.
// --------------------------------------------------------------------------- //

function XgCurve({
  series,
  home,
  away,
}: {
  series: { minute: number; home: number; away: number }[];
  home: string;
  away: string;
}) {
  const W = 640;
  const H = 220;
  const PAD = { t: 16, r: 16, b: 26, l: 34 };
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const maxMin = series[series.length - 1].minute || 90;
  const maxXg = Math.max(...series.map((p) => Math.max(p.home, p.away)), 1) * 1.1;

  const x = (min: number) => PAD.l + (min / maxMin) * iw;
  const y = (xg: number) => PAD.t + ih - (xg / maxXg) * ih;

  const path = (key: "home" | "away") =>
    series.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.minute).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");

  const area = (key: "home" | "away") =>
    `${path(key)} L${x(maxMin).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;

  const yTicks = [0, 0.5, 1, 1.5].filter((t) => t <= maxXg);
  const xTicks = [0, 15, 30, 45, 60, maxMin].filter((t, i, a) => a.indexOf(t) === i && t <= maxMin);

  const last = series[series.length - 1];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }} role="img" aria-label="Kümülatif xG eğrisi">
      <defs>
        <linearGradient id="xgfFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.22" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="xgaFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--crit)" stopOpacity="0.16" />
          <stop offset="100%" stopColor="var(--crit)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Izgara + y eksen etiketleri */}
      {yTicks.map((t) => (
        <g key={`y${t}`}>
          <line x1={PAD.l} y1={y(t)} x2={W - PAD.r} y2={y(t)} stroke="var(--line)" strokeWidth={1} />
          <text x={PAD.l - 7} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--dim)" style={{ fontSize: 10, fontFamily: "JetBrains Mono" }}>
            {t.toFixed(1)}
          </text>
        </g>
      ))}
      {/* x eksen etiketleri */}
      {xTicks.map((t) => (
        <text key={`x${t}`} x={x(t)} y={H - 8} textAnchor="middle" fill="var(--dim)" style={{ fontSize: 10, fontFamily: "JetBrains Mono" }}>
          {t}&#39;
        </text>
      ))}

      {/* Alanlar */}
      <path d={area("away")} fill="url(#xgaFill)" />
      <path d={area("home")} fill="url(#xgfFill)" />

      {/* Çizgiler */}
      <path d={path("away")} fill="none" stroke="var(--crit)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <path d={path("home")} fill="none" stroke="var(--accent)" strokeWidth={2.4} strokeLinejoin="round" strokeLinecap="round" />

      {/* Son nokta işaretleri */}
      <circle cx={x(last.minute)} cy={y(last.away)} r={3.5} fill="var(--crit)" />
      <circle cx={x(last.minute)} cy={y(last.home)} r={3.8} fill="var(--accent)" />

      {/* Legend */}
      <g transform={`translate(${PAD.l + 4}, ${PAD.t})`}>
        <rect x={0} y={0} width={11} height={3} rx={1.5} fill="var(--accent)" />
        <text x={16} y={4} dominantBaseline="middle" fill="var(--muted)" style={{ fontSize: 10.5, fontWeight: 600 }}>{home} xG</text>
        <rect x={92} y={0} width={11} height={3} rx={1.5} fill="var(--crit)" />
        <text x={108} y={4} dominantBaseline="middle" fill="var(--muted)" style={{ fontSize: 10.5, fontWeight: 600 }}>{away} xG</text>
      </g>
    </svg>
  );
}

// --------------------------------------------------------------------------- //
// TrendChart — genel çok-serili çizgi grafiği (rolling xG + PPDA için ortak).
// --------------------------------------------------------------------------- //
function TrendChart({
  xLabels,
  series,
  height = 190,
  yFmt = (v: number) => v.toFixed(1),
  refLine,
}: {
  xLabels: string[];
  series: { name: string; color: string; values: number[] }[];
  height?: number;
  yFmt?: (v: number) => string;
  refLine?: { value: number; label: string };
}) {
  const W = 640;
  const H = height;
  const PAD = { t: 24, r: 16, b: 26, l: 38 };
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const n = xLabels.length;
  const vals = series.flatMap((s) => s.values).concat(refLine ? [refLine.value] : []);
  const hi = Math.max(...vals) * 1.1;
  const loRaw = Math.min(...vals, 0);
  const lo = loRaw < 0 ? loRaw * 1.1 : 0;
  const x = (i: number) => PAD.l + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = (v: number) => PAD.t + ih - ((v - lo) / (hi - lo || 1)) * ih;
  const path = (values: number[]) =>
    values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const yTicks = [lo, (lo + hi) / 2, hi];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }} role="img" aria-label="Trend grafiği">
      {yTicks.map((t, i) => (
        <g key={i}>
          <line x1={PAD.l} y1={y(t)} x2={W - PAD.r} y2={y(t)} stroke="var(--line)" strokeWidth={1} />
          <text x={PAD.l - 6} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--dim)" style={{ fontSize: 10, fontFamily: "JetBrains Mono" }}>{yFmt(t)}</text>
        </g>
      ))}
      {refLine && (
        <>
          <line x1={PAD.l} y1={y(refLine.value)} x2={W - PAD.r} y2={y(refLine.value)} stroke="var(--dim)" strokeWidth={1} strokeDasharray="4 4" />
          <text x={W - PAD.r} y={y(refLine.value) - 4} textAnchor="end" fill="var(--dim)" style={{ fontSize: 9.5 }}>{refLine.label}</text>
        </>
      )}
      {xLabels.map((lbl, i) => (
        <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fill="var(--dim)" style={{ fontSize: 9.5, fontFamily: "JetBrains Mono" }}>{lbl}</text>
      ))}
      {series.map((s) => (
        <g key={s.name}>
          <path d={path(s.values)} fill="none" stroke={s.color} strokeWidth={2.4} strokeLinejoin="round" strokeLinecap="round" />
          {s.values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={2.6} fill={s.color} />)}
        </g>
      ))}
      <g transform={`translate(${PAD.l + 2}, 13)`}>
        {series.map((s, i) => (
          <g key={s.name} transform={`translate(${i * 130}, 0)`}>
            <rect x={0} y={-3} width={11} height={3} rx={1.5} fill={s.color} />
            <text x={16} y={0} dominantBaseline="middle" fill="var(--muted)" style={{ fontSize: 10.5, fontWeight: 600 }}>{s.name}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}

// --------------------------------------------------------------------------- //
// VaepBoard — oyuncu katkı sıralaması (VAEP/90). Kısa süre oynayıp yüksek
// üreten impact-sub'ları öne çıkarır; kaleci hariç.
// --------------------------------------------------------------------------- //
type VaepSortKey = "shirt" | "minutes" | "vaepPer90" | "vaep";

function VaepBoard({ players }: { players: LivePlayerImpact[] }) {
  const { key, dir, onSort } = useSort<VaepSortKey>("vaepPer90");
  const outfield = players.filter((p) => p.pos !== "GK");
  const ranked = [...outfield].sort((a, b) => (dir === "desc" ? b[key] - a[key] : a[key] - b[key]));
  const max = Math.max(...outfield.map((p) => p.vaepPer90), 0.1);
  return (
    <div className="tbl">
      <table>
        <thead><tr>
          <SortableTh active={key === "shirt"} dir={dir} label="#" onClick={() => onSort("shirt")} />
          <th>Oyuncu</th>
          <SortableTh active={key === "minutes"} dir={dir} label="Dakika" align="c" onClick={() => onSort("minutes")} />
          <SortableTh active={key === "vaepPer90"} dir={dir} label="VAEP/90 (dakikaya normalize katkı)" onClick={() => onSort("vaepPer90")} />
          <SortableTh active={key === "vaep"} dir={dir} label="Toplam" align="r" onClick={() => onSort("vaep")} />
        </tr></thead>
        <tbody>
          {ranked.map((p) => {
            const isSub = p.subbedInMinute != null;
            return (
              <tr key={p.shirt}>
                <td className="pnum">{p.shirt}</td>
                <td>
                  <span className="nm">{p.name}</span> <span className="nat">{p.pos}</span>
                  {isSub && (
                    <span style={{ marginLeft: 8, fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.4, color: "var(--mid)", border: "1px solid var(--mid)", borderRadius: 4, padding: "0 5px", verticalAlign: "middle" }}>impact-sub</span>
                  )}
                </td>
                <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)" }}>{p.minutes}&#39;</td>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ flex: 1, minWidth: 60, height: 6, background: "var(--surface2)", borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${(p.vaepPer90 / max) * 100}%`, height: "100%", background: isSub ? "var(--mid)" : "var(--accent)", borderRadius: 3 }} />
                    </div>
                    <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, minWidth: 38, textAlign: "right" }}>{p.vaepPer90.toFixed(2)}</span>
                  </div>
                </td>
                <td className="r" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{p.vaep.toFixed(2)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// ShotMap — yatay saha; ev sahibi sağa, rakip sola hücum eder. Nokta büyüklüğü
// xG ile orantılı; gol = dolu yeşil (halkalı), kaçan = içi boş.
// --------------------------------------------------------------------------- //
function ShotMap({ shots }: { shots: Shot[] }) {
  const W = 640;
  const H = 300;
  const M = 12;
  const pw = W - M * 2;
  const ph = H - M * 2;
  // home sağa hücum: px = x; away sola hücum: px = 100 - x (aynalama)
  const px = (s: Shot) => M + ((s.team === "home" ? s.x : 100 - s.x) / 100) * pw;
  const py = (s: Shot) => M + (s.y / 100) * ph;
  const rad = (xg: number) => 5 + xg * 24;
  const cx = M + pw / 2;
  const boxW = pw * 0.16;
  const boxH = ph * 0.6;
  const sixW = pw * 0.06;
  const sixH = ph * 0.3;
  const homeColor = "var(--accent)";
  const awayColor = "var(--crit)";

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }} role="img" aria-label="Şut haritası">
      {/* Saha */}
      <rect x={M} y={M} width={pw} height={ph} fill="var(--low-bg)" opacity={0.18} stroke="var(--line2)" strokeWidth={1.5} rx={4} />
      <line x1={cx} y1={M} x2={cx} y2={M + ph} stroke="var(--line2)" strokeWidth={1.5} />
      <circle cx={cx} cy={M + ph / 2} r={ph * 0.13} fill="none" stroke="var(--line2)" strokeWidth={1.5} />
      <circle cx={cx} cy={M + ph / 2} r={2.5} fill="var(--line2)" />
      {/* Sol ceza sahası (away'in saldırdığı = home kalesi solda? Hayır: home sağa hücum, home kalesi solda) */}
      <rect x={M} y={M + (ph - boxH) / 2} width={boxW} height={boxH} fill="none" stroke="var(--line2)" strokeWidth={1.5} />
      <rect x={M} y={M + (ph - sixH) / 2} width={sixW} height={sixH} fill="none" stroke="var(--line2)" strokeWidth={1.5} />
      {/* Sağ ceza sahası (home'un saldırdığı = rakip kalesi sağda) */}
      <rect x={M + pw - boxW} y={M + (ph - boxH) / 2} width={boxW} height={boxH} fill="none" stroke="var(--line2)" strokeWidth={1.5} />
      <rect x={M + pw - sixW} y={M + (ph - sixH) / 2} width={sixW} height={sixH} fill="none" stroke="var(--line2)" strokeWidth={1.5} />

      {/* Yön etiketleri */}
      <text x={M + 8} y={M + 16} fill={awayColor} style={{ fontSize: 10.5, fontWeight: 700 }}>← {DEMO_OPPONENT}</text>
      <text x={M + pw - 8} y={M + 16} textAnchor="end" fill={homeColor} style={{ fontSize: 10.5, fontWeight: 700 }}>{DEMO_CLUB} →</text>

      {/* Şutlar */}
      {shots.map((s, i) => {
        const c = s.team === "home" ? homeColor : awayColor;
        return (
          <g key={i}>
            <circle cx={px(s)} cy={py(s)} r={rad(s.xg)} fill={s.goal ? c : "none"} fillOpacity={s.goal ? 0.85 : 1} stroke={c} strokeWidth={2} />
            {s.goal && <circle cx={px(s)} cy={py(s)} r={rad(s.xg) + 4} fill="none" stroke={c} strokeWidth={1} strokeDasharray="2 2" />}
            <title>{`${s.player} · ${s.minute}' · xG ${s.xg.toFixed(2)}${s.goal ? " · GOL" : ""}`}</title>
          </g>
        );
      })}
    </svg>
  );
}

// --------------------------------------------------------------------------- //
// LİG xG SIRALAMASI (demo) — takımlar xG farkına (xGF − xGA) göre. FK Demo işaretli.
// "Skor değil, üretilen şans" perspektifinden lig konumu.
// --------------------------------------------------------------------------- //
interface LeagueXgRow { team: string; xgf: number; xga: number; pts: number }
const DEMO_LEAGUE: LeagueXgRow[] = [
  { team: "Yıldız FK", xgf: 61.2, xga: 32.1, pts: 74 },
  { team: "Demir SK", xgf: 55.8, xga: 38.4, pts: 68 },
  { team: DEMO_CLUB, xgf: 52.3, xga: 41.0, pts: 63 },
  { team: "Kartal Spor", xgf: 48.1, xga: 44.7, pts: 58 },
  { team: "Liman FK", xgf: 44.9, xga: 46.2, pts: 52 },
  { team: "Toros FK", xgf: 41.0, xga: 49.8, pts: 47 },
  { team: "Şahin SK", xgf: 38.7, xga: 53.1, pts: 41 },
];

type LeagueSortKey = "xgf" | "xga" | "xgd" | "pts";

function LeagueXgTable() {
  const { key, dir, onSort } = useSort<LeagueSortKey>("xgd");
  const rowsRaw = DEMO_LEAGUE.map((r) => ({ ...r, xgd: Math.round((r.xgf - r.xga) * 10) / 10 }));
  const ranked = [...rowsRaw].sort((a, b) => (dir === "desc" ? b[key] - a[key] : a[key] - b[key]));
  const maxAbs = Math.max(...rowsRaw.map((r) => Math.abs(r.xgd)), 1);

  return (
    <div className="tbl">
      <table>
        <thead><tr>
          <th>#</th><th>Takım</th>
          <SortableTh active={key === "xgf"} dir={dir} label="xGF" align="c" onClick={() => onSort("xgf")} />
          <SortableTh active={key === "xga"} dir={dir} label="xGA" align="c" onClick={() => onSort("xga")} />
          <SortableTh active={key === "xgd"} dir={dir} label="xG Farkı (sezon)" onClick={() => onSort("xgd")} />
          <SortableTh active={key === "pts"} dir={dir} label="Puan" align="r" onClick={() => onSort("pts")} />
        </tr></thead>
        <tbody>
          {ranked.map((r, i) => {
            const mine = r.team === DEMO_CLUB;
            const pos = r.xgd >= 0;
            return (
              <tr key={r.team} style={mine ? { background: "var(--accent-lt)" } : undefined}>
                <td className="pnum">{i + 1}</td>
                <td><span className="nm" style={mine ? { color: "var(--accent)" } : undefined}>{r.team}</span>{mine && <span className="nat"> · biz</span>}</td>
                <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{r.xgf.toFixed(1)}</td>
                <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{r.xga.toFixed(1)}</td>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ flex: 1, minWidth: 70, height: 6, background: "var(--surface2)", borderRadius: 3, position: "relative", overflow: "hidden" }}>
                      <div style={{ position: "absolute", left: pos ? "50%" : `${50 - (Math.abs(r.xgd) / maxAbs) * 50}%`, width: `${(Math.abs(r.xgd) / maxAbs) * 50}%`, height: "100%", background: pos ? "var(--low)" : "var(--crit)", borderRadius: 3 }} />
                    </div>
                    <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, minWidth: 42, textAlign: "right", color: pos ? "var(--low)" : "var(--crit)" }}>{signed(r.xgd, 1)}</span>
                  </div>
                </td>
                <td className="r" style={{ fontFamily: "JetBrains Mono", fontWeight: 600 }}>{r.pts}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// xG farkına göre kaçıncı sıradayız (sezon).
function leagueXgRank(): number {
  const ranked = [...DEMO_LEAGUE].sort((a, b) => (b.xgf - b.xga) - (a.xgf - a.xga));
  return ranked.findIndex((r) => r.team === DEMO_CLUB) + 1;
}

// --------------------------------------------------------------------------- //
// xG HİSTOGRAMI — şutların xG kalitesine göre dağılımı (kova: 0.1'lik dilimler).
// --------------------------------------------------------------------------- //
function XgHistogram({ shots }: { shots: Shot[] }) {
  const buckets = [
    { lo: 0, hi: 0.1, label: "0–.1" },
    { lo: 0.1, hi: 0.2, label: ".1–.2" },
    { lo: 0.2, hi: 0.3, label: ".2–.3" },
    { lo: 0.3, hi: 1.01, label: ".3+" },
  ];
  const counts = buckets.map((b) => shots.filter((s) => s.xg >= b.lo && s.xg < b.hi).length);
  const max = Math.max(...counts, 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 90, padding: "4px 4px 0" }}>
      {buckets.map((b, i) => (
        <div key={b.label} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
          <span style={{ fontSize: 11, fontFamily: "JetBrains Mono", fontWeight: 700, color: "var(--ink)" }}>{counts[i]}</span>
          <div style={{ width: "100%", maxWidth: 48, height: `${(counts[i] / max) * 60}px`, minHeight: counts[i] ? 4 : 0, background: i >= 2 ? "var(--low)" : "var(--accent)", opacity: i >= 2 ? 1 : 0.55, borderRadius: "4px 4px 0 0" }} />
          <span style={{ fontSize: 10, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>{b.label}</span>
        </div>
      ))}
    </div>
  );
}

const segBtn = (active: boolean): React.CSSProperties => ({
  background: active ? "var(--white)" : "transparent", border: 0,
  color: active ? "var(--ink)" : "var(--muted)", fontSize: 12, fontWeight: active ? 600 : 500,
  padding: "5px 12px", borderRadius: 7, cursor: "pointer", fontFamily: "inherit",
  boxShadow: active ? "0 1px 3px rgba(0,0,0,.08)" : "none",
});


export default function XgConsolePage() {
  const [team, setTeam] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [days, setDays] = React.useState(90);

  // Demo modunda canlı API'ye dokunma; dolu mock xG'yi göster (boş-state olmaz).
  const { data, isLoading, error } = useSWR<XgResp>(
    DEMO_MODE || !team ? null : `/admin/teams/${team}/xg-difference?days=${days}`,
    apiFetch,
    { shouldRetryOnError: false },
  );

  const xg: XgResp | undefined = DEMO_MODE ? demoXgFromMatches(days) : data;
  const op = xg?.overperformance ?? 0;
  const opHint =
    op > 0.05 ? "Klinik bitiricilik / şans (xG üstü)" : op < -0.05 ? "İsraf / şanssızlık (xG altı)" : "Beklentiyle uyumlu";
  const has = !!xg && xg.matches_analyzed > 0;

  // Demo: gösterilecek maç listesi (dönem filtresine bağlı).
  const matchN = days <= 30 ? 4 : days <= 90 ? 8 : DEMO_MATCHES.length;
  const matches = DEMO_MODE ? DEMO_MATCHES.slice(0, matchN) : [];

  // Form trendi: maçları eskiden yeniye sırala, 3 maçlık hareketli xG ortalaması.
  const chrono = [...matches].reverse();
  const rollAvg = (key: "xgf" | "xga", i: number) => {
    const win = chrono.slice(Math.max(0, i - 2), i + 1);
    return Math.round((win.reduce((a, m) => a + m[key], 0) / win.length) * 100) / 100;
  };
  const rollLabels = chrono.map((m) => m.date);
  const rollXgf = chrono.map((_, i) => rollAvg("xgf", i));
  const rollXga = chrono.map((_, i) => rollAvg("xga", i));

  // Şut haritası filtreleri (takım + sadece goller).
  const [shotTeam, setShotTeam] = React.useState<"all" | "home" | "away">("all");
  const [goalsOnly, setGoalsOnly] = React.useState(false);
  const filteredShots = DEMO_SHOTS.filter(
    (s) => (shotTeam === "all" || s.team === shotTeam) && (!goalsOnly || s.goal),
  );

  // Maç-maç tablo sıralaması. Türev alanlar (sd/xgd/over) + tarih sayısallaştırma.
  const matchSort = useSort<"date" | "sd" | "xgf" | "xga" | "xgd" | "over">("date");
  const dnum = (d: string) => { const [mm, dd] = d.split("-").map(Number); return mm * 100 + dd; };
  const decorated = matches.map((m) => ({
    ...m, sd: m.gf - m.ga, xgd: Math.round((m.xgf - m.xga) * 100) / 100,
    over: Math.round(((m.gf - m.ga) - (m.xgf - m.xga)) * 100) / 100,
  }));
  const valOf = (m: (typeof decorated)[number], k: typeof matchSort.key) => (k === "date" ? dnum(m.date) : m[k]);
  const sortedMatches = [...decorated].sort((a, b) =>
    matchSort.dir === "desc" ? valOf(b, matchSort.key) - valOf(a, matchSort.key) : valOf(a, matchSort.key) - valOf(b, matchSort.key),
  );

  const right = (
    <>
      <div className="rc">
        <h3>Overperformance Nedir?</h3>
        <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
          Gerçek averaj − xG farkı.
          <div style={{ marginTop: 8 }}><span style={{ color: "var(--low)" }}>Pozitif</span> = xG üstünde skor (klinik/şanslı).</div>
          <div style={{ marginTop: 4 }}><span style={{ color: "var(--crit)" }}>Negatif</span> = xG altında (israf/şanssız).</div>
          <div style={{ marginTop: 8, color: "var(--dim)" }}>Sürdürülebilirlik için 0&#39;a yakınlık beklenir.</div>
        </div>
      </div>

      {has && (
        <div className="rc">
          <h3>Gol Üretimi <span className="tiny">{xg!.days}g</span></h3>
          <div className="stat"><span>Attığı</span><span className="sv">{xg!.goals_for}</span></div>
          <div className="stat"><span>Yediği</span><span className="sv">{xg!.goals_against}</span></div>
          <div className="stat"><span>xG (lehte)</span><span className="sv">{xg!.xg_for.toFixed(1)}</span></div>
          <div className="stat"><span>xG (aleyhte)</span><span className="sv">{xg!.xg_against.toFixed(1)}</span></div>
          <div className="stat"><span>Analiz edilen maç</span><span className="sv">{xg!.matches_analyzed}</span></div>
        </div>
      )}

      {DEMO_MODE && (
        <div className="rc">
          <h3>Form Dökümü <span className="tiny">son {matches.length} maç</span></h3>
          <div className="stat">
            <span>Galibiyet</span>
            <span className="sv" style={{ color: "var(--low)" }}>{matches.filter((m) => m.res === "G").length}</span>
          </div>
          <div className="stat">
            <span>Berabere</span>
            <span className="sv" style={{ color: "var(--mid)" }}>{matches.filter((m) => m.res === "B").length}</span>
          </div>
          <div className="stat">
            <span>Mağlubiyet</span>
            <span className="sv" style={{ color: "var(--crit)" }}>{matches.filter((m) => m.res === "M").length}</span>
          </div>
          <div className="stat">
            <span>Maç başı xG</span>
            <span className="sv">{(xg!.xg_for / xg!.matches_analyzed).toFixed(2)}</span>
          </div>
        </div>
      )}
    </>
  );

  return (
    <ConsoleShell
      active="/xg"
      title="Performans Analizi"
      sub="xG · oyuncu katkısı · pres"
      desc="Beklenen gol (xG), oyuncu katkısı (VAEP/90), pres yoğunluğu (PPDA) ve şut kalitesiyle takım ve oyuncu verimliliğini bir arada gösterir."
      right={right}
    >
      {/* Demo: takım seçimi yerine sabit kulüp + dönem kontrolü */}
      <div className="st" style={{ marginTop: 0 }}>
        <h2>{DEMO_MODE ? `${DEMO_CLUB} — Süper Lig` : "Takım Seç"}</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {!DEMO_MODE && (
            <form onSubmit={(e) => { e.preventDefault(); setTeam(search.trim()); }} style={{ display: "flex", gap: 6 }}>
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Takım ID" inputMode="numeric" style={inputStyle} />
              <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Getir</button>
            </form>
          )}
          <div className="seg">
            {DAYS.map((d) => (
              <button key={d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>{d}g</button>
            ))}
          </div>
          {DEMO_MODE && (
            <button type="button" onClick={() => window.print()} style={{ padding: "7px 13px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontWeight: 600, fontSize: 12.5, cursor: "pointer", fontFamily: "inherit" }}>
              <i className="ti ti-file-type-pdf" style={{ marginRight: 6 }} />PDF / paylaş
            </button>
          )}
        </div>
      </div>

      {!DEMO_MODE && !team && <div className="pgdesc">Analiz için bir takım ID gir (örn. 611) ve dönem seç.</div>}
      {!DEMO_MODE && team && isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {!DEMO_MODE && error && <div className="pgdesc">xG verisi üretilemedi ya da yetki yok.</div>}
      {!DEMO_MODE && data?.note && <div className="pgdesc">{data.note}</div>}

      {has && (
        <div id="xg-print">
          <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
            <div className="kpi"><div className="kl">xG (lehte)</div><div className="kn">{xg!.xg_for.toFixed(2)}</div><div className="kd">üretilen şans</div></div>
            <div className="kpi"><div className="kl">xGA (aleyhte)</div><div className="kn">{xg!.xg_against.toFixed(2)}</div><div className="kd">verilen şans</div></div>
            <div className="kpi"><div className="kl">xG Farkı</div><div className="kn" style={{ color: signColor(xg!.xg_difference) }}>{signed(xg!.xg_difference)}</div><div className="kd">lehte − aleyhte</div></div>
            <div className="kpi"><div className="kl">Gerçek Averaj</div><div className="kn" style={{ color: signColor(xg!.actual_goal_difference) }}>{signed(xg!.actual_goal_difference, 0)}</div><div className="kd">attığı − yediği</div></div>
            <div className="kpi"><div className="kl">Overperformance</div><div className="kn" style={{ color: signColor(op) }}>{signed(op)}</div><div className="kd">gerçek − xG</div></div>
          </div>

          {/* Lig xG konumu — sezon xG farkına göre sıralama */}
          {DEMO_MODE && (
            <>
              <div className="st"><h2>Lig xG Konumu <span style={{ fontWeight: 400, color: "var(--dim)", fontSize: 12 }}>· sezon</span></h2><span className="ep">xG farkına göre {leagueXgRank()}. sıra</span></div>
              <LeagueXgTable />
              <p style={{ fontSize: "11.5px", color: "var(--muted)", margin: "8px 4px 0", lineHeight: 1.5 }}>
                Puan sıralaması değil — <b>üretilen şans</b> (xGF − xGA) sıralaması. {DEMO_CLUB} xG farkında lig {leagueXgRank()}. sırada; bu, sürdürülebilir performans potansiyelini gösterir.
              </p>
            </>
          )}

          {/* Maç-içi kümülatif xG eğrisi (son maç: FK Demo vs Rakip SK) */}
          {DEMO_MODE && (
            <>
              <div className="st">
                <h2>Maç-İçi xG Akışı</h2>
                <span className="ep">{demoLive.home} {demoLive.score[0]}–{demoLive.score[1]} {demoLive.away} · {demoLive.minute}&#39;</span>
              </div>
              <div className="rc" style={{ margin: 0, padding: "12px 14px 4px" }}>
                <XgCurve series={demoLive.series} home={DEMO_CLUB} away={DEMO_OPPONENT} />
                <p style={{ fontSize: "11.5px", color: "var(--muted)", margin: "6px 4px 8px", lineHeight: 1.5 }}>
                  Kümülatif beklenen gol. İlk yarı {demoLive.home} üstün başladı; 25–35. dk arası {demoLive.away} eğriyi yakaladı.
                  Maç sonu xG <b style={{ color: "var(--accent)" }}>{demoLive.homeXg.toFixed(2)}</b> – <b style={{ color: "var(--crit)" }}>{demoLive.awayXg.toFixed(2)}</b>:
                  skor 1–1 olmasına rağmen üretilen şanslar denk, momentum son bölümde rakipte.
                </p>
              </div>
            </>
          )}

          {/* Form trendi — 3 maçlık hareketli xG ortalaması */}
          {DEMO_MODE && chrono.length >= 2 && (
            <>
              <div className="st"><h2>Form Trendi <span style={{ fontWeight: 400, color: "var(--dim)", fontSize: 12 }}>· hareketli xG (3 maç)</span></h2><span className="ep">{chrono.length} maç · {days}g</span></div>
              <div className="rc" style={{ margin: 0, padding: "12px 14px 4px" }}>
                <TrendChart
                  xLabels={rollLabels}
                  series={[
                    { name: "xG (lehte)", color: "var(--accent)", values: rollXgf },
                    { name: "xGA (aleyhte)", color: "var(--crit)", values: rollXga },
                  ]}
                />
                <p style={{ fontSize: "11.5px", color: "var(--muted)", margin: "6px 4px 8px", lineHeight: 1.5 }}>
                  Maç başına üretilen ve verilen beklenen golün 3 maçlık hareketli ortalaması.
                  İki çizgi arasındaki açıklık ne kadar büyükse hücum–savunma dengesi o kadar lehte.
                </p>
              </div>
            </>
          )}

          {/* Oyuncu katkı sıralaması — VAEP/90 (son maç) */}
          {DEMO_MODE && (
            <>
              <div className="st"><h2>Oyuncu Katkı Sıralaması <span style={{ fontWeight: 400, color: "var(--dim)", fontSize: 12 }}>· VAEP/90</span></h2><span className="ep">son maç · {demoLive.home} {demoLive.score[0]}–{demoLive.score[1]} {demoLive.away}</span></div>
              <VaepBoard players={demoLive.lineup} />
              <p style={{ fontSize: "11.5px", color: "var(--muted)", margin: "8px 4px 0", lineHeight: 1.5 }}>
                VAEP, her aksiyonun gol olasılığına net katkısını ölçer; <b>/90</b> dakikaya normalize eder.
                Bu sayede az süre oynayıp çok üreten <span style={{ color: "var(--mid)", fontWeight: 600 }}>impact-sub</span>&#39;lar (ör. {demoLive.lineup.find((p) => p.subbedInMinute != null)?.name}) öne çıkar.
              </p>
            </>
          )}

          {/* Pres & tempo — PPDA faz faz */}
          {DEMO_MODE && (
            <>
              <div className="st"><h2>Pres &amp; Tempo <span style={{ fontWeight: 400, color: "var(--dim)", fontSize: 12 }}>· PPDA (faz faz)</span></h2><span className="ep">düşük = daha agresif pres</span></div>
              <div className="rc" style={{ margin: 0, padding: "12px 14px 4px" }}>
                <TrendChart
                  height={180}
                  xLabels={DEMO_PPDA.map((p) => `${p.phase}'`)}
                  yFmt={(v) => v.toFixed(0)}
                  refLine={{ value: PPDA_SEASON_AVG, label: `sezon ort. ${PPDA_SEASON_AVG.toFixed(0)}` }}
                  series={[
                    { name: DEMO_CLUB, color: "var(--accent)", values: DEMO_PPDA.map((p) => p.team) },
                    { name: DEMO_OPPONENT, color: "var(--crit)", values: DEMO_PPDA.map((p) => p.opp) },
                  ]}
                />
                <p style={{ fontSize: "11.5px", color: "var(--muted)", margin: "6px 4px 8px", lineHeight: 1.5 }}>
                  PPDA = rakibin savunma aksiyonu başına yaptığı pas sayısı; <b>düşük değer daha yoğun pres</b> demektir.
                  {DEMO_CLUB} ilk yarı baskılı başladı (<b style={{ color: "var(--accent)" }}>{DEMO_PPDA[0].team.toFixed(1)}</b>) ama
                  76&#39; sonrası pres çözüldü (<b style={{ color: "var(--crit)" }}>{DEMO_PPDA[DEMO_PPDA.length - 1].team.toFixed(1)}</b>) —
                  geç dakika tempo düşüşü, taze kanat oyuncusunu gerektiriyor.
                </p>
              </div>
            </>
          )}

          {/* Şut haritası — son maç (filtrelenebilir + xG histogramı) */}
          {DEMO_MODE && (
            <>
              <div className="st">
                <h2>Şut Haritası <span style={{ fontWeight: 400, color: "var(--dim)", fontSize: 12 }}>· son maç</span></h2>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div className="seg">
                    <button style={segBtn(shotTeam === "all")} onClick={() => setShotTeam("all")}>İkisi</button>
                    <button style={segBtn(shotTeam === "home")} onClick={() => setShotTeam("home")}>{DEMO_CLUB}</button>
                    <button style={segBtn(shotTeam === "away")} onClick={() => setShotTeam("away")}>{DEMO_OPPONENT}</button>
                  </div>
                  <button type="button" onClick={() => setGoalsOnly((v) => !v)} style={{ padding: "6px 12px", borderRadius: 8, border: `1px solid ${goalsOnly ? "var(--low)" : "var(--line)"}`, background: goalsOnly ? "var(--low-bg)" : "var(--panel)", color: goalsOnly ? "var(--low)" : "var(--muted)", fontWeight: 600, fontSize: 12, cursor: "pointer", fontFamily: "inherit" }}>
                    <i className="ti ti-ball-football" style={{ marginRight: 5 }} />Sadece goller
                  </button>
                </div>
              </div>
              <div className="rc" style={{ margin: 0, padding: "12px 14px 4px" }}>
                <ShotMap shots={filteredShots} />
                <div style={{ display: "grid", gridTemplateColumns: "1fr 200px", gap: 14, alignItems: "center", borderTop: "1px solid var(--line)", marginTop: 6, paddingTop: 8 }}>
                  <p style={{ fontSize: "11.5px", color: "var(--muted)", margin: "0 0 8px", lineHeight: 1.5 }}>
                    Her şut, kaleye göre konumu ve gol olasılığı (xG) ile gösterilir.
                    {shotTeam === "all"
                      ? ` ${DEMO_CLUB} ${DEMO_SHOTS.filter((s) => s.team === "home").length} şutta ${demoLive.homeXg.toFixed(2)} xG; rakip ${DEMO_SHOTS.filter((s) => s.team === "away").length} şutta ${demoLive.awayXg.toFixed(2)} xG — daha az ama daha kaliteli pozisyon.`
                      : ` Gösterilen: ${filteredShots.length} şut · toplam ${filteredShots.reduce((a, s) => a + s.xg, 0).toFixed(2)} xG.`}
                  </p>
                  <div>
                    <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--dim)", marginBottom: 2, textAlign: "center" }}>xG kalite dağılımı</div>
                    <XgHistogram shots={filteredShots} />
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Son maçlar — xG dökümü tablosu */}
          {DEMO_MODE && (
            <>
              <div className="st"><h2>Maç Maç xG Dökümü</h2><span className="ep">{matches.length} maç · {days}g</span></div>
              <div className="tbl">
                <table>
                  <thead><tr>
                    <SortableTh active={matchSort.key === "date"} dir={matchSort.dir} label="Tarih" onClick={() => matchSort.onSort("date")} />
                    <th>Rakip</th><th className="c">S</th>
                    <SortableTh active={matchSort.key === "sd"} dir={matchSort.dir} label="Skor" align="c" onClick={() => matchSort.onSort("sd")} />
                    <SortableTh active={matchSort.key === "xgf"} dir={matchSort.dir} label="xG" align="c" onClick={() => matchSort.onSort("xgf")} />
                    <SortableTh active={matchSort.key === "xga"} dir={matchSort.dir} label="xGA" align="c" onClick={() => matchSort.onSort("xga")} />
                    <SortableTh active={matchSort.key === "xgd"} dir={matchSort.dir} label="xG Farkı" align="c" onClick={() => matchSort.onSort("xgd")} />
                    <SortableTh active={matchSort.key === "over"} dir={matchSort.dir} label="Over" align="r" onClick={() => matchSort.onSort("over")} />
                  </tr></thead>
                  <tbody>
                    {sortedMatches.map((m, i) => {
                      const rl = RES_LABEL[m.res];
                      return (
                        <tr key={i}>
                          <td style={{ color: "var(--dim)", fontFamily: "JetBrains Mono", fontSize: "11px" }}>{m.date}</td>
                          <td>
                            <span className="nm">{m.opp}</span>{" "}
                            <span className="nat">{m.ha === "İ" ? "iç saha" : "deplasman"}</span>
                          </td>
                          <td className="c"><span className={`risk ${rl.cls}`}>{rl.txt}</span></td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 600 }}>{m.gf}–{m.ga}</td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{m.xgf.toFixed(2)}</td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{m.xga.toFixed(2)}</td>
                          <td className="c" style={{ fontFamily: "JetBrains Mono", color: signColor(m.xgd) }}>{signed(m.xgd)}</td>
                          <td className="r" style={{ color: signColor(m.over) }}>{signed(m.over)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <div className="st"><h2>Yorum</h2><span className="ep">{xg!.matches_analyzed} maç · {xg!.days}g</span></div>
          <div className="rc" style={{ margin: 0 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
              <span style={{ fontSize: "32px", fontWeight: 800, fontFamily: "JetBrains Mono", color: signColor(op) }}>{signed(op)}</span>
              <span style={{ fontSize: "13px", color: "var(--muted)" }}>{opHint}</span>
            </div>
            <p style={{ fontSize: "12px", color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>
              Gerçek averaj − xG farkı. Pozitif = xG&#39;nin üstünde skor (klinik/şanslı), negatif = altında (israf/şanssız).
              {DEMO_MODE && ` ${DEMO_CLUB} ${xg!.matches_analyzed} maçta xG farkını ${signed(xg!.xg_difference)} üretti; gerçek averaj ${signed(xg!.actual_goal_difference, 0)}. `}
              Sürdürülebilirlik için 0&#39;a yakınlık beklenir.
            </p>
          </div>
        </div>
      )}

      {/* PDF / paylaş → tarayıcı yazıcısı: yalnız analiz panosunu (#xg-print) yazdır. */}
      <style dangerouslySetInnerHTML={{ __html: `
        @media print {
          body * { visibility: hidden !important; }
          #xg-print, #xg-print * { visibility: visible !important; }
          #xg-print { position: absolute !important; left: 0; top: 0; width: 100%; }
          @page { margin: 10mm; }
        }
      ` }} />
    </ConsoleShell>
  );
}
