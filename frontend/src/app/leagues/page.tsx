"use client";

/**
 * Ligler — Süper Lig puan durumu. ConsoleShell çatısında.
 *
 * DEMO_MODE açıkken canlı API'ye dokunulmaz; aşağıdaki inline demo evreni
 * (Süper Lig — 34. Hafta, "Beşiktaş" lider yarışında) ile dolu, inandırıcı bir
 * puan durumu + form + KPI şeridi gösterilir (spinner / boş tablo / "ID gir" yok).
 * DEMO kapalıyken eski canlı-API (GET /leagues) davranışına döner.
 */

import * as React from "react";
import useSWR from "swr";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { Crest } from "@/lib/teams";
import { ConsoleShell } from "../_console/shell";
import { RiskDonut, LegendRow } from "../_console/viz";

interface League {
  sport: string;
  external_id: number;
  name: string;
  season: number;
  country: string | null;
}

// --------------------------------------------------------------------------- //
// DEMO EVRENİ — Süper Lig 34. Hafta puan durumu (bu dosyaya özel, inline)
// --------------------------------------------------------------------------- //

type FormResult = "G" | "B" | "M";

interface StandingRow {
  pos: number;
  team: string;
  short: string;
  played: number;
  win: number;
  draw: number;
  loss: number;
  gf: number;
  ga: number;
  pts: number;
  form: FormResult[]; // son 5, soldan eskiye → sağda en yeni
}

// Beşiktaş zirve yarışında 2.; lig "Süper Lig — 34. Hafta" evreniyle tutarlı.
const DEMO_STANDINGS: StandingRow[] = [
  { pos: 1, team: "Galatasaray", short: "GS", played: 34, win: 24, draw: 6, loss: 4, gf: 71, ga: 28, pts: 78, form: ["G", "G", "B", "G", "G"] },
  { pos: 2, team: "Beşiktaş", short: "BJK", played: 34, win: 23, draw: 7, loss: 4, gf: 68, ga: 31, pts: 76, form: ["G", "B", "G", "G", "G"] },
  { pos: 3, team: "Fenerbahçe", short: "FB", played: 34, win: 21, draw: 8, loss: 5, gf: 62, ga: 34, pts: 71, form: ["G", "G", "G", "B", "M"] },
  { pos: 4, team: "Trabzonspor", short: "TS", played: 34, win: 19, draw: 9, loss: 6, gf: 57, ga: 33, pts: 66, form: ["B", "G", "G", "G", "B"] },
  { pos: 5, team: "Samsunspor", short: "SAM", played: 34, win: 18, draw: 8, loss: 8, gf: 54, ga: 40, pts: 62, form: ["G", "M", "G", "B", "G"] },
  { pos: 6, team: "Başakşehir", short: "İBFK", played: 34, win: 16, draw: 9, loss: 9, gf: 49, ga: 42, pts: 57, form: ["B", "B", "G", "M", "G"] },
  { pos: 7, team: "Eyüpspor", short: "EYP", played: 34, win: 15, draw: 8, loss: 11, gf: 47, ga: 45, pts: 53, form: ["M", "G", "B", "G", "B"] },
  { pos: 8, team: "Göztepe", short: "GÖZ", played: 34, win: 14, draw: 9, loss: 11, gf: 45, ga: 46, pts: 51, form: ["G", "B", "M", "B", "G"] },
  { pos: 9, team: "Kasımpaşa", short: "KSM", played: 34, win: 13, draw: 10, loss: 11, gf: 43, ga: 44, pts: 49, form: ["B", "G", "B", "M", "B"] },
  { pos: 10, team: "Konyaspor", short: "KON", played: 34, win: 12, draw: 10, loss: 12, gf: 41, ga: 47, pts: 46, form: ["M", "B", "G", "B", "M"] },
  { pos: 11, team: "Antalyaspor", short: "ANT", played: 34, win: 12, draw: 8, loss: 14, gf: 39, ga: 49, pts: 44, form: ["M", "M", "B", "G", "B"] },
  { pos: 12, team: "Çaykur Rizespor", short: "RİZ", played: 34, win: 11, draw: 9, loss: 14, gf: 38, ga: 50, pts: 42, form: ["B", "M", "G", "M", "B"] },
  { pos: 13, team: "Alanyaspor", short: "ALY", played: 34, win: 10, draw: 10, loss: 14, gf: 36, ga: 51, pts: 40, form: ["M", "B", "M", "B", "G"] },
  { pos: 14, team: "Sivasspor", short: "SVS", played: 34, win: 9, draw: 11, loss: 14, gf: 35, ga: 52, pts: 38, form: ["B", "M", "B", "M", "B"] },
  { pos: 15, team: "Kayserispor", short: "KAY", played: 34, win: 9, draw: 9, loss: 16, gf: 33, ga: 55, pts: 36, form: ["M", "M", "B", "M", "G"] },
  { pos: 16, team: "Gaziantep FK", short: "GFK", played: 34, win: 8, draw: 9, loss: 17, gf: 31, ga: 58, pts: 33, form: ["M", "B", "M", "M", "B"] },
  { pos: 17, team: "Hatayspor", short: "HTY", played: 34, win: 6, draw: 10, loss: 18, gf: 28, ga: 62, pts: 28, form: ["M", "M", "M", "B", "M"] },
  { pos: 18, team: "Bodrum FK", short: "BOD", played: 34, win: 5, draw: 7, loss: 22, gf: 24, ga: 71, pts: 22, form: ["M", "M", "B", "M", "M"] },
];

