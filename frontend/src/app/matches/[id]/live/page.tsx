"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { ConfidenceBadge } from "@/components/ui";

interface Confidence {
  score: number;
  label: string;
  drivers: string[];
}

// Push notification: tarayıcı izin verir + ürettiği high urgency sub için
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
    // ignore
  }
}

interface SubRecommendation {
  player_external_id: number;
  urgency_score: number;
  urgency_label: string;
  reasons: string[];
}

interface PlayerShift {
  player_external_id: number;
  drift_distance: number;
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
  match_dominance?: {
    dominance_score?: number;
    label?: string;
    xg_diff?: number;
    possession_share?: number;
  };
  live_sub_recommendation?: {
    recommendations: SubRecommendation[];
    score_state: string;
  };
  opponent_shape_drift?: {
    shape_changed: boolean;
    n_players_significant_drift: number;
    alert_text: string;
    player_shifts?: PlayerShift[];
  };
  momentum?: {
    score?: number;
    holder?: string;
    alert_text?: string;
  };
  context?: {
    one_liner?: string | null;
    primary?: { headline?: string } | null;
    confidence_note?: string;
  };
  confidence?: {
    context?: Confidence | null;
    live_sub_recommendation?: Confidence | null;
    momentum?: Confidence | null;
  };
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

const TREND_DIR_TONE: Record<string, string> = {
  "bize doğru": "text-good",
  "rakibe doğru": "text-bad",
  "dengeli": "text-muted",
};

function StatCard({
  label, value, badge, accent = "default",
}: {
  label: string;
  value: string;
  badge?: string;
  accent?: "default" | "green" | "red" | "amber";
}) {
  const accentColors = {
    default: "border-muted",
    green: "border-green-500/40",
    red: "border-red-500/40",
    amber: "border-yellow-500/40",
  };
  return (
    <div className={`card border-l-2 ${accentColors[accent]}`}>
      <h3 className="text-xs uppercase text-muted mb-1">{label}</h3>
      <div className="text-2xl font-mono">{value}</div>
      {badge && (
        <div className="inline-block mt-1 px-2 py-0.5 rounded bg-accent/20 text-xs uppercase">
          {badge}
        </div>
      )}
    </div>
  );
}

export default function LiveMatchPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const matchId = params.id;
  const myTeam = search.get("my_team_id");
  const interval = search.get("interval_seconds") ?? "10";
  const maxMinute = search.get("max_minute") ?? "90";
  const tenantId = search.get("tenant_id") ?? "t-default";

  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  // Faz 3: 4 state — connecting | open | reconnecting | closed
  const [wsState, setWsState] = useState<
    "connecting" | "open" | "reconnecting" | "closed"
  >("connecting");
  const [reconnectCountdown, setReconnectCountdown] = useState<number | null>(null);
  const [ended, setEnded] = useState(false);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const notifiedPlayersRef = useRef<Set<number>>(new Set());
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalCloseRef = useRef<boolean>(false);
  const [manualReconnectTrigger, setManualReconnectTrigger] = useState(0);

  const connected = wsState === "open";

