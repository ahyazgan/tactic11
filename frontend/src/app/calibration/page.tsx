"use client";

/**
 * Kalibrasyon & Track Record — modelin tahmin geçmişi + doğruluğu.
 *
 * DEMO_MODE (reconcile kaydı yokken): tahmin defterinden (lib/track-record)
 * GERÇEK hesaplanır — isabet oranı, Brier, kalibrasyon bucket'ları, tür kırılımı
 * ve "tahmin → gerçek ✓/✗" makbuzları. Bu, "AI tahmin ediyor"u "tahminlerimiz
 * %X tuttu"ya çeviren güven katmanı.
 * Canlı: GET /admin/predict-accuracy?days=30 (Brier/log loss/ECE backend'den).
 */

import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { DemoLiveBanner } from "@/lib/demo-live-banner";
import { demoTrackRecord, demoPredictionLedger } from "@/lib/track-record";
import { ConsoleShell } from "../_console/shell";
import { TrackRecordBadge, TypeBreakdown, ReceiptsTable } from "../_console/track-record";

interface AccuracyResponse {
  brier_score: number | null;
  log_loss: number | null;
  ece: number | null;
  sample_count: number;
  calibration_buckets?: { bucket_lower: number; bucket_upper: number; actual_rate: number; count: number }[];
}

function tone(value: number | null, good: number, mid: number): string {
  if (value == null) return "var(--muted)";
  if (value < good) return "var(--low)";
  if (value < mid) return "var(--mid)";
  return "var(--crit)";
}
function rateColor(rate: number): string {
  return rate >= 0.7 ? "var(--low)" : rate >= 0.55 ? "var(--mid)" : "var(--high)";
}

