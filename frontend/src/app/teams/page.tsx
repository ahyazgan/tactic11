"use client";

/**
 * Takımlar — Süper Lig takım sıralaması. ConsoleShell çatısında.
 *
 * DEMO_MODE açıkken canlı API'ye hiç dokunmaz; "Süper Lig — 34. Hafta" evreninin
 * dolu lig tablosunu (18 takım), form/xG/güç metriklerini ve FK Demo odaklı sağ
 * paneli gösterir. Boş-state / "ID gir" prompt'u / spinner YOK.
 *
 * Demo bittiğinde (DEMO_MODE=false) eski "önce bir lig seç" girişine düşer.
 */

import * as React from "react";
import Link from "next/link";
import { DEMO_MODE } from "@/lib/demo-mode";
import { ConsoleShell } from "../_console/shell";
import { RiskDonut, LegendRow } from "../_console/viz";

type Form = "G" | "B" | "M";

interface DemoTeam {
  rank: number;
  name: string;
  short: string;
  played: number;
  win: number;
  draw: number;
  loss: number;
  gf: number;
  ga: number;
  xgf: number;       // beklenen attığı gol (sezon)
  xga: number;       // beklenen yediği gol (sezon)
  form: Form[];      // son 5 maç (en yeni en sağda)
  us?: boolean;      // FK Demo
  next?: boolean;    // sıradaki rakibimiz
}

// "Süper Lig — 34. Hafta" demo evreni. FK Demo zirve yarışında, sıradaki rakip
// Rakip SK orta-alt sıralarda. Puanlar 3*G + B ile tutarlı.
const DEMO_TEAMS: DemoTeam[] = [
  { rank: 1, name: "Anadolu Spor", short: "AND", played: 33, win: 22, draw: 6, loss: 5, gf: 64, ga: 29, xgf: 60.4, xga: 31.2, form: ["G", "G", "B", "G", "G"] },
  { rank: 2, name: "FK Demo", short: "FKD", played: 33, win: 21, draw: 7, loss: 5, gf: 61, ga: 28, xgf: 58.9, xga: 27.6, form: ["G", "B", "G", "G", "G"], us: true },
  { rank: 3, name: "Marmara United", short: "MAR", played: 33, win: 20, draw: 6, loss: 7, gf: 58, ga: 33, xgf: 55.1, xga: 35.0, form: ["G", "G", "M", "G", "B"] },
  { rank: 4, name: "Ege Atletik", short: "EGE", played: 33, win: 18, draw: 8, loss: 7, gf: 52, ga: 34, xgf: 50.7, xga: 36.4, form: ["B", "G", "G", "B", "G"] },
  { rank: 5, name: "Karadeniz FK", short: "KAR", played: 33, win: 17, draw: 7, loss: 9, gf: 49, ga: 38, xgf: 47.8, xga: 39.9, form: ["G", "M", "G", "G", "B"] },
  { rank: 6, name: "Başkent Gücü", short: "BAS", played: 33, win: 16, draw: 8, loss: 9, gf: 47, ga: 40, xgf: 45.2, xga: 41.1, form: ["B", "B", "G", "M", "G"] },
  { rank: 7, name: "Toros SK", short: "TOR", played: 33, win: 15, draw: 9, loss: 9, gf: 44, ga: 41, xgf: 43.6, xga: 42.0, form: ["G", "B", "M", "G", "B"] },
  { rank: 8, name: "Doğu Çelik", short: "DOG", played: 33, win: 14, draw: 9, loss: 10, gf: 42, ga: 42, xgf: 41.0, xga: 43.5, form: ["M", "G", "B", "G", "M"] },
  { rank: 9, name: "Akdeniz FK", short: "AKD", played: 33, win: 13, draw: 10, loss: 10, gf: 40, ga: 43, xgf: 39.7, xga: 44.2, form: ["B", "M", "G", "B", "G"] },
  { rank: 10, name: "Yıldız Spor", short: "YIL", played: 33, win: 12, draw: 11, loss: 10, gf: 39, ga: 41, xgf: 38.1, xga: 42.8, form: ["B", "G", "B", "M", "B"] },
  { rank: 11, name: "Rakip SK", short: "RKP", played: 33, win: 12, draw: 9, loss: 12, gf: 41, ga: 44, xgf: 38.9, xga: 45.7, form: ["M", "B", "G", "M", "G"], next: true },
  { rank: 12, name: "Boğaz United", short: "BOG", played: 33, win: 11, draw: 10, loss: 12, gf: 37, ga: 45, xgf: 36.4, xga: 46.0, form: ["G", "M", "B", "M", "B"] },
  { rank: 13, name: "Step Atletik", short: "STP", played: 33, win: 10, draw: 11, loss: 12, gf: 35, ga: 46, xgf: 34.8, xga: 46.9, form: ["B", "M", "M", "B", "G"] },
  { rank: 14, name: "Volkan FK", short: "VOL", played: 33, win: 10, draw: 9, loss: 14, gf: 34, ga: 49, xgf: 33.2, xga: 50.3, form: ["M", "M", "B", "G", "M"] },
  { rank: 15, name: "Fırat Spor", short: "FIR", played: 33, win: 9, draw: 10, loss: 14, gf: 32, ga: 50, xgf: 31.9, xga: 51.1, form: ["M", "B", "M", "B", "M"] },
  { rank: 16, name: "Demir Çelik SK", short: "DMR", played: 33, win: 8, draw: 9, loss: 16, gf: 30, ga: 54, xgf: 29.6, xga: 55.4, form: ["M", "G", "M", "M", "B"] },
  { rank: 17, name: "Granit FK", short: "GRA", played: 33, win: 6, draw: 10, loss: 17, gf: 27, ga: 58, xgf: 26.8, xga: 57.9, form: ["M", "M", "B", "M", "M"] },
  { rank: 18, name: "Şafak United", short: "SAF", played: 33, win: 5, draw: 8, loss: 20, gf: 24, ga: 63, xgf: 24.1, xga: 61.5, form: ["M", "M", "M", "B", "M"] },
];

