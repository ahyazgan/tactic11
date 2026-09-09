"use client";

/**
 * Video Analiz — tracking karesi olan maçları (StatsBomb 360 freeze-frame ya da
 * video takibi) dakika dakika sahada oynatır: Saha Overlay + pas seçenekleri +
 * baskı + alan kontrolü.
 *
 * Kaynak: GET /tracking/matches → seçim; GET /tracking/matches/{id}/frames
 * (pencere: son ~1 dk, limit 150 → video kaynağında ~30 sn). Kaynağa göre
 * kaydırıcı adımı değişir (event verisi 0.5 dk, video 0.1 dk).
 *
 * DEMO_MODE: gerçek veriden alınmış fixture kareleri (lib/tracking-demo).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { sourceTR, type TrackingFrame } from "@/lib/tracking-geometry";
import {
  DEMO_TRACKING_AWAY_TEAM_ID,
  DEMO_TRACKING_FRAMES,
  DEMO_TRACKING_HOME_TEAM_ID,
  demoTrackingWindow,
} from "@/lib/tracking-demo";
import { ConsoleShell } from "../_console/shell";
import { TrackIdentityPanel } from "../_console/track-identity-panel";
import { TrackingOverlayCard } from "../_console/tracking-pitch";
import { TrackingShapeCard } from "../_console/tracking-shape-card";
import { VideoJobPanel } from "../_console/video-job-panel";

interface TrackedMatch {
  match_id: number;
  frames: number;
  first_minute: number | null;
  last_minute: number | null;
  source: string | null;
  home_team_external_id: number | null;
  away_team_external_id: number | null;
  kickoff: string | null;
  score: string | null;
}

const DEMO_MATCHES: TrackedMatch[] = [{
  match_id: 3773672, frames: DEMO_TRACKING_FRAMES.length,
  first_minute: DEMO_TRACKING_FRAMES[0]?.minute ?? 0,
  last_minute: DEMO_TRACKING_FRAMES[DEMO_TRACKING_FRAMES.length - 1]?.minute ?? 90,
  source: "statsbomb_360",
  home_team_external_id: DEMO_TRACKING_HOME_TEAM_ID, away_team_external_id: DEMO_TRACKING_AWAY_TEAM_ID,
  kickoff: "2020-10-04", score: "1-1",
}];

const PLAY_TICK_MS = 500;

const sourceLabel = sourceTR;

/** 12.5 → "12'30\"" */
function fmtClock(minute: number): string {
  const m = Math.floor(minute + 1e-9);
  const s = Math.round((minute - m) * 60);
  return `${m}'${String(s).padStart(2, "0")}"`;
}

function matchLabel(m: TrackedMatch): string {
  const date = m.kickoff ? m.kickoff.slice(0, 10) : "";
  const teams = `${m.home_team_external_id ?? "?"} vs ${m.away_team_external_id ?? "?"}`;
  return `${sourceLabel(m.source)} · #${m.match_id} · ${teams}${m.score ? ` · ${m.score}` : ""}${date ? ` · ${date}` : ""} · ${m.frames} kare`;
}

const inputStyle = {
  width: "100%", marginTop: 4, padding: 6, background: "var(--panel2)",
  color: "var(--ink)", border: "1px solid var(--line)", borderRadius: 4, fontSize: 12,
} as const;

