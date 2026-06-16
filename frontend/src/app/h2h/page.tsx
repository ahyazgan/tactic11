"use client";

/**
 * Kafa Kafaya (H2H) — iki takımın geçmiş karşılaşma özeti. ConsoleShell çatısında.
 *
 * DEMO_MODE açıkken: canlı API'ye dokunmaz; Beşiktaş vs Antalyaspor için zengin
 * geçmiş-karşılaşma dökümü (skor, gol dağılımı, son maçlar, form, kıyas barları)
 * gösterir. Demo kapalıyken: lig → takım kademeli seçim + /teams/{a}/vs/{b}.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { DEMO_CLUB, DEMO_OPPONENT } from "@/lib/demo-data";
import { ConsoleShell } from "../_console/shell";
import { LoadingState, ErrorState } from "@/components/ui";

interface League { external_id: number; name: string }
interface Team { external_id: number; name: string }
interface H2HResult {
  value?: {
    team_a_external_id: number;
    team_b_external_id: number;
    matches_played: number;
    team_a_wins: number;
    draws: number;
    team_b_wins: number;
    team_a_goals: number;
    team_b_goals: number;
  };
  commentary?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// DEMO EVRENİ — Beşiktaş vs Antalyaspor kafa kafaya geçmişi (inline, paylaşımsız)
// ─────────────────────────────────────────────────────────────────────────────

type DemoOutcome = "G" | "B" | "M"; // Beşiktaş açısından: Galibiyet / Beraberlik / Mağlubiyet

interface DemoH2HMatch {
  date: string;
  competition: string;
  venue: "Ev" | "Dep";
  scoreHome: number;  // Beşiktaş gol
  scoreAway: number;  // Antalyaspor gol
  outcome: DemoOutcome;
  scorers: string;
}

// Eskiden yeniye değil — yeniden eskiye (en üst = en yeni). 12 karşılaşma.
const DEMO_MATCHES: DemoH2HMatch[] = [
  { date: "2026-01-26", competition: "Süper Lig — 18. Hafta", venue: "Dep", scoreHome: 2, scoreAway: 2, outcome: "B", scorers: "Oh Hyeon-Gyu, Milot Rashica" },
  { date: "2025-09-14", competition: "Süper Lig — 5. Hafta",  venue: "Ev",  scoreHome: 3, scoreAway: 1, outcome: "G", scorers: "Oh Hyeon-Gyu ×2, Orkun Kökçü" },
  { date: "2025-04-06", competition: "Türkiye Kupası — Çeyrek", venue: "Ev", scoreHome: 1, scoreAway: 0, outcome: "G", scorers: "Milot Rashica" },
  { date: "2025-02-09", competition: "Süper Lig — 22. Hafta", venue: "Dep", scoreHome: 0, scoreAway: 1, outcome: "M", scorers: "—" },
  { date: "2024-10-20", competition: "Süper Lig — 9. Hafta",  venue: "Ev",  scoreHome: 2, scoreAway: 0, outcome: "G", scorers: "Orkun Kökçü, Oh Hyeon-Gyu" },
  { date: "2024-05-12", competition: "Süper Lig — 33. Hafta", venue: "Dep", scoreHome: 1, scoreAway: 1, outcome: "B", scorers: "Salih Uçan" },
  { date: "2024-01-21", competition: "Süper Lig — 19. Hafta", venue: "Ev",  scoreHome: 0, scoreAway: 2, outcome: "M", scorers: "—" },
  { date: "2023-09-24", competition: "Süper Lig — 6. Hafta",  venue: "Dep", scoreHome: 2, scoreAway: 1, outcome: "G", scorers: "Oh Hyeon-Gyu, Cengiz Ünder" },
  { date: "2023-03-05", competition: "Türkiye Kupası — Yarı", venue: "Dep", scoreHome: 1, scoreAway: 1, outcome: "B", scorers: "Milot Rashica" },
  { date: "2022-11-13", competition: "Süper Lig — 13. Hafta", venue: "Ev",  scoreHome: 4, scoreAway: 1, outcome: "G", scorers: "Oh Hyeon-Gyu ×2, Orkun Kökçü, Milot Rashica" },
  { date: "2022-04-30", competition: "Süper Lig — 32. Hafta", venue: "Dep", scoreHome: 1, scoreAway: 2, outcome: "M", scorers: "Orkun Kökçü" },
  { date: "2021-12-04", competition: "Süper Lig — 15. Hafta", venue: "Ev",  scoreHome: 2, scoreAway: 2, outcome: "B", scorers: "Cengiz Ünder, Oh Hyeon-Gyu" },
];

const OUTCOME_VAR: Record<DemoOutcome, string> = {
  G: "var(--low)",
  B: "var(--mid)",
  M: "var(--crit)",
};
const OUTCOME_BG: Record<DemoOutcome, string> = {
  G: "var(--low-bg)",
  B: "var(--mid-bg)",
  M: "var(--crit-bg)",
};

// Toplu döküm (DEMO_MATCHES'ten türetilir).
const demoTotals = DEMO_MATCHES.reduce(
  (a, m) => {
    a.played += 1;
    a.goalsA += m.scoreHome;
    a.goalsB += m.scoreAway;
    if (m.outcome === "G") a.winsA += 1;
    else if (m.outcome === "B") a.draws += 1;
    else a.winsB += 1;
    return a;
  },
  { played: 0, winsA: 0, draws: 0, winsB: 0, goalsA: 0, goalsB: 0 },
);

// Son 6 maç formu (en yeni → en eski), Beşiktaş açısından.
const demoForm = DEMO_MATCHES.slice(0, 6).map((m) => m.outcome);

// Kıyas barları — iki takımı yan yana koyan istatistikler (sahte ama tutarlı).
interface CompareStat { label: string; a: number; b: number; unit?: string; betterHigh?: boolean }
const demoCompareStats: CompareStat[] = [
  { label: "Maç başı gol", a: +(demoTotals.goalsA / demoTotals.played).toFixed(2), b: +(demoTotals.goalsB / demoTotals.played).toFixed(2), betterHigh: true },
  { label: "Maç başı şut", a: 14.2, b: 11.6, betterHigh: true },
  { label: "Topa sahip olma", a: 56, b: 44, unit: "%", betterHigh: true },
  { label: "Maç başı xG", a: 1.71, b: 1.28, betterHigh: true },
  { label: "Clean sheet oranı", a: 33, b: 25, unit: "%", betterHigh: true },
  { label: "Duran toptan gol", a: 38, b: 29, unit: "%", betterHigh: true },
];

const demoCommentary = `${DEMO_CLUB}, son 12 karşılaşmanın 5'ini kazandı; ${DEMO_OPPONENT} 3 galibiyette kaldı, 4 maç berabere bitti. ` +
  `Ev sahibi olarak ${DEMO_CLUB} belirgin üstün (6 maçta 5 yenilmezlik). Gol üretiminde maç başı 1.58'e karşı 1.17 önde. ` +
  `Son 3 resmi maçın 2'sini ${DEMO_CLUB} kazandı — momentum lehte. Süper Lig 34. Hafta randevusunda model galibiyet olasılığını %48 veriyor.`;

// ─────────────────────────────────────────────────────────────────────────────

const selStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 9px",
  borderRadius: "7px",
  fontFamily: "inherit",
  minWidth: "140px",
};

function Sel({ value, onChange, options, placeholder, disabled }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; placeholder: string; disabled?: boolean;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} style={{ ...selStyle, opacity: disabled ? 0.5 : 1 }}>
      <option value="">{placeholder}</option>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

/** Form rozeti (G/B/M). */
function FormPill({ o }: { o: DemoOutcome }) {
  return (
    <span
      title={o === "G" ? "Galibiyet" : o === "B" ? "Beraberlik" : "Mağlubiyet"}
      style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: 26, height: 26, borderRadius: 7, fontSize: 12, fontWeight: 700,
        color: OUTCOME_VAR[o], background: OUTCOME_BG[o],
        fontFamily: "JetBrains Mono",
      }}
    >
      {o}
    </span>
  );
}

