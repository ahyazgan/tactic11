"use client";

/**
 * Canlı Maç Konsolu — WebSocket momentum + sub önerisi + karar logu.
 * ConsoleShell çatısında. WS reconnect (exp backoff) ve DecisionPanel korunur.
 * WS: /api/ws/matches/{id}/live?my_team_id&interval_seconds&max_minute&tenant_id.
 */

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoLive, demoDecisions, type LiveEvent, type LivePlayerImpact, type DecisionCard } from "@/lib/demo-data";
import { engineLabel } from "@/lib/labels";
import { ConsoleShell } from "../../../_console/shell";

interface Confidence { score: number; label: string; drivers: string[] }

function Conf({ c }: { c?: Confidence | null }) {
  if (!c) return null;
  return <span style={{ fontSize: 10, textTransform: "uppercase", fontFamily: "JetBrains Mono", color: "var(--muted)", border: "1px solid var(--line)", borderRadius: 5, padding: "1px 6px" }}>güven {c.label} ({Math.round(c.score * 100)})</span>;
}

function notifyHighUrgency(playerId: number, score: number) {
  if (typeof window === "undefined") return;
  if (!("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  try {
    new Notification("Yüksek aciliyetli sub önerisi", {
      body: `Player #${playerId} — aciliyet ${score.toFixed(2)}. Şu an düşün.`,
      tag: `sub-${playerId}`,
      requireInteraction: false,
    });
  } catch {
    /* ignore */
  }
}

interface SubRecommendation { player_external_id: number; urgency_score: number; urgency_label: string; reasons: string[] }
interface PlayerShift { player_external_id: number; drift_distance: number }
interface VaepPlayer {
  player_id: number;
  vaep_value: number;
  total_actions: number;
  minutes_played?: number;
  on_pitch?: boolean | null;
  vaep_per_90?: number | null;
}
interface Snapshot {
  match_id?: number;
  my_team_id?: number;
  opponent_id?: number;
  current_minute?: number;
  events_so_far?: number;
  score?: string;
  mode?: string;
  phase?: string;
  data_quality?: { status?: string; score?: number };
  ppda?: { ppda?: number };
  field_tilt?: { team_a_tilt?: number };
  match_dominance?: { dominance_score?: number; label?: string; xg_diff?: number; possession_share?: number };
  live_sub_recommendation?: { recommendations: SubRecommendation[]; score_state: string };
  opponent_shape_drift?: { shape_changed: boolean; n_players_significant_drift: number; alert_text: string; player_shifts?: PlayerShift[] };
  momentum?: { score?: number; holder?: string; alert_text?: string };
  vaep?: {
    my_team_total?: number;
    opp_team_total?: number;
    top_players?: VaepPlayer[];
  };
  context?: { one_liner?: string | null; primary?: { headline?: string } | null; confidence_note?: string };
  confidence?: { context?: Confidence | null; live_sub_recommendation?: Confidence | null; momentum?: Confidence | null };
  trend?: {
    status?: string;
    momentum?: { direction?: string; sustained_snapshots?: number; delta?: number };
    field_tilt?: string;
    dominance?: string;
    stability?: { primary?: string | null; repeats?: number; stable?: boolean };
  };
  // Gizli karar motorları (backend zaten emit ediyor — ekrana taşınan):
  tactical_triggers?: { type: string; urgency: string; recommendation: string }[];
  live_matchup?: { struggling_defender?: number | null; hot_opponent?: number | null; alerts: string[] };
  spatial_control?: { gap_between_lines?: number; superiority_flank?: string; shape_state?: string; alerts: string[] };
  score_time_matrix?: { score_state?: string; posture?: string; closing_recipe?: string; alerts?: string[] };
  sub_timing?: { package: string[]; rationale: string; advices: { player_id: number; verdict: string; impact: number }[] };
  live_alerts?: { total: number; critical: number; warning: number; info: number; alerts: { type: string; severity: string; message: string; player_id?: number | null }[] };
  live_risk_monitor?: { score_state: string; time_management: string; card_flags: RiskFlag[]; injury_flags: RiskFlag[]; total_flags: number };
  type?: string;
  error?: string;
  note?: string;
}

const TREND_DIR_VAR: Record<string, string> = {
  "bize doğru": "var(--low)",
  "rakibe doğru": "var(--crit)",
  "dengeli": "var(--muted)",
};

// =========================================================================== //
// Gizli karar motorları — paylaşılan sunum panelleri (demo + WS aynı bileşeni
// besler). Backend WS snapshot'ı bu sinyalleri zaten üretiyor; biz görselleştiriyoruz.
// =========================================================================== //

const SEV_VAR: Record<string, string> = {
  critical: "var(--crit)", high: "var(--crit)", "kritik": "var(--crit)",
  warning: "var(--high)", medium: "var(--high)", "yüksek": "var(--high)",
  info: "var(--mid)", low: "var(--mid)", "orta": "var(--mid)",
};
const sevVar = (s?: string) => (s ? SEV_VAR[s.toLowerCase()] : undefined) ?? "var(--muted)";

const TRIGGER_LABEL: Record<string, string> = {
  formation: "Formasyon", press_height: "Pres Hattı", channel_shift: "Kanal Kaydır",
};

interface RiskFlag { player_external_id: number; risk_type: string; severity: string; message: string }
interface AlertItem { type: string; severity: string; message: string; player_id?: number | null }
interface TacticalTrigger { type: string; urgency: string; recommendation: string }
interface SubTimingAdvice { player_id: number; verdict: string; impact: number }

function TriggersPanel({ triggers }: { triggers: TacticalTrigger[] }) {
  if (!triggers.length) return null;
  return (
    <>
      <div className="st"><h2>Taktik Tetikler</h2><span className="ep">{triggers.length} aktif</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 12, marginBottom: 14 }}>
        {triggers.map((t, i) => {
          const v = sevVar(t.urgency);
          return (
            <div className="rc" key={i} style={{ margin: 0, borderLeft: `2px solid ${v}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <b style={{ fontSize: 12.5 }}>{TRIGGER_LABEL[t.type] ?? t.type}</b>
                <span style={{ fontSize: 10, textTransform: "uppercase", color: v }}>{t.urgency}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{t.recommendation}</div>
            </div>
          );
        })}
      </div>
    </>
  );
}

function ClosingPanel({ scoreState, posture, recipe }: { scoreState?: string; posture?: string; recipe?: string }) {
  if (!recipe && !posture) return null;
  return (
    <div className="rc" style={{ margin: 0 }}>
      <h3>Kapanış Reçetesi {scoreState && <span className="tiny">{scoreState}</span>}</h3>
      {posture && <div style={{ fontSize: 12, color: "var(--low)", fontWeight: 600, marginBottom: 4 }}>{posture}</div>}
      {recipe && <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5 }}>{recipe}</div>}
    </div>
  );
}

function SpatialPanel({ gap, flank, shapeState, alerts }: { gap?: number; flank?: string; shapeState?: string; alerts: string[] }) {
  if (gap == null && !flank && !alerts.length) return null;
  return (
    <div className="rc" style={{ margin: 0 }}>
      <h3>Mekânsal Kontrol</h3>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 14, fontSize: 12, marginBottom: 6 }}>
        {gap != null && <span style={{ color: "var(--muted)" }}>Hat boşluğu: <b style={{ color: "var(--ink)", fontFamily: "JetBrains Mono" }}>{gap}m</b></span>}
        {flank && <span style={{ color: "var(--muted)" }}>Üstün kanat: <b style={{ color: "var(--low)" }}>{flank}</b></span>}
      </div>
      {shapeState && <div style={{ fontSize: 11.5, color: "var(--dim)", marginBottom: 4 }}>Şekil: {shapeState}</div>}
      {alerts.map((a, i) => <div key={i} style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45, marginTop: 4 }}>· {a}</div>)}
    </div>
  );
}

function MatchupPanel({ alerts }: { alerts: string[] }) {
  if (!alerts.length) return null;
  return (
    <>
      <div className="st"><h2>Bireysel Eşleşme Uyarıları</h2><span className="ep">{alerts.length}</span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        {alerts.map((a, i) => (
          <div key={i} style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.5, padding: "7px 0", borderTop: i ? "1px solid var(--line)" : undefined }}>{a}</div>
        ))}
      </div>
    </>
  );
}

function SubTimingPanel({ pkg, rationale, advices }: { pkg: string[]; rationale?: string; advices: SubTimingAdvice[] }) {
  if (!advices.length && !pkg.length) return null;
  return (
    <>
      <div className="st"><h2>Değişiklik Zamanlaması</h2>{pkg.length > 0 && <span className="ep">paket: {pkg.join(" + ")}</span>}</div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        {rationale && <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5, marginBottom: 8 }}>{rationale}</div>}
        {advices.map((a, i) => (
          <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, fontSize: 12, padding: "5px 0", borderTop: i ? "1px solid var(--line)" : undefined }}>
            <span style={{ fontFamily: "JetBrains Mono" }}>#{a.player_id}</span>
            <span style={{ color: "var(--ink)", flex: 1, textAlign: "center" }}>{a.verdict}</span>
            <span style={{ fontFamily: "JetBrains Mono", color: "var(--low)" }}>etki +{a.impact.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function RiskPanel({ cardFlags, injuryFlags, timeManagement }: { cardFlags: RiskFlag[]; injuryFlags: RiskFlag[]; timeManagement?: string }) {
  const flags = [...cardFlags, ...injuryFlags];
  return (
    <div className="rc">
      <h3>Risk Monitörü <span className="tiny">{flags.length} bayrak</span></h3>
      {flags.length === 0 && <div style={{ fontSize: 12, color: "var(--dim)" }}>Aktif kart/sakatlık riski yok.</div>}
      {flags.map((f, i) => {
        const v = sevVar(f.severity);
        return (
          <div className="alrt" key={i}>
            <span className="ai" style={{ background: v }} />
            <div className="am"><b>{f.risk_type === "card" ? "Kart riski" : "Sakatlık riski"}</b>
              <span className="tm">{f.message}</span>
            </div>
          </div>
        );
      })}
      {timeManagement && (
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--line)", lineHeight: 1.45 }}>
          <b style={{ color: "var(--ink)" }}>Zaman yönetimi:</b> {timeManagement}
        </div>
      )}
    </div>
  );
}

const ALERT_ORDER: Record<string, number> = { critical: 0, warning: 1, info: 2 };

function AlertsFeedPanel({ alerts }: { alerts: AlertItem[] }) {
  if (!alerts.length) return null;
  const sorted = [...alerts].sort((a, b) => (ALERT_ORDER[a.severity] ?? 9) - (ALERT_ORDER[b.severity] ?? 9));
  return (
    <div className="rc">
      <h3>Uyarı Akışı <span className="tiny">{alerts.length}</span></h3>
      {sorted.map((a, i) => {
        const v = sevVar(a.severity);
        return (
          <div className="alrt" key={i}>
            <span className="ai" style={{ background: v }} />
            <div className="am"><b style={{ textTransform: "uppercase", fontSize: 10, color: v }}>{a.severity}</b>
              <span className="tm">{a.message}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DataQualityLine({ status, score }: { status?: string; score?: number }) {
  if (!status) return null;
  const v = status === "ok" ? "var(--low)" : status === "degraded" ? "var(--mid)" : "var(--crit)";
  return (
    <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 8, fontFamily: "JetBrains Mono" }}>
      veri kalitesi: <span style={{ color: v }}>{status}</span>{score != null ? ` (%${Math.round(score * 100)})` : ""}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Sıradaki En İyi Hamle — tüm motorların tetiklenen sinyallerini tek bir
// önceliklendirilmiş direktife indirger ("sistem karar veriyor → tek net hamle").
// Hem demo (demoDecisions) hem WS (snapshot sinyalleri) bu bileşeni besler.
// --------------------------------------------------------------------------- //

interface NbaSignal { engine: string; label: string; magnitude?: number }
interface NextAction {
  headline: string;
  decisionType?: string;
  urgency: string;        // kritik|yüksek|orta | critical|high|medium
  confidence?: number;    // 0..100
  timing?: string;
  signals: NbaSignal[];
}

function NextBestActionPanel({ action }: { action: NextAction | null }) {
  if (!action) return null;
  const v = sevVar(action.urgency);
  return (
    <div className="rc" style={{ margin: "0 0 14px", borderLeft: `3px solid ${v}`, background: "var(--panel2)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 6 }}>
        <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>
          ▶ Sıradaki En İyi Hamle{action.decisionType ? ` · ${action.decisionType}` : ""}
        </span>
        <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {action.timing && <span style={{ fontSize: 11, color: "var(--low)", fontFamily: "JetBrains Mono" }}>{action.timing}</span>}
          <span style={{ fontSize: 10, textTransform: "uppercase", color: v, border: `1px solid ${v}`, borderRadius: 5, padding: "1px 6px" }}>{action.urgency}</span>
        </span>
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, color: "var(--ink)", lineHeight: 1.4, marginBottom: action.signals.length ? 8 : 0 }}>
        {action.headline}
      </div>
      {action.signals.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 5, paddingTop: 8, borderTop: "1px solid var(--line)" }}>
          {action.signals.map((s, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11.5 }}>
              <span title={s.engine} style={{ color: "var(--dim)", minWidth: 140 }}>{engineLabel(s.engine)}</span>
              <span style={{ color: "var(--muted)", flex: 1 }}>{s.label}</span>
              {s.magnitude != null && (
                <span className="mbar" style={{ width: 48, display: "inline-block" }}>
                  <i style={{ width: `${Math.round(s.magnitude * 100)}%`, background: v }} />
                </span>
              )}
            </div>
          ))}
        </div>
      )}
      {action.confidence != null && (
        <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 8, fontFamily: "JetBrains Mono" }}>model güveni %{action.confidence}</div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Karar Zaman Şeridi — maçın karar anları dakika ekseninde; bir noktaya
// tıklayınca o kararın kanıt zinciri (motor · sinyal · örneklem · güç) açılır.
// "Sistem nasıl karar verdi"yi somutlaştırır. (demo: demoDecisions)
// --------------------------------------------------------------------------- //

const DTYPE_ICON: Record<string, string> = {
  "Oyuncu Değişikliği": "🔁", "Taktik": "📐", "Risk": "⚠", "Duran Top": "🎯",
};

function DecisionTimeline({ decisions, currentMinute }: { decisions: DecisionCard[]; currentMinute: number }) {
  const sorted = [...decisions].sort((a, b) => a.minute - b.minute);
  // varsayılan seçili: şu ana kadar verilmiş en son karar
  const activeIdx = sorted.reduce((acc, d, i) => (d.minute <= currentMinute ? i : acc), 0);
  const [sel, setSel] = useState(activeIdx);
  if (!sorted.length) return null;
  const span = 90;
  const card = sorted[Math.min(sel, sorted.length - 1)];
  const v = sevVar(card.urgency);
  const nowPct = Math.min(100, (currentMinute / span) * 100);
  return (
    <>
      <div className="st"><h2>Karar Zaman Şeridi</h2><span className="ep">{sorted.length} karar · motor gerekçeli</span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <div style={{ position: "relative", height: 34, marginBottom: 12 }}>
          <div style={{ position: "absolute", top: 18, left: 0, right: 0, height: 2, background: "var(--line)" }} />
          {/* geçmiş kısmı vurgula */}
          <div style={{ position: "absolute", top: 18, left: 0, width: `${nowPct}%`, height: 2, background: "var(--border2)" }} />
          {/* şimdi imleci */}
          <div style={{ position: "absolute", top: 0, left: `${nowPct}%`, transform: "translateX(-50%)", fontSize: 9, color: "var(--accent)", fontFamily: "JetBrains Mono" }}>şimdi</div>
          <div style={{ position: "absolute", top: 12, bottom: 0, left: `${nowPct}%`, width: 1, background: "var(--accent)" }} />
          {sorted.map((d, i) => {
            const dv = sevVar(d.urgency);
            const left = Math.min(100, (d.minute / span) * 100);
            const isSel = i === sel;
            const future = d.minute > currentMinute;
            return (
              <button key={i} type="button" onClick={() => setSel(i)} title={`${d.minute}' — ${d.headline}`}
                style={{ position: "absolute", top: isSel ? 9 : 11, left: `${left}%`, transform: "translateX(-50%)", width: isSel ? 20 : 16, height: isSel ? 20 : 16, borderRadius: "50%", border: `2px solid ${dv}`, background: isSel ? dv : "var(--panel)", cursor: "pointer", padding: 0, opacity: future ? 0.45 : 1, fontSize: 9, lineHeight: 1 }}>
                <span style={{ position: "absolute", top: 22, left: "50%", transform: "translateX(-50%)", fontSize: 9, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>{d.minute}&apos;</span>
              </button>
            );
          })}
        </div>
        <div style={{ borderLeft: `3px solid ${v}`, paddingLeft: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
            <b style={{ fontSize: 13.5 }}>{DTYPE_ICON[card.decisionType] ?? "•"} {card.minute}&apos; — {card.headline}</b>
            <span style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
              <span style={{ fontSize: 10, textTransform: "uppercase", color: v }}>{card.urgency}</span>
              <span style={{ fontSize: 10, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>%{card.confidence}</span>
            </span>
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5, marginBottom: 8 }}>{card.rationale}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {card.signals.map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
                <span title={s.engine} style={{ color: "var(--dim)", minWidth: 150 }}>{engineLabel(s.engine)}</span>
                <span style={{ color: "var(--muted)", flex: 1 }}>{s.label}</span>
                <span style={{ fontSize: 10, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>n={s.sampleSize}</span>
                <span className="mbar" style={{ width: 44, display: "inline-block" }}>
                  <i style={{ width: `${Math.round(s.magnitude * 100)}%`, background: v }} />
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

const URGENCY_RANK: Record<string, number> = { "kritik": 4, "yüksek": 3, "orta": 2, "düşük": 1 };

// Demo: verilmiş kararlar arasından şu ana kadarki en yüksek öncelikli olanı seç.
function demoNextAction(): NextAction | null {
  const cur = demoLive.minute;
  const cands = demoDecisions.filter((d) => d.minute <= cur);
  if (!cands.length) return null;
  const best = [...cands].sort(
    (a, b) => (URGENCY_RANK[b.urgency] - URGENCY_RANK[a.urgency]) || (b.confidence - a.confidence) || (b.minute - a.minute),
  )[0];
  const timing = best.decisionType === "Oyuncu Değişikliği"
    ? demoLive.subTiming.advices[0]?.verdict : undefined;
  return {
    headline: best.headline,
    decisionType: best.decisionType,
    urgency: best.urgency,
    confidence: best.confidence,
    timing,
    signals: best.signals.map((s) => ({ engine: s.engine, label: s.label, magnitude: s.magnitude })),
  };
}

// WS: canlı snapshot sinyallerini önceliklendir (kritik uyarı > yüksek sub >
// yüksek taktik tetik). Momentum trendi + risk bayrakları gerekçe olarak eklenir.
function wsNextAction(snap: Snapshot): NextAction | null {
  const corro: NbaSignal[] = [];
  const tm = snap.trend?.momentum;
  if (tm?.direction && tm.direction !== "dengeli") {
    corro.push({
      engine: "momentum_tracker",
      label: `Momentum ${tm.direction}${(tm.sustained_snapshots ?? 0) >= 2 ? ` · ${tm.sustained_snapshots} snapshot` : ""}`,
      magnitude: tm.delta != null ? Math.min(1, Math.abs(tm.delta)) : undefined,
    });
  }
  const rm = snap.live_risk_monitor;
  if (rm && rm.total_flags > 0) {
    corro.push({ engine: "live_risk_monitor", label: `${rm.total_flags} risk bayrağı (kart/sakatlık)` });
  }

  const crit = snap.live_alerts?.alerts?.find((a) => a.severity === "critical");
  if (crit) {
    return { headline: crit.message, decisionType: "Acil Uyarı", urgency: "critical", signals: corro };
  }
  const sub = (snap.live_sub_recommendation?.recommendations ?? []).find((r) => r.urgency_label === "high");
  if (sub) {
    return {
      headline: `Değişiklik düşün — #${sub.player_external_id} (${sub.reasons[0] ?? "yüksek aciliyet"})`,
      decisionType: "Oyuncu Değişikliği",
      urgency: "yüksek",
      confidence: snap.confidence?.live_sub_recommendation?.score != null
        ? Math.round(snap.confidence.live_sub_recommendation.score * 100) : undefined,
      signals: [
        { engine: "sub_timing", label: `aciliyet skoru ${sub.urgency_score.toFixed(2)}`, magnitude: Math.min(1, sub.urgency_score) },
        ...corro,
      ],
    };
  }
  const trig = (snap.tactical_triggers ?? []).find((t) => t.urgency === "high") ?? (snap.tactical_triggers ?? [])[0];
  if (trig) {
    return { headline: trig.recommendation, decisionType: "Taktik", urgency: trig.urgency, signals: corro };
  }
  return null;
}

function LiveWsView() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const matchId = params.id;
  const myTeam = search.get("my_team_id");
  const interval = search.get("interval_seconds") ?? "10";
  const maxMinute = search.get("max_minute") ?? "90";
  const tenantId = search.get("tenant_id") ?? "t-default";

  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [wsState, setWsState] = useState<"connecting" | "open" | "reconnecting" | "closed">("connecting");
  const [reconnectCountdown, setReconnectCountdown] = useState<number | null>(null);
  const [ended, setEnded] = useState(false);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const notifiedPlayersRef = useRef<Set<number>>(new Set());
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef<boolean>(false);
  const [manualReconnectTrigger, setManualReconnectTrigger] = useState(0);

  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  useEffect(() => {
    if (!myTeam || ended) return;
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${proto}//${host}/api/ws/matches/${matchId}/live?my_team_id=${myTeam}&interval_seconds=${interval}&max_minute=${maxMinute}&tenant_id=${tenantId}`;

    intentionalCloseRef.current = false;
    setWsState("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;
    ws.onopen = () => {
      setWsState("open");
      reconnectAttemptsRef.current = 0;
      setReconnectCountdown(null);
    };
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as Snapshot;
        if (data.type === "match_ended") {
          setEnded(true);
          intentionalCloseRef.current = true;
          return;
        }
        setSnapshot(data);
        setHistory((h) => [...h.slice(-19), data]);
        const recs = data.live_sub_recommendation?.recommendations ?? [];
        for (const rec of recs) {
          if (rec.urgency_label === "high" && !notifiedPlayersRef.current.has(rec.player_external_id)) {
            notifyHighUrgency(rec.player_external_id, rec.urgency_score);
            notifiedPlayersRef.current.add(rec.player_external_id);
          }
        }
      } catch {
        /* ignore */
      }
    };
    ws.onclose = () => {
      if (intentionalCloseRef.current || ended) {
        setWsState("closed");
        return;
      }
      const attempts = reconnectAttemptsRef.current;
      if (attempts >= 10) {
        setWsState("closed");
        return;
      }
      const delay = Math.min(30_000, 2_000 * Math.pow(2, attempts));
      reconnectAttemptsRef.current = attempts + 1;
      setWsState("reconnecting");
      setReconnectCountdown(Math.ceil(delay / 1000));
      const countdownInterval = setInterval(() => {
        setReconnectCountdown((c) => (c !== null && c > 0 ? c - 1 : c));
      }, 1000);
      reconnectTimerRef.current = setTimeout(() => {
        clearInterval(countdownInterval);
        setReconnectCountdown(null);
        setManualReconnectTrigger((x) => x + 1);
      }, delay);
    };
    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      ws.close();
    };
  }, [matchId, myTeam, interval, maxMinute, tenantId, ended, manualReconnectTrigger]);

  const handleManualReconnect = () => {
    reconnectAttemptsRef.current = 0;
    setManualReconnectTrigger((x) => x + 1);
  };

  if (!myTeam) {
    return (
      <ConsoleShell active="/matches" title={`Canlı — Maç #${matchId}`} sub="Canlı maç konsolu">
        <div className="pgdesc"><code style={{ fontFamily: "JetBrains Mono" }}>?my_team_id=&lt;N&gt;</code> parametresi gerekli (Maç detayından gel).</div>
      </ConsoleShell>
    );
  }

  const dom = snapshot?.match_dominance?.dominance_score ?? 0;
  const recs = snapshot?.live_sub_recommendation?.recommendations ?? [];

  const right = (
    <>
      <div className="rc">
        <h3>Bağlantı</h3>
        {ended && <div style={{ fontSize: 13, color: "var(--muted)" }}>● Maç bitti</div>}
        {!ended && wsState === "open" && <div style={{ fontSize: 13, color: "var(--low)", fontWeight: 700 }}>● Canlı</div>}
        {!ended && wsState === "connecting" && <div style={{ fontSize: 13, color: "var(--mid)" }}>Bağlanıyor…</div>}
        {!ended && wsState === "reconnecting" && <div style={{ fontSize: 13, color: "var(--mid)" }}>Yeniden bağlanıyor{reconnectCountdown !== null ? ` (${reconnectCountdown}sn)` : ""}</div>}
        {!ended && wsState === "closed" && (
          <div>
            <div style={{ fontSize: 13, color: "var(--crit)", marginBottom: 8 }}>Bağlantı koptu</div>
            <button type="button" onClick={handleManualReconnect} style={{ fontSize: 11, textTransform: "uppercase", padding: "5px 10px", borderRadius: 6, border: "1px solid var(--line)", color: "var(--ink)", background: "var(--panel3)", cursor: "pointer" }}>Yeniden bağlan</button>
          </div>
        )}
        <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 10, fontFamily: "JetBrains Mono" }}>geçmiş: {history.length} kayıt · {interval}sn</div>
        <DataQualityLine status={snapshot?.data_quality?.status} score={snapshot?.data_quality?.score} />
      </div>
      {snapshot?.live_risk_monitor && (
        <RiskPanel
          cardFlags={snapshot.live_risk_monitor.card_flags ?? []}
          injuryFlags={snapshot.live_risk_monitor.injury_flags ?? []}
          timeManagement={snapshot.live_risk_monitor.time_management}
        />
      )}
      {(snapshot?.live_alerts?.alerts?.length ?? 0) > 0 && (
        <AlertsFeedPanel alerts={snapshot!.live_alerts!.alerts} />
      )}
      {recs.length > 0 && (
        <div className="rc">
          <h3>Sub Önerileri <span className="tiny">top {recs.length}</span></h3>
          {recs.map((rec) => {
            const v = rec.urgency_label === "high" ? "var(--crit)" : rec.urgency_label === "medium" ? "var(--mid)" : "var(--muted)";
            return (
              <div className="alrt" key={rec.player_external_id}>
                <span className="ai" style={{ background: v }} />
                <div className="am"><b style={{ fontFamily: "JetBrains Mono" }}>#{rec.player_external_id}</b> · {rec.urgency_label}
                  <span className="tm">aciliyet {rec.urgency_score.toFixed(2)} · {rec.reasons[0] ?? ""}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );

  const statusLabel = ended ? "Maç bitti" : wsState === "open" ? "● Canlı" : wsState === "connecting" ? "Bağlanıyor" : wsState === "reconnecting" ? "Yeniden bağlanıyor" : "Bağlantı koptu";

  return (
    <ConsoleShell
      active="/matches"
      title={`Canlı — Maç #${matchId}`}
      sub={`Takım #${myTeam} · ${statusLabel}`}
      desc="WebSocket canlı momentum, dominance ve oyuncu değişikliği önerileri."
      right={right}
    >
      {snapshot?.note && <div className="pgdesc">{snapshot.note}</div>}
      {snapshot?.error && <div className="rc" style={{ margin: "0 0 14px", borderLeft: "2px solid var(--crit)", color: "var(--crit)", fontSize: 13 }}>{snapshot.error}</div>}

      {snapshot && !snapshot.error && (
        <>
          <div className="st" style={{ marginTop: 0 }}>
            <h2>Maç Durumu</h2>
            <span className="tiny" style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {snapshot.mode && (
                <span title="Gerçek-zamanlı feed değil, StatsBomb maçının sadık replay'i" style={{ color: snapshot.mode === "replay_statsbomb" ? "var(--mid)" : "var(--low)" }}>
                  {snapshot.mode === "replay_statsbomb" ? "Replay (StatsBomb)" : "Live"}
                </span>
              )}
              {snapshot.data_quality?.status && (
                <span title="Event akışı veri kalitesi" style={{ color: snapshot.data_quality.status === "ok" ? "var(--low)" : snapshot.data_quality.status === "degraded" ? "var(--mid)" : "var(--crit)" }}>
                  veri: {snapshot.data_quality.status}
                </span>
              )}
            </span>
          </div>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
            <div className="kpi"><div className="kl">Dakika</div><div className="kn">{snapshot.current_minute?.toFixed(0) ?? "—"}</div><div className="kd">{snapshot.phase ?? ""}</div></div>
            <div className="kpi"><div className="kl">Skor{snapshot.current_minute != null ? ` (${snapshot.current_minute.toFixed(0)}'e kadar)` : ""}</div><div className="kn">{snapshot.score ?? "—"}</div><div className="kd">{snapshot.live_sub_recommendation?.score_state ?? ""}</div></div>
            <div className="kpi"><div className="kl">Olay</div><div className="kn">{snapshot.events_so_far ?? 0}</div></div>
            <div className="kpi"><div className="kl">Dominance</div><div className="kn" style={{ color: dom > 1 ? "var(--low)" : dom < -1 ? "var(--crit)" : "var(--ink)" }}>{snapshot.match_dominance?.dominance_score?.toFixed(2) ?? "—"}</div><div className="kd">{snapshot.match_dominance?.label ?? ""}</div></div>
          </div>

          <NextBestActionPanel action={wsNextAction(snapshot)} />

          {snapshot.context?.one_liner && (
            <>
              <div className="st"><h2>Bağlam & Güven</h2></div>
              <div className="rc" style={{ margin: "0 0 14px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                  <span style={{ fontSize: 13, color: "var(--ink)" }}>{snapshot.context.one_liner}</span>
                  <Conf c={snapshot.confidence?.context} />
                </div>
                {snapshot.context.confidence_note && <div style={{ fontSize: 12, color: "var(--mid)", marginTop: 6 }}>⚠ {snapshot.context.confidence_note}</div>}
                {snapshot.momentum?.alert_text && (
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--line)" }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>{snapshot.momentum.alert_text}</span>
                    <Conf c={snapshot.confidence?.momentum} />
                  </div>
                )}
                {snapshot.trend?.status === "ok" && snapshot.trend.momentum && (
                  <div style={{ fontSize: 12, marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--line)", color: "var(--muted)" }}>
                    Trend: momentum <span style={{ color: TREND_DIR_VAR[snapshot.trend.momentum.direction ?? ""] ?? "var(--muted)" }}>{snapshot.trend.momentum.direction}</span>
                    {(snapshot.trend.momentum.sustained_snapshots ?? 0) >= 2 && <> · {snapshot.trend.momentum.sustained_snapshots} snapshot&apos;tır</>}
                    {snapshot.trend.stability?.stable && <span style={{ color: "var(--low)" }}> · sinyal istikrarlı</span>}
                  </div>
                )}
              </div>
            </>
          )}

          <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
            <div className="kpi"><div className="kl">PPDA</div><div className="kn" style={{ fontSize: 22 }}>{snapshot.ppda?.ppda?.toFixed(2) ?? "—"}</div></div>
            <div className="kpi"><div className="kl">Field Tilt (biz)</div><div className="kn" style={{ fontSize: 22 }}>{snapshot.field_tilt ? `%${Math.round((snapshot.field_tilt.team_a_tilt ?? 0) * 100)}` : "—"}</div></div>
            <div className="kpi"><div className="kl">xG Farkı</div><div className="kn" style={{ fontSize: 22 }}>{snapshot.match_dominance?.xg_diff?.toFixed(2) ?? "—"}</div></div>
          </div>

          <TriggersPanel triggers={snapshot.tactical_triggers ?? []} />

          {(snapshot.score_time_matrix || snapshot.spatial_control) && (
            <>
              <div className="st"><h2>Kapanış & Mekân</h2></div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
                <ClosingPanel scoreState={snapshot.score_time_matrix?.score_state} posture={snapshot.score_time_matrix?.posture} recipe={snapshot.score_time_matrix?.closing_recipe} />
                <SpatialPanel gap={snapshot.spatial_control?.gap_between_lines} flank={snapshot.spatial_control?.superiority_flank} shapeState={snapshot.spatial_control?.shape_state} alerts={snapshot.spatial_control?.alerts ?? []} />
              </div>
            </>
          )}

          <MatchupPanel alerts={snapshot.live_matchup?.alerts ?? []} />

          <SubTimingPanel pkg={snapshot.sub_timing?.package ?? []} rationale={snapshot.sub_timing?.rationale} advices={snapshot.sub_timing?.advices ?? []} />

          {recs.length > 0 && (
            <>
              <div className="st"><h2>Değişiklik Önerileri (Top 3)</h2></div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 14 }}>
                {recs.map((rec) => {
                  const v = rec.urgency_label === "high" ? "var(--crit)" : rec.urgency_label === "medium" ? "var(--mid)" : "var(--muted)";
                  return (
                    <div className="rc" key={rec.player_external_id} style={{ margin: 0, borderLeft: `2px solid ${v}` }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontFamily: "JetBrains Mono" }}>#{rec.player_external_id}</span>
                        <span style={{ fontSize: 10, textTransform: "uppercase", color: v }}>{rec.urgency_label}</span>
                      </div>
                      <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6 }}>Aciliyet: <span style={{ fontFamily: "JetBrains Mono" }}>{rec.urgency_score.toFixed(2)}</span></div>
                      <ul style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.6, paddingLeft: 0, listStyle: "none", margin: 0 }}>
                        {rec.reasons.map((r, i) => <li key={i}>· {r}</li>)}
                      </ul>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {(snapshot.vaep?.top_players?.length ?? 0) > 0 && (
            <>
              <div className="st">
                <h2>Oyuncu Etkisi (VAEP)</h2>
                <span className="tiny" style={{ fontFamily: "JetBrains Mono" }}>
                  takım toplam {snapshot.vaep?.my_team_total?.toFixed(2) ?? "—"}
                </span>
              </div>
              <div className="rc" style={{ margin: "0 0 14px", padding: 0, overflow: "hidden" }}>
                <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto auto auto", fontSize: 11, color: "var(--dim)", textTransform: "uppercase", padding: "8px 12px", borderBottom: "1px solid var(--line)", gap: 10 }}>
                  <span>Oyuncu</span><span>Durum</span><span style={{ textAlign: "right" }}>Dakika</span><span style={{ textAlign: "right" }}>VAEP</span><span style={{ textAlign: "right" }}>VAEP/90</span>
                </div>
                {snapshot.vaep?.top_players?.map((p) => {
                  const onPitch = p.on_pitch;
                  const badge = onPitch === true
                    ? { t: "sahada", c: "var(--low)" }
                    : onPitch === false
                    ? { t: "çıktı", c: "var(--crit)" }
                    : null;
                  return (
                    <div key={p.player_id} style={{ display: "grid", gridTemplateColumns: "auto 1fr auto auto auto", alignItems: "center", padding: "7px 12px", borderTop: "1px solid var(--line)", gap: 10, opacity: onPitch === false ? 0.6 : 1 }}>
                      <span style={{ fontFamily: "JetBrains Mono" }}>#{p.player_id}</span>
                      <span>{badge ? <span style={{ fontSize: 10, textTransform: "uppercase", color: badge.c }}>● {badge.t}</span> : <span style={{ fontSize: 10, color: "var(--dim)" }}>—</span>}</span>
                      <span style={{ textAlign: "right", fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{p.minutes_played != null ? `${p.minutes_played.toFixed(0)}'` : "—"}</span>
                      <span style={{ textAlign: "right", fontFamily: "JetBrains Mono" }}>{p.vaep_value.toFixed(2)}</span>
                      <span style={{ textAlign: "right", fontFamily: "JetBrains Mono", color: "var(--low)" }}>{p.vaep_per_90 != null ? p.vaep_per_90.toFixed(2) : "—"}</span>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {snapshot.opponent_shape_drift && (
            <>
              <div className="st"><h2>Rakip Formasyon Takibi</h2></div>
              <div className="rc" style={{ margin: "0 0 14px", borderLeft: snapshot.opponent_shape_drift.shape_changed ? "2px solid var(--crit)" : undefined }}>
                <div style={{ fontSize: 13, color: "var(--ink)" }}>{snapshot.opponent_shape_drift.alert_text}</div>
                {snapshot.opponent_shape_drift.player_shifts && snapshot.opponent_shape_drift.player_shifts.length > 0 && (
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, fontFamily: "JetBrains Mono" }}>
                    Drift: {snapshot.opponent_shape_drift.player_shifts.slice(0, 5).map((p) => `#${p.player_external_id} (${p.drift_distance.toFixed(1)})`).join(", ")}
                  </div>
                )}
              </div>
            </>
          )}

          <DecisionPanel matchId={Number(matchId)} teamId={Number(myTeam)} currentMinute={snapshot.current_minute ?? 0} />
        </>
      )}
    </ConsoleShell>
  );
}

function DecisionPanel({ matchId, teamId, currentMinute }: { matchId: number; teamId: number; currentMinute: number }) {
  const [type, setType] = useState<"substitution" | "formation_change" | "tactical_instruction">("substitution");
  const [subjectPid, setSubjectPid] = useState("");
  const [relatedPid, setRelatedPid] = useState("");
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState<{ id: number; minute: number }[]>([]);
  const [error, setError] = useState("");

  async function submit() {
    setError("");
    try {
      const res = await fetch(`/api/admin/matches/${matchId}/decisions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          team_external_id: teamId,
          minute: currentMinute,
          period: currentMinute > 45 ? 2 : 1,
          decision_type: type,
          subject_player_external_id: subjectPid ? Number(subjectPid) : null,
          related_player_external_id: relatedPid ? Number(relatedPid) : null,
          notes: notes || null,
        }),
      });
      if (!res.ok) {
        setError(`HTTP ${res.status}`);
        return;
      }
      const body = await res.json();
      setSaved((s) => [...s, { id: body.id, minute: body.minute }]);
      setSubjectPid("");
      setRelatedPid("");
      setNotes("");
    } catch (e) {
      setError(String(e));
    }
  }

  const fld: CSSProperties = { background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 6, padding: "6px 9px", fontSize: 12.5, color: "var(--ink)", fontFamily: "inherit" };

  return (
    <>
      <div className="st"><h2>Karar Logu</h2><span className="ep">TD hamlesi kaydet</span></div>
      <div className="rc" style={{ margin: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 8, marginBottom: 8 }}>
          <select value={type} onChange={(e) => setType(e.target.value as typeof type)} style={fld}>
            <option value="substitution">Substitution</option>
            <option value="formation_change">Formation change</option>
            <option value="tactical_instruction">Tactical instruction</option>
          </select>
          <input placeholder="Çıkan oyuncu ID" value={subjectPid} onChange={(e) => setSubjectPid(e.target.value)} style={fld} />
          <input placeholder="Giren oyuncu ID" value={relatedPid} onChange={(e) => setRelatedPid(e.target.value)} style={fld} />
          <button onClick={submit} style={{ ...fld, background: "var(--besiktas)", color: "#fff", fontWeight: 600, cursor: "pointer", border: 0 }}>Kaydet @ {currentMinute.toFixed(0)}.dk</button>
        </div>
        <input placeholder="Not (opsiyonel)" value={notes} onChange={(e) => setNotes(e.target.value)} style={{ ...fld, width: "100%", boxSizing: "border-box" }} />
        {error && <div style={{ color: "var(--crit)", fontSize: 11, marginTop: 8 }}>{error}</div>}
        {saved.length > 0 && (
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8 }}>Bu oturumda {saved.length} karar: {saved.map((s) => `#${s.id}@${s.minute.toFixed(0)}'`).join(", ")}</div>
        )}
      </div>
    </>
  );
}

// =========================================================================== //
// DEMO görünümü — backend/WS YOK; xG yarışı + momentum + olay akışı + sub.
// =========================================================================== //

const HOME_COLOR = "#3d7eff";
const AWAY_COLOR = "#ef4444";

const EV_ICON: Record<LiveEvent["type"], string> = {
  gol: "⚽", sari_kart: "🟨", kirmizi_kart: "🟥",
  sakatlik: "🩹", degisiklik: "🔁", buyuk_firsat: "✨",
};

// Faz B — sahadaki kadro farkındalığı: as-of sahadaki XI, oyuncu-başı gerçek
// dakika ve dakikaya normalize VAEP/90. En yüksek VAEP/90 üstte; çıkan oyuncu
// soluk + "öneri havuzundan düştü". Kısa süre oynayan etkili oyuncuyu öne çıkarır.
function LineupImpact({ lineup, clock, formation }: { lineup: LivePlayerImpact[]; clock: number; formation: string }) {
  const onPitch = lineup.filter((p) => p.onPitch);
  const off = lineup.filter((p) => !p.onPitch);
  const rows = [...lineup].sort((a, b) => Number(b.onPitch) - Number(a.onPitch) || b.vaepPer90 - a.vaepPer90);
  const maxPer90 = Math.max(0.8, ...lineup.map((p) => p.vaepPer90));
  const topImpact = onPitch.reduce((best, p) => (p.vaepPer90 > best.vaepPer90 ? p : best), onPitch[0]);

  return (
    <>
      <div className="st">
        <h2>Sahadaki Kadro & Oyuncu Etkisi</h2>
        <span className="ep">{formation} · {onPitch.length} sahada · {clock}&apos;e kadar</span>
      </div>
      <div className="tbl" style={{ marginBottom: 8 }}>
        <table>
          <thead>
            <tr>
              <th>Oyuncu</th>
              <th className="c">Durum</th>
              <th className="r">Dakika</th>
              <th className="r">VAEP</th>
              <th className="r">VAEP/90</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const minPct = Math.min(100, (p.minutes / clock) * 100);
              const p90Pct = Math.min(100, (p.vaepPer90 / maxPer90) * 100);
              const isTop = p.onPitch && p.shirt === topImpact.shirt;
              return (
                <tr key={p.shirt} style={{ opacity: p.onPitch ? 1 : 0.5 }}>
                  <td>
                    <span className="pnum" style={{ marginRight: 8 }}>{p.shirt}</span>
                    <span className="nm">{p.name}</span>
                    <span className="pos" style={{ marginLeft: 8 }}>{p.pos}</span>
                    {p.subbedInMinute != null && (
                      <span style={{ marginLeft: 8, fontSize: 10.5, color: "var(--low)", fontWeight: 600 }}>girdi {p.subbedInMinute}&apos;</span>
                    )}
                  </td>
                  <td className="c">
                    {p.onPitch ? (
                      <span className="risk risk-low"><i className="rd" style={{ background: "var(--low)" }} />sahada</span>
                    ) : (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, color: "var(--dim)", fontWeight: 600 }}>
                        çıktı {p.subbedOutMinute}&apos;
                      </span>
                    )}
                  </td>
                  <td className="r">
                    <span style={{ display: "block" }}>{p.minutes}&apos;</span>
                    <span className="mbar" style={{ width: 56, display: "inline-block", margin: "3px 0 0" }}>
                      <i style={{ width: `${minPct}%`, background: "var(--border2)" }} />
                    </span>
                  </td>
                  <td className="r" style={{ color: "var(--muted)" }}>{p.vaep.toFixed(2)}</td>
                  <td className="r">
                    <span style={{ color: isTop ? "var(--accent)" : "var(--ink)", fontWeight: 700 }}>{p.vaepPer90.toFixed(2)}</span>
                    <span className="mbar" style={{ width: 56, display: "inline-block", margin: "3px 0 0" }}>
                      <i style={{ width: `${p90Pct}%`, background: isTop ? "var(--accent)" : "var(--low)" }} />
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px", fontSize: 11.5, color: "var(--dim)", marginBottom: 14, lineHeight: 1.5 }}>
        <span><b style={{ color: "var(--accent)" }}>VAEP/90</b> = etki ÷ gerçek dakika × 90 — {topImpact.name} {topImpact.minutes}&apos;de {topImpact.vaepPer90.toFixed(2)} ile öne çıkıyor.</span>
        {off.length > 0 && (
          <span>Çıkan {off.map((p) => p.name).join(", ")} öneri havuzundan otomatik düştü.</span>
        )}
      </div>
    </>
  );
}

function DemoLiveView() {
  const d = demoLive;
  const events = [...d.events].sort((a, b) => b.minute - a.minute); // en yeni üstte
  const subUv: Record<string, string> = { "kritik": "var(--crit)", "yüksek": "var(--high)", "orta": "var(--mid)" };

  const right = (
    <>
      <div className="rc">
        <h3>Bağlantı <span className="tiny">replay (demo)</span></h3>
        <div style={{ fontSize: 13, color: "var(--low)", fontWeight: 700 }}>● Canlı (demo)</div>
        <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 6, fontFamily: "JetBrains Mono" }}>{d.minute}. dakika · momentum {d.momentumHolder}</div>
        <DataQualityLine status={d.dataQuality.status} score={d.dataQuality.score} />
      </div>
      <RiskPanel cardFlags={d.riskMonitor.card_flags} injuryFlags={d.riskMonitor.injury_flags} timeManagement={d.riskMonitor.time_management} />
      <AlertsFeedPanel alerts={d.alerts.alerts} />
      <div className="rc">
        <h3>Değişiklik Önerileri <span className="tiny">top {d.subs.length}</span></h3>
        {d.subs.map((s, i) => {
          const c = subUv[s.urgency] ?? "var(--muted)";
          return (
            <div key={i} style={{ padding: "9px 0", borderTop: i ? "1px solid var(--line)" : undefined }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 3 }}>
                <b style={{ fontSize: 12.5 }}>{s.player_out}</b>
                <span style={{ fontSize: 9.5, textTransform: "uppercase", color: c }}>{s.urgency}</span>
              </div>
              <div style={{ fontSize: 11.5, color: "var(--low)", marginBottom: 4 }}>↳ {s.player_in}</div>
              <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>{s.rationale}</div>
            </div>
          );
        })}
      </div>
    </>
  );

  return (
    <ConsoleShell active="/matches/demo/live" title="Canlı Maç" sub={`${d.home} vs ${d.away} · ${d.minute}'`}
      desc="Event-zaman güdümlü replay (demo). xG yarışı, momentum, olay akışı ve gerekçeli oyuncu değişikliği önerileri." right={right}>
      {/* Skor başlığı */}
      <div className="rc" style={{ margin: "0 0 14px", display: "flex", alignItems: "center", justifyContent: "center", gap: 22 }}>
        <div style={{ textAlign: "right", flex: 1 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: HOME_COLOR }}>{d.home}</div>
          <div style={{ fontSize: 11, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>xG {d.homeXg.toFixed(2)}</div>
        </div>
        <div style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 34, letterSpacing: 2 }}>{d.score[0]}-{d.score[1]}</div>
        <div style={{ textAlign: "left", flex: 1 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: AWAY_COLOR }}>{d.away}</div>
          <div style={{ fontSize: 11, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>xG {d.awayXg.toFixed(2)}</div>
        </div>
      </div>

      {/* Sentez: tüm motorların tek önceliklendirilmiş hamlesi */}
      <NextBestActionPanel action={demoNextAction()} />

      {/* xG yarışı */}
      <div className="st" style={{ marginTop: 0 }}><h2>xG Yarışı</h2><span className="ep">{d.minute}. dakikaya kadar</span></div>
      <div className="rc" style={{ margin: "0 0 14px", height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={d.series} margin={{ top: 8, right: 12, bottom: 4, left: -18 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="minute" tick={{ fontSize: 11, fill: "var(--dim)" }} stroke="var(--line)" />
            <YAxis tick={{ fontSize: 11, fill: "var(--dim)" }} stroke="var(--line)" />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} labelFormatter={(m) => `${m}. dakika`} />
            <Line type="monotone" dataKey="home" name={d.home} stroke={HOME_COLOR} strokeWidth={2.5} dot={false} />
            <Line type="monotone" dataKey="away" name={d.away} stroke={AWAY_COLOR} strokeWidth={2.5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Momentum */}
      <div className="st"><h2>Momentum</h2><span className="ep">+ {d.home} · − {d.away}</span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <div style={{ display: "flex", gap: 3, alignItems: "center", height: 44 }}>
          {d.series.map((p) => {
            const m = p.momentum; // -100..100
            const pos = m >= 0;
            return (
              <div key={p.minute} title={`${p.minute}': ${m}`} style={{ flex: 1, height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
                <div style={{ height: `${Math.abs(m) / 2 + 6}%`, background: pos ? HOME_COLOR : AWAY_COLOR, borderRadius: 2, alignSelf: pos ? "flex-start" : "flex-end", width: "100%", opacity: 0.85 }} />
              </div>
            );
          })}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8 }}>Son 8 dakikada momentum <b style={{ color: AWAY_COLOR }}>{d.away}</b>'e geçti — üst üste 2 korner.</div>
      </div>

      {/* Kararların zaman ekseni + kanıt zinciri */}
      <DecisionTimeline decisions={demoDecisions} currentMinute={d.minute} />

      {/* Gizli motor: canlı taktik tetikler */}
      <TriggersPanel triggers={d.tacticalTriggers} />

      {/* Gizli motor: kapanış reçetesi + mekânsal kontrol */}
      <div className="st"><h2>Kapanış & Mekân</h2></div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
        <ClosingPanel scoreState={d.closing.score_state} posture={d.closing.posture} recipe={d.closing.closing_recipe} />
        <SpatialPanel gap={d.spatial.gap_between_lines} flank={d.spatial.superiority_flank} shapeState={d.spatial.shape_state} alerts={d.spatial.alerts} />
      </div>

      {/* Gizli motor: bireysel eşleşme uyarıları */}
      <MatchupPanel alerts={d.matchup.alerts} />

      {/* Faz B — sahadaki kadro & oyuncu etkisi */}
      <LineupImpact lineup={d.lineup} clock={d.minute} formation={d.formation} />

      {/* Gizli motor: değişiklik zamanlaması */}
      <SubTimingPanel pkg={d.subTiming.package} rationale={d.subTiming.rationale} advices={d.subTiming.advices} />

      {/* Olay akışı */}
      <div className="st"><h2>Olay Akışı</h2><span className="ep">{d.events.length} olay</span></div>
      <div className="rc" style={{ margin: 0, padding: 0, overflow: "hidden" }}>
        {events.map((e, i) => {
          const c = e.team === "home" ? HOME_COLOR : AWAY_COLOR;
          return (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "auto auto 1fr", gap: 11, alignItems: "center", padding: "10px 14px", borderTop: i ? "1px solid var(--line)" : undefined }}>
              <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 12, color: "var(--ink)", minWidth: 26 }}>{e.minute}&apos;</span>
              <span style={{ fontSize: 15 }}>{EV_ICON[e.type]}</span>
              <span style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.45, borderLeft: `2px solid ${c}`, paddingLeft: 10 }}>{e.text}</span>
            </div>
          );
        })}
      </div>
    </ConsoleShell>
  );
}

export default function LiveMatchPage() {
  return DEMO_MODE ? <DemoLiveView /> : <LiveWsView />;
}
