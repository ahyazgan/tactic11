"use client";

/**
 * Sub Chess — değişiklik senaryoları (forward-projection). ConsoleShell çatısında.
 * Dakika slider → top-3 senaryo (yorgunluk projeksiyonu + dominance Δ).
 *
 * DEMO_MODE: backend yok. demoSquad + demoLive üzerinden deterministik bir
 * forward-projection motoru çalışır — slider'ı oynat, senaryolar yeniden hesaplanır.
 * Canlı mod (DEMO_MODE=false): GET /admin/matches/{id}/substitution-chess.
 */

import * as React from "react";
import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoSquad, demoLive, DEMO_CLUB, DEMO_OPPONENT, type SquadPlayer } from "@/lib/demo-data";
import { ConsoleShell } from "../../../_console/shell";

interface Scenario {
  out_player_id: number;
  out_player_current_fatigue: number;
  out_player_projected_fatigue_at_full_time: number;
  in_player_id: number | null;
  in_player_projected_fatigue_at_full_time: number;
  minutes_remaining: number;
  projected_dominance_delta: number;
  confidence: string;
}
interface SubChessResponse {
  value?: {
    team_external_id: number;
    current_minute: number;
    minutes_remaining: number;
    scenarios: Scenario[];
    best_scenario_index: number;
    no_action_baseline: number;
  };
  events_loaded?: number;
  note?: string;
}

// --------------------------------------------------------------------------- //
// DEMO — forward-projection motoru (deterministik, backend'siz)
// --------------------------------------------------------------------------- //

// Sahadaki 11 (demoLive momentum/skor evreniyle uyumlu). İlk-11 id'leri.
const DEMO_PITCH_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];

interface DemoSub {
  out: SquadPlayer;
  in: SquadPlayer | null;
  outFatigueNow: number;       // 0..100 (yorgunluk = 100 - kondisyon, drift'li)
  outFatigueFT: number;        // tam-zamanda projeksiyon
  inFatigueFT: number;         // taze oyuncunun tam-zaman projeksiyonu
  dominanceDelta: number;      // -0.4..+0.5 (+ bize avantaj)
  confidence: number;          // 0..100
  rationale: string;
}

/** 100 - kondisyon = baz yorgunluk. */
function baseFatigue(p: SquadPlayer): number {
  return 100 - p.condition;
}

/** Yorgunluk dakikaya göre artar; riskli/yaşlı oyuncuda daha dik. Tam-zamana (90') projekte. */
function projectFatigue(p: SquadPlayer, fromMinute: number, toMinute: number): number {
  const base = baseFatigue(p);
  const minutesOnPitch = Math.max(0, toMinute - 0); // başından beri sahada varsayımı
  // Risk skoru ve yaş dikliği artırır (saatlik ~ yorgunluk eğimi).
  const slope = 0.16 + (p.risk_score / 100) * 0.34 + Math.max(0, p.age - 27) * 0.012;
  const drift = (minutesOnPitch / 90) * slope * 100 * 0.5;
  const v = base + drift - (fromMinute / 90) * 2; // küçük düzeltme — şu ana kadar bir miktar zaten yansıdı
  return Math.min(99, Math.max(base, Math.round(v)));
}

/** Aynı pozisyondan, en taze (düşük risk + yüksek kondisyon), sahada olmayan yedek. */
function pickReplacement(out: SquadPlayer): SquadPlayer | null {
  const cands = demoSquad
    .filter((p) => p.position === out.position && !DEMO_PITCH_IDS.includes(p.player_id))
    .sort((a, b) => (b.condition - b.risk_score) - (a.condition - a.risk_score));
  return cands[0] ?? null;
}

