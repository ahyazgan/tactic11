"use client";

/**
 * Maç — Fikstür & Sonuçlar. ConsoleShell çatısını kullanır.
 * Takım programındaki yaklaşan maçlar (fikstür) + son sonuçlar + form serisi +
 * sıradaki maç kartı. Gerçek veri: GET /teams/{id}/schedule.
 *
 * DEMO_MODE açıkken canlı API'ye hiç dokunulmaz; "Beşiktaş" evreninden dolu,
 * inandırıcı bir fikstür/sonuç listesi gösterilir (spinner / boş tablo / ID
 * prompt'u olmaz). Demo kapatılırsa eski canlı-API davranışına döner.
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { DEMO_CLUB } from "@/lib/demo-data";
import { Crest } from "@/lib/teams";
import { SM_TEAM_ID, type SmMatch, type SmScheduleResp } from "@/lib/sportmonks";
import { ConsoleShell } from "../_console/shell";

interface ScheduleResp {
  value?: { next_kickoffs?: string[] };
}

// --------------------------------------------------------------------------- //
// DEMO EVRENİ — "Beşiktaş" fikstür & sonuçlar (yalnız bu sayfada, inline)
// --------------------------------------------------------------------------- //

type DemoResult = "G" | "B" | "M";

interface DemoFixture {
  id: number;
  date: string;        // gösterim için hazır TR tarih
  iso: string;         // sıralama/saat için ISO
  time: string;
  opponent: string;
  venue: "İç Saha" | "Deplasman";
  competition: string;
  win: number;         // 0..1 (model tahmini)
  draw: number;
  loss: number;
}

interface DemoPast {
  id: number;
  date: string;
  opponent: string;
  venue: "İç Saha" | "Deplasman";
  competition: string;
  scoreHome: number;
  scoreAway: number;
  result: DemoResult;
  xgFor: number;
  xgAgainst: number;
}

// Sıradaki + yaklaşan maçlar (kurgusal Süper Lig sezon sonu)
const DEMO_FIXTURES: DemoFixture[] = [
  { id: 9001, date: "08 Haz Paz", iso: "2026-06-08T20:00:00", time: "20:00", opponent: "Antalyaspor", venue: "İç Saha", competition: "Süper Lig — 34. Hafta", win: 0.48, draw: 0.27, loss: 0.25 },
  { id: 9002, date: "12 Haz Per", iso: "2026-06-12T19:00:00", time: "19:00", opponent: "Kayserispor", venue: "Deplasman", competition: "Türkiye Kupası — Yarı Final", win: 0.41, draw: 0.24, loss: 0.35 },
  { id: 9003, date: "15 Haz Paz", iso: "2026-06-15T21:30:00", time: "21:30", opponent: "Konyaspor", venue: "İç Saha", competition: "Süper Lig — 35. Hafta", win: 0.55, draw: 0.26, loss: 0.19 },
  { id: 9004, date: "19 Haz Cum", iso: "2026-06-19T20:45:00", time: "20:45", opponent: "Trabzonspor", venue: "Deplasman", competition: "Süper Lig — 36. Hafta", win: 0.38, draw: 0.28, loss: 0.34 },
  { id: 9005, date: "23 Haz Sal", iso: "2026-06-23T20:00:00", time: "20:00", opponent: "Galatasaray", venue: "İç Saha", competition: "Türkiye Kupası — Final", win: 0.46, draw: 0.25, loss: 0.29 },
  { id: 9006, date: "27 Haz Cmt", iso: "2026-06-27T19:30:00", time: "19:30", opponent: "Göztepe", venue: "Deplasman", competition: "Süper Lig — 37. Hafta", win: 0.52, draw: 0.27, loss: 0.21 },
];

// Son sonuçlar (en yeni en üstte)
const DEMO_PAST: DemoPast[] = [
  { id: 8010, date: "04 Haz Çar", opponent: "Başakşehir", venue: "Deplasman", competition: "Süper Lig — 33. Hafta", scoreHome: 2, scoreAway: 1, result: "G", xgFor: 1.9, xgAgainst: 1.1 },
  { id: 8009, date: "31 May Cmt", opponent: "Fenerbahçe", venue: "İç Saha", competition: "Süper Lig — 32. Hafta", scoreHome: 3, scoreAway: 0, result: "G", xgFor: 2.6, xgAgainst: 0.6 },
  { id: 8008, date: "25 May Paz", opponent: "Kayserispor", venue: "Deplasman", competition: "Türkiye Kupası — Çeyrek", scoreHome: 1, scoreAway: 1, result: "B", xgFor: 1.3, xgAgainst: 1.2 },
  { id: 8007, date: "18 May Paz", opponent: "Trabzonspor", venue: "İç Saha", competition: "Süper Lig — 31. Hafta", scoreHome: 0, scoreAway: 2, result: "M", xgFor: 0.9, xgAgainst: 1.7 },
  { id: 8006, date: "11 May Paz", opponent: "Göztepe", venue: "Deplasman", competition: "Süper Lig — 30. Hafta", scoreHome: 2, scoreAway: 2, result: "B", xgFor: 2.1, xgAgainst: 1.8 },
  { id: 8005, date: "04 May Paz", opponent: "Konyaspor", venue: "İç Saha", competition: "Süper Lig — 29. Hafta", scoreHome: 1, scoreAway: 0, result: "G", xgFor: 1.4, xgAgainst: 0.8 },
  { id: 8004, date: "27 Nis Paz", opponent: "Galatasaray", venue: "Deplasman", competition: "Süper Lig — 28. Hafta", scoreHome: 3, scoreAway: 1, result: "G", xgFor: 2.3, xgAgainst: 1.0 },
  { id: 8003, date: "20 Nis Paz", opponent: "Başakşehir", venue: "İç Saha", competition: "Süper Lig — 27. Hafta", scoreHome: 0, scoreAway: 0, result: "B", xgFor: 1.1, xgAgainst: 0.9 },
];

const RESULT_VAR: Record<DemoResult, string> = {
  G: "var(--low)",
  B: "var(--mid)",
  M: "var(--crit)",
};
const RESULT_TXT: Record<DemoResult, string> = { G: "Galibiyet", B: "Berabere", M: "Mağlubiyet" };

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

function fmt(iso: string): { date: string; time: string } {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return { date: iso.slice(0, 10), time: iso.slice(11, 16) };
  return {
    date: d.toLocaleDateString("tr-TR", { day: "2-digit", month: "short", weekday: "short" }),
    time: d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
  };
}

/** Form serisinden (en eski→en yeni) basit xG fark sparkline'ı çiz. */
function FormSpark({ data }: { data: { xgFor: number; xgAgainst: number; result: DemoResult }[] }) {
  const w = 240;
  const h = 56;
  const pad = 6;
  const diffs = data.map((d) => d.xgFor - d.xgAgainst);
  const max = Math.max(1, ...diffs.map((v) => Math.abs(v)));
  const stepX = data.length > 1 ? (w - pad * 2) / (data.length - 1) : 0;
  const y = (v: number) => h / 2 - (v / max) * (h / 2 - pad);
  const pts = diffs.map((v, i) => `${pad + i * stepX},${y(v)}`).join(" ");

  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block" }}>
      <line x1={pad} y1={h / 2} x2={w - pad} y2={h / 2} stroke="var(--border)" strokeWidth={1} strokeDasharray="3 3" />
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {diffs.map((v, i) => (
        <circle key={i} cx={pad + i * stepX} cy={y(v)} r={3} fill={RESULT_VAR[data[i].result]} stroke="var(--white)" strokeWidth={1.5} />
      ))}
    </svg>
  );
}

