"use client";

/**
 * TD Performansı — beklenen puan (xPts) vs gerçek puan + maç bazlı olasılıklar.
 * ConsoleShell çatısında.
 *
 * DEMO_MODE açıkken canlı API'ye dokunmaz; "Beşiktaş" evreni için dolu, gerçekçi
 * mock sezon performansı gösterir (boş-state / "ID gir" / spinner olmaz).
 * Backend: GET /admin/manager-performance?team_external_id={id}&days={n}.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { DEMO_CLUB } from "@/lib/demo-data";
import { ConsoleShell } from "../_console/shell";

interface PerMatch {
  match_id: number;
  is_home: boolean;
  xpts: number;
  actual_pts: number;
  delta: number;
  p_win: number;
  p_draw: number;
  p_loss: number;
}
interface MgrResp {
  team_id: number;
  days: number;
  matches_considered: number;
  xpts: number;
  actual_points: number;
  overperformance: number;
  per_match: PerMatch[];
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

/* ───────────────────────── DEMO EVRENİ (inline) ─────────────────────────
   Beşiktaş'ın Süper Lig sezonu — son 18 maç, en yeni en üstte. Her maç için
   olasılıklardan beklenen puan (xPts = 3·p_win + 1·p_draw) ve gerçek puan.
   delta = gerçek − xPts. Rakipler tutarlı bir lig evreninden (Antalyaspor dahil). */

interface DemoMatch {
  match_id: number;
  date: string;        // "34. Hafta" gibi
  opponent: string;
  is_home: boolean;
  score: [number, number]; // [Beşiktaş, rakip]
  p_win: number;
  p_draw: number;
  p_loss: number;
}

// p_win/p_draw/p_loss toplamı ~1. Gerçek puan skordan türetilir (3/1/0).
const DEMO_MATCHES: DemoMatch[] = [
  { match_id: 9034, date: "34. Hafta", opponent: "Antalyaspor",     is_home: true,  score: [2, 1], p_win: 0.48, p_draw: 0.27, p_loss: 0.25 },
  { match_id: 9033, date: "33. Hafta", opponent: "Gaziantep FK",    is_home: false, score: [1, 1], p_win: 0.34, p_draw: 0.31, p_loss: 0.35 },
  { match_id: 9032, date: "32. Hafta", opponent: "Kasımpaşa",       is_home: true,  score: [3, 0], p_win: 0.61, p_draw: 0.23, p_loss: 0.16 },
  { match_id: 9031, date: "31. Hafta", opponent: "Konyaspor",       is_home: false, score: [0, 2], p_win: 0.29, p_draw: 0.28, p_loss: 0.43 },
  { match_id: 9030, date: "30. Hafta", opponent: "Galatasaray",     is_home: true,  score: [1, 0], p_win: 0.55, p_draw: 0.26, p_loss: 0.19 },
  { match_id: 9029, date: "29. Hafta", opponent: "Samsunspor",      is_home: false, score: [2, 2], p_win: 0.40, p_draw: 0.29, p_loss: 0.31 },
  { match_id: 9028, date: "28. Hafta", opponent: "Başakşehir",      is_home: true,  score: [2, 0], p_win: 0.58, p_draw: 0.24, p_loss: 0.18 },
  { match_id: 9027, date: "27. Hafta", opponent: "Çaykur Rizespor", is_home: false, score: [1, 3], p_win: 0.26, p_draw: 0.27, p_loss: 0.47 },
  { match_id: 9026, date: "26. Hafta", opponent: "Sivasspor",       is_home: true,  score: [4, 1], p_win: 0.64, p_draw: 0.21, p_loss: 0.15 },
  { match_id: 9025, date: "25. Hafta", opponent: "Göztepe",         is_home: false, score: [0, 0], p_win: 0.32, p_draw: 0.33, p_loss: 0.35 },
  { match_id: 9024, date: "24. Hafta", opponent: "Antalyaspor",     is_home: false, score: [1, 2], p_win: 0.31, p_draw: 0.28, p_loss: 0.41 },
  { match_id: 9023, date: "23. Hafta", opponent: "Gaziantep FK",    is_home: true,  score: [2, 2], p_win: 0.50, p_draw: 0.26, p_loss: 0.24 },
  { match_id: 9022, date: "22. Hafta", opponent: "Kasımpaşa",       is_home: false, score: [1, 0], p_win: 0.38, p_draw: 0.30, p_loss: 0.32 },
  { match_id: 9021, date: "21. Hafta", opponent: "Konyaspor",       is_home: true,  score: [3, 1], p_win: 0.53, p_draw: 0.25, p_loss: 0.22 },
  { match_id: 9020, date: "20. Hafta", opponent: "Galatasaray",     is_home: false, score: [2, 1], p_win: 0.36, p_draw: 0.29, p_loss: 0.35 },
  { match_id: 9019, date: "19. Hafta", opponent: "Samsunspor",      is_home: true,  score: [1, 1], p_win: 0.57, p_draw: 0.24, p_loss: 0.19 },
  { match_id: 9018, date: "18. Hafta", opponent: "Başakşehir",      is_home: false, score: [0, 1], p_win: 0.33, p_draw: 0.30, p_loss: 0.37 },
  { match_id: 9017, date: "17. Hafta", opponent: "Çaykur Rizespor", is_home: true,  score: [2, 0], p_win: 0.52, p_draw: 0.26, p_loss: 0.22 },
];