/** Bir oyuncuyu çıkarmanın tam-zamana dominance etkisini kur. */
function buildSub(out: SquadPlayer, minute: number): DemoSub {
  const replacement = pickReplacement(out);
  const outFatigueNow = projectFatigue(out, minute, minute);
  const outFatigueFT = projectFatigue(out, minute, 90);
  const inFatigueFT = replacement ? projectFatigue(replacement, minute, 90) : outFatigueFT;

  // Dominance Δ: çıkanın tam-zaman yorgunluk fazlası ne kadar büyükse, taze oyuncuyla
  // o kadar kazanırız. Kalan dakika çoksa kazanç büyür; azsa marjinal.
  const minutesRemaining = Math.max(0, 90 - minute);
  const fatigueGain = (outFatigueFT - inFatigueFT) / 100;          // 0..~0.5
  const timeWeight = minutesRemaining / 45;                        // 0..2
  const positionWeight = out.position === "MF" ? 1.15 : out.position === "FW" ? 1.05 : 0.95;
  const raw = fatigueGain * timeWeight * positionWeight * 0.42;
  const dominanceDelta = Math.round(raw * 1000) / 1000;

  // Güven: yorgunluk farkı net + kalan zaman makulse yüksek.
  const confidence = Math.min(94, Math.max(48, Math.round(
    52 + (outFatigueFT - inFatigueFT) * 0.5 + Math.min(20, minutesRemaining * 0.4)
  )));

  let rationale: string;
  if (out.risk_label === "Kritik") {
    rationale = `${out.player_name} kritik yük bandında (risk ${out.risk_score}); ${minute}. dakikada çıkarmak sakatlığı önler ve orta sahaya taze yaratıcılık katar.`;
  } else if (out.risk_label === "Yüksek") {
    rationale = `${out.player_name} yorgunluk eşiğine yaklaşıyor; tam-zamana projeksiyon ${outFatigueFT} (taze yedek ${inFatigueFT}). Erken hamle dominance'ı korur.`;
  } else {
    rationale = `${out.player_name} taktik amaçlı çıkabilir; ${replacement ? replacement.player_name : "yedek"} ile son ${minutesRemaining} dk daha yüksek tempo.`;
  }

  return { out, in: replacement, outFatigueNow, outFatigueFT, inFatigueFT, dominanceDelta, confidence, rationale };
}

/** Top-3 senaryo: sahadaki en yorgun/riskli 3 oyuncu için en iyi değişiklik. */
function demoScenariosFor(minute: number): DemoSub[] {
  const onPitch = demoSquad.filter((p) => DEMO_PITCH_IDS.includes(p.player_id) && p.position !== "GK");
  return onPitch
    .map((p) => buildSub(p, minute))
    .sort((a, b) => b.dominanceDelta - a.dominanceDelta || b.confidence - a.confidence)
    .slice(0, 3);
}

function confLabel(c: number): string {
  return c >= 80 ? "YÜKSEK" : c >= 62 ? "ORTA" : "DÜŞÜK";
}
function fatVar(v: number): string {
  return v >= 80 ? "var(--crit)" : v >= 65 ? "var(--high)" : v >= 50 ? "var(--mid)" : "var(--low)";
}

