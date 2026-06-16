"use client";

/**
 * Devre Arası Brief — Teknik Ekip Konsolu. ConsoleShell çatısında.
 * 1. yarı sayıları (PPDA/tilt/xT/dominance), 1. yarı xG eğrisi, motor sinyalleri,
 * AI brief ve senaryo bazlı 2. yarı planı.
 *
 * DEMO_MODE: backend YOK — `demo-data.ts` evreninden (Beşiktaş vs Antalyaspor)
 * dolu, inandırıcı bir devre arası brifingi türetilir.
 * DEMO kapalı: eski canlı-API görünümü (/admin/matches/{id}/halftime-brief).
 */

import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  demoLive,
  demoPlan,
  demoScenarios,
  demoWeaknesses,
  demoMatchups,
  demoDecisions,
  demoSquad,
  type Scenario,
} from "@/lib/demo-data";
import { engineLabel } from "@/lib/labels";
import {
  halftimeSubs, halftimeMoves, halftimeBrief, type HtMove,
} from "@/lib/halftime-advice";
import { ConsoleShell } from "../../../_console/shell";

interface HalftimeBrief {
  match_external_id: number;
  my_team_external_id: number;
  opponent_team_external_id: number;
  my_side: "home" | "away";
  halftime_score: string;
  events_loaded: number;
  first_half_event_counts?: {
    passes: number;
    carries: number;
    defensive_actions: number;
    shots: number;
  };
  stats?: {
    ppda: number;
    pressing_style: string;
    field_tilt_my_share: number;
    team_xt_total: number;
    match_dominance_score: number;
    match_dominance_label: string;
  };
  opponent_weakness?: {
    most_vulnerable_channel: string;
    recommendation: string;
    by_channel: { channel: string; score: number; our_attacks: number; opp_def_actions: number }[];
  };
  fatigue_alerts?: {
    player_id: number;
    fatigue_score: number;
    recommendation: string;
    pass_completion_drop: number;
  }[];
  opponent_set_piece_pattern?: {
    most_frequent_zone?: string;
    most_dangerous_zone?: string;
    alert_text?: string;
    total_shots?: number;
  };
  sub_recommendations?: {
    recommendations: {
      player_external_id: number;
      urgency_score: number;
      urgency_label: string;
      reasons: string[];
    }[];
    score_state?: string;
  };
  ai_brief?: string;
  note?: string;
}

// =========================================================================== //
// CANLI-API görünümü (DEMO kapalıyken). ConsoleShell çatısına sarılı.
// =========================================================================== //

function HalftimeApiView() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const matchId = params.id;
  const myTeam = search.get("my_team_id");
  const { data, error, isLoading } = useSWR<HalftimeBrief>(
    myTeam ? `/admin/matches/${matchId}/halftime-brief?my_team_id=${myTeam}` : null,
    apiFetch,
  );

  if (!myTeam) {
    return (
      <ConsoleShell active="/matches" title={`Devre Arası — Maç #${matchId}`} sub="Devre arası brief">
        <div className="pgdesc">
          <code style={{ fontFamily: "JetBrains Mono" }}>?my_team_id=&lt;N&gt;</code> parametresi gerekli (Maç detayından gel).
        </div>
      </ConsoleShell>
    );
  }
  if (error) {
    return (
      <ConsoleShell active="/matches" title={`Devre Arası — Maç #${matchId}`} sub={`Takım #${myTeam}`}>
        <div className="rc" style={{ borderLeft: "2px solid var(--crit)", color: "var(--crit)", fontSize: 13 }}>
          Yüklenemedi: {String(error)}
        </div>
      </ConsoleShell>
    );
  }
  if (isLoading || !data) {
    return (
      <ConsoleShell active="/matches" title={`Devre Arası — Maç #${matchId}`} sub={`Takım #${myTeam}`}>
        <div className="pgdesc">Yükleniyor…</div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell
      active="/matches"
      title={`Devre Arası — Takım #${data.my_team_external_id}`}
      sub={`İY ${data.halftime_score}`}
      desc={`Maç #${data.match_external_id} · vs #${data.opponent_team_external_id} (${data.my_side === "home" ? "ev" : "dep"}) · ${data.events_loaded} event`}
    >
      <div className="kpis" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
        <div className="kpi"><div className="kl">PPDA</div><div className="kn" style={{ fontSize: 20 }}>{data.stats?.ppda.toFixed(2) ?? "—"}</div><div className="kd">{data.stats?.pressing_style ?? ""}</div></div>
        <div className="kpi"><div className="kl">Field Tilt</div><div className="kn" style={{ fontSize: 20 }}>{data.stats ? `%${Math.round(data.stats.field_tilt_my_share * 100)}` : "—"}</div></div>
        <div className="kpi"><div className="kl">Team xT</div><div className="kn" style={{ fontSize: 20 }}>{data.stats?.team_xt_total.toFixed(2) ?? "—"}</div></div>
        <div className="kpi"><div className="kl">Dominance</div><div className="kn" style={{ fontSize: 20 }}>{data.stats?.match_dominance_score.toFixed(2) ?? "—"}</div><div className="kd">{data.stats?.match_dominance_label ?? ""}</div></div>
        <div className="kpi"><div className="kl">Şutlar</div><div className="kn" style={{ fontSize: 20 }}>{data.first_half_event_counts?.shots ?? 0}</div></div>
        <div className="kpi"><div className="kl">Pas</div><div className="kn" style={{ fontSize: 20 }}>{data.first_half_event_counts?.passes ?? 0}</div></div>
      </div>
      {data.ai_brief && (
        <>
          <div className="st"><h2>AI Brief — 2. yarı önerisi</h2></div>
          <div className="rc" style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.6 }}>{data.ai_brief}</div>
        </>
      )}
    </ConsoleShell>
  );
}