const LEAGUE = "Süper Lig";
const SEASON = "2025/26 · 34. Hafta";

const FORM_VAR: Record<Form, string> = { G: "var(--low)", B: "var(--mid)", M: "var(--crit)" };

function points(t: DemoTeam): number {
  return t.win * 3 + t.draw;
}

/** Sıra bandına göre satır vurgusu: şampiyonluk / Avrupa / orta / düşme. */
function zoneColor(rank: number): string {
  if (rank <= 2) return "var(--low)";       // şampiyonluk yarışı
  if (rank <= 5) return "var(--accent)";    // Avrupa kupaları
  if (rank >= 16) return "var(--crit)";     // düşme hattı
  return "var(--dim)";
}

/** Mini form rozetleri (son 5 maç). */
function FormPips({ form }: { form: Form[] }) {
  return (
    <span style={{ display: "inline-flex", gap: 4 }}>
      {form.map((f, i) => (
        <span
          key={i}
          title={f === "G" ? "Galibiyet" : f === "B" ? "Beraberlik" : "Mağlubiyet"}
          style={{
            width: 16,
            height: 16,
            borderRadius: 5,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 10,
            fontWeight: 700,
            color: "#fff",
            background: FORM_VAR[f],
          }}
        >
          {f}
        </span>
      ))}
    </span>
  );
}

type Scope = "all" | "top" | "drop";