// Lider yarışı sağ-panel mini grafiği için ilk 4 takımın puanı.
const TITLE_RACE = DEMO_STANDINGS.slice(0, 4);

// Demo modunda lig listesi sekmesinde gösterilecek "sync edilmiş ligler".
const DEMO_LEAGUES: League[] = [
  { sport: "football", external_id: 1001, name: "Süper Lig", season: 2025, country: "Türkiye" },
  { sport: "football", external_id: 1002, name: "1. Lig", season: 2025, country: "Türkiye" },
  { sport: "football", external_id: 1003, name: "Türkiye Kupası", season: 2025, country: "Türkiye" },
];

const FORM_VAR: Record<FormResult, string> = {
  G: "var(--low)",
  B: "var(--mid)",
  M: "var(--crit)",
};

/** Sıraya göre konum bandı rengi (Avrupa / orta / düşme hattı). */
function zoneColor(pos: number): string {
  if (pos <= 2) return "var(--low)";   // şampiyonluk / kupa
  if (pos <= 5) return "var(--accent)"; // Avrupa kupaları
  if (pos >= 16) return "var(--crit)";  // düşme hattı
  return "var(--dim)";
}

function zoneLabel(pos: number): string | null {
  if (pos === 1) return "Lider";
  if (pos <= 5) return "Avrupa";
  if (pos >= 16) return "Düşme";
  return null;
}

function FormDots({ form }: { form: FormResult[] }) {
  return (
    <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
      {form.map((r, i) => (
        <span
          key={i}
          title={r === "G" ? "Galibiyet" : r === "B" ? "Beraberlik" : "Mağlubiyet"}
          style={{
            width: 16,
            height: 16,
            borderRadius: 5,
            background: FORM_VAR[r],
            color: "#fff",
            fontSize: 9.5,
            fontWeight: 800,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: "JetBrains Mono",
          }}
        >
          {r}
        </span>
      ))}
    </span>
  );
}