function actualPtsOf(m: DemoMatch): number {
  const [gf, ga] = m.score;
  return gf > ga ? 3 : gf === ga ? 1 : 0;
}

/** Demo maçları MgrResp'e dönüştür (en yeni N maçı dönem filtresine göre al). */
function buildDemoResp(days: number): MgrResp {
  // 30g≈son 4, 90g≈son 10, 180g≈hepsi (18). Dönem segmenti gerçek filtre gibi çalışır.
  const take = days <= 30 ? 4 : days <= 90 ? 10 : DEMO_MATCHES.length;
  const slice = DEMO_MATCHES.slice(0, take);
  const per_match: PerMatch[] = slice.map((m) => {
    const xpts = 3 * m.p_win + 1 * m.p_draw;
    const actual_pts = actualPtsOf(m);
    return {
      match_id: m.match_id,
      is_home: m.is_home,
      xpts,
      actual_pts,
      delta: actual_pts - xpts,
      p_win: m.p_win,
      p_draw: m.p_draw,
      p_loss: m.p_loss,
    };
  });
  const xpts = per_match.reduce((a, p) => a + p.xpts, 0);
  const actual_points = per_match.reduce((a, p) => a + p.actual_pts, 0);
  return {
    team_id: 0,
    days,
    matches_considered: per_match.length,
    xpts,
    actual_points,
    overperformance: actual_points - xpts,
    per_match,
  };
}

/** Maç bilgisini match_id ile eşle (rakip/skor/hafta için). */
const MATCH_BY_ID = new Map(DEMO_MATCHES.map((m) => [m.match_id, m]));