// =========================================================================== //
// DEMO görünümü — backend YOK; 1. yarı özeti + motor sinyalleri + 2. yarı planı.
// =========================================================================== //

// Tema renkleri (hardcoded mavi/kırmızı yerine): biz = marka yeşili, rakip = turuncu.
const HOME_COLOR = "var(--accent)";
const AWAY_COLOR = "var(--high)";

// 1. yarı (≤45') kümülatif xG eğrisi — canlı demo serisinden süzülür.
const FIRST_HALF = demoLive.series.filter((p) => p.minute <= 45);
const HT_HOME_XG = FIRST_HALF[FIRST_HALF.length - 1].home; // 0.91
const HT_AWAY_XG = FIRST_HALF[FIRST_HALF.length - 1].away; // 0.83

// 1. yarı olayları (devre arası brifingi sadece ilk yarıyı özetler).
const FIRST_HALF_EVENTS = demoLive.events.filter((e) => e.minute <= 45);
const FH_SHOTS_HOME = 8;
const FH_SHOTS_AWAY = 6;

// 1. yarı sayıları (motor çıktısı gibi sunulan tutarlı değerler).
const FH_STATS = {
  ppda: 9.4,
  pressing_style: "Orta-yüksek pres",
  field_tilt: 0.57, // bizim saha hakimiyeti payı
  team_xt: 1.18,
  dominance: 0.62,
  dominance_label: "Hafif üstün",
  possession: 0.54,
  pass_accuracy: 0.86,
};

const SEV_VAR: Record<string, string> = {
  yüksek: "var(--crit)",
  orta: "var(--mid)",
  düşük: "var(--low)",
};

const URG_VAR: Record<string, string> = {
  kritik: "var(--crit)",
  yüksek: "var(--high)",
  orta: "var(--mid)",
  düşük: "var(--low)",
};

// Rakip set-piece pattern — beraberlik golü far-post zaafından geldi.
const SET_PIECE = {
  total_shots: 4,
  most_frequent_zone: "Far-post (ikinci direk)",
  most_dangerous_zone: "Far-post (ikinci direk)",
  alert_text:
    "Beraberlik golü 45. dk köşe vuruşunda far-post'tan geldi. Rakip ilk yarı 4 duran top şutu üretti; ikinci direği örtmüyoruz. 2. yarı zonal dizilimi adam-adama kaydır.",
};

function EV_ICON(t: string): string {
  if (t === "gol") return "⚽";
  if (t === "sari_kart") return "🟨";
  if (t === "kirmizi_kart") return "🟥";
  if (t === "sakatlik") return "🩹";
  if (t === "degisiklik") return "🔁";
  return "✨";
}

