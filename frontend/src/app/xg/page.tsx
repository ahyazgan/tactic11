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
import { demoLive, DEMO_CLUB, DEMO_OPPONENT } from "@/lib/demo-data";
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
      title="Analiz — xG"
      sub="Beklenen gol performansı"
      desc="Beklenen gol üretimi (xG) vs gerçek skor — over/underperformance ile gerçek verimliliği gösterir."
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
        </div>
      </div>

      {!DEMO_MODE && !team && <div className="pgdesc">Analiz için bir takım ID gir (örn. 611) ve dönem seç.</div>}
      {!DEMO_MODE && team && isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {!DEMO_MODE && error && <div className="pgdesc">xG verisi üretilemedi ya da yetki yok.</div>}
      {!DEMO_MODE && data?.note && <div className="pgdesc">{data.note}</div>}

      {has && (
        <>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
            <div className="kpi"><div className="kl">xG (lehte)</div><div className="kn">{xg!.xg_for.toFixed(2)}</div><div className="kd">üretilen şans</div></div>
            <div className="kpi"><div className="kl">xGA (aleyhte)</div><div className="kn">{xg!.xg_against.toFixed(2)}</div><div className="kd">verilen şans</div></div>
            <div className="kpi"><div className="kl">xG Farkı</div><div className="kn" style={{ color: signColor(xg!.xg_difference) }}>{signed(xg!.xg_difference)}</div><div className="kd">lehte − aleyhte</div></div>
            <div className="kpi"><div className="kl">Gerçek Averaj</div><div className="kn" style={{ color: signColor(xg!.actual_goal_difference) }}>{signed(xg!.actual_goal_difference, 0)}</div><div className="kd">attığı − yediği</div></div>
            <div className="kpi"><div className="kl">Overperformance</div><div className="kn" style={{ color: signColor(op) }}>{signed(op)}</div><div className="kd">gerçek − xG</div></div>
          </div>

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

          {/* Son maçlar — xG dökümü tablosu */}
          {DEMO_MODE && (
            <>
              <div className="st"><h2>Maç Maç xG Dökümü</h2><span className="ep">{matches.length} maç · {days}g</span></div>
              <div className="tbl">
                <table>
                  <thead><tr>
                    <th>Tarih</th><th>Rakip</th><th className="c">S</th><th className="c">Skor</th>
                    <th className="c">xG</th><th className="c">xGA</th><th className="c">xG Farkı</th><th className="r">Over</th>
                  </tr></thead>
                  <tbody>
                    {matches.map((m, i) => {
                      const xgd = m.xgf - m.xga;
                      const over = (m.gf - m.ga) - xgd;
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
                          <td className="c" style={{ fontFamily: "JetBrains Mono", color: signColor(xgd) }}>{signed(xgd)}</td>
                          <td className="r" style={{ color: signColor(over) }}>{signed(over)}</td>
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
        </>
      )}
    </ConsoleShell>
  );
}