/** İki takımı yan yana koyan kıyas barı. */
function CompareRow({ s, aName, bName }: { s: CompareStat; aName: string; bName: string }) {
  const total = s.a + s.b || 1;
  const aPct = Math.round((s.a / total) * 100);
  const aBetter = s.betterHigh ? s.a >= s.b : s.a <= s.b;
  return (
    <div style={{ padding: "9px 0", borderBottom: "1px solid var(--border)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 5, fontSize: 12.5 }}>
        <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: aBetter ? "var(--low)" : "var(--muted)" }} title={aName}>
          {s.a}{s.unit ?? ""}
        </span>
        <span style={{ color: "var(--dim)", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.4 }}>{s.label}</span>
        <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: !aBetter ? "var(--high)" : "var(--muted)" }} title={bName}>
          {s.b}{s.unit ?? ""}
        </span>
      </div>
      <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", background: "var(--surface2)", gap: 2 }}>
        <i style={{ width: `${aPct}%`, background: "var(--accent)", borderRadius: 3, display: "block", height: "100%" }} />
        <i style={{ width: `${100 - aPct}%`, background: "var(--high)", borderRadius: 3, display: "block", height: "100%" }} />
      </div>
    </div>
  );
}

export default function H2HConsolePage() {
  const aName = DEMO_CLUB;
  const bName = DEMO_OPPONENT;

  const [leagueA, setLeagueA] = React.useState("");
  const [leagueB, setLeagueB] = React.useState("");
  const [teamA, setTeamA] = React.useState("");
  const [teamB, setTeamB] = React.useState("");
  const [go, setGo] = React.useState(false);

  // Demo modunda canlı API'ye dokunma (null key → istek atılmaz).
  const { data: leagues } = useSWR<League[]>(DEMO_MODE ? null : "/leagues", apiFetch, { shouldRetryOnError: false });
  const { data: teamsA } = useSWR<Team[]>(!DEMO_MODE && leagueA ? `/teams/${leagueA}` : null, apiFetch, { shouldRetryOnError: false });
  const { data: teamsB } = useSWR<Team[]>(!DEMO_MODE && leagueB ? `/teams/${leagueB}` : null, apiFetch, { shouldRetryOnError: false });
  const { data: h2h, error, isLoading } = useSWR<H2HResult>(
    !DEMO_MODE && go && teamA && teamB ? `/teams/${teamA}/vs/${teamB}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  const liveTeamAName = teamsA?.find((t) => String(t.external_id) === teamA)?.name ?? "Takım A";
  const liveTeamBName = teamsB?.find((t) => String(t.external_id) === teamB)?.name ?? "Takım B";
  const lgOpts = leagues?.map((l) => ({ value: String(l.external_id), label: l.name })) ?? [];
  const v = h2h?.value;

  // ── Sağ kolon ──
  const right = DEMO_MODE ? (
    <>
      <div className="rc">
        <h3>Form <span className="tiny">son 6 maç</span></h3>
        <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
          {demoForm.map((o, i) => <FormPill key={i} o={o} />)}
        </div>
        <div style={{ fontSize: 11.5, color: "var(--dim)", lineHeight: 1.5 }}>
          En yeni soldan. {aName} açısından — son 3 resmi maçın 2'si galibiyet.
        </div>
      </div>

      <div className="rc">
        <h3>Maç Kıyası <span className="tiny">son 12 maç ort.</span></h3>
        {demoCompareStats.slice(0, 4).map((s) => (
          <CompareRow key={s.label} s={s} aName={aName} bName={bName} />
        ))}
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--dim)", marginTop: 8 }}>
          <span style={{ color: "var(--accent)", fontWeight: 600 }}>{aName}</span>
          <span style={{ color: "var(--high)", fontWeight: 600 }}>{bName}</span>
        </div>
      </div>

      <div className="rc">
        <h3>Yorum</h3>
        <div style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.55 }}>{demoCommentary}</div>
      </div>
    </>
  ) : (
    <div className="rc">
      <h3>Nasıl Kullanılır?</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
        Her iki takım için önce lig, sonra takım seç; ardından <b style={{ color: "var(--ink)" }}>Karşılaştır</b>.
        Geçmiş karşılaşmaların galibiyet/beraberlik/gol dökümünü gösterir.
      </div>
      {v && h2h?.commentary && (
        <div style={{ fontSize: "12px", color: "var(--ink)", marginTop: 12, lineHeight: 1.5, borderTop: "1px solid var(--line)", paddingTop: 10 }}>{h2h.commentary}</div>
      )}
    </div>
  );

  // ─────────────────────────────────────────────────────────────────────────
  // DEMO GÖRÜNÜMÜ
  // ─────────────────────────────────────────────────────────────────────────
  if (DEMO_MODE) {
    const t = demoTotals;
    const winPctA = Math.round((t.winsA / t.played) * 100);
    const avgA = (t.goalsA / t.played).toFixed(2);
    const avgB = (t.goalsB / t.played).toFixed(2);
    // Galibiyet barı oranları (G/B/M)
    const segG = Math.round((t.winsA / t.played) * 100);
    const segB = Math.round((t.draws / t.played) * 100);
    const segM = 100 - segG - segB;

    return (
      <ConsoleShell
        active="/h2h"
        title="Kafa Kafaya"
        sub="Geçmiş karşılaşmalar"
        desc={`${aName} vs ${bName} — tarihsel karşılaşma özeti: galibiyet, beraberlik, gol dağılımı ve form.`}
        right={right}
      >
        {/* Eşleşme başlığı */}
        <div
          className="rc"
          style={{ marginTop: 0, marginBottom: 14, display: "flex", alignItems: "center", justifyContent: "center", gap: 20, padding: "16px 14px" }}
        >
          <div style={{ textAlign: "center", flex: 1 }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: "var(--ink)" }}>{aName}</div>
            <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 2 }}>ev sahibi avantajı</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 800, fontFamily: "JetBrains Mono", color: "var(--ink)", letterSpacing: -1 }}>
              {t.winsA}<span style={{ color: "var(--dim)", margin: "0 6px" }}>-</span>{t.draws}<span style={{ color: "var(--dim)", margin: "0 6px" }}>-</span>{t.winsB}
            </div>
            <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5 }}>G · B · M</div>
          </div>
          <div style={{ textAlign: "center", flex: 1 }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: "var(--muted)" }}>{bName}</div>
            <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 2 }}>Süper Lig — 34. Hafta</div>
          </div>
        </div>

        {/* KPI şeridi */}
        <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
          <div className="kpi"><div className="kl">Toplam Maç</div><div className="kn">{t.played}</div><div className="kd">resmi karşılaşma</div></div>
          <div className="kpi"><div className="kl">{aName}</div><div className="kn" style={{ color: "var(--low)" }}>{t.winsA}</div><div className="kd">galibiyet · {t.goalsA} gol</div></div>
          <div className="kpi"><div className="kl">Beraberlik</div><div className="kn" style={{ color: "var(--mid)" }}>{t.draws}</div><div className="kd">eşit sonuç</div></div>
          <div className="kpi"><div className="kl">{bName}</div><div className="kn" style={{ color: "var(--high)" }}>{t.winsB}</div><div className="kd">galibiyet · {t.goalsB} gol</div></div>
          <div className="kpi"><div className="kl">Galibiyet Oranı</div><div className="kn" style={{ color: "var(--low)" }}>{winPctA}<span className="pct">%</span></div><div className="kd">{aName} lehine</div></div>
        </div>

        {/* Sonuç dağılımı barı */}
        <div className="st"><h2>Sonuç Dağılımı</h2><span className="ep">{aName} açısından</span></div>
        <div className="rc" style={{ margin: 0, marginBottom: 4 }}>
          <div className="probbar" style={{ height: 10, marginBottom: 10 }}>
            <i style={{ width: `${segG}%`, background: "var(--low)" }} />
            <i style={{ width: `${segB}%`, background: "var(--mid)" }} />
            <i style={{ width: `${segM}%`, background: "var(--crit)" }} />
          </div>
          <div className="probleg">
            <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>%{segG}</div><div className="pl">Galibiyet</div></div>
            <div className="pi"><div className="pv" style={{ color: "var(--mid)" }}>%{segB}</div><div className="pl">Berabere</div></div>
            <div className="pi"><div className="pv" style={{ color: "var(--crit)" }}>%{segM}</div><div className="pl">Mağlubiyet</div></div>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 12, fontSize: 12, color: "var(--muted)" }}>
            <span>Maç başı gol — <b style={{ color: "var(--low)", fontFamily: "JetBrains Mono" }}>{avgA}</b> / <b style={{ color: "var(--high)", fontFamily: "JetBrains Mono" }}>{avgB}</b></span>
            <span>Toplam gol — <b style={{ color: "var(--ink)", fontFamily: "JetBrains Mono" }}>{t.goalsA + t.goalsB}</b></span>
          </div>
        </div>

        {/* Detaylı kıyas (full genişlik) */}
        <div className="st"><h2>İstatistik Kıyası</h2><span className="ep">son 12 maç ortalaması</span></div>
        <div className="rc" style={{ margin: 0 }}>
          {demoCompareStats.map((s) => (
            <CompareRow key={s.label} s={s} aName={aName} bName={bName} />
          ))}
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--dim)", marginTop: 10 }}>
            <span style={{ color: "var(--accent)", fontWeight: 600 }}>{aName}</span>
            <span style={{ color: "var(--high)", fontWeight: 600 }}>{bName}</span>
          </div>
        </div>

        {/* Geçmiş maçlar tablosu */}
        <div className="st"><h2>Son Karşılaşmalar</h2><span className="ep">{DEMO_MATCHES.length} maç</span></div>
        <div className="tbl">
          <table>
            <thead><tr>
              <th>Tarih</th><th>Turnuva</th><th className="c">Saha</th>
              <th className="c">Skor</th><th className="c">Sonuç</th><th>Goller ({aName})</th>
            </tr></thead>
            <tbody>
              {DEMO_MATCHES.map((m, i) => (
                <tr key={i}>
                  <td style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11.5 }}>{m.date}</td>
                  <td>{m.competition}</td>
                  <td className="c"><span className="pos">{m.venue}</span></td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: "var(--ink)" }}>{m.scoreHome}–{m.scoreAway}</td>
                  <td className="c">
                    <span className="risk" style={{ color: OUTCOME_VAR[m.outcome], background: OUTCOME_BG[m.outcome] }}>
                      <span className="rd" style={{ background: OUTCOME_VAR[m.outcome] }} />
                      {m.outcome === "G" ? "Galibiyet" : m.outcome === "B" ? "Berabere" : "Mağlubiyet"}
                    </span>
                  </td>
                  <td style={{ color: m.scorers === "—" ? "var(--dim)" : "var(--muted)", fontSize: 12 }}>{m.scorers}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ConsoleShell>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // CANLI GÖRÜNÜM (demo kapalı) — orijinal seçim akışı
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <ConsoleShell
      active="/h2h"
      title="Kafa Kafaya"
      sub="Geçmiş karşılaşmalar"
      desc="İki takımın tarihsel karşılaşma özeti — galibiyet, beraberlik, gol dağılımı."
      source="api_football"
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}><h2>Takım Seç</h2></div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--muted)", marginBottom: 6 }}>Takım A</div>
          <div style={{ display: "flex", gap: 6 }}>
            <Sel value={leagueA} onChange={(x) => { setLeagueA(x); setTeamA(""); }} options={lgOpts} placeholder="Lig" />
            <Sel value={teamA} onChange={setTeamA} options={teamsA?.map((t) => ({ value: String(t.external_id), label: t.name })) ?? []} placeholder="Takım" disabled={!leagueA} />
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--muted)", marginBottom: 6 }}>Takım B</div>
          <div style={{ display: "flex", gap: 6 }}>
            <Sel value={leagueB} onChange={(x) => { setLeagueB(x); setTeamB(""); }} options={lgOpts} placeholder="Lig" />
            <Sel value={teamB} onChange={setTeamB} options={teamsB?.map((t) => ({ value: String(t.external_id), label: t.name })) ?? []} placeholder="Takım" disabled={!leagueB} />
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "flex-end" }}>
          <button type="button" onClick={() => setGo(true)} disabled={!teamA || !teamB || teamA === teamB} style={{ ...selStyle, minWidth: 0, cursor: "pointer", color: "var(--ink)", background: "var(--panel3)", opacity: !teamA || !teamB || teamA === teamB ? 0.5 : 1 }}>Karşılaştır</button>
        </div>
      </div>

      {go && isLoading && <LoadingState />}
      {error && <ErrorState title="Yüklenemedi ya da yetki yok." />}

      {v && (
        <>
          <div className="st"><h2>{liveTeamAName} vs {liveTeamBName}</h2><span className="ep">{v.matches_played} maç</span></div>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
            <div className="kpi"><div className="kl">{liveTeamAName}</div><div className="kn" style={{ color: "var(--low)" }}>{v.team_a_wins}</div><div className="kd">{v.team_a_goals} gol</div></div>
            <div className="kpi"><div className="kl">Beraberlik</div><div className="kn" style={{ color: "var(--mid)" }}>{v.draws}</div><div className="kd">eşit</div></div>
            <div className="kpi"><div className="kl">{liveTeamBName}</div><div className="kn" style={{ color: "var(--high)" }}>{v.team_b_wins}</div><div className="kd">{v.team_b_goals} gol</div></div>
          </div>
          <div className="pgdesc">Toplam {v.matches_played} maç oynandı.</div>
        </>
      )}
    </ConsoleShell>
  );
}