export default function CalibrationConsolePage() {
  const { data: liveData, error, isLoading } = useSWR<AccuracyResponse>(
    "/admin/predict-accuracy?days=30",
    apiFetch,
    { shouldRetryOnError: false },
  );
  // Demo: backend reconcile kaydı yoksa tahmin defterinden hesapla.
  const useDemo = DEMO_MODE && (!liveData || liveData.sample_count === 0);
  const ledger = demoPredictionLedger();
  const tr = demoTrackRecord();

  // Reliability tablosu için ortak bucket şekli (demo defteri ya da backend).
  const buckets = useDemo
    ? tr.buckets.map((b) => ({ lower: b.lower, upper: b.upper, actual: b.actual, count: b.count }))
    : (liveData?.calibration_buckets ?? []).map((b) => ({ lower: b.bucket_lower, upper: b.bucket_upper, actual: b.actual_rate, count: b.count }));

  // Demo ECE: bucket'lardan ağırlıklı |gerçek − beklenen|.
  const demoEce = tr.buckets.length
    ? tr.buckets.reduce((s, b) => s + b.count * Math.abs(b.actual - b.expected), 0) / tr.resolved
    : null;

  const right = (
    <>
      <div className="rc">
        <h3>Genel İsabet <span className="tiny">track record</span></h3>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <span style={{ fontSize: 30, fontWeight: 800, fontFamily: "JetBrains Mono", color: rateColor(tr.hitRate) }}>
            %{Math.round(tr.hitRate * 100)}
          </span>
          <span style={{ fontSize: 12, color: "var(--muted)" }}>{tr.resolved} değerlendirme</span>
        </div>
        <div style={{ marginTop: 8 }}><TrackRecordBadge tr={tr} /></div>
        <div style={{ display: "flex", gap: 14, marginTop: 10, fontSize: 11.5, color: "var(--muted)", fontFamily: "JetBrains Mono" }}>
          <span>son seri <b style={{ color: "var(--low)" }}>{tr.streak}✓</b></span>
          <span>açık <b style={{ color: "var(--ink)" }}>{tr.open}</b></span>
          {tr.rollingHitRate != null && <span>son 20 <b style={{ color: rateColor(tr.rollingHitRate) }}>%{Math.round(tr.rollingHitRate * 100)}</b></span>}
        </div>
      </div>
      <div className="rc">
        <h3>Nasıl Okunur?</h3>
        <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.6 }}>
          <div><b style={{ color: "var(--ink)" }}>İsabet</b> ↑ — tahminlerin yüzde kaçı tuttu</div>
          <div><b style={{ color: "var(--ink)" }}>Brier</b> ↓ — güven gerçeği yansıtıyor mu, &lt;0.2 iyi</div>
          <div><b style={{ color: "var(--ink)" }}>ECE</b> ↓ — kalibrasyon hatası, &lt;0.05 iyi</div>
          <div style={{ marginTop: 8, color: "var(--dim)" }}>Yüksek isabet + düşük Brier = güvenilir model.</div>
        </div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/calibration"
      title="Kalibrasyon & Track Record"
      sub="Tahmin geçmişi · doğruluk"
      desc="Model her tahmini defterler; sonuç gelince isabet/ıska işaretlenir. 'AI tahmin ediyor' değil — 'tahminlerimiz şu kadar tuttu'."
      right={right}
    >
      <DemoLiveBanner />
      {isLoading && !useDemo && <div className="pgdesc">Yükleniyor…</div>}
      {error && !useDemo && <div className="pgdesc">Veri alınamadı ya da yetki yok (admin).</div>}

      <div className="kpis" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        <div className="kpi">
          <div className="kl">İsabet Oranı</div>
          <div className="kn" style={{ color: rateColor(tr.hitRate) }}>%{Math.round(tr.hitRate * 100)}</div>
          <div className="kd">{tr.hits}/{tr.resolved} tuttu</div>
        </div>
        <div className="kpi">
          <div className="kl">Brier</div>
          <div className="kn" style={{ color: tone(useDemo ? tr.brier : (liveData?.brier_score ?? null), 0.15, 0.25) }}>
            {useDemo ? (tr.brier != null ? tr.brier.toFixed(3) : "—") : (liveData?.brier_score != null ? liveData.brier_score.toFixed(3) : "—")}
          </div>
          <div className="kd">güven↔gerçek, ↓ iyi</div>
        </div>
        <div className="kpi">
          <div className="kl">ECE</div>
          <div className="kn" style={{ color: tone(useDemo ? demoEce : (liveData?.ece ?? null), 0.05, 0.1) }}>
            {useDemo ? (demoEce != null ? demoEce.toFixed(3) : "—") : (liveData?.ece != null ? liveData.ece.toFixed(3) : "—")}
          </div>
          <div className="kd">kalibrasyon hatası</div>
        </div>
        <div className="kpi">
          <div className="kl">Değerlendirme</div>
          <div className="kn">{useDemo ? tr.resolved : (liveData?.sample_count ?? 0)}</div>
          <div className="kd">{useDemo ? `${tr.open} açık tahmin` : "reconcile tahmin"}</div>
        </div>
      </div>

      {useDemo && (
        <>
          <div className="st"><h2>Tür Bazında İsabet</h2><span className="ep">tahmin defteri</span></div>
          <div className="rc" style={{ margin: 0 }}><TypeBreakdown tr={tr} /></div>
        </>
      )}

      <div className="st"><h2>Reliability Diyagramı</h2><span className="ep">{useDemo ? "tahmin defterinden" : "GET /admin/predict-accuracy"}</span></div>
      <div className="tbl">
        <table>
          <thead><tr><th>Güven Aralığı</th><th className="r">Beklenen Orta</th><th className="r">Gerçek İsabet</th><th className="r">Örneklem</th></tr></thead>
          <tbody>
            {buckets.length === 0 && (
              <tr><td colSpan={4} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>Bucket verisi yok.</td></tr>
            )}
            {buckets.map((b, i) => {
              const exp = (b.lower + b.upper) / 2;
              const dev = Math.abs(b.actual - exp);
              return (
                <tr key={i}>
                  <td style={{ fontFamily: "JetBrains Mono" }}>{b.lower.toFixed(2)} – {b.upper.toFixed(2)}</td>
                  <td className="r" style={{ color: "var(--muted)" }}>{exp.toFixed(2)}</td>
                  <td className="r" style={{ color: dev < 0.05 ? "var(--low)" : dev < 0.12 ? "var(--mid)" : "var(--crit)" }}>{b.actual.toFixed(2)}</td>
                  <td className="r" style={{ color: "var(--muted)" }}>{b.count}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {useDemo && (
        <>
          <div className="st"><h2>Tahmin Makbuzları</h2><span className="ep">tahmin → gerçekleşen · son 12</span></div>
          <ReceiptsTable preds={ledger} limit={12} />
        </>
      )}
    </ConsoleShell>
  );
}
