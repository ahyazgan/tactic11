"use client";

/**
 * Video işleme paneli — klip seç/yükle → kalibrasyon → iş başlat → durum & log.
 * Backend: /tracking/videos, /tracking/calibrations, /tracking/jobs (app/api/tracking_jobs.py).
 * İş bitince `onDone(match_id)` ile sayfa yeni maçı seçer.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface VideoItem { name: string; size_mb: number }
interface CalibItem { name: string; points: number; reprojection_error_m: number | null; valid: boolean }
export interface TrackingJob {
  id: string; state: "queued" | "running" | "ingesting" | "done" | "failed";
  created_at: string; video: string; calibration: string | null; auto_anchor?: boolean; label?: string | null;
  match_id: number; frames?: number; error?: string | null;
  summary?: Record<string, unknown> | null; log_tail?: string[];
}
interface JobsList { jobs: TrackingJob[]; total: number; worker_available: boolean; default_weights: string | null; worker_python: string }

const inputStyle = {
  width: "100%", marginTop: 4, padding: 6, background: "var(--panel2)",
  color: "var(--ink)", border: "1px solid var(--line)", borderRadius: 4, fontSize: 12,
} as const;
const STATE_TR: Record<TrackingJob["state"], string> = {
  queued: "sırada", running: "işleniyor", ingesting: "DB'ye alınıyor", done: "bitti", failed: "hata",
};
const STATE_COLOR: Record<TrackingJob["state"], string> = {
  queued: "var(--muted)", running: "var(--high)", ingesting: "var(--high)", done: "var(--low)", failed: "var(--crit)",
};
const ACTIVE = new Set(["queued", "running", "ingesting"]);
// Çapasız başlangıç: kalibratör çapayı saha çizgilerinden bulur (TV kuralı).
// Elle kalibrasyon daha doğrudur (0.09 m vs ~1.7 m); bu seçenek yayın gibi
// kalibrasyonu olmayan kaynaklar içindir.
const AUTO_ANCHOR = "__auto__";

export function VideoJobPanel({ onDone }: { onDone: (matchId: number) => void }) {
  const { data: videos, mutate: refreshVideos } = useSWR<{ videos: VideoItem[] }>("/tracking/videos", apiFetch, { revalidateOnFocus: false });
  const { data: calibs } = useSWR<{ calibrations: CalibItem[] }>("/tracking/calibrations", apiFetch, { revalidateOnFocus: false });
  const { data: jobs, mutate: refreshJobs } = useSWR<JobsList>("/tracking/jobs?limit=8", apiFetch, {
    revalidateOnFocus: false,
    refreshInterval: (d) => (d?.jobs?.some((j) => ACTIVE.has(j.state)) ? 3000 : 0),
  });

  const [video, setVideo] = useState("");
  const [calib, setCalib] = useState("");
  const [home, setHome] = useState(9001);
  const [away, setAway] = useState(9002);
  const [label, setLabel] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [fps, setFps] = useState(5);
  const [trackFps, setTrackFps] = useState(15);
  const [tiles, setTiles] = useState(6);
  const [threshold, setThreshold] = useState(0.3);
  const [maxSeconds, setMaxSeconds] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [openLog, setOpenLog] = useState<string | null>(null);
  const [seenDone, setSeenDone] = useState<Set<string>>(new Set());

  useEffect(() => { if (!video && videos?.videos?.length) setVideo(videos.videos[0].name); }, [videos, video]);
  useEffect(() => {
    if (calib || !calibs) return;
    const first = calibs.calibrations.find((c) => c.valid)?.name;
    setCalib(first ?? AUTO_ANCHOR);
  }, [calibs, calib]);

  // Yeni biten işleri sayfaya bildir (bir kez)
  useEffect(() => {
    for (const j of jobs?.jobs ?? []) {
      if (j.state === "done" && !seenDone.has(j.id)) {
        setSeenDone((s) => new Set(s).add(j.id));
        onDone(j.match_id);
      }
    }
  }, [jobs, seenDone, onDone]);

  const running = useMemo(() => (jobs?.jobs ?? []).some((j) => ACTIVE.has(j.state)), [jobs]);
  const { data: openJob } = useSWR<TrackingJob>(openLog ? `/tracking/jobs/${openLog}` : null, apiFetch, {
    refreshInterval: 3000, revalidateOnFocus: false,
  });

  const start = async () => {
    setBusy(true); setErr(null);
    try {
      await apiFetch("/tracking/jobs", {
        method: "POST",
        body: JSON.stringify({
          video, calibration: calib === AUTO_ANCHOR ? null : calib,
          home_team_id: home, away_team_id: away, label: label || null,
          fps, track_fps: trackFps, tiles, threshold, ball_threshold: threshold, preview: true,
          max_seconds: maxSeconds === "" ? null : maxSeconds,
        }),
      });
      await refreshJobs();
    } catch (e) {
      setErr(String(e).slice(0, 220));
    } finally {
      setBusy(false);
    }
  };

  const upload = async (f: File | null) => {
    if (!f) return;
    setBusy(true); setErr(null);
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await apiFetch<{ name: string }>("/tracking/videos", { method: "POST", body: fd });
      await refreshVideos(); setVideo(r.name);
    } catch (e) {
      setErr(String(e).slice(0, 220));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rc">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>Video işle</h3>
        {jobs && !jobs.worker_available && <span style={{ fontSize: 10, color: "var(--crit)" }}>işçi yok (venv-cv)</span>}
      </div>
      <label style={{ fontSize: 11.5, display: "block", marginTop: 6 }}>Klip
        <select value={video} onChange={(e) => setVideo(e.target.value)} style={inputStyle}>
          {(videos?.videos ?? []).length === 0 && <option value="">(yüklü klip yok)</option>}
          {(videos?.videos ?? []).map((v) => <option key={v.name} value={v.name}>{v.name} · {v.size_mb} MB</option>)}
        </select>
      </label>
      <input type="file" accept="video/mp4,video/quicktime,.mkv,.avi" disabled={busy} onChange={(e) => upload(e.target.files?.[0] ?? null)} style={{ ...inputStyle, padding: 4 }} />
      <label style={{ fontSize: 11.5, display: "block", marginTop: 8 }}>Kalibrasyon
        <select value={calib} onChange={(e) => setCalib(e.target.value)} style={inputStyle}>
          <option value={AUTO_ANCHOR}>Otomatik çapa — saha çizgilerinden (yayın / kalibrasyon yok)</option>
          {(calibs?.calibrations ?? []).map((c) => (
            <option key={c.name} value={c.name} disabled={!c.valid}>{c.name} · {c.points} nokta{c.reprojection_error_m != null ? ` · ${c.reprojection_error_m} m` : ""}{c.valid ? "" : " · geçersiz"}</option>
          ))}
        </select>
      </label>
      <div style={{ fontSize: 10.5, marginTop: 4 }}><Link href="/video-tracking/calibrate">+ Yeni kalibrasyon (kare üstünde tıkla)</Link></div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
        <label style={{ fontSize: 11.5 }}>Ev sahibi id<input type="number" value={home} onChange={(e) => setHome(parseInt(e.target.value) || 0)} style={inputStyle} /></label>
        <label style={{ fontSize: 11.5 }}>Deplasman id<input type="number" value={away} onChange={(e) => setAway(parseInt(e.target.value) || 0)} style={inputStyle} /></label>
      </div>
      <label style={{ fontSize: 11.5, display: "block", marginTop: 8 }}>Etiket
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Antrenman 09.09 — 1. yarı" style={inputStyle} />
      </label>
      <button type="button" onClick={() => setAdvanced((a) => !a)} style={{ background: "none", border: "none", color: "var(--muted)", fontSize: 10.5, cursor: "pointer", padding: 0, marginTop: 8 }}>
        {advanced ? "▾ Gelişmiş" : "▸ Gelişmiş (fps, dilim, eşik)"}
      </button>
      {advanced && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 4 }}>
          <label style={{ fontSize: 11 }}>Çıktı fps<input type="number" step={1} min={1} max={30} value={fps} onChange={(e) => setFps(parseFloat(e.target.value) || 5)} style={inputStyle} /></label>
          <label style={{ fontSize: 11 }}>Takip fps<input type="number" step={1} min={5} max={60} value={trackFps} onChange={(e) => setTrackFps(parseFloat(e.target.value) || 15)} style={inputStyle} /></label>
          <label style={{ fontSize: 11 }}>Dilim<input type="number" min={1} max={10} value={tiles} onChange={(e) => setTiles(parseInt(e.target.value) || 6)} style={inputStyle} /></label>
          <label style={{ fontSize: 11 }}>Eşik<input type="number" step={0.05} min={0.05} max={0.95} value={threshold} onChange={(e) => setThreshold(parseFloat(e.target.value) || 0.3)} style={inputStyle} /></label>
          <label style={{ fontSize: 11, gridColumn: "1 / -1" }}>En fazla saniye (boş = tümü)<input type="number" min={1} value={maxSeconds} onChange={(e) => setMaxSeconds(e.target.value === "" ? "" : parseFloat(e.target.value))} style={inputStyle} /></label>
        </div>
      )}
      <button type="button" onClick={start} disabled={busy || !video || !calib || running}
        style={{ width: "100%", marginTop: 10, padding: "9px 10px", background: running ? "var(--panel2)" : "var(--accent)", color: running ? "var(--muted)" : "#fff", border: "1px solid var(--line)", borderRadius: 4, cursor: "pointer", fontSize: 12, fontWeight: 700 }}>
        {running ? "Bir iş çalışıyor…" : "▶ İşle (GPU)"}
      </button>
      {jobs?.default_weights && <div style={{ fontSize: 10, color: "var(--dim)", marginTop: 4 }}>İnce-ayarlı dedektör kullanılacak.</div>}
      {err && <div style={{ fontSize: 11, color: "var(--crit)", marginTop: 6 }}>{err}</div>}

      {(jobs?.jobs ?? []).length > 0 && (
        <div style={{ marginTop: 10, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
          <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>Son işler</div>
          {(jobs?.jobs ?? []).map((j) => (
            <div key={j.id} style={{ fontSize: 11, padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 6 }}>
                <span style={{ color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{j.label || j.video}</span>
                <span style={{ color: STATE_COLOR[j.state], fontWeight: 700, whiteSpace: "nowrap" }}>{STATE_TR[j.state]}</span>
              </div>
              <div style={{ color: "var(--muted)", fontSize: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span>#{j.match_id}</span>
                {j.frames != null && <span>{j.frames} kare</span>}
                {j.summary && typeof j.summary.tracks === "number" && <span>{String(j.summary.tracks)} takip</span>}
                {j.state === "done" && <button type="button" onClick={() => onDone(j.match_id)} style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", fontSize: 10, padding: 0 }}>aç →</button>}
                <button type="button" onClick={() => setOpenLog(openLog === j.id ? null : j.id)} style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 10, padding: 0 }}>{openLog === j.id ? "logu kapat" : "log"}</button>
              </div>
              {j.error && <div style={{ color: "var(--crit)", fontSize: 10 }}>{j.error}</div>}
              {openLog === j.id && (
                <pre style={{ fontSize: 9.5, background: "var(--panel2)", padding: 6, borderRadius: 4, marginTop: 4, maxHeight: 160, overflow: "auto", whiteSpace: "pre-wrap" }}>
                  {(openJob?.log_tail ?? j.log_tail ?? []).join("\n") || "(log yok)"}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