// Forward-projection grafiği: çıkan vs taze oyuncu yorgunluk eğrisi (şimdiden 90'a).
function ProjectionChart({ sub, minute }: { sub: DemoSub; minute: number }) {
  const W = 520, H = 150, padL = 34, padR = 12, padT = 12, padB = 22;
  const x = (m: number) => padL + ((m - minute) / Math.max(1, 90 - minute)) * (W - padL - padR);
  const y = (f: number) => padT + (1 - f / 100) * (H - padT - padB);
  const steps = 6;
  const outPts: string[] = [];
  const inPts: string[] = [];
  for (let i = 0; i <= steps; i++) {
    const m = minute + ((90 - minute) / steps) * i;
    outPts.push(`${x(m).toFixed(1)},${y(projectFatigue(sub.out, minute, m)).toFixed(1)}`);
    if (sub.in) inPts.push(`${x(m).toFixed(1)},${y(projectFatigue(sub.in, minute, m)).toFixed(1)}`);
  }
  const gridY = [40, 60, 80];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="Yorgunluk projeksiyon eğrisi" style={{ display: "block" }}>
      {gridY.map((g) => (
        <g key={g}>
          <line x1={padL} y1={y(g)} x2={W - padR} y2={y(g)} stroke="var(--border)" strokeWidth={1} strokeDasharray="3 3" />
          <text x={4} y={y(g) + 3} fontSize={9} fill="var(--dim)" fontFamily="JetBrains Mono">{g}</text>
        </g>
      ))}
      {/* kritik bant */}
      <rect x={padL} y={y(100)} width={W - padL - padR} height={y(80) - y(100)} fill="var(--crit)" opacity={0.05} />
      {/* çıkan oyuncu (kötüleşen) */}
      <polyline points={outPts.join(" ")} fill="none" stroke="var(--crit)" strokeWidth={2.2} />
      {/* taze oyuncu */}
      {sub.in && <polyline points={inPts.join(" ")} fill="none" stroke="var(--low)" strokeWidth={2.2} strokeDasharray="5 3" />}
      {/* şimdi / FT etiketleri */}
      <text x={padL} y={H - 6} fontSize={9} fill="var(--dim)" fontFamily="JetBrains Mono">{minute}&apos;</text>
      <text x={W - padR} y={H - 6} fontSize={9} fill="var(--dim)" textAnchor="end" fontFamily="JetBrains Mono">90&apos; (FT)</text>
    </svg>
  );
}

// --------------------------------------------------------------------------- //

