"use client";

/**
 * Saha kalibrasyonu — videodan bir kare al, saha işaretlerine tıkla, homografiyi
 * anında gör (saha çizgileri kareye geri-izdüşülür), kaydet.
 *
 * Akış: video seç → saniye seç → kare (backend işçi ile çıkarılır) → her tıklama
 * bir nokta; sağdan hangi saha işareti olduğunu seç → ≥4 nokta olunca çizgiler
 * çizilir, geri-izdüşüm hatası gösterilir → ad ver, kaydet (POST /tracking/calibrations).
 *
 * Tıklama koordinatları kaynak çözünürlüğe (X-Source-Width/Height) ölçeklenir;
 * kalibrasyon JSON'u işçinin okuduğu tam-çözünürlük pikselleriyle yazılır.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch, apiFetchResponse } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  LANDMARKS,
  PITCH_L,
  PITCH_W,
  applyH,
  dltHomography,
  invert3,
  pitchPolylines,
  reprojectionErrorM,
  type Mat3,
  type Pt,
} from "@/lib/homography";
import { ConsoleShell } from "../../_console/shell";

interface VideoItem { name: string; size_mb: number; modified: string }
interface ClickPoint { id: number; image: Pt; landmark: string }

const inputStyle = {
  width: "100%", marginTop: 4, padding: 6, background: "var(--panel2)",
  color: "var(--ink)", border: "1px solid var(--line)", borderRadius: 4, fontSize: 12,
} as const;
const btn = (primary = false) => ({
  padding: "8px 10px", borderRadius: 4, cursor: "pointer", fontSize: 12, fontWeight: 700,
  background: primary ? "var(--accent)" : "var(--panel2)", color: primary ? "#fff" : "var(--ink)",
  border: "1px solid var(--line)",
}) as const;

export default function CalibratePage() {
  const { data: videosData, mutate: refreshVideos } = useSWR<{ videos: VideoItem[] }>(
    DEMO_MODE ? null : "/tracking/videos", apiFetch, { revalidateOnFocus: false },
  );
  const videos = videosData?.videos ?? [];
  const [video, setVideo] = useState<string>("");
  const [t, setT] = useState(2);
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [src, setSrc] = useState<{ w: number; h: number; fw: number; fh: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [points, setPoints] = useState<ClickPoint[]>([]);
  const [nextLandmark, setNextLandmark] = useState<string>(LANDMARKS[0].id);
  const [L, setL] = useState(PITCH_L);
  const [W, setW] = useState(PITCH_W);
  const [name, setName] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [disp, setDisp] = useState({ w: 0, h: 0 });

  useEffect(() => {
    if (!video && videos.length) setVideo(videos[0].name);
  }, [videos, video]);

  const loadFrame = useCallback(async () => {
    if (!video) return;
    setLoading(true); setErr(null);
    try {
      const res = await apiFetchResponse(`/tracking/videos/${encodeURIComponent(video)}/frame?t=${t}&width=1920`);
      const blob = await res.blob();
      const fw = parseInt(res.headers.get("X-Frame-Width") ?? "0"), fh = parseInt(res.headers.get("X-Frame-Height") ?? "0");
      const w = parseInt(res.headers.get("X-Source-Width") ?? "0") || fw, h = parseInt(res.headers.get("X-Source-Height") ?? "0") || fh;
      setSrc({ w, h, fw, fh });
      setFrameUrl((old) => { if (old) URL.revokeObjectURL(old); return URL.createObjectURL(blob); });
    } catch (e) {
      setErr(String(e).slice(0, 200));
    } finally {
      setLoading(false);
    }
  }, [video, t]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(() => {
      const img = imgRef.current;
      if (img) setDisp({ w: img.clientWidth, h: img.clientHeight });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [frameUrl]);

  const srcPts = useMemo(() => points.map((p) => p.image), [points]);
  const dstPts = useMemo(
    () => points.map((p) => (LANDMARKS.find((l) => l.id === p.landmark) ?? LANDMARKS[0]).pitch(L, W)),
    [points, L, W],
  );
  const H: Mat3 | null = useMemo(() => (points.length >= 4 ? dltHomography(srcPts, dstPts) : null), [srcPts, dstPts, points.length]);
  const Hinv = useMemo(() => (H ? invert3(H) : null), [H]);
  const reproj = useMemo(() => (H ? reprojectionErrorM(H, srcPts, dstPts) : null), [H, srcPts, dstPts]);
  const dupLandmarks = useMemo(() => {
    const seen = new Set<string>(); const dup = new Set<string>();
    for (const p of points) { if (seen.has(p.landmark)) dup.add(p.landmark); seen.add(p.landmark); }
    return dup;
  }, [points]);

  // Kaynak px → ekran px
  const toDisp = (p: Pt): Pt => (src ? [p[0] / src.w * disp.w, p[1] / src.h * disp.h] : p);

  const onClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!src || !imgRef.current) return;
    const rect = imgRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width * src.w;
    const y = (e.clientY - rect.top) / rect.height * src.h;
    if (x < 0 || y < 0 || x > src.w || y > src.h) return;
    setPoints((ps) => [...ps, { id: Date.now(), image: [Math.round(x * 10) / 10, Math.round(y * 10) / 10], landmark: nextLandmark }]);
    // Bir sonraki mantıklı işareti öner (kullanılmayan ilk)
    const used = new Set([...points.map((p) => p.landmark), nextLandmark]);
    const nxt = LANDMARKS.find((l) => !used.has(l.id));
    if (nxt) setNextLandmark(nxt.id);
  };

  const linesDisp = useMemo(() => {
    if (!Hinv || !src) return [];
    return pitchPolylines(L, W).map(({ pts, closed }) => {
      const d = pts.map((p) => applyH(Hinv, p)).filter((q): q is Pt => !!q && isFinite(q[0]) && isFinite(q[1])).map(toDisp);
      return { d, closed };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Hinv, src, disp, L, W]);

  const save = async () => {
    if (!H || !src) return;
    setSaved(null); setErr(null);
    const calibration = {
      image_size: [src.w, src.h], pitch_length_m: L, pitch_width_m: W,
      points: points.map((p) => ({
        image: p.image, pitch: (LANDMARKS.find((l) => l.id === p.landmark) ?? LANDMARKS[0]).pitch(L, W),
        label: LANDMARKS.find((l) => l.id === p.landmark)?.label ?? p.landmark,
      })),
      meta: { source: "calibrate-ui", video, t, created: new Date().toISOString() },
    };
    try {
      const r = await apiFetch<{ name: string; reprojection_error_m: number }>("/tracking/calibrations", {
        method: "POST", body: JSON.stringify({ name: name || video.replace(/\.[^.]+$/, ""), calibration }),
      });
      setSaved(`${r.name} kaydedildi · geri-izdüşüm ${r.reprojection_error_m} m`);
    } catch (e) {
      setErr(String(e).slice(0, 200));
    }
  };

  const onUpload = async (f: File | null) => {
    if (!f) return;
    setUploading(true); setErr(null);
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await apiFetch<{ name: string }>("/tracking/videos", { method: "POST", body: fd });
      await refreshVideos();
      setVideo(r.name);
    } catch (e) {
      setErr(String(e).slice(0, 200));
    } finally {
      setUploading(false);
    }
  };

  const right = (
    <>
      <div className="rc">
        <h3>Video</h3>
        <label style={{ fontSize: 11.5 }}>Klip
          <select value={video} onChange={(e) => { setVideo(e.target.value); setPoints([]); }} style={inputStyle}>
            {videos.length === 0 && <option value="">(yüklü klip yok)</option>}
            {videos.map((v) => <option key={v.name} value={v.name}>{v.name} · {v.size_mb} MB</option>)}
          </select>
        </label>
        <label style={{ fontSize: 11.5, display: "block", marginTop: 8 }}>Yükle
          <input type="file" accept="video/mp4,video/quicktime,.mkv,.avi" disabled={uploading}
            onChange={(e) => onUpload(e.target.files?.[0] ?? null)} style={{ ...inputStyle, padding: 4 }} />
        </label>
        <label style={{ fontSize: 11.5, display: "block", marginTop: 8 }}>Kare zamanı (sn)
          <input type="number" min={0} step={0.5} value={t} onChange={(e) => setT(parseFloat(e.target.value) || 0)} style={inputStyle} />
        </label>
        <button type="button" onClick={loadFrame} disabled={!video || loading} style={{ ...btn(true), width: "100%", marginTop: 8 }}>
          {loading ? "Kare alınıyor…" : "Kareyi getir"}
        </button>
      </div>
      <div className="rc">
        <h3>Saha ölçüsü</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <label style={{ fontSize: 11.5 }}>Uzunluk (m)<input type="number" value={L} onChange={(e) => setL(parseFloat(e.target.value) || PITCH_L)} style={inputStyle} /></label>
          <label style={{ fontSize: 11.5 }}>Genişlik (m)<input type="number" value={W} onChange={(e) => setW(parseFloat(e.target.value) || PITCH_W)} style={inputStyle} /></label>
        </div>
      </div>
      <div className="rc">
        <h3>Sıradaki işaret</h3>
        <select value={nextLandmark} onChange={(e) => setNextLandmark(e.target.value)} style={inputStyle}>
          {LANDMARKS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
        </select>
        <MiniPitch L={L} W={W} highlight={nextLandmark} placed={points.map((p) => p.landmark)} />
        <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
          Görüntüde bu işareti tıkla. En az 4 nokta; köşeler + orta nokta en sağlam kombinasyon. Kameradan görünmeyen işaretleri atla.
        </div>
      </div>
      <div className="rc">
        <h3>Kaydet</h3>
        <label style={{ fontSize: 11.5 }}>Kalibrasyon adı
          <input value={name} onChange={(e) => setName(e.target.value.replace(/[^A-Za-z0-9_.-]/g, "_"))} placeholder={video.replace(/\.[^.]+$/, "") || "saha"} style={inputStyle} />
        </label>
        <div style={{ fontSize: 11.5, color: reproj != null && reproj > 1 ? "var(--crit)" : "var(--muted)", marginTop: 8 }}>
          {H ? `Geri-izdüşüm hatası ~${reproj?.toFixed(2)} m (${points.length} nokta)` : `${points.length}/4 nokta`}
          {dupLandmarks.size > 0 && <div style={{ color: "var(--crit)" }}>Aynı işaret iki kez seçildi.</div>}
        </div>
        <button type="button" onClick={save} disabled={!H || dupLandmarks.size > 0} style={{ ...btn(true), width: "100%", marginTop: 8 }}>Kaydet</button>
        {saved && <div style={{ fontSize: 11, color: "var(--low)", marginTop: 6 }}>{saved}</div>}
        {err && <div style={{ fontSize: 11, color: "var(--crit)", marginTop: 6 }}>{err}</div>}
        <div style={{ marginTop: 10, fontSize: 11 }}><Link href="/video-tracking">← Video Analiz</Link></div>
      </div>
    </>
  );

  return (
    <ConsoleShell active="/video-tracking" title="Saha Kalibrasyonu" sub={video ? `${video} · ${t}s` : "Klip seçin"}
      desc="Sabit kamera için bir kez: karede saha işaretlerine tıkla, homografi hesaplanır, saha çizgileri kareye geri-izdüşülür. Çizgiler oturuyorsa kalibrasyon doğru." right={right}>
      {DEMO_MODE && <div className="pgdesc">Demo modunda kalibrasyon kapalı — canlı mod (NEXT_PUBLIC_DEMO_MODE=false) ve backend gerekir.</div>}
      <div className="rc" style={{ padding: 8 }}>
        {!frameUrl && (
          <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
            Sağdan klip seç ve <b>Kareyi getir</b>. Kare çıkarma işçi (venv-cv) ile yapılır; ilk seferde birkaç saniye sürer.
          </div>
        )}
        {frameUrl && (
          <div ref={wrapRef} onClick={onClick} style={{ position: "relative", cursor: "crosshair", userSelect: "none" }}>
            <img ref={imgRef} src={frameUrl} alt="kare" style={{ display: "block", width: "100%", height: "auto", borderRadius: 6 }}
              onLoad={() => { const img = imgRef.current; if (img) setDisp({ w: img.clientWidth, h: img.clientHeight }); }} />
            <svg viewBox={`0 0 ${disp.w} ${disp.h}`} width={disp.w} height={disp.h} style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none" }}>
              {linesDisp.map((ln, i) => (
                <polyline key={i} points={[...ln.d, ...(ln.closed && ln.d.length ? [ln.d[0]] : [])].map((p) => `${p[0]},${p[1]}`).join(" ")}
                  fill="none" stroke="#fff" strokeWidth={1.5} opacity={0.9} />
              ))}
              {points.map((p, i) => {
                const d = toDisp(p.image);
                return (
                  <g key={p.id}>
                    <circle cx={d[0]} cy={d[1]} r={6} fill="none" stroke="#ffd54a" strokeWidth={2} />
                    <line x1={d[0] - 9} y1={d[1]} x2={d[0] + 9} y2={d[1]} stroke="#ffd54a" strokeWidth={1} />
                    <line x1={d[0]} y1={d[1] - 9} x2={d[0]} y2={d[1] + 9} stroke="#ffd54a" strokeWidth={1} />
                    <text x={d[0] + 9} y={d[1] - 9} fontSize={11} fill="#ffd54a" fontWeight={700}>{i + 1}</text>
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </div>
      {points.length > 0 && (
        <div className="rc" style={{ marginTop: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <h3 style={{ margin: 0 }}>Noktalar</h3>
            <button type="button" onClick={() => setPoints([])} style={btn()}>Temizle</button>
          </div>
          <table style={{ width: "100%", fontSize: 11.5, marginTop: 6, borderCollapse: "collapse" }}>
            <thead><tr style={{ color: "var(--muted)", textAlign: "left" }}><th>#</th><th>Görüntü (px)</th><th>İşaret</th><th>Saha (m)</th><th /></tr></thead>
            <tbody>
              {points.map((p, i) => {
                const lm = LANDMARKS.find((l) => l.id === p.landmark) ?? LANDMARKS[0];
                const pit = lm.pitch(L, W);
                return (
                  <tr key={p.id} style={{ borderTop: "1px solid var(--line)" }}>
                    <td style={{ padding: "4px 0" }}>{i + 1}</td>
                    <td style={{ fontFamily: "JetBrains Mono, monospace" }}>{p.image[0]}, {p.image[1]}</td>
                    <td>
                      <select value={p.landmark} onChange={(e) => setPoints((ps) => ps.map((q) => (q.id === p.id ? { ...q, landmark: e.target.value } : q)))}
                        style={{ ...inputStyle, marginTop: 0, padding: 3, width: "auto", color: dupLandmarks.has(p.landmark) ? "var(--crit)" : "var(--ink)" }}>
                        {LANDMARKS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
                      </select>
                    </td>
                    <td style={{ fontFamily: "JetBrains Mono, monospace" }}>{pit[0].toFixed(1)}, {pit[1].toFixed(1)}</td>
                    <td><button type="button" onClick={() => setPoints((ps) => ps.filter((q) => q.id !== p.id))} style={{ ...btn(), padding: "2px 8px" }}>sil</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </ConsoleShell>
  );
}

/** Seçili işareti ve yerleştirilmiş olanları gösteren küçük saha şeması. */
function MiniPitch({ L, W, highlight, placed }: { L: number; W: number; highlight: string; placed: string[] }) {
  const pw = 210, ph = pw * (W / L), m = 8;
  const sx = (x: number) => m + (x / L) * (pw - 2 * m), sy = (y: number) => m + (y / W) * (ph - 2 * m);
  return (
    <svg viewBox={`0 0 ${pw} ${ph + 2 * m}`} width="100%" style={{ marginTop: 8, background: "color-mix(in srgb, var(--low) 9%, var(--panel))", borderRadius: 6 }}>
      {pitchPolylines(L, W).map(({ pts, closed }, i) => (
        <polyline key={i} points={[...pts, ...(closed ? [pts[0]] : [])].map((p) => `${sx(p[0])},${sy(p[1])}`).join(" ")} fill="none" stroke="var(--line2)" strokeWidth={0.8} />
      ))}
      {LANDMARKS.map((l) => {
        const p = l.pitch(L, W);
        const hot = l.id === highlight, done = placed.includes(l.id);
        return <circle key={l.id} cx={sx(p[0])} cy={sy(p[1])} r={hot ? 4 : 2.2} fill={hot ? "#ffd54a" : done ? "var(--accent)" : "var(--dim)"} stroke={hot ? "#000" : "none"} strokeWidth={0.6} />;
      })}
      <text x={pw / 2} y={ph + m + 4} fontSize={7} fill="var(--dim)" textAnchor="middle">sarı = sıradaki · yeşil = yerleştirildi · x sağa, y aşağı</text>
    </svg>
  );
}
