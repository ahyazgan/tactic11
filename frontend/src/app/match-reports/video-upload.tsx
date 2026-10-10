"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { DetailedError, Upload } from "tus-js-client";
import { apiFetch, apiFetchResponse, getAccessToken, getOrRefreshToken } from "@/lib/api";
import styles from "./reports.module.css";

interface Video { id: string; filename: string; duration_seconds: number; size_bytes: number }
interface Pending { id: string; filename: string; offset: number; length: number; expires: number }
const endpoint = "/api/match-reports/uploads";
const mb = (n: number) => (n / 1024 / 1024).toFixed(1);

function identity(token: string | null): string {
  try {
    const body = JSON.parse(atob(token!.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return `${body.sub}:${body.tenant_id}`;
  } catch { return ""; }
}

function safeURL(value: string): URL {
  const url = new URL(value, window.location.href);
  if (url.origin !== window.location.origin || !/^\/api\/match-reports\/uploads(?:\/[0-9a-f-]{36})?$/.test(url.pathname)
    || url.search || url.hash || url.username || url.password) throw new Error("Geçersiz yükleme adresi.");
  return url;
}

export function VideoUpload({ account, onUploaded }: { account: string; onUploaded: (video: Video) => Promise<void> }) {
  const [state, setState] = useState<"idle" | "starting" | "sending" | "paused" | "error" | "done">("idle");
  const [progress, setProgress] = useState({ sent: 0, total: 0 });
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const ref = useRef<Upload | null>(null);
  const alive = useRef(true);
  const { data: pending, mutate } = useSWR<Pending[]>(["/match-reports/uploads", account], ([path]: [string, string]) => apiFetch(path));
  const active = state === "starting" || state === "sending";

  useEffect(() => { alive.current = true; return () => { alive.current = false; void ref.current?.abort(); }; }, []);
  useEffect(() => {
    if (!active) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [active]);

  const start = async (file: File) => {
    setError(""); setState("starting"); setName(file.name); setProgress({ sent: 0, total: file.size });
    try {
      await ref.current?.abort();
      const owner = identity(getAccessToken());
      const checkOwner = () => { if (!alive.current || !owner || identity(getAccessToken()) !== owner) throw new Error("Oturum değişti. Aynı hesapla giriş yapıp dosyayı yeniden seçin."); };
      // Samples strengthen tus's usual name/size/mtime identity without loading
      // a multi-GB file into memory. The server hashes every completed byte.
      const sample = await new Blob([file.slice(0, 65536), file.slice(Math.max(0, Math.floor(file.size / 2) - 32768), Math.floor(file.size / 2) + 32768), file.slice(-65536)]).arrayBuffer();
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", sample))).map(b => b.toString(16).padStart(2, "0")).join("");
      checkOwner();
      const upload = new Upload(file, {
        endpoint: new URL(endpoint, window.location.origin).href,
        chunkSize: 2 * 1024 * 1024, retryDelays: [0, 1000, 3000, 5000, 15000, 30000, 60000],
        metadata: { filename: file.name }, removeFingerprintOnSuccess: true,
        fingerprint: async () => `manager-review-v1:${account}:${owner}:${file.name}:${file.size}:${file.lastModified}:${hash}`,
        onBeforeRequest: request => {
          checkOwner(); safeURL(request.getURL());
          request.setHeader("Authorization", `Bearer ${getAccessToken()}`);
        },
        onAfterResponse: async (_, response) => {
          if (response.getStatus() === 401) { checkOwner(); await getOrRefreshToken(); checkOwner(); }
        },
        onShouldRetry: error => [0, 401, 409, 423, 429, 500, 502, 503, 504].includes(error.originalResponse?.getStatus() ?? 0),
        onProgress: (sent, total) => { if (alive.current) setProgress({ sent, total }); },
        onError: err => {
          if (!alive.current) return;
          let detail = "Bağlantı kesildi. Devam et ile yeniden deneyin; sayfayı yenilediyseniz aynı dosyayı seçin.";
          if (err instanceof DetailedError) {
            try { const body = JSON.parse(err.originalResponse?.getBody() || "{}"); if (typeof body.detail === "string") detail = body.detail; } catch { /* Proxy errors contain no user-facing detail. */ }
          }
          setError(detail); setState("error"); void mutate();
        },
        onSuccess: () => { void (async () => {
          try {
            checkOwner();
            const path = safeURL(upload.url!).pathname.slice(4);
            const result = await apiFetch<{ video: Video }>(path);
            checkOwner();
            if (!result.video) throw new Error("Video doğrulaması tamamlanamadı.");
            await onUploaded(result.video); setState("done"); ref.current = null; await mutate();
          } catch { if (alive.current) { setError("Video kaydı alınamadı. Aynı dosyayı yeniden seçerek kontrol edin."); setState("error"); } }
        })(); },
      });
      ref.current = upload;
      const previous = await upload.findPreviousUploads();
      checkOwner();
      const candidate = previous.find(item => { try { return !!item.uploadUrl && !!safeURL(item.uploadUrl); } catch { return false; } });
      if (candidate) upload.resumeFromPreviousUpload(candidate);
      setState("sending"); upload.start();
    } catch (err) { if (alive.current) { setError(err instanceof Error ? err.message : "Yükleme başlatılamadı."); setState("error"); } }
  };

  return <div className={styles.stack}>
    <label>MP4 video yükle<input type="file" accept="video/mp4,.mp4" disabled={active}
      onChange={e => { const file = e.target.files?.[0]; if (file) void start(file); e.target.value = ""; }} /></label>
    <small>H.264 (8 bit) MP4 · En fazla 3 saat / varsayılan 2 GB. Yarım yükleme 24 saat korunur. Yeniledikten sonra aynı dosyayı seçin.</small>
    {name && <div aria-live="polite"><strong>{name}</strong>
      <progress aria-label="Video yükleme ilerlemesi" max={progress.total || 1} value={progress.sent} className={styles.uploadProgress} />
      <small>{mb(progress.sent)} / {mb(progress.total)} MB · {state === "done" ? "Video kaydedildi" : state === "paused" ? "Duraklatıldı" : progress.sent === progress.total && active ? "Video kontrol ediliyor…" : active ? "Yükleniyor…" : "Devam edilebilir"}</small>
      <div className={styles.toolbar}>
        {state === "sending" && <button type="button" onClick={() => { void ref.current?.abort().then(() => { setState("paused"); void mutate(); }); }}>Duraklat</button>}
        {(state === "paused" || state === "error") && ref.current && <button type="button" onClick={() => { setError(""); setState("sending"); ref.current?.start(); }}>Yüklemeye devam et</button>}
      </div>
    </div>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {!!pending?.length && <details><summary>Yarım kalan yüklemeler ({pending.length})</summary>{pending.map(item => <div key={item.id} className={styles.export}>
      <small>{item.filename} · {mb(item.offset)} / {mb(item.length)} MB</small>
      <button type="button" className={styles.secondary} disabled={active} onClick={() => { void (async () => {
        try {
          await apiFetchResponse(`/match-reports/uploads/${item.id}`, { method: "DELETE", headers: { "Tus-Resumable": "1.0.0" } });
          if (ref.current?.url?.endsWith(item.id)) { await ref.current.abort(); ref.current = null; setState("idle"); setName(""); }
          await mutate();
        } catch { setError("Yükleme iptal edilemedi. Video tamamlanmış olabilir; listeyi yenileyin."); }
      })(); }}>Yarım yüklemeyi iptal et</button>
    </div>)}</details>}
  </div>;
}
