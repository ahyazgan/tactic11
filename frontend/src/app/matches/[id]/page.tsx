"use client";

/**
 * Maç Detayı / Hub — skor + dizilim + tahmin (G/B/M) + maç konsollarına geçiş.
 * ConsoleShell çatısında.
 *
 * DEMO_MODE açıkken canlı API'ye hiç dokunulmaz; "Beşiktaş vs Antalyaspor" evreninden
 * dolu, inandırıcı bir maç önizlemesi gösterilir (spinner / boş-state / takım-ID
 * prompt'u olmaz): tahmin, ilk 11 saha dizilimi, eşleşme avantajı, rakip zaafları
 * ve canlı/devre-arası/değişiklik konsollarına linkler. Demo kapatılırsa (DEMO_MODE
 * = false) eski canlı-API (GET /matches/{id}/predict) davranışına döner.
 */

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  demoSquad,
  demoNextMatch,
  demoMatchups,
  demoWeaknesses,
  DEMO_CLUB,
  DEMO_OPPONENT,
  type SquadPlayer,
} from "@/lib/demo-data";
import { ConsoleShell } from "../../_console/shell";

interface PredictResponse {
  value: {
    prob_home_win: number;
    prob_draw: number;
    prob_away_win: number;
    expected_home_goals: number;
    expected_away_goals: number;
    most_likely_score: [number, number];
  };
  confidence: { score: number; label: string; drivers: string[] } | null;
}

// --------------------------------------------------------------------------- //
// DEMO yardımcıları (yalnız bu sayfa)
// --------------------------------------------------------------------------- //

// Demo maç günü için beklenen goller + en olası skor (demoNextMatch ile tutarlı).
const DEMO_EXP_HOME = 1.74;
const DEMO_EXP_AWAY = 1.31;
const DEMO_MOST_LIKELY: [number, number] = [2, 1];

/** Bir mevkiden, kondisyonu en yüksek n oyuncuyu seç (ilk 11 + yedekler için). */
function pickByCondition(pos: SquadPlayer["position"], n: number): SquadPlayer[] {
  return demoSquad
    .filter((p) => p.position === pos)
    .sort((a, b) => b.condition - a.condition)
    .slice(0, n);
}

// 4-3-3 ilk 11 — her hat kondisyona göre.
const XI_GK = pickByCondition("GK", 1);
const XI_DF = pickByCondition("DF", 4);
const XI_MF = pickByCondition("MF", 3);
const XI_FW = pickByCondition("FW", 3);
const DEMO_XI: SquadPlayer[] = [...XI_GK, ...XI_DF, ...XI_MF, ...XI_FW];
const DEMO_XI_IDS = new Set(DEMO_XI.map((p) => p.player_id));
const DEMO_BENCH = demoSquad.filter((p) => !DEMO_XI_IDS.has(p.player_id)).slice(0, 7);

const RISK_VAR: Record<string, string> = {
  Kritik: "var(--crit)",
  Yüksek: "var(--high)",
  Orta: "var(--mid)",
  Düşük: "var(--low)",
};

function condColor(v: number): string {
  return v >= 85 ? "var(--low)" : v >= 72 ? "var(--mid)" : "var(--high)";
}

// Saha düzeni: her hat için yatay (%x) konumlar. dikey (%y) hat başına sabit.
const PITCH_ROWS: { y: number; players: SquadPlayer[] }[] = [
  { y: 90, players: XI_GK },
  { y: 70, players: XI_DF },
  { y: 45, players: XI_MF },
  { y: 20, players: XI_FW },
];

function xPositions(n: number): number[] {
  // Hattı eşit aralıklı yay (kenarlardan 14% pay bırak).
  if (n <= 1) return [50];
  const left = 14;
  const span = 100 - left * 2;
  return Array.from({ length: n }, (_, i) => left + (span * i) / (n - 1));
}

