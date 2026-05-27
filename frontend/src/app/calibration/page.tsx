"use client";

import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface AccuracyResponse {
  brier_score: number | null;
  log_loss: number | null;
  ece: number | null;
  sample_count: number;
  calibration_buckets?: { bucket_lower: number; bucket_upper: number; actual_rate: number; count: number }[];
}

function MetricCard({ label, value, hint, lowerIsBetter }: {
  label: string; value: number | null; hint: string; lowerIsBetter?: boolean;
}) {
  const tone = value == null
    ? "text-muted"
    : lowerIsBetter
      ? (value < 0.1 ? "text-good" : value < 0.2 ? "text-warn" : "text-bad")
      : (value > 0.7 ? "text-good" : value > 0.5 ? "text-warn" : "text-bad");
  return (
    <div className="card">
      <div className="text-xs uppercase text-muted">{label}</div>
      <div className={`text-2xl font-mono mt-1 ${tone}`}>
        {value == null ? "—" : value.toFixed(4)}
      </div>
      <div className="text-xs text-muted mt-1">{hint}</div>
    </div>
  );
}

export default function CalibrationPage() {
  const { data, error, isLoading } = useSWR<AccuracyResponse>(
    "/admin/predict-accuracy?days=30",
    apiFetch,
  );

  return (
    <main className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-2">Kalibrasyon (son 30 gün)</h1>
      <p className="text-muted text-sm mb-6">
        Tahminlerin doğruluğunu ölç. Brier ↓ ve ECE ↓ daha iyi; log loss ↓ daha iyi.
      </p>

      {error && <p className="text-bad mb-4">Hata: {String(error)}</p>}
      {isLoading && <p className="text-muted">Yükleniyor...</p>}

      {data && (
        <>
          <div className="grid md:grid-cols-3 gap-3 mb-6">
            <MetricCard label="Brier score" value={data.brier_score} hint="3-class Brier, 0..1; <0.1 mükemmel" lowerIsBetter />
            <MetricCard label="Log loss" value={data.log_loss} hint="Cross-entropy; <0.4 iyi" lowerIsBetter />
            <MetricCard label="ECE" value={data.ece} hint="Expected calibration error; <0.05 iyi" lowerIsBetter />
          </div>
          <div className="card">
            <div className="text-xs uppercase text-muted mb-2">Örneklem</div>
            <div className="font-mono">{data.sample_count} reconcile edilmiş tahmin</div>
          </div>
          {data.calibration_buckets && data.calibration_buckets.length > 0 && (
            <div className="card mt-4">
              <h2 className="text-sm uppercase text-muted mb-3">Reliability diagram (buckets)</h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted text-xs">
                    <th className="text-left py-1">Olasılık aralığı</th>
                    <th className="text-right">Beklenen orta</th>
                    <th className="text-right">Gerçek oran</th>
                    <th className="text-right">Örneklem</th>
                  </tr>
                </thead>
                <tbody>
                  {data.calibration_buckets.map((b, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="py-1 font-mono">{b.bucket_lower.toFixed(2)} – {b.bucket_upper.toFixed(2)}</td>
                      <td className="text-right font-mono">{((b.bucket_lower + b.bucket_upper) / 2).toFixed(2)}</td>
                      <td className="text-right font-mono">{b.actual_rate.toFixed(2)}</td>
                      <td className="text-right font-mono">{b.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </main>
  );
}