export default function SubChessConsolePage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const matchId = params.id;
  const myTeamId = search.get("my_team_id");
  const initialMinute = Number(search.get("current_minute") ?? (DEMO_MODE ? "67" : "60"));
  const [minute, setMinute] = React.useState<number>(initialMinute);

  // Canlı mod URL'i; DEMO'da SWR'ı tamamen kapat.
  const url = !DEMO_MODE && myTeamId && minute
    ? `/admin/matches/${matchId}/substitution-chess?my_team_id=${myTeamId}&current_minute=${minute}`
    : null;
  const { data, error, isLoading } = useSWR<SubChessResponse>(url, apiFetch, { shouldRetryOnError: false });

  // ── DEMO içeriği ──────────────────────────────────────────────────────────
  if (DEMO_MODE) {
    const subs = demoScenariosFor(minute);
    const best = subs[0];
    const minutesRemaining = Math.max(0, 90 - minute);
    const noActionDrop = Math.round(subs.reduce((s, x) => s + (x.outFatigueFT - x.outFatigueNow), 0) / Math.max(1, subs.length));

    const right = (
      <>
        <div className="rc">
          <h3>Maç Dakikası</h3>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <input type="range" min={45} max={88} step={1} value={minute} onChange={(e) => setMinute(Number(e.target.value))} style={{ flex: 1, accentColor: "var(--accent)" }} aria-label="Maç dakikası" />
            <span style={{ fontFamily: "JetBrains Mono", fontSize: 16, width: 40, textAlign: "right", fontWeight: 700 }}>{minute}&apos;</span>
          </div>
          <div style={{ fontSize: "11.5px", color: "var(--dim)", lineHeight: 1.5 }}>Slider&apos;ı oynat → tam-zaman (90&apos;) projeksiyonu ve senaryolar yeniden hesaplanır.</div>
          <div className="stat" style={{ marginTop: 10 }}><span style={{ fontSize: 11.5, color: "var(--muted)" }}>Kalan süre</span><span className="sv">{minutesRemaining}&apos;</span></div>
          <div className="stat"><span style={{ fontSize: 11.5, color: "var(--muted)" }}>Skor</span><span className="sv">{demoLive.score[0]}–{demoLive.score[1]}</span></div>
          <div className="stat"><span style={{ fontSize: 11.5, color: "var(--muted)" }}>Momentum</span><span className="sv" style={{ color: "var(--crit)" }}>{demoLive.momentumHolder}</span></div>
        </div>

        <div className="rc">
          <h3>Hamlesiz Senaryo <span className="tiny">no-action</span></h3>
          <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.6 }}>
            Hiç değişiklik yapılmazsa, ilk-11&apos;deki yorgun oyuncular tam-zamana kadar ortalama
            {" "}<b style={{ color: "var(--crit)" }}>+{noActionDrop} puan</b> daha yorulur ve dominance kademeli düşer.
          </div>
          <div className="stat" style={{ marginTop: 10 }}><span style={{ fontSize: 11.5, color: "var(--muted)" }}>En iyi hamle Δ</span><span className="sv" style={{ color: "var(--low)" }}>+{best.dominanceDelta.toFixed(3)}</span></div>
        </div>

        <div className="rc">
          <h3>Açıklama</h3>
          <div style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 11.5, color: "var(--muted)", marginBottom: 6 }}>
            <span style={{ width: 18, height: 0, borderTop: "2.4px solid var(--crit)" }} /> Çıkan oyuncu (yorulan)
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 11.5, color: "var(--muted)" }}>
            <span style={{ width: 18, height: 0, borderTop: "2.4px dashed var(--low)" }} /> Taze yedek (90&apos; proj.)
          </div>
        </div>
      </>
    );

    return (
      <ConsoleShell
        active="/matches"
        title={`Sub Chess — Maç #${matchId}`}
        sub={`${DEMO_CLUB} vs ${DEMO_OPPONENT} · ${minute}. dakika`}
        desc="Forward-projection ile en iyi 3 değişiklik senaryosu — her hamlenin tam-zaman yorgunluk ve dominance etkisi."
        right={right}
      >
        <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
          <div className="kpi"><div className="kl">Şu An</div><div className="kn">{minute}<span className="pct">&apos;</span></div><div className="kd">kalan {minutesRemaining} dk</div></div>
          <div className="kpi"><div className="kl">En İyi Hamle</div><div className="kn" style={{ fontSize: 18, lineHeight: 1.15 }}>#{best.out.shirt} {best.out.player_name.split(" ")[0]}</div><div className="kd">→ {best.in ? `#${best.in.shirt} ${best.in.player_name.split(" ")[0]}` : "TD seçer"}</div></div>
          <div className="kpi"><div className="kl">Dominance Δ</div><div className="kn" style={{ color: "var(--low)" }}>+{best.dominanceDelta.toFixed(3)}</div><div className="kd">tam-zamana etki</div></div>
          <div className="kpi"><div className="kl">Model Güveni</div><div className="kn" style={{ color: best.confidence >= 80 ? "var(--low)" : "var(--mid)" }}>%{best.confidence}</div><div className="kd">{confLabel(best.confidence).toLowerCase()}</div></div>
        </div>

        <div className="st" style={{ marginTop: 0 }}><h2>Top 3 Değişiklik Senaryosu</h2><span className="ep">forward-projection · kalan {minutesRemaining} dk</span></div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          {subs.map((s, i) => {
            const isBest = i === 0;
            return (
              <div className="rc" key={s.out.player_id} style={{ margin: 0, borderLeft: isBest ? "3px solid var(--low)" : "3px solid var(--border2)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)" }}>Senaryo {i + 1}{isBest ? " ★" : ""}</span>
                  <span className={`risk risk-${s.confidence >= 80 ? "low" : s.confidence >= 62 ? "mid" : "high"}`}>
                    <span className="rd" style={{ background: s.confidence >= 80 ? "var(--low)" : s.confidence >= 62 ? "var(--mid)" : "var(--high)" }} />%{s.confidence}
                  </span>
                </div>
                <div style={{ fontSize: 13.5, color: "var(--ink)", marginBottom: 4, fontWeight: 600 }}>
                  <span className="pos" style={{ marginRight: 6 }}>{s.out.pos_detail}</span>
                </div>
                <div style={{ fontSize: 13, color: "var(--ink)", marginBottom: 10 }}>
                  <span style={{ color: "var(--crit)" }}>#{s.out.shirt} {s.out.player_name}</span>
                  {" → "}
                  <span style={{ color: "var(--low)" }}>{s.in ? `#${s.in.shirt} ${s.in.player_name}` : "TD seçer"}</span>
                </div>
                <div style={{ fontSize: 24, fontWeight: 800, fontFamily: "JetBrains Mono", color: s.dominanceDelta > 0 ? "var(--low)" : "var(--crit)", marginBottom: 2, lineHeight: 1 }}>
                  {(s.dominanceDelta > 0 ? "+" : "") + s.dominanceDelta.toFixed(3)}
                </div>
                <div style={{ fontSize: 10.5, color: "var(--dim)", marginBottom: 10, textTransform: "uppercase", letterSpacing: ".4px" }}>dominance Δ (tam-zaman)</div>

                <div style={{ fontSize: 11, fontFamily: "JetBrains Mono", lineHeight: 1.7, marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "var(--muted)" }}>Çıkan şimdi</span><span style={{ color: fatVar(s.outFatigueNow) }}>{s.outFatigueNow}</span></div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "var(--muted)" }}>Çıkan 90&apos;</span><span style={{ color: "var(--crit)", fontWeight: 700 }}>{s.outFatigueFT}</span></div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "var(--muted)" }}>Taze 90&apos;</span><span style={{ color: "var(--low)", fontWeight: 700 }}>{s.inFatigueFT}</span></div>
                  <div className="mbar" style={{ marginTop: 6 }}><i style={{ width: `${Math.min(100, ((s.outFatigueFT - s.inFatigueFT) / 50) * 100)}%`, background: "var(--low)" }} /></div>
                  <div style={{ color: "var(--dim)", fontSize: 10, textTransform: "uppercase", letterSpacing: ".3px" }}>yorgunluk kazancı {s.outFatigueFT - s.inFatigueFT} puan</div>
                </div>

                <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.55, borderTop: "1px solid var(--border)", paddingTop: 8 }}>{s.rationale}</div>
              </div>
            );
          })}
        </div>

        <div className="st"><h2>Forward-Projection — {best.out.player_name} hamlesi</h2><span className="ep">en iyi senaryo</span></div>
        <div className="rc" style={{ margin: 0 }}>
          <div style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 8, lineHeight: 1.5 }}>
            <span style={{ color: "var(--crit)", fontWeight: 700 }}>#{best.out.shirt} {best.out.player_name}</span> sahada kalırsa yorgunluk eğrisi
            {" "}90. dakikaya kadar <b style={{ color: "var(--crit)" }}>{best.outFatigueFT}</b>&apos;e tırmanıyor (kritik bant).
            {best.in && <> Taze <b style={{ color: "var(--low)" }}>#{best.in.shirt} {best.in.player_name}</b> ise sonu <b style={{ color: "var(--low)" }}>{best.inFatigueFT}</b> ile kapatır.</>}
          </div>
          <ProjectionChart sub={best} minute={minute} />
        </div>

        <div className="st"><h2>İlk-11 Yorgunluk Tablosu</h2><span className="ep">tam-zaman projeksiyonu</span></div>
        <div className="tbl">
          <table>
            <thead><tr>
              <th className="c">#</th><th>Oyuncu</th><th>Mevki</th>
              <th className="c">Şimdi</th><th className="c">90&apos; proj.</th><th className="c">Δ</th><th className="r">Risk</th>
            </tr></thead>
            <tbody>
              {demoSquad
                .filter((p) => DEMO_PITCH_IDS.includes(p.player_id))
                .map((p) => {
                  const now = projectFatigue(p, minute, minute);
                  const ft = projectFatigue(p, minute, 90);
                  const delta = ft - now;
                  return (
                    <tr key={p.player_id}>
                      <td className="pnum c">{p.shirt}</td>
                      <td><span className="nm">{p.player_name}</span></td>
                      <td><span className="pos">{p.pos_detail}</span></td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: fatVar(now) }}>{now}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: fatVar(ft), fontWeight: 700 }}>{ft}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: delta >= 15 ? "var(--crit)" : delta >= 8 ? "var(--mid)" : "var(--dim)" }}>+{delta}</td>
                      <td className="r" style={{ color: p.risk_label === "Kritik" ? "var(--crit)" : p.risk_label === "Yüksek" ? "var(--high)" : p.risk_label === "Orta" ? "var(--mid)" : "var(--low)" }}>{p.risk_score}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </ConsoleShell>
    );
  }

  // ── Canlı mod (DEMO_MODE=false) ───────────────────────────────────────────
  const isEvent0 = data?.events_loaded === 0;

  const right = (
    <div className="rc">
      <h3>Dakika</h3>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <input type="range" min={5} max={90} step={5} value={minute} onChange={(e) => setMinute(Number(e.target.value))} style={{ flex: 1 }} aria-label="Maç dakikası" />
        <span style={{ fontFamily: "JetBrains Mono", fontSize: 16, width: 40, textAlign: "right" }}>{minute}&apos;</span>
      </div>
      <div style={{ fontSize: "11.5px", color: "var(--dim)", lineHeight: 1.5 }}>Slider&apos;ı oynat → senaryolar yeniden hesaplanır.</div>
    </div>
  );

  if (!myTeamId) {
    return (
      <ConsoleShell active="/matches" title={`Sub Chess — Maç #${matchId}`} sub="Değişiklik senaryoları">
        <div className="pgdesc"><code style={{ fontFamily: "JetBrains Mono" }}>?my_team_id=&lt;N&gt;</code> parametresi gerekli (Maç detayından gel).</div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell
      active="/matches"
      title={`Sub Chess — Maç #${matchId}`}
      sub={`Takım #${myTeamId} · ${minute}. dakika`}
      desc="Forward-projection ile en iyi 3 değişiklik senaryosu — yorgunluk ve dominance etkisi."
      right={right}
    >
      {error && <div className="pgdesc">Yüklenemedi: {String(error)}</div>}
      {isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {isEvent0 && <div className="pgdesc">{data?.note}</div>}

      {data?.value && data.value.scenarios.length > 0 && (
        <>
          <div className="st" style={{ marginTop: 0 }}><h2>Top 3 Senaryo</h2><span className="ep">kalan {data.value.minutes_remaining.toFixed(0)} dk</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            {data.value.scenarios.map((s, i) => {
              const isBest = i === data.value!.best_scenario_index;
              return (
                <div className="rc" key={i} style={{ margin: 0, borderLeft: isBest ? "2px solid var(--low)" : undefined }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)" }}>Senaryo {i + 1}{isBest ? " ★" : ""}</span>
                    <span style={{ fontSize: 10, textTransform: "uppercase", color: "var(--muted)", fontFamily: "JetBrains Mono" }}>{s.confidence}</span>
                  </div>
                  <div style={{ fontSize: 13, color: "var(--ink)", marginBottom: 8 }}>#{s.out_player_id} → {s.in_player_id ? `#${s.in_player_id}` : "TD seçer"}</div>
                  <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "JetBrains Mono", color: s.projected_dominance_delta > 0 ? "var(--low)" : "var(--crit)", marginBottom: 8 }}>
                    {(s.projected_dominance_delta > 0 ? "+" : "") + s.projected_dominance_delta.toFixed(3)}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.6, fontFamily: "JetBrains Mono" }}>
                    <div>Out şimdi: {s.out_player_current_fatigue.toFixed(2)}</div>
                    <div>Out FT: <span style={{ color: "var(--crit)" }}>{s.out_player_projected_fatigue_at_full_time.toFixed(2)}</span></div>
                    <div>In FT: <span style={{ color: "var(--low)" }}>{s.in_player_projected_fatigue_at_full_time.toFixed(2)}</span></div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