export default function TeamsConsolePage() {
  const [scope, setScope] = React.useState<Scope>("all");

  // DEMO kapalı: eski "önce bir lig seç" girişine düş.
  if (!DEMO_MODE) {
    return (
      <ConsoleShell
        active="/teams"
        title="Takımlar"
        sub="Lig bazlı liste"
        desc="Takım listesi lig bazında tutulur. Önce bir lig seç, ardından takımları gör."
        right={
          <div className="rc">
            <h3>İpucu</h3>
            <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
              Ligler ekranından bir lige tıklayınca o ligin takımları açılır.
            </div>
          </div>
        }
      >
        <div className="rc" style={{ margin: 0 }}>
          <div style={{ fontSize: 13, color: "var(--ink)", marginBottom: 12 }}>Takımları görmek için önce bir lig seç:</div>
          <Link href="/leagues" style={{ display: "inline-block", fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.5, padding: "7px 14px", borderRadius: 7, border: "1px solid var(--line)", color: "var(--ink)", background: "var(--panel3)", textDecoration: "none" }}>
            Liglere git →
          </Link>
        </div>
      </ConsoleShell>
    );
  }

  // ── Demo metrikleri ──
  const teams = DEMO_TEAMS;
  const us = teams.find((t) => t.us)!;
  const next = teams.find((t) => t.next)!;
  const leader = teams[0];
  const gapToLeader = points(leader) - points(us);

  // Lig geneli atak/savunma için en iyi/en kötü hücum.
  const bestAttack = [...teams].sort((a, b) => b.gf - a.gf)[0];
  const bestDefense = [...teams].sort((a, b) => a.ga - b.ga)[0];

  // Sağ kolon donut: ligin sıra bölgeleri.
  const zone = [
    { label: "Şampiyonluk (1-2)", n: teams.filter((t) => t.rank <= 2).length, v: "var(--low)" },
    { label: "Avrupa (3-5)", n: teams.filter((t) => t.rank >= 3 && t.rank <= 5).length, v: "var(--accent)" },
    { label: "Orta sıra (6-15)", n: teams.filter((t) => t.rank >= 6 && t.rank <= 15).length, v: "var(--dim)" },
    { label: "Düşme hattı (16-18)", n: teams.filter((t) => t.rank >= 16).length, v: "var(--crit)" },
  ];

  // En formda 5 takım (son 5 maçtan puan).
  const formPts = (t: DemoTeam) => t.form.reduce((s, f) => s + (f === "G" ? 3 : f === "B" ? 1 : 0), 0);
  const inForm = [...teams].sort((a, b) => formPts(b) - formPts(a)).slice(0, 5);

  const shown = teams.filter((t) => {
    if (scope === "top") return t.rank <= 5;
    if (scope === "drop") return t.rank >= 14;
    return true;
  });

  const right = (
    <>
      <div className="rc">
        <h3>Lig Bölgeleri <span className="tiny">{teams.length} takım</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut segments={zone.map((z) => ({ value: z.n, color: z.v }))} centerLabel={teams.length} centerSub="takım" />
          <div style={{ flex: 1, minWidth: 0 }}>
            {zone.map((z) => (
              <LegendRow key={z.label} color={z.v} label={z.label} value={z.n} />
            ))}
          </div>
        </div>
      </div>

      <div className="rc">
        <h3>Sıradaki Rakip <span className="tiny">{LEAGUE} · 34. Hafta</span></h3>
        <div className="nm-vs"><span className="t">{us.name}</span><span className="x">vs</span><span className="t away">{next.name}</span></div>
        <div className="nm-when">Ev sahibi · {next.name} ligde {next.rank}. sırada</div>
        <div className="stat"><span>Bizim sıramız</span><span className="sv" style={{ color: "var(--low)" }}>{us.rank}.</span></div>
        <div className="stat"><span>Rakip sırası</span><span className="sv">{next.rank}.</span></div>
        <div className="stat"><span>Rakip son 5 (puan)</span><span className="sv" style={{ color: "var(--mid)" }}>{formPts(next)}/15</span></div>
        <div className="stat"><span>Rakip averajı</span><span className="sv" style={{ color: next.gf - next.ga >= 0 ? "var(--low)" : "var(--crit)" }}>{next.gf - next.ga >= 0 ? "+" : ""}{next.gf - next.ga}</span></div>
        <div style={{ marginTop: 10 }}>
          <Link href="/opponent" style={{ display: "inline-block", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5, padding: "6px 12px", borderRadius: 7, border: "1px solid var(--accent)", color: "var(--accent)", background: "var(--accent-lt)", textDecoration: "none", fontWeight: 600 }}>
            Rakip raporu →
          </Link>
        </div>
      </div>

      <div className="rc">
        <h3>En Formda <span className="tiny">son 5 maç</span></h3>
        {inForm.map((t) => (
          <div className="alrt" key={t.name}>
            <span className="ai" style={{ background: t.us ? "var(--accent)" : "var(--low)" }} />
            <div className="am"><b>{t.name}</b>{t.us ? " · biz" : ""}
              <span className="tm">{formPts(t)}/15 puan · {t.rank}. sıra · averaj {t.gf - t.ga >= 0 ? "+" : ""}{t.gf - t.ga}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/teams"
      title="Takımlar"
      sub={LEAGUE}
      desc={`${LEAGUE} ${SEASON} sıralaması. Form, gol ve beklenen-gol (xG) metrikleriyle. FK Demo zirve yarışında.`}
      right={right}
    >
      <div className="kpis">
        <div className="kpi"><div className="kl">Sıramız</div><div className="kn">{us.rank}<span className="pct">.</span></div><div className="kd"><span className="u">{points(us)} puan</span> · {us.played} maç</div></div>
        <div className="kpi"><div className="kl">Lidere Fark</div><div className="kn" style={{ color: gapToLeader <= 0 ? "var(--low)" : "var(--mid)" }}>{gapToLeader <= 0 ? "Lider" : `-${gapToLeader}`}</div><div className="kd">{leader.name}</div></div>
        <div className="kpi"><div className="kl">Averajımız</div><div className="kn" style={{ color: us.gf - us.ga >= 0 ? "var(--low)" : "var(--crit)" }}>{us.gf - us.ga >= 0 ? "+" : ""}{us.gf - us.ga}</div><div className="kd">{us.gf} attık · {us.ga} yedik</div></div>
        <div className="kpi"><div className="kl">En İyi Hücum</div><div className="kn">{bestAttack.gf}</div><div className="kd">{bestAttack.name}</div></div>
        <div className="kpi"><div className="kl">En İyi Savunma</div><div className="kn">{bestDefense.ga}</div><div className="kd">{bestDefense.name}</div></div>
      </div>

      <div className="st">
        <h2>{LEAGUE} — Puan Durumu</h2>
        <div className="seg">
          <button className={scope === "all" ? "on" : ""} onClick={() => setScope("all")}>Tümü</button>
          <button className={scope === "top" ? "on" : ""} onClick={() => setScope("top")}>Zirve</button>
          <button className={scope === "drop" ? "on" : ""} onClick={() => setScope("drop")}>Dip</button>
        </div>
      </div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th>
            <th>Takım</th>
            <th className="c">O</th>
            <th className="c">G</th>
            <th className="c">B</th>
            <th className="c">M</th>
            <th className="c">A-Y</th>
            <th className="c">Av</th>
            <th className="c">Form</th>
            <th className="r">P</th>
          </tr></thead>
          <tbody>
            {shown.map((t) => {
              const zc = zoneColor(t.rank);
              const diff = t.gf - t.ga;
              return (
                <tr key={t.name} style={t.us ? { background: "var(--accent-lt)" } : undefined}>
                  <td className="pnum c"><span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 3, height: 14, borderRadius: 2, background: zc }} />{t.rank}
                  </span></td>
                  <td>
                    <span className="pos" style={{ marginRight: 8 }}>{t.short}</span>
                    <span className="nm">{t.name}</span>
                    {t.us && <span className="nat"> · biz</span>}
                    {t.next && <span className="nat"> · sıradaki rakip</span>}
                  </td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{t.played}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--low)" }}>{t.win}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{t.draw}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--crit)" }}>{t.loss}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)", fontSize: 11 }}>{t.gf}:{t.ga}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 600, color: diff >= 0 ? "var(--low)" : "var(--crit)" }}>{diff >= 0 ? "+" : ""}{diff}</td>
                  <td className="c"><FormPips form={t.form} /></td>
                  <td className="r">{points(t)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="st"><h2>Beklenen Gol (xG) — Güç Sıralaması</h2><span className="ep">sezon kümülatif xG / xGA</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th>
            <th>Takım</th>
            <th>Hücum gücü (xG attığı)</th>
            <th>Savunma gücü (xGA yediği)</th>
            <th className="r">Net xG</th>
          </tr></thead>
          <tbody>
            {[...teams]
              .sort((a, b) => (b.xgf - b.xga) - (a.xgf - a.xga))
              .slice(0, 10)
              .map((t, i) => {
                const net = t.xgf - t.xga;
                // Ölçek: en yüksek xGF ~64, en yüksek xGA ~62 → 0..100 bar.
                const atkW = Math.round((t.xgf / 64) * 100);
                const defW = Math.round((t.xga / 62) * 100);
                return (
                  <tr key={t.name} style={t.us ? { background: "var(--accent-lt)" } : undefined}>
                    <td className="pnum c">{i + 1}</td>
                    <td><span className="nm">{t.name}</span>{t.us && <span className="nat"> · biz</span>}</td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--muted)", minWidth: 34 }}>{t.xgf.toFixed(1)}</span>
                        <span className="mbar" style={{ flex: 1, margin: 0 }}><i style={{ width: `${atkW}%`, background: "var(--low)" }} /></span>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--muted)", minWidth: 34 }}>{t.xga.toFixed(1)}</span>
                        <span className="mbar" style={{ flex: 1, margin: 0 }}><i style={{ width: `${defW}%`, background: "var(--high)" }} /></span>
                      </div>
                    </td>
                    <td className="r" style={{ color: net >= 0 ? "var(--low)" : "var(--crit)" }}>{net >= 0 ? "+" : ""}{net.toFixed(1)}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
