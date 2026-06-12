"use client";

/**
 * Track Record görselleştirmesi — modelin isabet geçmişini gösteren güven katmanı.
 * lib/track-record.ts çıktısını render eder. `TrackRecordBadge` her tahminin
 * yanına konabilen kompakt güven rozeti (unicorn güven sinyali); `ReceiptsTable`
 * "tahmin → gerçek ✓/✗" makbuzları. Kalibrasyon sayfası + tahmin gösteren her
 * yerde yeniden kullanılır.
 */

import * as React from "react";
import {
  TYPE_LABEL, TYPE_GLYPH, type Prediction, type TrackRecord, type PredictionType,
} from "@/lib/track-record";

function rateColor(rate: number): string {
  return rate >= 0.7 ? "var(--low)" : rate >= 0.55 ? "var(--mid)" : "var(--high)";
}

/**
 * Kompakt güven rozeti — "Model: %72 isabet · 53 değerlendirme". Bir tahminin
 * yanına konunca o tahmine güveni somutlar. type verilirse o türün oranı.
 */
export function TrackRecordBadge({
  tr, type, compact = false,
}: { tr: TrackRecord; type?: PredictionType; compact?: boolean }) {
  const scoped = type ? tr.byType.find((t) => t.type === type) : null;
  const rate = scoped ? scoped.hitRate : tr.hitRate;
  const n = scoped ? scoped.resolved : tr.resolved;
  const color = rateColor(rate);
  if (!n) return null;
  return (
    <span
      title={`${type ? TYPE_LABEL[type] + " " : ""}tahminlerinin geçmiş isabet oranı (${n} değerlendirme)`}
      style={{
        display: "inline-flex", alignItems: "center", gap: 5,
        fontSize: compact ? 10.5 : 11.5, fontFamily: "JetBrains Mono",
        padding: compact ? "1px 7px" : "2px 9px", borderRadius: 999,
        border: `1px solid ${color}`, color,
        background: "color-mix(in srgb, var(--panel3) 70%, transparent)",
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: 999, background: color }} />
      Model: %{Math.round(rate * 100)} isabet
      {!compact && <span style={{ color: "var(--dim)" }}>· {n} değerlendirme</span>}
    </span>
  );
}

/** Tür başına isabet oranı barları. */
export function TypeBreakdown({ tr }: { tr: TrackRecord }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
      {tr.byType.map((t) => {
        const color = rateColor(t.hitRate);
        return (
          <div key={t.type}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: 11.5, marginBottom: 3 }}>
              <span style={{ color: "var(--muted)" }}>{TYPE_GLYPH[t.type]} {TYPE_LABEL[t.type]}</span>
              <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color }}>%{Math.round(t.hitRate * 100)}</span>
            </div>
            <div className="mbar"><i style={{ width: `${t.hitRate * 100}%`, background: color }} /></div>
            <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 2 }}>{t.hits}/{t.resolved} isabet</div>
          </div>
        );
      })}
    </div>
  );
}

/** "Tahmin → Gerçek ✓/✗" makbuz tablosu (en yeni resolved önce). */
export function ReceiptsTable({ preds, limit = 12 }: { preds: Prediction[]; limit?: number }) {
  const resolved = preds
    .filter((p) => p.status === "resolved" && p.outcome)
    .sort((a, b) => b.outcome!.resolved_at.localeCompare(a.outcome!.resolved_at) || b.id - a.id)
    .slice(0, limit);
  return (
    <div className="tbl">
      <table>
        <thead><tr>
          <th>Tür</th><th>Konu</th><th>Tahmin</th><th className="c">Güven</th><th>Gerçekleşen</th><th className="c">Sonuç</th>
        </tr></thead>
        <tbody>
          {resolved.length === 0 && (
            <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--dim)", padding: 18 }}>Sonuçlanmış tahmin yok.</td></tr>
          )}
          {resolved.map((p) => (
            <tr key={p.id}>
              <td style={{ whiteSpace: "nowrap", color: "var(--muted)", fontSize: 11.5 }}>{TYPE_GLYPH[p.type]} {TYPE_LABEL[p.type]}</td>
              <td style={{ fontSize: 12 }}>{p.subject}</td>
              <td style={{ fontSize: 11.5, color: "var(--muted)" }}>{p.claim}</td>
              <td className="c" style={{ fontFamily: "JetBrains Mono", fontSize: 11.5, color: "var(--muted)" }}>%{Math.round(p.confidence * 100)}</td>
              <td style={{ fontSize: 11.5, color: "var(--muted)" }}>{p.outcome!.actual}</td>
              <td className="c">
                <span className={`risk ${p.outcome!.hit ? "risk-low" : "risk-crit"}`} style={{ fontSize: 11 }}>
                  <span className="rd" style={{ background: p.outcome!.hit ? "var(--low)" : "var(--crit)" }} />
                  {p.outcome!.hit ? "✓ tuttu" : "✗ ıska"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
