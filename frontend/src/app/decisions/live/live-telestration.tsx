"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { ApiError, apiFetch, apiFetchResponse } from "@/lib/api";

// canli_mac --telestration işçisinin son segmenti (scripts.telestrate_live → tele/latest.json)
interface LiveTelestration {
  segment: string;
  video_url: string;
  updated: string;
  summary: {
    frames_written: number;
    start_minute: number;
    drawn_ratio: number;
    label: string | null;
    codec: string;
  };
}

const REFRESH_MS = 5000;

/**
 * Canlı telestrasyon: işlenen son 30 sn'lik segmentin halka/blok çizgisi/faz
 * etiketli videosu. Uç kimlik doğrulama istediği için video <video src> ile değil
 * yetkili istekle (blob) alınır; segment değişince eski blob bırakılır.
 */
export function LiveTelestrationCard({ matchId, live }: { matchId: number; live: boolean }) {
  const { data, error } = useSWR<LiveTelestration>(
    `/tracking/live/${matchId}/telestration`, apiFetch,
    { revalidateOnFocus: false, shouldRetryOnError: false, refreshInterval: live ? REFRESH_MS : 0 },
  );
  // Yükleme sonucu hangi segment adresine aitse onunla tutulur: segment değişince
  // eski sonuç kendiliğinden geçersizleşir (efekt içinde senkron sıfırlama yok).
  const [loaded, setLoaded] = useState<{ key: string; src: string | null; failed: boolean } | null>(null);

  useEffect(() => {
    const key = data?.video_url;
    if (!key) return undefined;
    let url: string | null = null;
    let cancelled = false;
    apiFetchResponse(key)
      .then((res) => res.blob())
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setLoaded({ key, src: url, failed: false });
      })
      .catch(() => { if (!cancelled) setLoaded({ key, src: null, failed: true }); });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [data?.video_url]);

  const current = loaded && loaded.key === data?.video_url ? loaded : null;
  const src = current?.src ?? null;
  const videoError = current?.failed ?? false;

  const missing = error instanceof ApiError && error.status === 404;
  const s = data?.summary;
  return (
    <div className="rc" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>
          Canlı Telestrasyon
          {s?.label && <span style={{ fontWeight: 400, color: "var(--muted)", fontSize: 11 }}> · {s.label}</span>}
        </h3>
        {s && (
          <span style={{ fontSize: 10, color: "var(--muted)" }}>
            {data?.segment} · {s.start_minute.toFixed(1)}&apos; · çizilen kare %{Math.round(100 * s.drawn_ratio)}
          </span>
        )}
      </div>
      {missing || (!data && !error) ? (
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>
          Bu maç için canlı telestrasyon yok. Canlı modu
          <code style={{ margin: "0 4px" }}>--telestration --calibration &lt;saha&gt;.json --home-attack x+</code>
          ile başlatın.
        </div>
      ) : error ? (
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>Telestrasyon okunamadı; yeniden denenecek.</div>
      ) : videoError ? (
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>Segment videosu alınamadı.</div>
      ) : src ? (
        <video
          key={src}
          src={src}
          autoPlay
          muted
          loop
          playsInline
          controls
          style={{ width: "100%", marginTop: 10, borderRadius: 10, background: "#000" }}
        />
      ) : (
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>Segment yükleniyor…</div>
      )}
    </div>
  );
}