/** Kümülatif xPts vs gerçek puan SVG çizgi grafiği (eskiden yeniye). */
function CumulativeChart({ per_match }: { per_match: PerMatch[] }) {
  // Sayfa "en yeni en üstte" sıralı; grafik için eskiden yeniye çevir.
  const seq = [...per_match].reverse();
  const W = 560, H = 150, padL = 30, padR = 10, padT = 12, padB = 22;
  const n = seq.length;

  let cx = 0, ca = 0;
  const xpPts: { x: number; cum: number }[] = [];
  const acPts: { x: number; cum: number }[] = [];
  seq.forEach((m, i) => {
    cx += m.xpts;
    ca += m.actual_pts;
    const x = n > 1 ? padL + (i / (n - 1)) * (W - padL - padR) : padL;
    xpPts.push({ x, cum: cx });
    acPts.push({ x, cum: ca });
  });
  const maxY = Math.max(cx, ca, 1);
  const yOf = (v: number) => padT + (1 - v / maxY) * (H - padT - padB);
  const toPath = (pts: { x: number; cum: number }[]) =>
    pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${yOf(p.cum).toFixed(1)}`).join(" ");

  // Gerçek alanı (gerçek > xPts → yeşil dolgu, altında → kırmızı izlenimi için sadece çizgi)
  const gridY = [0, 0.5, 1].map((f) => maxY * f);

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }} role="img" aria-label="Kümülatif beklenen puan ve gerçek puan">
      {gridY.map((g, i) => (
        <g key={i}>
          <line x1={padL} x2={W - padR} y1={yOf(g)} y2={yOf(g)} stroke="var(--border)" strokeWidth={1} />
          <text x={padL - 6} y={yOf(g) + 3} textAnchor="end" fill="var(--dim)" style={{ fontSize: 9, fontFamily: "JetBrains Mono" }}>{Math.round(g)}</text>
        </g>
      ))}
      {/* xPts (beklenen) — kesik mor çizgi */}
      <path d={toPath(xpPts)} fill="none" stroke="var(--accent)" strokeWidth={2} strokeDasharray="4 3" strokeLinejoin="round" />
      {/* Gerçek puan — düz çizgi */}
      <path d={toPath(acPts)} fill="none" stroke="var(--low)" strokeWidth={2.4} strokeLinejoin="round" />
      {acPts.map((p, i) => (
        <circle key={i} cx={p.x} cy={yOf(p.cum)} r={2.4} fill="var(--low)" />
      ))}
      <text x={padL} y={H - 6} fill="var(--dim)" style={{ fontSize: 9 }}>eski</text>
      <text x={W - padR} y={H - 6} textAnchor="end" fill="var(--dim)" style={{ fontSize: 9 }}>yeni</text>
    </svg>
  );
}

export default function ManagerPerfConsolePage() {
  const [team, setTeam] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [days, setDays] = React.useState(90);

  // Demo modunda canlı API'ye dokunma; dolu mock sezon performansını göster.
  const { data, isLoading, error } = useSWR<MgrResp>(
    DEMO_MODE || !team ? null : `/admin/manager-performance?team_external_id=${team}&days=${days}`,
    apiFetch,
    { shouldRetryOnError: false },
  );

  const demo = React.useMemo(() => (DEMO_MODE ? buildDemoResp(days) : null), [days]);
  const resp = DEMO_MODE ? demo : data;
  const rows = resp?.per_match ?? [];
  const has = !!resp && resp.matches_considered > 0;
  const op = resp?.overperformance ?? 0;

  // Demo: özet/dağılım göstergeleri
  const wins = rows.filter((m) => m.actual_pts === 3).length;
  const draws = rows.filter((m) => m.actual_pts === 1).length;
  const losses = rows.filter((m) => m.actual_pts === 0).length;
  const overCount = rows.filter((m) => m.delta > 0.05).length;
  const underCount = rows.filter((m) => m.delta < -0.05).length;
  const homeXpts = rows.filter((m) => m.is_home).reduce((a, m) => a + m.xpts, 0);
  const awayXpts = rows.filter((m) => !m.is_home).reduce((a, m) => a + m.xpts, 0);
  const homeActual = rows.filter((m) => m.is_home).reduce((a, m) => a + m.actual_pts, 0);
  const awayActual = rows.filter((m) => !m.is_home).reduce((a, m) => a + m.actual_pts, 0);
  const ppg = has ? resp!.actual_points / resp!.matches_considered : 0;

  // En büyük üstün/altında performans maçları (sağ panel)
  const ranked = [...rows].sort((a, b) => b.delta - a.delta);
  const bestOver = ranked[0];
  const worstUnder = ranked[ranked.length - 1];

  const right = (
    <>
      <div className="rc">
        <h3>Nasıl Okunur?</h3>
        <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
          <b style={{ color: "var(--ink)" }}>xPts</b> = maç olasılıklarından beklenen puan (3·G + 1·B).
          <div style={{ marginTop: 8 }}><span style={{ color: "var(--low)" }}>Pozitif fark</span> = modelin üstünde sonuç (iyi yönetim/şans).</div>
          <div style={{ marginTop: 4 }}><span style={{ color: "var(--crit)" }}>Negatif</span> = altında sonuç.</div>
          <div style={{ marginTop: 8, color: "var(--dim)" }}>Çubuk: galibiyet / beraberlik / mağlubiyet olasılığı.</div>
        </div>
      </div>

      {has && (
        <>
          <div className="rc">
            <h3>Sezon Formu <span className="tiny">{resp!.matches_considered} maç</span></h3>
            <div className="stat"><span>Galibiyet</span><span className="sv" style={{ color: "var(--low)" }}>{wins}</span></div>
            <div className="stat"><span>Beraberlik</span><span className="sv" style={{ color: "var(--muted)" }}>{draws}</span></div>
            <div className="stat"><span>Mağlubiyet</span><span className="sv" style={{ color: "var(--high)" }}>{losses}</span></div>
            <div className="stat"><span>Puan / Maç</span><span className="sv">{ppg.toFixed(2)}</span></div>
            <div style={{ marginTop: 4 }}>
              <span className="probbar">
                <i style={{ width: `${(wins / resp!.matches_considered) * 100}%`, background: "var(--low)" }} />
                <i style={{ width: `${(draws / resp!.matches_considered) * 100}%`, background: "var(--dim)" }} />
                <i style={{ width: `${(losses / resp!.matches_considered) * 100}%`, background: "var(--high)" }} />
              </span>
              <div className="probleg">
                <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>{wins}G</div><div className="pl">Galibiyet</div></div>
                <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>{draws}B</div><div className="pl">Berabere</div></div>
                <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>{losses}M</div><div className="pl">Mağlubiyet</div></div>
              </div>
            </div>
          </div>

          <div className="rc">
            <h3>Ev / Deplasman <span className="tiny">xPts → gerçek</span></h3>
            <div className="stat"><span>Ev xPts</span><span className="sv">{homeXpts.toFixed(1)}</span></div>
            <div className="stat"><span>Ev gerçek</span><span className="sv" style={{ color: signColor(homeActual - homeXpts) }}>{homeActual}</span></div>
            <div className="stat"><span>Deplasman xPts</span><span className="sv">{awayXpts.toFixed(1)}</span></div>
            <div className="stat"><span>Deplasman gerçek</span><span className="sv" style={{ color: signColor(awayActual - awayXpts) }}>{awayActual}</span></div>
          </div>

          {bestOver && worstUnder && (
            <div className="rc">
              <h3>Öne Çıkanlar <span className="tiny">fark</span></h3>
              <div className="alrt">
                <span className="ai" style={{ background: "var(--low)" }} />
                <div className="am"><b>{MATCH_BY_ID.get(bestOver.match_id)?.opponent ?? `#${bestOver.match_id}`}</b> — beklentinin en üstünde
                  <span className="tm">{MATCH_BY_ID.get(bestOver.match_id)?.date} · fark {signed(bestOver.delta, 1)}</span>
                </div>
              </div>
              <div className="alrt">
                <span className="ai" style={{ background: "var(--crit)" }} />
                <div className="am"><b>{MATCH_BY_ID.get(worstUnder.match_id)?.opponent ?? `#${worstUnder.match_id}`}</b> — beklentinin en altında
                  <span className="tm">{MATCH_BY_ID.get(worstUnder.match_id)?.date} · fark {signed(worstUnder.delta, 1)}</span>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );

  return (
    <ConsoleShell
      active="/manager-performance"
      title="TD Performansı"
      sub="Beklenen vs gerçek puan"
      desc="Beklenen puan (xPts) vs gerçek puan. Pozitif fark = modelin üstünde sonuç (iyi yönetim/şans), negatif = altında."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>{DEMO_MODE ? `${DEMO_CLUB} — Sezon` : "Takım Seç"}</h2>
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

      {!DEMO_MODE && !team && <div className="pgdesc">Bir takım ID gir (örn. 611) ve dönem seç.</div>}
      {!DEMO_MODE && team && isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {!DEMO_MODE && error && <div className="pgdesc">Veri üretilemedi ya da yetki yok.</div>}

      {has && (
        <>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
            <div className="kpi"><div className="kl">xPts (beklenen)</div><div className="kn">{resp!.xpts.toFixed(1)}</div><div className="kd">{resp!.matches_considered} maç · {resp!.days}g</div></div>
            <div className="kpi"><div className="kl">Gerçek Puan</div><div className="kn">{resp!.actual_points}</div><div className="kd"><span className="u">{wins}G</span> · {draws}B · {losses}M</div></div>
            <div className="kpi"><div className="kl">Fark</div><div className="kn" style={{ color: signColor(op) }}>{signed(op, 1)}</div><div className="kd">gerçek − xPts</div></div>
            <div className="kpi"><div className="kl">Puan / Maç</div><div className="kn">{ppg.toFixed(2)}</div><div className="kd">ortalama verim</div></div>
            <div className="kpi"><div className="kl">Üstün / Altında</div><div className="kn"><span style={{ color: "var(--low)" }}>{overCount}</span><span style={{ color: "var(--dim)", fontWeight: 500 }}> / </span><span style={{ color: "var(--crit)" }}>{underCount}</span></div><div className="kd">maç bazlı fark</div></div>
          </div>

          <div className="st"><h2>Kümülatif: Beklenen vs Gerçek</h2><span className="ep">{resp!.matches_considered} maç</span></div>
          <div className="rc" style={{ margin: 0 }}>
            <div style={{ display: "flex", gap: 16, marginBottom: 6, fontSize: 11.5, color: "var(--muted)" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span style={{ width: 16, height: 0, borderTop: "2px solid var(--low)" }} /> Gerçek puan</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span style={{ width: 16, height: 0, borderTop: "2px dashed var(--accent)" }} /> Beklenen (xPts)</span>
              <span style={{ marginLeft: "auto", color: signColor(op), fontWeight: 700, fontFamily: "JetBrains Mono" }}>{signed(op, 1)} puan</span>
            </div>
            <CumulativeChart per_match={rows} />
          </div>

          <div className="st"><h2>Maç Bazlı</h2><span className="ep">{resp!.matches_considered} maç · {resp!.days}g</span></div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th>Hafta</th><th>Rakip</th><th className="c">Saha</th><th className="c">Skor</th>
                <th>Olasılık (G/B/M)</th>
                <th className="r">xP</th><th className="r">Gerçek</th><th className="r">Fark</th>
              </tr></thead>
              <tbody>
                {rows.map((m) => {
                  const info = MATCH_BY_ID.get(m.match_id);
                  return (
                    <tr key={m.match_id}>
                      <td style={{ color: "var(--dim)", fontSize: 11.5 }}>{info?.date ?? `#${m.match_id}`}</td>
                      <td><span className="nm">{info?.opponent ?? `#${m.match_id}`}</span></td>
                      <td className="c" style={{ fontSize: 10.5, textTransform: "uppercase", color: "var(--dim)" }}>{m.is_home ? "Ev" : "Dep"}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: m.actual_pts === 3 ? "var(--low)" : m.actual_pts === 1 ? "var(--muted)" : "var(--high)" }}>
                        {info ? `${info.score[0]}–${info.score[1]}` : "—"}
                      </td>
                      <td>
                        <span className="probbar" style={{ marginBottom: 0, width: 140 }}>
                          <i style={{ width: `${m.p_win * 100}%`, background: "var(--low)" }} />
                          <i style={{ width: `${m.p_draw * 100}%`, background: "var(--dim)" }} />
                          <i style={{ width: `${m.p_loss * 100}%`, background: "var(--high)" }} />
                        </span>
                      </td>
                      <td className="r" style={{ color: "var(--muted)" }}>{m.xpts.toFixed(1)}</td>
                      <td className="r">{m.actual_pts}p</td>
                      <td className="r" style={{ color: signColor(m.delta) }}>{signed(m.delta, 1)}</td>
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