// 1. yarı xG eğrisi — saf inline SVG (recharts'a gerek yok, küçük seri).
function FirstHalfXgChart() {
  const w = 560;
  const h = 150;
  const padL = 30;
  const padR = 10;
  const padT = 10;
  const padB = 22;
  const maxX = 45;
  const maxY = Math.max(HT_HOME_XG, HT_AWAY_XG, 0.4) * 1.15;
  const x = (m: number) => padL + (m / maxX) * (w - padL - padR);
  const y = (v: number) => h - padB - (v / maxY) * (h - padT - padB);
  const line = (key: "home" | "away") =>
    FIRST_HALF.map((p, i) => `${i ? "L" : "M"} ${x(p.minute).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(" ");
  const grid = [0, 0.25, 0.5, 0.75, 1].map((g) => g * maxY);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} style={{ display: "block" }}>
      {grid.map((g, i) => (
        <g key={i}>
          <line x1={padL} y1={y(g)} x2={w - padR} y2={y(g)} stroke="var(--line)" strokeWidth={1} />
          <text x={4} y={y(g) + 3} fontSize={9} fill="var(--dim)" fontFamily="JetBrains Mono">{g.toFixed(1)}</text>
        </g>
      ))}
      {[0, 15, 30, 45].map((m) => (
        <text key={m} x={x(m)} y={h - 6} fontSize={9} fill="var(--dim)" textAnchor="middle" fontFamily="JetBrains Mono">{m}&apos;</text>
      ))}
      {/* gol işaretleri */}
      {FIRST_HALF_EVENTS.filter((e) => e.type === "gol").map((e, i) => (
        <line key={i} x1={x(e.minute)} y1={padT} x2={x(e.minute)} y2={h - padB}
          stroke={e.team === "home" ? HOME_COLOR : AWAY_COLOR} strokeWidth={1} strokeDasharray="3 3" opacity={0.5} />
      ))}
      <path d={line("away")} fill="none" stroke={AWAY_COLOR} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      <path d={line("home")} fill="none" stroke={HOME_COLOR} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function ScenarioCard({ s }: { s: Scenario }) {
  const tone =
    s.state === "Öndeyiz" ? "var(--low)" : s.state === "Geride" ? "var(--crit)" : "var(--mid)";
  return (
    <div className="rc" style={{ margin: 0, borderTop: `3px solid ${tone}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 8 }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: tone, boxShadow: `0 0 7px ${tone}` }} />
        <b style={{ fontSize: 13, color: "var(--ink)" }}>{s.state}</b>
      </div>
      <div style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.5, marginBottom: 8 }}>{s.plan}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", borderTop: "1px solid var(--line)", paddingTop: 7 }}>
        <span style={{ color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.3 }}>Değişiklik:</span> {s.subs}
      </div>
    </div>
  );
}

const MOVE_ICON: Record<HtMove["kind"], string> = { sub: "🔁", attack: "🎯", defense: "🛡️", tempo: "⏱️" };

