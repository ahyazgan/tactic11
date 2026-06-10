"use client";

/**
 * Kalibrasyon — tahmin doğruluğu (Brier / log loss / ECE) + reliability buckets.
 * ConsoleShell çatısında. Veri: GET /admin/predict-accuracy?days=30.
 */

import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { DemoLiveBanner } from "@/lib/demo-live-banner";
import { ConsoleShell } from "../_console/shell";

interface AccuracyResponse {
  brier_score: number | null;
  log_loss: number | null;
  ece: number | null;
  sample_count: number;
  calibration_buckets?: { bucket_lower: number; bucket_upper: number; actual_rate: number; count: number }[];
}

// Demo örnek verisi — backend'te reconcile edilmiş tahmin yokken sayfa boş
// kalmasın. Değerler "iyi ama kusursuz değil" bandında (inandırıcı): Brier orta,
// ECE iyi; bucket'lar hafif sapmalı. Canlı kayıt varsa daima o gösterilir.
const DEMO_ACCURACY: AccuracyResponse = {
  brier_score: 0.1684,
  log_loss: 0.5112,
  ece: 0.0421,
  sample_count: 412,
  calibration_buckets: [
    { bucket_lower: 0.0, bucket_upper: 0.2, actual_rate: 0.13, count: 96 },
    { bucket_lower: 0.2, bucket_upper: 0.4, actual_rate: 0.31, count: 118 },
    { bucket_lower: 0.4, bucket_upper: 0.6, actual_rate: 0.52, count: 104 },
    { bucket_lower: 0.6, bucket_upper: 0.8, actual_rate: 0.66, count: 67 },
    { bucket_lower: 0.8, bucket_upper: 1.0, actual_rate: 0.87, count: 27 },
  ],
};

function tone(value: number | null, good: number, mid: number): string {
  if (value == null) return "var(--muted)";
  if (value < good) return "var(--low)";
  if (value < mid) return "var(--mid)";
  return "var(--crit)";
}

export default function CalibrationConsolePage() {
  const { data: liveData, error, isLoading } = useSWR<AccuracyResponse>(
    "/admin/predict-accuracy?days=30",
    apiFetch,
    { shouldRetryOnError: false },
  );
  // Demo modunda reconcile edilmiş tahmin yoksa örnek metrikler.
  const useDemo = DEMO_MODE && (!liveData || liveData.sample_count === 0);
  const data = useDemo ? DEMO_ACCURACY : liveData;
  const buckets = data?.calibration_buckets ?? [];

  const right = (
    <div className="rc">
      <h3>Nasıl Okunur?</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.6 }}>
        <div><b style={{ color: "var(--ink)" }}>Brier</b> ↓ — 3-sınıf, &lt;0.1 mükemmel</div>
        <div><b style={{ color: "var(--ink)" }}>Log loss</b> ↓ — cross-entropy, &lt;0.4 iyi</div>
        <div><b style={{ color: "var(--ink)" }}>ECE</b> ↓ — kalibrasyon hatası, &lt;0.05 iyi</div>
        <div style={{ marginTop: 8, color: "var(--dim)" }}>Hepsi düşük = model güvenilir.</div>
      </div>
    </div>
  );

  return (
    <ConsoleShell
      active="/calibration"
      title="Kalibrasyon"
      sub="Son 30 gün"
      desc="Tahminlerin doğruluğunu ölçer. Brier ↓, log loss ↓ ve ECE ↓ daha iyidir."
      right={right}
    >
      <DemoLiveBanner />
      {isLoading && !useDemo && <div className="pgdesc">Yükleniyor…</div>}
      {error && !useDemo && <div className="pgdesc">Veri alınamadı ya da yetki yok (admin).</div>}

      <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        <div className="kpi"><div className="kl">Brier</div><div className="kn" style={{ color: tone(data?.brier_score ?? null, 0.1, 0.2) }}>{data?.brier_score != null ? data.brier_score.toFixed(4) : "—"}</div><div className="kd">3-sınıf, ↓ iyi</div></div>
        <div className="kpi"><div className="kl">Log Loss</div><div className="kn" style={{ color: tone(data?.log_loss ?? null, 0.4, 0.6) }}>{data?.log_loss != null ? data.log_loss.toFixed(4) : "—"}</div><div className="kd">cross-entropy</div></div>
        <div className="kpi"><div className="kl">ECE</div><div className="kn" style={{ color: tone(data?.ece ?? null, 0.05, 0.1) }}>{data?.ece != null ? data.ece.toFixed(4) : "—"}</div><div className="kd">kalibrasyon hatası</div></div>
        <div className="kpi"><div className="kl">Örneklem</div><div className="kn">{data?.sample_count ?? 0}</div><div className="kd">reconcile tahmin</div></div>
      </div>

      <div className="st"><h2>Reliability Diyagramı</h2><span className="ep">{useDemo ? "örnek veri (reconcile kaydı yok)" : "GET /admin/predict-accuracy"}</span></div>
      <div className="tbl">
        <table>
          <thead><tr><th>Olasılık Aralığı</th><th className="r">Beklenen Orta</th><th className="r">Gerçek Oran</th><th className="r">Örneklem</th></tr></thead>
          <tbody>
            {buckets.length === 0 && (
              <tr><td colSpan={4} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                Bucket verisi yok.
              </td></tr>
            )}
            {buckets.map((b, i) => {
              const exp = (b.bucket_lower + b.bucket_upper) / 2;
              const dev = Math.abs(b.actual_rate - exp);
              return (
                <tr key={i}>
                  <td style={{ fontFamily: "JetBrains Mono" }}>{b.bucket_lower.toFixed(2)} – {b.bucket_upper.toFixed(2)}</td>
                  <td className="r" style={{ color: "var(--muted)" }}>{exp.toFixed(2)}</td>
                  <td className="r" style={{ color: dev < 0.05 ? "var(--low)" : dev < 0.12 ? "var(--mid)" : "var(--crit)" }}>{b.actual_rate.toFixed(2)}</td>
                  <td className="r" style={{ color: "var(--muted)" }}>{b.count}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