export default function MatchesConsolePage() {
  const [team, setTeam] = React.useState(String(SM_TEAM_ID));
  const [search, setSearch] = React.useState(String(SM_TEAM_ID));

  // Demo modunda canlı API'ye dokunma; dolu mock fikstürü göster.
  const { data, error, isLoading } = useSWR<ScheduleResp>(
    DEMO_MODE ? null : team ? `/teams/${team}/schedule` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );
  // Canlı program — Sportmonks (/sm/schedule): bitenler + yaklaşanlar + adlar.
  // Erişim yoksa eski /teams/{id}/schedule davranışına düşer.
  const { data: smSched } = useSWR<SmScheduleResp>(
    DEMO_MODE ? null : team ? `/sm/schedule?team_id=${team}&last_n=10` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  // --- DEMO yolu ---
  if (DEMO_MODE) {
    const next = DEMO_FIXTURES[0];
    const recent = DEMO_PAST.slice(0, 5);
    const wins = DEMO_PAST.filter((p) => p.result === "G").length;
    const draws = DEMO_PAST.filter((p) => p.result === "B").length;
    const losses = DEMO_PAST.filter((p) => p.result === "M").length;
    const goalsFor = DEMO_PAST.reduce((a, p) => a + p.scoreHome, 0);
    const goalsAgainst = DEMO_PAST.reduce((a, p) => a + p.scoreAway, 0);
    const points = wins * 3 + draws;
    // Form: en yeni 5 maç, kronolojik (eski→yeni) sparkline + rozetler.
    const formChrono = [...recent].reverse();

    const right = (
      <>
        <div className="rc">
          <h3>Sıradaki Maç <span className="tiny">{next.date} · {next.time}</span></h3>
          <div className="nm-vs"><span className="t" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Crest team={DEMO_CLUB} size={18} />{DEMO_CLUB}</span><span className="x">vs</span><span className="t away" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>{next.opponent}<Crest team={next.opponent} size={18} /></span></div>
          <div className="nm-when">{next.competition} · {next.venue}</div>
          <div className="probbar">
            <i style={{ width: `${Math.round(next.win * 100)}%`, background: "var(--low)" }} />
            <i style={{ width: `${Math.round(next.draw * 100)}%`, background: "var(--dim)" }} />
            <i style={{ width: `${Math.round(next.loss * 100)}%`, background: "var(--high)" }} />
          </div>
          <div className="probleg">
            <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>%{Math.round(next.win * 100)}</div><div className="pl">Galibiyet</div></div>
            <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>%{Math.round(next.draw * 100)}</div><div className="pl">Berabere</div></div>
            <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>%{Math.round(next.loss * 100)}</div><div className="pl">Mağlubiyet</div></div>
          </div>
          <Link href={`/matches/${next.id}`} style={{ display: "block", marginTop: 12, textAlign: "center", color: "var(--accent)", fontSize: 12, fontWeight: 600, textDecoration: "none", background: "var(--accent-lt)", border: "1px solid var(--accent)", borderRadius: 8, padding: "7px 0" }}>Maç önizleme →</Link>
        </div>

        <div className="rc">
          <h3>Son 5 Maç Formu <span className="tiny">xG farkı</span></h3>
          <FormSpark data={formChrono} />
          <div style={{ display: "flex", gap: 5, justifyContent: "center", marginTop: 8 }}>
            {formChrono.map((p) => (
              <span key={p.id} style={{ width: 20, height: 20, borderRadius: 6, background: RESULT_VAR[p.result], color: "#fff", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>{p.result}</span>
            ))}
          </div>
        </div>

        <div className="rc">
          <h3>Sezon Özeti <span className="tiny">son {DEMO_PAST.length} maç</span></h3>
          <div className="stat"><span>Galibiyet / Berabere / Mağlubiyet</span><span className="sv">{wins}-{draws}-{losses}</span></div>
          <div className="stat"><span>Atılan / Yenen Gol</span><span className="sv">{goalsFor} / {goalsAgainst}</span></div>
          <div className="stat"><span>Averaj</span><span className="sv" style={{ color: goalsFor - goalsAgainst >= 0 ? "var(--low)" : "var(--crit)" }}>{goalsFor - goalsAgainst >= 0 ? "+" : ""}{goalsFor - goalsAgainst}</span></div>
          <div className="stat"><span>Toplanan Puan</span><span className="sv">{points}</span></div>
        </div>
      </>
    );

    return (
      <ConsoleShell
        active="/matches"
        title="Maç"
        sub="Fikstür & Sonuçlar"
        desc="Yaklaşan maçlar ve son sonuçlar. Bir maça tıklayarak önizleme ve plana geç."
        right={right}
      >
        <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
          <div className="kpi"><div className="kl">Sıradaki</div><div className="kn" style={{ fontSize: 18 }}>{next.opponent}</div><div className="kd">{next.date} · {next.venue.toLowerCase()}</div></div>
          <div className="kpi"><div className="kl">Yaklaşan</div><div className="kn">{DEMO_FIXTURES.length}</div><div className="kd">programda</div></div>
          <div className="kpi"><div className="kl">Galibiyet Olasılığı</div><div className="kn" style={{ color: "var(--low)" }}>%{Math.round(next.win * 100)}</div><div className="kd">model tahmini</div></div>
          <div className="kpi"><div className="kl">Son 8 Maç</div><div className="kn">{wins}<span className="pct">G</span> {draws}<span className="pct">B</span> {losses}<span className="pct">M</span></div><div className="kd">{points} puan</div></div>
          <div className="kpi"><div className="kl">Gol Averajı</div><div className="kn" style={{ color: goalsFor - goalsAgainst >= 0 ? "var(--low)" : "var(--crit)" }}>{goalsFor - goalsAgainst >= 0 ? "+" : ""}{goalsFor - goalsAgainst}</div><div className="kd">{goalsFor} atılan · {goalsAgainst} yenen</div></div>
        </div>

        <div className="st" style={{ marginTop: 4 }}><h2>Yaklaşan Maçlar</h2><span className="ep">Süper Lig · Türkiye Kupası</span></div>
        <div className="tbl">
          <table>
            <thead><tr>
              <th className="c">#</th><th>Tarih</th><th className="c">Saat</th><th>Eşleşme</th><th>Turnuva</th><th className="c">G / B / M</th><th className="r">Detay</th>
            </tr></thead>
            <tbody>
              {DEMO_FIXTURES.map((m, i) => (
                <tr key={m.id}>
                  <td className="pnum c">{i + 1}</td>
                  <td><span className="nm">{m.date}</span></td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{m.time}</td>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <span className="nm">{DEMO_CLUB}</span>
                      <span className="nat">vs</span>
                      <Crest team={m.opponent} size={16} />
                      <span className="nat">{m.opponent}</span>
                    </span>
                    <span className="pos" style={{ marginLeft: 8 }}>{m.venue === "İç Saha" ? "İÇ" : "DEP"}</span>
                  </td>
                  <td style={{ color: "var(--muted)", fontSize: 11.5 }}>{m.competition}</td>
                  <td className="c">
                    <span className="probbar" style={{ width: 70, display: "inline-flex", margin: 0, verticalAlign: "middle" }}>
                      <i style={{ width: `${Math.round(m.win * 100)}%`, background: "var(--low)" }} />
                      <i style={{ width: `${Math.round(m.draw * 100)}%`, background: "var(--dim)" }} />
                      <i style={{ width: `${Math.round(m.loss * 100)}%`, background: "var(--high)" }} />
                    </span>
                  </td>
                  <td className="r">
                    <Link href={`/matches/${m.id}`} style={{ color: "var(--accent)", textDecoration: "none", fontSize: 12, fontWeight: 600 }}>Detay →</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="st"><h2>Son Sonuçlar</h2><span className="ep">{wins}G · {draws}B · {losses}M</span></div>
        <div className="tbl">
          <table>
            <thead><tr>
              <th className="c">#</th><th>Tarih</th><th>Eşleşme</th><th>Turnuva</th><th className="c">Skor</th><th className="c">xG (lehte/aleyhte)</th><th className="r">Sonuç</th>
            </tr></thead>
            <tbody>
              {DEMO_PAST.map((m, i) => {
                const rv = RESULT_VAR[m.result];
                return (
                  <tr key={m.id}>
                    <td className="pnum c">{i + 1}</td>
                    <td><span className="nm">{m.date}</span></td>
                    <td>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                        <span className="nm">{DEMO_CLUB}</span>
                        <span className="nat">vs</span>
                        <Crest team={m.opponent} size={16} />
                        <span className="nat">{m.opponent}</span>
                      </span>
                      <span className="pos" style={{ marginLeft: 8 }}>{m.venue === "İç Saha" ? "İÇ" : "DEP"}</span>
                    </td>
                    <td style={{ color: "var(--muted)", fontSize: 11.5 }}>{m.competition}</td>
                    <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>{m.scoreHome}-{m.scoreAway}</td>
                    <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11.5 }}>{m.xgFor.toFixed(1)} / {m.xgAgainst.toFixed(1)}</td>
                    <td className="r">
                      <span className="risk" style={{ color: rv }}><span className="rd" style={{ background: rv, boxShadow: `0 0 7px ${rv}` }} />{RESULT_TXT[m.result]}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </ConsoleShell>
    );
  }

  // --- CANLI yol — Sportmonks programı (gerçek skor + takım adları) ---
  if (smSched && (smSched.finished.length > 0 || smSched.upcoming.length > 0)) {
    const tid = Number(team);
    const nameOf = (id: number) => smSched.team_names[String(id)] ?? `#${id}`;
    const resultFor = (m: SmMatch): DemoResult => {
      const hs = m.home_score ?? 0;
      const as = m.away_score ?? 0;
      if (hs === as) return "B";
      const weAreHome = m.home_team_external_id === tid;
      return (weAreHome ? hs > as : as > hs) ? "G" : "M";
    };
    const wins = smSched.finished.filter((m) => resultFor(m) === "G").length;
    const draws = smSched.finished.filter((m) => resultFor(m) === "B").length;
    const losses = smSched.finished.filter((m) => resultFor(m) === "M").length;
    const next = smSched.upcoming[0] ?? null;
    const nextF = next ? fmt(next.kickoff) : null;
    // Form rozetleri: en yeni 5 bitmiş maç, kronolojik (eski→yeni).
    const formChrono = [...smSched.finished.slice(0, 5)].reverse();

    const right = (
      <>
        <div className="rc">
          <h3>Sıradaki Maç <span className="tiny">{nextF ? `${nextF.date} · ${nextF.time}` : "—"}</span></h3>
          {next ? (
            <>
              <div className="nm-vs">
                <span className="t">{nameOf(next.home_team_external_id)}</span>
                <span className="x">vs</span>
                <span className="t away">{nameOf(next.away_team_external_id)}</span>
              </div>
              <div className="nm-when">{next.status === "NS" ? "Başlamadı" : next.status} · sezon {next.season}/{(next.season + 1) % 100}</div>
            </>
          ) : (
            <div className="nm-when">Yaklaşan maç yok (sezon arası olabilir).</div>
          )}
        </div>

        <div className="rc">
          <h3>Son {formChrono.length} Maç Formu <span className="tiny">CANLI</span></h3>
          <div style={{ display: "flex", gap: 5, justifyContent: "center", marginTop: 4 }}>
            {formChrono.map((m) => {
              const r = resultFor(m);
              return (
                <span key={m.external_id} title={`${nameOf(m.home_team_external_id)} ${m.home_score}-${m.away_score} ${nameOf(m.away_team_external_id)}`} style={{ width: 20, height: 20, borderRadius: 6, background: RESULT_VAR[r], color: "#fff", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>{r}</span>
              );
            })}
          </div>
          <div className="stat" style={{ marginTop: 10 }}><span>G / B / M</span><span className="sv">{wins}-{draws}-{losses}</span></div>
          <div className="stat"><span>Toplanan Puan</span><span className="sv">{wins * 3 + draws}</span></div>
        </div>
      </>
    );

    return (
      <ConsoleShell
        active="/matches"
        title="Maç"
        sub={`${nameOf(tid)} — Fikstür & Sonuçlar`}
        desc="Sportmonks canlı program: yaklaşan maçlar ve gerçek sonuçlar."
        right={right}
      >
        <div className="st" style={{ marginTop: 0 }}>
          <h2>Takım Programı</h2>
          <form onSubmit={(e) => { e.preventDefault(); setTeam(search.trim()); }} style={{ display: "flex", gap: 6 }}>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Takım ID" inputMode="numeric" style={inputStyle} />
            <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Getir</button>
          </form>
        </div>

        <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
          <div className="kpi"><div className="kl">Takım</div><div className="kn" style={{ fontSize: 18 }}>{nameOf(tid)}</div><div className="kd">Sportmonks #{tid}</div></div>
          <div className="kpi"><div className="kl">Yaklaşan</div><div className="kn">{smSched.upcoming.length}</div><div className="kd">programda</div></div>
          <div className="kpi"><div className="kl">Sıradaki</div><div className="kn" style={{ fontSize: 18 }}>{nextF ? nextF.date : "—"}</div><div className="kd">{nextF ? nextF.time : "tarih yok"}</div></div>
          <div className="kpi"><div className="kl">Son {smSched.finished.length} Maç</div><div className="kn">{wins}<span className="pct">G</span> {draws}<span className="pct">B</span> {losses}<span className="pct">M</span></div><div className="kd">{wins * 3 + draws} puan</div></div>
        </div>

        {smSched.upcoming.length > 0 && (
          <>
            <div className="st"><h2>Yaklaşan Maçlar</h2><span className="ep">GET /sm/schedule · CANLI</span></div>
            <div className="tbl">
              <table>
                <thead><tr>
                  <th className="c">#</th><th>Tarih</th><th className="c">Saat</th><th>Eşleşme</th><th className="r">Durum</th>
                </tr></thead>
                <tbody>
                  {smSched.upcoming.map((m, i) => {
                    const f = fmt(m.kickoff);
                    const home = m.home_team_external_id === tid;
                    return (
                      <tr key={m.external_id}>
                        <td className="pnum c">{i + 1}</td>
                        <td><span className="nm">{f.date}</span></td>
                        <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{f.time}</td>
                        <td>
                          <span className="nm">{nameOf(m.home_team_external_id)}</span>
                          <span className="nat" style={{ margin: "0 6px" }}>vs</span>
                          <span className="nat">{nameOf(m.away_team_external_id)}</span>
                          <span className="pos" style={{ marginLeft: 8 }}>{home ? "İÇ" : "DEP"}</span>
                        </td>
                        <td className="r" style={{ color: "var(--dim)", fontSize: 11.5 }}>{m.status === "NS" ? "Programda" : m.status}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        <div className="st"><h2>Son Sonuçlar</h2><span className="ep">{wins}G · {draws}B · {losses}M · CANLI</span></div>
        <div className="tbl">
          <table>
            <thead><tr>
              <th className="c">#</th><th>Tarih</th><th>Eşleşme</th><th className="c">Skor</th><th className="r">Sonuç</th>
            </tr></thead>
            <tbody>
              {smSched.finished.map((m, i) => {
                const f = fmt(m.kickoff);
                const r = resultFor(m);
                const rv = RESULT_VAR[r];
                const home = m.home_team_external_id === tid;
                return (
                  <tr key={m.external_id}>
                    <td className="pnum c">{i + 1}</td>
                    <td><span className="nm">{f.date}</span></td>
                    <td>
                      <span className="nm">{nameOf(m.home_team_external_id)}</span>
                      <span className="nat" style={{ margin: "0 6px" }}>vs</span>
                      <span className="nat">{nameOf(m.away_team_external_id)}</span>
                      <span className="pos" style={{ marginLeft: 8 }}>{home ? "İÇ" : "DEP"}</span>
                    </td>
                    <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>{m.home_score ?? "-"}-{m.away_score ?? "-"}</td>
                    <td className="r">
                      <span className="risk" style={{ color: rv }}><span className="rd" style={{ background: rv, boxShadow: `0 0 7px ${rv}` }} />{RESULT_TXT[r]}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </ConsoleShell>
    );
  }

  // --- CANLI yol (DEMO kapalı) — eski davranış ---
  const kickoffs = (data?.value?.next_kickoffs ?? []).filter(Boolean);
  const next = kickoffs[0];
  const nextF = next ? fmt(next) : null;

  const right = (
    <div className="rc">
      <h3>Sıradaki Maç <span className="tiny">Takım #{team}</span></h3>
      <div className="nm-vs"><span className="t">#{team}</span><span className="x">vs</span><span className="t away">—</span></div>
      <div className="nm-when">{nextF ? `${nextF.date} · ${nextF.time}` : "Program verisi yok"}</div>
      <div className="probbar">
        <i style={{ width: "34%", background: "var(--low)" }} />
        <i style={{ width: "33%", background: "var(--dim)" }} />
        <i style={{ width: "33%", background: "var(--high)" }} />
      </div>
      <div className="probleg">
        <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>—</div><div className="pl">Galibiyet</div></div>
        <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>—</div><div className="pl">Berabere</div></div>
        <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>—</div><div className="pl">Mağlubiyet</div></div>
      </div>
    </div>
  );

  return (
    <ConsoleShell
      active="/matches"
      title="Maç"
      sub="Yaklaşan program"
      desc="Takım programındaki yaklaşan maçlar. Detay için maça tıkla."
      source="api_football"
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Takım Programı</h2>
        <form onSubmit={(e) => { e.preventDefault(); setTeam(search.trim()); }} style={{ display: "flex", gap: 6 }}>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Takım ID" inputMode="numeric" style={inputStyle} />
          <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Getir</button>
        </form>
      </div>

      <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
        <div className="kpi"><div className="kl">Yaklaşan Maç</div><div className="kn">{kickoffs.length}</div><div className="kd">programda</div></div>
        <div className="kpi"><div className="kl">Sıradaki</div><div className="kn" style={{ fontSize: 18 }}>{nextF ? nextF.date : "—"}</div><div className="kd">{nextF ? nextF.time : "tarih yok"}</div></div>
        <div className="kpi"><div className="kl">Takım</div><div className="kn">#{team}</div><div className="kd">seçili</div></div>
      </div>

      {isLoading && <div className="pgdesc">Program yükleniyor…</div>}
      {error && <div className="pgdesc">Program verisi alınamadı (sync_league çalıştırıldı mı?).</div>}

      <div className="st"><h2>Yaklaşan Maçlar</h2><span className="ep">GET /teams/{team}/schedule</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th><th>Tarih</th><th className="c">Saat</th><th>Eşleşme</th><th className="r">Detay</th>
          </tr></thead>
          <tbody>
            {kickoffs.length === 0 && (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                Maç yok (backend bağlı değilse veya program boşsa).
              </td></tr>
            )}
            {kickoffs.map((iso, i) => {
              const f = fmt(iso);
              const mid = 1000 + i;
              return (
                <tr key={mid}>
                  <td className="pnum c">{i + 1}</td>
                  <td><span className="nm">{f.date}</span></td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{f.time}</td>
                  <td><span className="nm">#{team}</span> <span className="nat">vs —</span></td>
                  <td className="r">
                    <Link href={`/matches/${mid}`} style={{ color: "var(--low)", textDecoration: "none", fontSize: 12, fontWeight: 600 }}>Detay →</Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