export default function LeaguesConsolePage() {
  const router = useRouter();
  // Demo modunda canlı API'ye dokunma; dolu mock puan durumunu göster.
  const { data, error, isLoading } = useSWR<League[]>(
    DEMO_MODE ? null : "/leagues",
    apiFetch,
    { shouldRetryOnError: false },
  );

  const rows = DEMO_MODE ? DEMO_LEAGUES : (data ?? []);
  const standings = DEMO_STANDINGS;

  // KPI türevleri (demo evreninden).
  const us = standings.find((s) => s.team === "Beşiktaş")!;
  const leader = standings[0];
  const gap = leader.pts - us.pts; // lidere fark
  const totalGoals = standings.reduce((a, s) => a + s.gf, 0);
  const avgGoals = (totalGoals / (standings.length * us.played / 2)).toFixed(2);
  const usWinPct = Math.round((us.win / us.played) * 100);

  // Lider yarışı için bar genişlikleri (en yüksek puan = %100).
  const maxPts = TITLE_RACE[0].pts;

  const right = (
    <>
      <div className="rc">
        <h3>Lider Yarışı <span className="tiny">İlk 4</span></h3>
        {TITLE_RACE.map((t) => {
          const mine = t.team === "Beşiktaş";
          return (
            <div key={t.team} style={{ marginBottom: 9 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 2 }}>
                <span style={{ fontWeight: mine ? 700 : 500, color: mine ? "var(--accent)" : "var(--ink)" }}>
                  {t.pos}. {t.team}
                </span>
                <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>{t.pts}</span>
              </div>
              <div className="mbar" style={{ margin: "2px 0 0" }}>
                <i style={{ width: `${Math.round((t.pts / maxPts) * 100)}%`, background: mine ? "var(--accent)" : "var(--dim)" }} />
              </div>
            </div>
          );
        })}
        <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 4, lineHeight: 1.5 }}>
          Beşiktaş lidere <b style={{ color: "var(--mid)" }}>{gap} puan</b> geride; 4 maç kaldı.
        </div>
      </div>

      <div className="rc">
        <h3>Beşiktaş Sezonu <span className="tiny">{us.played} maç</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut
            segments={[
              { value: us.win, color: "var(--low)" },
              { value: us.draw, color: "var(--mid)" },
              { value: us.loss, color: "var(--crit)" },
            ]}
            centerLabel={us.pts}
            centerSub="puan"
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            <LegendRow color="var(--low)" label="Galibiyet" value={us.win} />
            <LegendRow color="var(--mid)" label="Beraberlik" value={us.draw} />
            <LegendRow color="var(--crit)" label="Mağlubiyet" value={us.loss} />
          </div>
        </div>
        <div className="stat" style={{ marginTop: 6 }}><span>Averaj</span><span className="sv" style={{ color: "var(--low)" }}>+{us.gf - us.ga}</span></div>
        <div className="stat"><span>Atılan / Yenen</span><span className="sv">{us.gf} / {us.ga}</span></div>
        <div className="stat"><span>Galibiyet oranı</span><span className="sv">%{usWinPct}</span></div>
      </div>

      <div className="rc">
        <h3>Sync Edilmiş Ligler <span className="tiny">{rows.length}</span></h3>
        {rows.map((l) => (
          <div
            className="alrt"
            key={l.external_id}
            onClick={() => router.push(`/leagues/${l.external_id}/teams`)}
            style={{ cursor: "pointer" }}
          >
            <span className="ai" style={{ background: "var(--accent)" }} />
            <div className="am"><b>{l.name}</b>
              <span className="tm">{l.country ?? "—"} · {l.season}/{l.season + 1}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/leagues"
      title="Ligler"
      sub="Süper Lig — 34. Hafta"
      desc="Sync edilmiş liglerin güncel puan durumu. Bir takıma tıkla → kadro/takım detayı."
      source="api_football"
      right={right}
    >
      {!DEMO_MODE && isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {!DEMO_MODE && error && <div className="pgdesc">Yüklenemedi ya da yetki yok.</div>}

      <div className="kpis">
        <div className="kpi"><div className="kl">Lig</div><div className="kn" style={{ fontSize: 20 }}>Süper Lig</div><div className="kd">Türkiye · 2025/26</div></div>
        <div className="kpi"><div className="kl">Hafta</div><div className="kn">34<span className="pct">/38</span></div><div className="kd">4 maç kaldı</div></div>
        <div className="kpi"><div className="kl">Beşiktaş</div><div className="kn" style={{ color: "var(--accent)" }}>{us.pos}.</div><div className="kd"><span className="u">{us.pts} puan</span> · lidere {gap}</div></div>
        <div className="kpi"><div className="kl">Averaj</div><div className="kn" style={{ color: "var(--low)" }}>+{us.gf - us.ga}</div><div className="kd">{us.gf} attı · {us.ga} yedi</div></div>
        <div className="kpi"><div className="kl">Maç Başı Gol</div><div className="kn">{avgGoals}</div><div className="kd">lig geneli ort.</div></div>
      </div>

      <div className="st" style={{ marginTop: 4 }}>
        <h2>Puan Durumu</h2>
        <span className="ep">{DEMO_MODE ? "Süper Lig · 18 takım" : "GET /leagues"}</span>
      </div>
      <div className="tbl">
        <table>
          <thead>
            <tr>
              <th className="c">#</th>
              <th>Takım</th>
              <th className="c">O</th>
              <th className="c">G</th>
              <th className="c">B</th>
              <th className="c">M</th>
              <th className="c">A</th>
              <th>Form</th>
              <th className="r">P</th>
            </tr>
          </thead>
          <tbody>
            {standings.map((s) => {
              const mine = s.team === "Beşiktaş";
              const zc = zoneColor(s.pos);
              const zl = zoneLabel(s.pos);
              return (
                <tr
                  key={s.team}
                  onClick={() => router.push(`/leagues/1001/teams`)}
                  style={{ cursor: "pointer", background: mine ? "var(--accent-lt)" : undefined }}
                >
                  <td className="c" style={{ position: "relative" }}>
                    <span style={{ position: "absolute", left: 0, top: 6, bottom: 6, width: 3, borderRadius: 3, background: zc }} />
                    <span className="pnum" style={{ color: s.pos <= 2 ? "var(--low)" : s.pos >= 16 ? "var(--crit)" : "var(--dim)" }}>{s.pos}</span>
                  </td>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, marginRight: 4 }}>
                      <Crest team={s.team} size={20} />
                      <span className="nm" style={{ color: mine ? "var(--accent)" : "var(--ink)" }}>{s.team}</span>
                    </span>
                    {zl && (
                      <span className="risk" style={{ marginLeft: 8, color: zc, padding: "2px 8px", fontSize: 10.5 }}>
                        <span className="rd" style={{ background: zc }} />{zl}
                      </span>
                    )}
                  </td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{s.played}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--low)" }}>{s.win}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--mid)" }}>{s.draw}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--crit)" }}>{s.loss}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: (s.gf - s.ga) >= 0 ? "var(--low)" : "var(--crit)" }}>
                    {(s.gf - s.ga) >= 0 ? "+" : ""}{s.gf - s.ga}
                  </td>
                  <td><FormDots form={s.form} /></td>
                  <td className="r" style={{ color: mine ? "var(--accent)" : "var(--ink)", fontSize: 13 }}>{s.pts}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 12, fontSize: 11.5, color: "var(--dim)" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><i style={{ width: 10, height: 10, borderRadius: 3, background: "var(--low)" }} /> Şampiyonluk / kupa</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><i style={{ width: 10, height: 10, borderRadius: 3, background: "var(--accent)" }} /> Avrupa kupaları</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><i style={{ width: 10, height: 10, borderRadius: 3, background: "var(--crit)" }} /> Düşme hattı</span>
      </div>
    </ConsoleShell>
  );
}