function DemoHalftimeView() {
  const params = useParams<{ id: string }>();
  const matchId = params.id;
  const d = demoLive;

  // ── Devre arası reçetesi — İLK YARI verisinden CANLI hesaplanır (sabit değil) ──
  const htSubs = halftimeSubs();
  const htMoves = halftimeMoves(htSubs);
  const brief = halftimeBrief(htSubs);

  // İlk yarı motor sinyalleri (devre arasında masaya konacak en kritik kararlar).
  const htDecisions = demoDecisions.filter((dec) => dec.minute <= 45);
  const topChannel = demoWeaknesses[0];

  // Sağ kolon: devre arası özeti + en kritik karar + yorgun oyuncular.
  const fatigued = demoSquad
    .filter((p) => p.condition < 75)
    .sort((a, b) => a.condition - b.condition)
    .slice(0, 4);

  const right = (
    <>
      <div className="rc">
        <h3>Devre Arası <span className="tiny">45&apos; +1</span></h3>
        <div className="nm-vs">
          <span className="t" style={{ color: HOME_COLOR }}>{d.home}</span>
          <span className="x" style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 20, color: "var(--ink)" }}>
            {d.score[0]}-{d.score[1]}
          </span>
          <span className="t away" style={{ color: AWAY_COLOR }}>{d.away}</span>
        </div>
        <div className="nm-when">İlk yarı · xG {HT_HOME_XG.toFixed(2)} – {HT_AWAY_XG.toFixed(2)}</div>
        <div className="stat"><span style={{ fontSize: 11.5, color: "var(--muted)" }}>Topla oynama</span><span className="sv">%{Math.round(FH_STATS.possession * 100)}</span></div>
        <div className="stat"><span style={{ fontSize: 11.5, color: "var(--muted)" }}>Pas isabeti</span><span className="sv">%{Math.round(FH_STATS.pass_accuracy * 100)}</span></div>
        <div className="stat"><span style={{ fontSize: 11.5, color: "var(--muted)" }}>Şut (biz–rakip)</span><span className="sv">{FH_SHOTS_HOME}–{FH_SHOTS_AWAY}</span></div>
        <div className="stat"><span style={{ fontSize: 11.5, color: "var(--muted)" }}>Momentum (45&apos;)</span><span className="sv" style={{ color: FIRST_HALF[FIRST_HALF.length - 1].momentum >= 0 ? HOME_COLOR : AWAY_COLOR }}>{FIRST_HALF[FIRST_HALF.length - 1].momentum >= 0 ? "+" : ""}{FIRST_HALF[FIRST_HALF.length - 1].momentum} {FIRST_HALF[FIRST_HALF.length - 1].momentum >= 0 ? d.home : d.away}</span></div>
      </div>

      <div className="rc">
        <h3>En Kritik Karar <span className="tiny">45. dk</span></h3>
        {htSubs.length === 0 ? (
          <div style={{ fontSize: 11.5, color: "var(--muted)" }}>Saha-içi acil değişiklik gerektiren oyuncu yok.</div>
        ) : (() => {
          const c = htSubs[0];
          return (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                <b style={{ fontSize: 12.5 }}>{c.out}</b>
                <span style={{ fontSize: 9.5, textTransform: "uppercase", color: URG_VAR[c.urgency] }}>{c.urgency}</span>
              </div>
              <div style={{ fontSize: 11.5, color: "var(--low)", marginBottom: 6 }}>↳ {c.in}</div>
              <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>{c.reasons[0]}</div>
            </>
          );
        })()}
      </div>

      <div className="rc">
        <h3>Yorgunluk İzleme <span className="tiny">kondisyon &lt;75</span></h3>
        {fatigued.map((p) => {
          const v = p.condition < 65 ? "var(--crit)" : p.condition < 72 ? "var(--high)" : "var(--mid)";
          return (
            <div className="alrt" key={p.player_id}>
              <span className="ai" style={{ background: v }} />
              <div className="am"><b>{p.player_name}</b> · {p.pos_detail}
                <span className="tm">kondisyon {p.condition} · {p.risk_label.toLowerCase()} risk</span>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/matches"
      title="Devre Arası Brief"
      sub={`${d.home} ${d.score[0]}-${d.score[1]} ${d.away}`}
      desc={`Maç #${matchId} · ${demoPlan.summary.split(";")[0]}. İlk yarı özeti, motor sinyalleri ve senaryo bazlı 2. yarı planı.`}
      right={right}
    >
      {/* 1. yarı KPI'ları */}
      <div className="st" style={{ marginTop: 0 }}><h2>1. Yarı Sayılar</h2><span className="ep">≤ 45. dakika</span></div>
      <div className="kpis" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
        <div className="kpi"><div className="kl">PPDA</div><div className="kn" style={{ fontSize: 22 }}>{FH_STATS.ppda.toFixed(1)}</div><div className="kd">{FH_STATS.pressing_style}</div></div>
        <div className="kpi"><div className="kl">Field Tilt</div><div className="kn" style={{ fontSize: 22, color: "var(--low)" }}>%{Math.round(FH_STATS.field_tilt * 100)}</div><div className="kd">saha hakimiyeti</div></div>
        <div className="kpi"><div className="kl">Team xT</div><div className="kn" style={{ fontSize: 22 }}>{FH_STATS.team_xt.toFixed(2)}</div><div className="kd">tehdit üretimi</div></div>
        <div className="kpi"><div className="kl">Dominance</div><div className="kn" style={{ fontSize: 22, color: "var(--low)" }}>+{FH_STATS.dominance.toFixed(2)}</div><div className="kd">{FH_STATS.dominance_label}</div></div>
        <div className="kpi"><div className="kl">xG (biz)</div><div className="kn" style={{ fontSize: 22 }}>{HT_HOME_XG.toFixed(2)}</div><div className="kd">rakip {HT_AWAY_XG.toFixed(2)}</div></div>
        <div className="kpi"><div className="kl">Şut</div><div className="kn" style={{ fontSize: 22 }}>{FH_SHOTS_HOME}</div><div className="kd">isabetli {FH_SHOTS_HOME - 3}</div></div>
      </div>

      {/* 1. yarı xG eğrisi */}
      <div className="st"><h2>1. Yarı xG Eğrisi</h2><span className="ep" style={{ display: "flex", gap: 12 }}>
        <span style={{ color: HOME_COLOR }}>● {d.home}</span><span style={{ color: AWAY_COLOR }}>● {d.away}</span>
      </span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <FirstHalfXgChart />
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>
          23&apos; Oh Hyeon-Gyu golüyle öne geçtik, xG akışında üstündük; 45&apos; far-post korner golüyle beraberlik. Maç başa baş kapandı.
        </div>
      </div>

      {/* 2. Yarı Öncelikli Hamleler — ilk yarı verisinden CANLI hesaplanır */}
      <div className="st"><h2>2. Yarı Öncelikli Hamleler</h2><span className="ep">ilk yarı verisinden · önceliklendirilmiş</span></div>
      <div className="rc" style={{ margin: "0 0 14px", padding: 0, overflow: "hidden" }}>
        {htMoves.map((m, i) => {
          const v = URG_VAR[m.urgency] ?? "var(--muted)";
          return (
            <div key={m.id} style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 12, alignItems: "center", padding: "11px 14px", borderTop: i ? "1px solid var(--line)" : undefined, borderLeft: `3px solid ${v}` }}>
              <span style={{ fontSize: 17 }}>{MOVE_ICON[m.kind]}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--ink)" }}>{m.title}</div>
                <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45, marginTop: 2 }}>{m.detail}</div>
              </div>
              <span className="risk" style={{ color: v, fontSize: 10, flexShrink: 0 }}><span className="rd" style={{ background: v }} />{m.urgency}</span>
            </div>
          );
        })}
      </div>

      {/* AI Brief — hesaplanan (ilk yarı özeti + en acil değişiklik + en iyi eşleşme) */}
      <div className="st"><h2>AI Brief — TD için 2. yarı önerisi</h2><span className="ep">otomatik · ilk yarı verisinden</span></div>
      <div className="rc" style={{ margin: "0 0 14px", lineHeight: 1.65, fontSize: 13 }}>
        <p style={{ marginBottom: 10 }}><b>Özet.</b> {brief.summary}</p>
        <p style={{ marginBottom: 10 }}><b>Ne çalıştı.</b> {brief.whatWorked}</p>
        <p style={{ marginBottom: 10 }}><b>Risk.</b> {brief.risk}</p>
        <p style={{ margin: 0 }}><b>Plan.</b> {brief.plan}</p>
      </div>

      {/* 45. dk değişiklik önerileri */}
      <div className="st"><h2>45. dk Değişiklik Önerileri</h2><span className="ep">{htSubs.length} öneri · risk endeksinden</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, marginBottom: 14 }}>
        {htSubs.map((s, i) => {
          const v = URG_VAR[s.urgency] ?? "var(--muted)";
          return (
            <div className="rc" key={i} style={{ margin: 0, borderLeft: `2px solid ${v}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 3 }}>
                <b style={{ fontSize: 12.5 }}>{s.out}</b>
                <span style={{ fontSize: 9.5, textTransform: "uppercase", color: v }}>{s.urgency}</span>
              </div>
              <div style={{ fontSize: 11.5, color: "var(--low)", marginBottom: 5 }}>↳ {s.in}</div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>
                Aciliyet <span style={{ fontFamily: "JetBrains Mono", color: "var(--ink)" }}>{s.score.toFixed(2)}</span>
              </div>
              <ul style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.55, paddingLeft: 0, listStyle: "none", margin: 0 }}>
                {s.reasons.map((r, j) => <li key={j}>· {r}</li>)}
              </ul>
            </div>
          );
        })}
      </div>

      {/* Motor sinyalleri — ilk yarı kararları */}
      <div className="st"><h2>Motor Sinyalleri</h2><span className="ep">ilk yarı çıktıları</span></div>
      <div className="tbl" style={{ marginBottom: 14 }}>
        <table>
          <thead><tr>
            <th className="c">Dk</th><th>Karar</th><th>Tür</th><th className="c">Aciliyet</th><th className="r">Güven</th>
          </tr></thead>
          <tbody>
            {htDecisions.map((dec) => {
              const v = URG_VAR[dec.urgency] ?? "var(--muted)";
              return (
                <tr key={dec.minute}>
                  <td className="c pnum">{dec.minute}&apos;</td>
                  <td>
                    <span className="nm">{dec.headline}</span>
                    <span style={{ display: "block", fontSize: 11, color: "var(--dim)", marginTop: 2 }}>
                      <span title={dec.signals[0].engine}>{engineLabel(dec.signals[0].engine)}</span> · {dec.signals[0].label}
                    </span>
                  </td>
                  <td><span className="pos">{dec.decisionType}</span></td>
                  <td className="c"><span className="risk" style={{ color: v }}><span className="rd" style={{ background: v, boxShadow: `0 0 7px ${v}` }} />{dec.urgency}</span></td>
                  <td className="r">{dec.confidence}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Rakibin zayıf kanalı */}
      <div className="st"><h2>Rakibin Zayıf Noktaları</h2><span className="ep">2. yarı hedef</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, marginBottom: 14 }}>
        {demoWeaknesses.map((wk, i) => {
          const v = SEV_VAR[wk.severity] ?? "var(--muted)";
          return (
            <div className="rc" key={i} style={{ margin: 0, borderTop: `3px solid ${v}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                <b style={{ fontSize: 12.5, color: "var(--ink)" }}>{wk.title}</b>
                <span style={{ fontSize: 9.5, textTransform: "uppercase", color: v }}>{wk.severity}</span>
              </div>
              <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>{wk.detail}</div>
            </div>
          );
        })}
      </div>

      {/* En iyi eşleşme + set-piece uyarısı (iki kolon) */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 14 }}>
        <div>
          <div className="st" style={{ marginTop: 0 }}><h2>Sömürülecek Eşleşme</h2></div>
          <div className="rc" style={{ margin: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)", marginBottom: 4 }}>{topChannel.title}</div>
            <div style={{ fontSize: 12.5, color: "var(--ink)", marginBottom: 8 }}>
              {demoMatchups[0].ours} <span style={{ color: "var(--dim)" }}>vs</span> rakip {demoMatchups[0].theirs}
            </div>
            <div className="mbar"><i style={{ width: `${demoMatchups[0].advantage}%`, background: "var(--low)" }} /></div>
            <div style={{ fontSize: 11.5, color: "var(--muted)" }}>
              Avantaj <b style={{ color: "var(--low)" }}>%{demoMatchups[0].advantage}</b> · {demoMatchups[0].note}
            </div>
          </div>
        </div>
        <div>
          <div className="st" style={{ marginTop: 0 }}><h2>Duran Top Uyarısı</h2><span className="ep">{SET_PIECE.total_shots} şut</span></div>
          <div className="rc" style={{ margin: 0, borderLeft: "2px solid var(--crit)" }}>
            <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.5, marginBottom: 8 }}>{SET_PIECE.alert_text}</div>
            <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "JetBrains Mono" }}>
              en sık: {SET_PIECE.most_frequent_zone} · en tehlikeli: {SET_PIECE.most_dangerous_zone}
            </div>
          </div>
        </div>
      </div>

      {/* 2. yarı senaryo planı */}
      <div className="st"><h2>2. Yarı Planı — Senaryolar</h2><span className="ep">durum bazlı</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, marginBottom: 14 }}>
        {demoScenarios.map((s) => <ScenarioCard key={s.state} s={s} />)}
      </div>

      {/* 1. yarı öne çıkan olaylar */}
      <div className="st"><h2>1. Yarı Öne Çıkanlar</h2><span className="ep">{FIRST_HALF_EVENTS.length} olay</span></div>
      <div className="rc" style={{ margin: 0, padding: 0, overflow: "hidden" }}>
        {[...FIRST_HALF_EVENTS].reverse().map((e, i) => {
          const c = e.team === "home" ? HOME_COLOR : AWAY_COLOR;
          return (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "auto auto 1fr", gap: 11, alignItems: "center", padding: "10px 14px", borderTop: i ? "1px solid var(--line)" : undefined }}>
              <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 12, color: "var(--ink)", minWidth: 26 }}>{e.minute}&apos;</span>
              <span style={{ fontSize: 15 }}>{EV_ICON(e.type)}</span>
              <span style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.45, borderLeft: `2px solid ${c}`, paddingLeft: 10 }}>{e.text}</span>
            </div>
          );
        })}
      </div>
    </ConsoleShell>
  );
}

export default function HalftimePage() {
  return DEMO_MODE ? <DemoHalftimeView /> : <HalftimeApiView />;
}