  // İlk render'da push notification izni iste
  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window
      && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  useEffect(() => {
    if (!myTeam || ended) return;
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url =
      `${proto}//${host}/api/ws/matches/${matchId}/live` +
      `?my_team_id=${myTeam}&interval_seconds=${interval}` +
      `&max_minute=${maxMinute}&tenant_id=${tenantId}`;

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
          if (rec.urgency_label === "high"
            && !notifiedPlayersRef.current.has(rec.player_external_id)) {
            notifyHighUrgency(rec.player_external_id, rec.urgency_score);
            notifiedPlayersRef.current.add(rec.player_external_id);
          }
        }
      } catch {
        // ignore
      }
    };
    ws.onclose = () => {
      if (intentionalCloseRef.current || ended) {
        setWsState("closed");
        return;
      }
      // Exponential backoff: 2, 4, 8, 16, max 30 sn; max 10 deneme
      const attempts = reconnectAttemptsRef.current;
      if (attempts >= 10) {
        setWsState("closed");
        return;
      }
      const delay = Math.min(30_000, 2_000 * Math.pow(2, attempts));
      reconnectAttemptsRef.current = attempts + 1;
      setWsState("reconnecting");
      setReconnectCountdown(Math.ceil(delay / 1000));

      // Geri sayım
      const countdownInterval = setInterval(() => {
        setReconnectCountdown((c) => (c !== null && c > 0 ? c - 1 : c));
      }, 1000);
      reconnectTimerRef.current = setTimeout(() => {
        clearInterval(countdownInterval);
        setReconnectCountdown(null);
        // Bağlantıyı yeniden kur — manual trigger ile useEffect tetikle
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
      <main className="max-w-5xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-3">Canlı Maç Dashboard</h1>
        <div className="card">
          <p className="text-muted">
            <code className="font-mono">?my_team_id=&lt;N&gt;</code> parametresi gerek.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-6xl mx-auto p-6">
      <div className="flex items-baseline justify-between mb-4">
        <h1 className="text-2xl font-bold">
          Canlı — Maç #{matchId}
        </h1>
        <div className="text-xs uppercase flex items-center gap-2">
          {snapshot?.mode && (
            <span
              className={`px-2 py-0.5 rounded ${
                snapshot.mode === "replay_statsbomb"
                  ? "bg-accent/20 text-accent"
                  : "bg-win/15 text-win"
              }`}
              title="Veri kaynağı: gerçek-zamanlı feed değil, StatsBomb maçının sadık replay'i"
            >
              {snapshot.mode === "replay_statsbomb" ? "Replay (StatsBomb)" : "Live"}
            </span>
          )}
          {snapshot?.data_quality?.status && (
            <span
              className={`px-2 py-0.5 rounded ${
                snapshot.data_quality.status === "ok"
                  ? "bg-win/15 text-win"
                  : snapshot.data_quality.status === "degraded"
                  ? "bg-warn/15 text-warn"
                  : "bg-danger/15 text-danger"
              }`}
              title="Event akışı veri kalitesi"
            >
              veri: {snapshot.data_quality.status}
            </span>
          )}
          {ended && (
            <span className="px-2 py-0.5 rounded bg-textmut/30">Maç bitti</span>
          )}
          {!ended && wsState === "open" && (
            <span className="px-2 py-0.5 rounded bg-win/15 text-win">
              ● Canlı
            </span>
          )}
          {!ended && wsState === "connecting" && (
            <span className="px-2 py-0.5 rounded bg-warn/15 text-warn">
              Bağlanıyor...
            </span>
          )}
          {!ended && wsState === "reconnecting" && (
            <span className="px-2 py-0.5 rounded bg-warn/15 text-warn">
              Yeniden bağlanıyor
              {reconnectCountdown !== null && ` (${reconnectCountdown}sn)`}
            </span>
          )}
          {!ended && wsState === "closed" && (
            <span className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded bg-danger/15 text-danger">
                Bağlantı koptu
              </span>
              <button
                type="button"
                onClick={handleManualReconnect}
                className="text-[11px] uppercase px-2 py-1 rounded border border-borderlt text-accent hover:bg-surface2"
              >
                Yeniden bağlan
              </button>
            </span>
          )}
        </div>
      </div>

      {snapshot?.note && (
        <div className="card mb-4 text-muted">{snapshot.note}</div>
      )}
      {snapshot?.error && (
        <div className="card border-l-2 border-red-500/40 mb-4">
          <p className="text-red-400 text-sm">{snapshot.error}</p>
        </div>
      )}

      {snapshot && !snapshot.error && (
        <>
          <h2 className="text-sm uppercase text-muted mb-3">Maç Durumu</h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            <StatCard label="Dakika"
              value={snapshot.current_minute?.toFixed(0) ?? "—"}
              badge={snapshot.phase} />
            <StatCard label={`Skor (${snapshot.current_minute?.toFixed(0) ?? "—"}'’e kadar)`}
              value={snapshot.score ?? "—"}
              badge={snapshot.live_sub_recommendation?.score_state} />
            <StatCard label="Olay sayısı"
              value={String(snapshot.events_so_far ?? 0)} />
            <StatCard label="Dominance"
              value={snapshot.match_dominance?.dominance_score?.toFixed(2) ?? "—"}
              badge={snapshot.match_dominance?.label}
              accent={
                (snapshot.match_dominance?.dominance_score ?? 0) > 1
                  ? "green"
                  : (snapshot.match_dominance?.dominance_score ?? 0) < -1
                  ? "red"
                  : "default"
              } />
          </div>

          {snapshot.context?.one_liner && (
            <>
              <h2 className="text-sm uppercase text-muted mb-3">
                Bağlam & Güven (Orkestra Şefi)
              </h2>
              <div className="card mb-6">
                <div className="flex items-start justify-between gap-3 mb-1">
                  <span className="text-sm">{snapshot.context.one_liner}</span>
                  {snapshot.confidence?.context && (
                    <ConfidenceBadge
                      score={snapshot.confidence.context.score}
                      label={snapshot.confidence.context.label}
                      drivers={snapshot.confidence.context.drivers}
                    />
                  )}
                </div>
                {snapshot.context.confidence_note && (
                  <div className="text-xs text-warn mb-1">
                    ⚠ {snapshot.context.confidence_note}
                  </div>
                )}
                {snapshot.momentum?.alert_text && (
                  <div className="flex items-center justify-between gap-3 mt-2 pt-2 border-t border-borderlt">
                    <span className="text-xs text-muted">
                      {snapshot.momentum.alert_text}
                    </span>
                    {snapshot.confidence?.momentum && (
                      <ConfidenceBadge
                        score={snapshot.confidence.momentum.score}
                        label={snapshot.confidence.momentum.label}
                        drivers={snapshot.confidence.momentum.drivers}
                      />
                    )}
                  </div>
                )}
                {snapshot.trend?.status === "ok" && snapshot.trend.momentum && (
                  <div className="text-xs mt-2 pt-2 border-t border-borderlt">
                    Trend: momentum{" "}
                    <span
                      className={
                        TREND_DIR_TONE[snapshot.trend.momentum.direction ?? ""]
                          ?? "text-muted"
                      }
                    >
                      {snapshot.trend.momentum.direction}
                    </span>
                    {(snapshot.trend.momentum.sustained_snapshots ?? 0) >= 2 && (
                      <> · {snapshot.trend.momentum.sustained_snapshots} snapshot'tır</>
                    )}
                    {snapshot.trend.stability?.stable && (
                      <span className="text-good"> · sinyal istikrarlı</span>
                    )}
                  </div>
                )}
              </div>
            </>
          )}

          <div className="grid md:grid-cols-3 gap-3 mb-6">
            <StatCard label="PPDA"
              value={snapshot.ppda?.ppda?.toFixed(2) ?? "—"} />
            <StatCard label="Field Tilt (biz)"
              value={
                snapshot.field_tilt
                  ? `%${Math.round((snapshot.field_tilt.team_a_tilt ?? 0) * 100)}`
                  : "—"
              } />
            <StatCard label="xG Farkı"
              value={snapshot.match_dominance?.xg_diff?.toFixed(2) ?? "—"} />
          </div>

          {snapshot.live_sub_recommendation
            && snapshot.live_sub_recommendation.recommendations.length > 0 && (
            <>
              <h2 className="text-sm uppercase text-muted mb-3">
                Oyuncu Değişikliği Önerileri (Top 3)
              </h2>
              <div className="grid md:grid-cols-3 gap-3 mb-6">
                {snapshot.live_sub_recommendation.recommendations.map((rec) => (
                  <div
                    key={rec.player_external_id}
                    className={`card border-l-2 ${
                      rec.urgency_label === "high"
                        ? "border-red-500/50"
                        : rec.urgency_label === "medium"
                        ? "border-yellow-500/50"
                        : "border-muted"
                    }`}
                  >
                    <div className="flex justify-between mb-1">
                      <span className="font-mono">
                        Player #{rec.player_external_id}
                      </span>
                      <span className="text-xs uppercase px-2 py-0.5 rounded bg-accent/20">
                        {rec.urgency_label}
                      </span>
                    </div>
                    <div className="text-sm text-muted mb-2">
                      Aciliyet:{" "}
                      <span className="font-mono">{rec.urgency_score.toFixed(2)}</span>
                    </div>
                    <ul className="text-xs space-y-1">
                      {rec.reasons.map((r, i) => (
                        <li key={i} className="text-muted">
                          · {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </>
          )}

          {snapshot.opponent_shape_drift && (
            <>
              <h2 className="text-sm uppercase text-muted mb-3">
                Rakip Formasyon Takibi
              </h2>
              <div
                className={`card mb-6 ${
                  snapshot.opponent_shape_drift.shape_changed
                    ? "border-l-2 border-red-500/50"
                    : ""
                }`}
              >
                <div className="text-sm">
                  {snapshot.opponent_shape_drift.alert_text}
                </div>
                {snapshot.opponent_shape_drift.player_shifts
                  && snapshot.opponent_shape_drift.player_shifts.length > 0 && (
                  <div className="text-xs text-muted mt-2">
                    Drift olan oyuncular:{" "}
                    {snapshot.opponent_shape_drift.player_shifts
                      .slice(0, 5)
                      .map(
                        (p) =>
                          `#${p.player_external_id} (${p.drift_distance.toFixed(1)})`,
                      )
                      .join(", ")}
                  </div>
                )}
              </div>
            </>
          )}

          <DecisionPanel
            matchId={Number(matchId)}
            teamId={Number(myTeam)}
            currentMinute={snapshot.current_minute ?? 0}
          />

          <div className="text-xs text-muted">
            Snapshot geçmişi: {history.length} kayıt · Interval {interval}sn
          </div>
        </>
      )}
    </main>
  );
}


function DecisionPanel({
  matchId, teamId, currentMinute,
}: {
  matchId: number;
  teamId: number;
  currentMinute: number;
}) {
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

  return (
    <>
      <h2 className="text-sm uppercase text-muted mb-3 mt-6">
        Karar Logu (TD hamlesi kaydet)
      </h2>
      <div className="card mb-4">
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-2 mb-2">
          <select
            value={type}
            onChange={(e) => setType(e.target.value as typeof type)}
            className="bg-transparent border border-muted/30 rounded px-2 py-1 text-sm"
          >
            <option value="substitution">Substitution</option>
            <option value="formation_change">Formation change</option>
            <option value="tactical_instruction">Tactical instruction</option>
          </select>
          <input
            placeholder="Çıkan oyuncu ID (sub)"
            value={subjectPid}
            onChange={(e) => setSubjectPid(e.target.value)}
            className="bg-transparent border border-muted/30 rounded px-2 py-1 text-sm"
          />
          <input
            placeholder="Giren oyuncu ID (sub)"
            value={relatedPid}
            onChange={(e) => setRelatedPid(e.target.value)}
            className="bg-transparent border border-muted/30 rounded px-2 py-1 text-sm"
          />
          <button
            onClick={submit}
            className="bg-accent/30 hover:bg-accent/50 rounded px-3 py-1 text-sm"
          >
            Kaydet @ {currentMinute.toFixed(0)}.dk
          </button>
        </div>
        <input
          placeholder="Not (opsiyonel)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="w-full bg-transparent border border-muted/30 rounded px-2 py-1 text-sm"
        />
        {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
        {saved.length > 0 && (
          <p className="text-xs text-muted mt-2">
            Bu oturumda {saved.length} karar kaydedildi:{" "}
            {saved.map((s) => `#${s.id}@${s.minute.toFixed(0)}'`).join(", ")}
          </p>
        )}
      </div>
    </>
  );
}