export default function VideoTrackingPage() {
  const { data: listData, error: listError, mutate: refreshMatches } = useSWR<{ matches: TrackedMatch[] }>(
    DEMO_MODE ? null : "/tracking/matches", apiFetch,
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const matches = DEMO_MODE ? DEMO_MATCHES : (listData?.matches ?? []);

  const [matchId, setMatchId] = useState<number | null>(null);
  const onJobDone = useCallback(async (mid: number) => {
    await refreshMatches();
    setMatchId(mid);
  }, [refreshMatches]);
  const [side, setSide] = useState<"home" | "away">("home");
  const [minute, setMinute] = useState<number>(0);
  const [playing, setPlaying] = useState(false);

  const match = useMemo(
    () => matches.find((m) => m.match_id === matchId) ?? matches[0] ?? null,
    [matches, matchId],
  );
  const isVideo = match?.source === "video_tracking";
  // Video: 1 sn adım (kısa klipler), event verisi: 30 sn
  const step = isVideo ? 1 / 60 : 0.5;
  const minMinute = match?.first_minute ?? 0;
  const maxMinute = match?.last_minute ?? 90;

  // Maç değişince kaydırıcıyı son kareye al
  useEffect(() => {
    if (!match) return;
    setMatchId(match.match_id);
    setMinute(match.last_minute ?? 0);
    setPlaying(false);
  }, [match?.match_id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(() => {
      setMinute((m) => {
        const next = m + step;
        if (next > maxMinute + 1e-9) { setPlaying(false); return m; }
        return next;
      });
    }, PLAY_TICK_MS);
    return () => clearInterval(id);
  }, [playing, step, maxMinute]);

  const windowMin = isVideo ? 1 : 3;
  const framesPath = !DEMO_MODE && match
    ? `/tracking/matches/${match.match_id}/frames?from_minute=${Math.max(0, minute - windowMin)}&to_minute=${minute}&limit=150`
    : null;
  const { data: framesData, mutate: refreshFrames } = useSWR<{ frames: TrackingFrame[] }>(
    framesPath, apiFetch, { revalidateOnFocus: false, shouldRetryOnError: false, keepPreviousData: true },
  );
  const frames = DEMO_MODE ? demoTrackingWindow(minute) : (framesData?.frames ?? []);
  const frame = frames.length ? frames[frames.length - 1] : null;
  const ourTeamId = match
    ? (side === "home" ? match.home_team_external_id : match.away_team_external_id) ?? 0
    : 0;

  const right = (
    <>
      {!DEMO_MODE && <VideoJobPanel onDone={onJobDone} />}
      <div className="rc">
        <h3>Kaynak</h3>
        <label style={{ fontSize: 11.5 }}>Maç
          <select value={match?.match_id ?? ""} onChange={(e) => setMatchId(parseInt(e.target.value))} style={inputStyle}>
            {matches.map((m) => (
              <option key={m.match_id} value={m.match_id}>{matchLabel(m)}</option>
            ))}
          </select>
        </label>
        <label style={{ fontSize: 11.5, display: "block", marginTop: 8 }}>Biz
          <select value={side} onChange={(e) => setSide(e.target.value as "home" | "away")} style={inputStyle}>
            <option value="home">Ev sahibi (#{match?.home_team_external_id ?? "?"})</option>
            <option value="away">Deplasman (#{match?.away_team_external_id ?? "?"})</option>
          </select>
        </label>
        {!DEMO_MODE && listError && (
          <div style={{ fontSize: 11, color: "var(--crit)", marginTop: 8 }}>Liste yüklenemedi: {String(listError).slice(0, 120)}</div>
        )}
        {!DEMO_MODE && !listError && matches.length === 0 && (
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8 }}>
            Henüz tracking karesi olan maç yok. <code>scripts.ingest_statsbomb_360</code> ya da
            <code style={{ marginLeft: 4 }}>scripts.track_video</code> + <code>scripts.ingest_tracking_json</code> ile yükle.
          </div>
        )}
      </div>
      <div className="rc">
        <h3>Zaman</h3>
        <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "JetBrains Mono, monospace", color: "var(--ink)" }}>
          {fmtClock(minute)}
        </div>
        <input
          type="range" min={minMinute} max={maxMinute} step={step} value={minute}
          onChange={(e) => { setPlaying(false); setMinute(parseFloat(e.target.value)); }}
          style={{ width: "100%", marginTop: 6 }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--dim)" }}>
          <span>{fmtClock(minMinute)}</span><span>{fmtClock(maxMinute)}</span>
        </div>
        <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
          <button type="button" onClick={() => setPlaying((p) => !p)}
            style={{ flex: 1, padding: "8px 10px", background: playing ? "var(--panel2)" : "var(--accent)",
              color: playing ? "var(--ink)" : "#fff", border: "1px solid var(--line)", borderRadius: 4, cursor: "pointer", fontSize: 12, fontWeight: 700 }}>
            {playing ? "⏸ Duraklat" : "▶ Oynat"}
          </button>
          <button type="button" onClick={() => { setPlaying(false); setMinute(minMinute); }}
            style={{ padding: "8px 10px", background: "var(--panel2)", color: "var(--ink)", border: "1px solid var(--line)", borderRadius: 4, cursor: "pointer", fontSize: 12 }}
            title="Başa dön">↺</button>
        </div>
        <div style={{ fontSize: 10, color: "var(--dim)", marginTop: 6 }}>
          Adım {isVideo ? "1 sn" : "30 sn"} · pencere son {windowMin} dk ({frames.length} kare)
        </div>
      </div>
      <div className="rc">
        <h3>Açıklama</h3>
        <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.6 }}>
          {isVideo
            ? "Video takibi: RF-DETR tespit + ByteTrack + saha homografisi. Takımlar forma renginden, kimlikler takip numarasından (~tahmini). Top görünmediğinde aktör yok."
            : "StatsBomb 360: event anındaki kamera görüş alanı içindeki oyuncular. Aktör gerçek kimlik, diğerleri ~tahmini."}
        </div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/video-tracking"
      title="Video Analiz"
      sub={match ? `${sourceLabel(match.source)} · Maç #${match.match_id}` : "Tracking kaynağı seçin"}
      desc="Pozisyon karelerini sahada oynat: pas seçenekleri, en yakın baskı, yerel alan kontrolü ve topa sahip olma — kaynak StatsBomb 360 ya da video takibi, aynı overlay."
      right={right}
    >
      <TrackingOverlayCard frame={frame} recent={frames} ourTeamId={ourTeamId} minute={minute} />
      {!DEMO_MODE && match && (
        <>
          <TrackingShapeCard matchId={match.match_id} minute={minute} ourSide={side} windowMin={windowMin} />
          {isVideo && <TrackIdentityPanel matchId={match.match_id} ourTeamId={ourTeamId} onSaved={() => { refreshFrames(); }} />}
        </>
      )}
    </ConsoleShell>
  );
}
