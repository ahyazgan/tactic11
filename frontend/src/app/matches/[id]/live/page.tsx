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
import { demoLive, type LiveEvent, type LivePlayerImpact } from "@/lib/demo-data";
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
  type?: string;
  error?: string;
  note?: string;
}

const TREND_DIR_VAR: Record<string, string> = {
  "bize doğru": "var(--low)",
  "rakibe doğru": "var(--crit)",
  "dengeli": "var(--muted)",
};

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
      </div>
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
      </div>
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

      {/* Faz B — sahadaki kadro & oyuncu etkisi */}
      <LineupImpact lineup={d.lineup} clock={d.minute} formation={d.formation} />

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