/** İlk 11 saha dizilimi — saf SVG, tema renkli. */
function PitchXI() {
  return (
    <div
      style={{
        position: "relative",
        background: "linear-gradient(180deg,#1f8a4c,#176b3b)",
        borderRadius: 12,
        border: "1px solid var(--border)",
        aspectRatio: "16 / 11",
        overflow: "hidden",
      }}
    >
      {/* Saha çizgileri */}
      <svg viewBox="0 0 160 110" preserveAspectRatio="none" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.5 }}>
        <rect x="3" y="3" width="154" height="104" fill="none" stroke="#fff" strokeWidth="0.8" />
        <line x1="3" y1="55" x2="157" y2="55" stroke="#fff" strokeWidth="0.8" />
        <circle cx="80" cy="55" r="13" fill="none" stroke="#fff" strokeWidth="0.8" />
        <rect x="48" y="3" width="64" height="20" fill="none" stroke="#fff" strokeWidth="0.8" />
        <rect x="48" y="87" width="64" height="20" fill="none" stroke="#fff" strokeWidth="0.8" />
        <rect x="66" y="3" width="28" height="8" fill="none" stroke="#fff" strokeWidth="0.8" />
        <rect x="66" y="99" width="28" height="8" fill="none" stroke="#fff" strokeWidth="0.8" />
      </svg>

      {/* Oyuncu jetonları */}
      {PITCH_ROWS.map((row) =>
        xPositions(row.players.length).map((x, i) => {
          const p = row.players[i];
          if (!p) return null;
          const crit = p.risk_label === "Kritik" || p.risk_label === "Yüksek";
          return (
            <div
              key={p.player_id}
              style={{
                position: "absolute",
                left: `${x}%`,
                top: `${row.y}%`,
                transform: "translate(-50%,-50%)",
                textAlign: "center",
                width: 64,
              }}
            >
              <div
                style={{
                  width: 30,
                  height: 30,
                  margin: "0 auto",
                  borderRadius: "50%",
                  background: "var(--white)",
                  border: `2px solid ${crit ? RISK_VAR[p.risk_label] : "var(--accent)"}`,
                  color: "var(--ink)",
                  fontWeight: 800,
                  fontSize: 12.5,
                  fontFamily: "JetBrains Mono",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  boxShadow: "0 1px 4px rgba(0,0,0,.35)",
                }}
              >
                {p.shirt}
              </div>
              <div
                style={{
                  marginTop: 3,
                  fontSize: 10,
                  fontWeight: 600,
                  color: "#fff",
                  textShadow: "0 1px 2px rgba(0,0,0,.6)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {p.player_name.split(" ").slice(-1)[0]}
              </div>
            </div>
          );
        }),
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// SAYFA
// --------------------------------------------------------------------------- //

export default function MatchDetailConsolePage() {
  const params = useParams<{ id: string }>();
  const matchId = params.id;

  if (DEMO_MODE) return <MatchDemo matchId={matchId} />;
  return <MatchLive matchId={matchId} />;
}

// --------------------------------------------------------------------------- //
// DEMO görünümü
// --------------------------------------------------------------------------- //

function MatchDemo({ matchId }: { matchId: string }) {
  const m = demoNextMatch;
  const winPct = Math.round(m.win * 100);
  const drawPct = Math.round(m.draw * 100);
  const lossPct = Math.round(m.loss * 100);

  const readyCount = demoSquad.filter((p) => p.risk_label === "Düşük").length;
  const criticalPlayer = demoSquad.find((p) => p.risk_label === "Kritik");
  const avgCond = Math.round(demoSquad.reduce((a, p) => a + p.condition, 0) / demoSquad.length);

  // Sub-konsol linkleri — demo'da takım-ID kapısı yok, hep aktif (id "demo" mock).
  const consoles = [
    { href: `/matches/${matchId}/live?my_team_id=demo&interval_seconds=5&max_minute=90`, label: "Canlı Maç Konsolu", desc: "WebSocket momentum + xG akışı + değişiklik önerisi", icon: "ti-ball-football" },
    { href: `/matches/${matchId}/halftime?my_team_id=demo`, label: "Devre Arası Brief", desc: "1. yarı 7 motor analizi + AI brief", icon: "ti-clipboard-list" },
    { href: `/matches/${matchId}/sub-chess?my_team_id=demo&current_minute=60`, label: "Değişiklik Senaryoları", desc: "Top-3 değişiklik ileri-projeksiyonu", icon: "ti-arrows-exchange" },
  ];

  const right = (
    <>
      <div className="rc">
        <h3>Maç Tahmini <span className="tiny">{m.competition.split("—")[1]?.trim() ?? ""}</span></h3>
        <div className="nm-vs"><span className="t">{DEMO_CLUB}</span><span className="x">vs</span><span className="t away">{DEMO_OPPONENT}</span></div>
        <div className="nm-when">{m.date} · {m.kickoff} · İç Saha</div>
        <div className="probbar">
          <i style={{ width: `${winPct}%`, background: "var(--low)" }} />
          <i style={{ width: `${drawPct}%`, background: "var(--dim)" }} />
          <i style={{ width: `${lossPct}%`, background: "var(--high)" }} />
        </div>
        <div className="probleg">
          <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>%{winPct}</div><div className="pl">Galibiyet</div></div>
          <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>%{drawPct}</div><div className="pl">Berabere</div></div>
          <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>%{lossPct}</div><div className="pl">Mağlubiyet</div></div>
        </div>
        <div className="stat" style={{ marginTop: 6 }}><span>Beklenen skor</span><span className="sv">{DEMO_EXP_HOME.toFixed(2)} - {DEMO_EXP_AWAY.toFixed(2)}</span></div>
        <div className="stat"><span>En olası skor</span><span className="sv">{DEMO_MOST_LIKELY[0]}-{DEMO_MOST_LIKELY[1]}</span></div>
      </div>

      <div className="rc">
        <h3>Maç Konsolları</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {consoles.map((c) => (
            <Link key={c.href} href={c.href} style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "9px 11px", textDecoration: "none" }}>
              <i className={`ti ${c.icon}`} style={{ fontSize: 18, color: "var(--accent)", flexShrink: 0 }} aria-hidden="true" />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink)" }}>{c.label}</div>
                <div style={{ fontSize: 11, color: "var(--muted)" }}>{c.desc}</div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {criticalPlayer && (
        <div className="rc">
          <h3>Maç Günü Uyarısı</h3>
          <div className="alrt">
            <span className="ai" style={{ background: "var(--crit)" }} />
            <div className="am"><b>{criticalPlayer.player_name}</b> (#{criticalPlayer.shirt}) · kritik risk
              <span className="tm">kondisyon {criticalPlayer.condition} · 60. dk sonrası değişiklik planla</span>
            </div>
          </div>
          <Link href={`/matches/${matchId}/sub-chess?my_team_id=demo&current_minute=60`} style={{ display: "block", marginTop: 10, textAlign: "center", color: "var(--accent)", fontSize: 12, fontWeight: 600, textDecoration: "none", background: "var(--accent-lt)", border: "1px solid var(--accent)", borderRadius: 8, padding: "7px 0" }}>Değişiklik senaryoları →</Link>
        </div>
      )}
    </>
  );

  return (
    <ConsoleShell
      active="/matches"
      title={`${DEMO_CLUB} — ${DEMO_OPPONENT}`}
      sub={`Maç #${matchId} · önizleme`}
      desc="Maç tahmini (G/B/M), ilk 11 dizilimi, eşleşme avantajı ve canlı maç konsollarına geçiş."
      right={right}
    >
      <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
        <div className="kpi"><div className="kl">Galibiyet Olasılığı</div><div className="kn" style={{ color: "var(--low)" }}>{winPct}<span className="pct">%</span></div><div className="kd">model tahmini</div></div>
        <div className="kpi"><div className="kl">Beklenen Skor</div><div className="kn" style={{ fontSize: 20 }}>{DEMO_EXP_HOME.toFixed(1)}-{DEMO_EXP_AWAY.toFixed(1)}</div><div className="kd">en olası {DEMO_MOST_LIKELY[0]}-{DEMO_MOST_LIKELY[1]}</div></div>
        <div className="kpi"><div className="kl">Başlama</div><div className="kn" style={{ fontSize: 20 }}>{m.kickoff}</div><div className="kd">{m.date} · iç saha</div></div>
        <div className="kpi"><div className="kl">Sahaya Hazır</div><div className="kn" style={{ color: "var(--low)" }}>{readyCount}<span className="pct">/{demoSquad.length}</span></div><div className="kd">ort. kondisyon %{avgCond}</div></div>
        <div className="kpi"><div className="kl">Kritik Risk</div><div className="kn" style={{ color: "var(--crit)" }}>{demoSquad.filter((p) => p.risk_label === "Kritik").length}</div><div className="kd">{criticalPlayer ? `${criticalPlayer.player_name} (#${criticalPlayer.shirt})` : "yok"}</div></div>
      </div>

      <div className="st"><h2>Tahmin Dağılımı</h2><span className="ep">güven: orta (74)</span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <div className="probbar" style={{ height: 12, marginBottom: 12 }}>
          <i style={{ width: `${winPct}%`, background: "var(--low)" }} />
          <i style={{ width: `${drawPct}%`, background: "var(--dim)" }} />
          <i style={{ width: `${lossPct}%`, background: "var(--high)" }} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
          <div style={{ textAlign: "center" }}><div style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 22, color: "var(--low)" }}>%{winPct}</div><div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.4 }}>{DEMO_CLUB} galibiyeti</div></div>
          <div style={{ textAlign: "center" }}><div style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 22, color: "var(--mid)" }}>%{drawPct}</div><div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.4 }}>beraberlik</div></div>
          <div style={{ textAlign: "center" }}><div style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 22, color: "var(--high)" }}>%{lossPct}</div><div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.4 }}>{DEMO_OPPONENT} galibiyeti</div></div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.35fr) minmax(0,1fr)", gap: 14, alignItems: "start" }}>
        <div>
          <div className="st" style={{ marginTop: 0 }}><h2>İlk 11 — Dizilim</h2><span className="ep">4-3-3</span></div>
          <PitchXI />
          <div style={{ display: "flex", gap: 14, marginTop: 8, fontSize: 11, color: "var(--muted)", flexWrap: "wrap" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 9, height: 9, borderRadius: "50%", border: "2px solid var(--accent)", background: "var(--white)" }} /> kadroda</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 9, height: 9, borderRadius: "50%", border: "2px solid var(--high)", background: "var(--white)" }} /> yük riski</span>
          </div>
        </div>

        <div>
          <div className="st" style={{ marginTop: 0 }}><h2>Yedekler</h2><span className="ep">{DEMO_BENCH.length} oyuncu</span></div>
          <div className="tbl">
            <table>
              <thead><tr><th className="c">#</th><th>Oyuncu</th><th className="c">Mevki</th><th className="c">Kond.</th></tr></thead>
              <tbody>
                {DEMO_BENCH.map((p) => (
                  <tr key={p.player_id}>
                    <td className="pnum c" style={{ fontFamily: "JetBrains Mono" }}>{p.shirt}</td>
                    <td>
                      <span className="nm">{p.player_name}</span>
                      {(p.risk_label === "Kritik" || p.risk_label === "Yüksek") && (
                        <span className="nat" style={{ color: RISK_VAR[p.risk_label], marginLeft: 6 }}>· {p.risk_label.toLowerCase()}</span>
                      )}
                    </td>
                    <td className="c"><span className="pos">{p.pos_detail}</span></td>
                    <td className="c"><span className="cond"><i style={{ width: `${p.condition}%`, background: condColor(p.condition) }} /></span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="st"><h2>Eşleşme Avantajı</h2><span className="ep">{DEMO_CLUB} vs {DEMO_OPPONENT}</span></div>
      <div className="rc" style={{ margin: "0 0 14px", padding: 0, overflow: "hidden" }}>
        {demoMatchups.map((mu, i) => {
          const adv = mu.advantage;
          const c = adv >= 65 ? "var(--low)" : adv >= 50 ? "var(--mid)" : "var(--high)";
          return (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 12, alignItems: "center", padding: "10px 14px", borderTop: i ? "1px solid var(--line)" : undefined }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600 }}>{mu.ours} <span style={{ color: "var(--dim)" }}>vs</span> {mu.theirs}</div>
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{mu.note}</div>
                <div style={{ height: 6, borderRadius: 4, background: "var(--panel3)", overflow: "hidden", marginTop: 6 }}>
                  <i style={{ display: "block", height: "100%", width: `${adv}%`, background: c }} />
                </div>
              </div>
              <div style={{ fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 18, color: c }}>%{adv}</div>
            </div>
          );
        })}
      </div>

      <div className="st"><h2>Rakip Zaafları</h2><span className="ep">{DEMO_OPPONENT}</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 4 }}>
        {demoWeaknesses.map((w, i) => {
          const sv = w.severity === "yüksek" ? "var(--crit)" : w.severity === "orta" ? "var(--mid)" : "var(--muted)";
          return (
            <div className="rc" key={i} style={{ margin: 0, borderTop: `2px solid ${sv}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                <b style={{ fontSize: 12.5 }}>{w.title}</b>
                <span style={{ fontSize: 9.5, textTransform: "uppercase", color: sv }}>{w.severity}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{w.detail}</div>
            </div>
          );
        })}
      </div>
    </ConsoleShell>
  );
}

// --------------------------------------------------------------------------- //
// CANLI görünüm (DEMO kapalı) — eski davranış
// --------------------------------------------------------------------------- //

function MatchLive({ matchId }: { matchId: string }) {
  const [teamId, setTeamId] = useState("");

  const { data: predict, error } = useSWR<PredictResponse>(
    `/matches/${matchId}/predict?use_ml=true`,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const v = predict?.value;

  const consoles = [
    { href: `/matches/${matchId}/live?my_team_id=${teamId}&interval_seconds=5&max_minute=90`, label: "Canlı Maç Konsolu", desc: "WebSocket momentum + değişiklik önerisi" },
    { href: `/matches/${matchId}/halftime?my_team_id=${teamId}`, label: "Devre Arası Brief", desc: "1. yarı 7 engine + AI brief" },
    { href: `/matches/${matchId}/sub-chess?my_team_id=${teamId}&current_minute=60`, label: "Değişiklik Senaryoları", desc: "Top-3 sub forward-projection" },
  ];

  const right = (
    <div className="rc">
      <h3>Maç Konsolları</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", marginBottom: 10, lineHeight: 1.5 }}>
        Kendi takımının ID&apos;sini gir → canlı analiz, devre arası ve değişiklik senaryolarına geç.
      </div>
      <input value={teamId} onChange={(e) => setTeamId(e.target.value.replace(/[^0-9]/g, ""))} inputMode="numeric" placeholder="Takım ID (senin takımın)"
        style={{ width: "100%", background: "var(--panel2)", border: "1px solid var(--line)", color: "var(--ink)", fontSize: 12.5, padding: "7px 9px", borderRadius: 7, marginBottom: 10, fontFamily: "inherit" }} />
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {consoles.map((c) => teamId ? (
          <Link key={c.href} href={c.href} style={{ display: "block", background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "9px 11px", textDecoration: "none" }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink)" }}>{c.label}</div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>{c.desc}</div>
          </Link>
        ) : (
          <div key={c.href} style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "9px 11px", opacity: 0.5 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink)" }}>{c.label}</div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>{c.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <ConsoleShell
      active="/matches"
      title={`Maç #${matchId}`}
      sub="Tahmin & konsollar"
      desc="ML tahmini (kazanma olasılıkları, beklenen skor) ve canlı maç konsollarına geçiş."
      source={["statsbomb", "xg_model"]}
      right={right}
    >
      {error && <div className="pgdesc">Tahmin alınamadı: {String(error)}</div>}

      {v && (
        <>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
            <div className="kpi"><div className="kl">Ev Galibiyet</div><div className="kn" style={{ color: "var(--low)" }}>{Math.round(v.prob_home_win * 100)}<span className="pct">%</span></div><div className="kd">ev sahibi</div></div>
            <div className="kpi"><div className="kl">Beraberlik</div><div className="kn" style={{ color: "var(--mid)" }}>{Math.round(v.prob_draw * 100)}<span className="pct">%</span></div><div className="kd">eşit</div></div>
            <div className="kpi"><div className="kl">Dep Galibiyet</div><div className="kn" style={{ color: "var(--high)" }}>{Math.round(v.prob_away_win * 100)}<span className="pct">%</span></div><div className="kd">deplasman</div></div>
          </div>

          <div className="st"><h2>Tahmin Detayı</h2>{predict?.confidence && <span className="ep">güven: {predict.confidence.label} ({Math.round(predict.confidence.score * 100)})</span>}</div>
          <div className="tbl" style={{ marginBottom: 14 }}>
            <table>
              <tbody>
                <tr><td>Olasılık dağılımı</td><td className="r">
                  <span className="probbar" style={{ marginBottom: 0, width: 200, display: "inline-flex" }}>
                    <i style={{ width: `${v.prob_home_win * 100}%`, background: "var(--low)" }} />
                    <i style={{ width: `${v.prob_draw * 100}%`, background: "var(--dim)" }} />
                    <i style={{ width: `${v.prob_away_win * 100}%`, background: "var(--high)" }} />
                  </span>
                </td></tr>
                <tr><td>Beklenen skor</td><td className="r">{v.expected_home_goals.toFixed(2)} - {v.expected_away_goals.toFixed(2)}</td></tr>
                <tr><td>En olası skor</td><td className="r">{v.most_likely_score[0]}-{v.most_likely_score[1]}</td></tr>
              </tbody>
            </table>
          </div>
        </>
      )}
      {!v && !error && <div className="pgdesc">Tahmin yükleniyor…</div>}
    </ConsoleShell>
  );
}
