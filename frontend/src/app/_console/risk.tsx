"use client";

/**
 * Birleşik Sakatlık Risk Endeksi görselleştirmesi — saf SVG, tema-değişkenli.
 * lib/injury-risk.ts çıktısını (RiskIndex) gösterir: 0-100 gauge + şeffaf
 * faktör kırılımı + en yüksek-kaldıraçlı öneri. Oyuncu profili + Tıbbi Merkez
 * gibi sayfalarda yeniden kullanılır (tek kaynak, tutarlı görünüm).
 */

import * as React from "react";
import {
  LEVEL_VAR, LEVEL_LABEL, TREND_LABEL, TREND_GLYPH,
  type RiskIndex, type RiskFactor,
} from "@/lib/injury-risk";

/** 0-100 risk arkı (gauge.value % yerine /100, risk renkli). */
export function RiskGauge({ score, level, size = 116 }: { score: number; level: keyof typeof LEVEL_VAR; size?: number }) {
  const v = Math.max(0, Math.min(100, score));
  const color = LEVEL_VAR[level];
  const thickness = 11;
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const track = c * 0.75;          // 270°
  const fill = track * (v / 100);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block" }}>
      <g transform={`rotate(135 ${size / 2} ${size / 2})`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--panel3)" strokeWidth={thickness} strokeDasharray={`${track} ${c}`} strokeLinecap="round" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={thickness} strokeDasharray={`${fill} ${c}`} strokeLinecap="round" />
      </g>
      <text x="50%" y="48%" textAnchor="middle" dominantBaseline="middle" fill="var(--ink)" style={{ fontSize: size * 0.26, fontWeight: 800, fontFamily: "JetBrains Mono" }}>
        {Math.round(v)}
        <tspan style={{ fontSize: size * 0.12, fill: "var(--dim)" }}>/100</tspan>
      </text>
      <text x="50%" y="68%" textAnchor="middle" fill={color} style={{ fontSize: size * 0.11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>
        {LEVEL_LABEL[level]}
      </text>
    </svg>
  );
}

/** Tek faktör kırılım satırı: ad + katkı barı (puan/ağırlık) + değer. */
function FactorRow({ f }: { f: RiskFactor }) {
  const color = LEVEL_VAR[f.level];
  const pct = f.weight > 0 ? (f.points / f.weight) * 100 : 0;
  return (
    <div style={{ padding: "5px 0", borderBottom: "1px solid var(--line)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ flex: 1, fontSize: 12, color: "var(--ink)", fontWeight: 600 }}>{f.label}</span>
        <span className="mbar" style={{ width: 88, margin: 0, flexShrink: 0 }}>
          <i style={{ width: `${Math.max(3, pct)}%`, background: color }} />
        </span>
        <span style={{ fontFamily: "JetBrains Mono", fontSize: 11.5, fontWeight: 700, color, width: 52, textAlign: "right", flexShrink: 0 }}>
          +{f.points.toFixed(1)}<span style={{ color: "var(--dim)", fontWeight: 400 }}>/{f.weight}</span>
        </span>
      </div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2, lineHeight: 1.4 }}>{f.detail}</div>
    </div>
  );
}

/** Trend rozeti — yükseliyor (kötü) kırmızımsı, geriliyor (iyi) yeşilimsi. */
export function TrendChip({ trend }: { trend: RiskIndex["trend"] }) {
  const color = trend === "rising" ? "var(--high)" : trend === "falling" ? "var(--low)" : "var(--muted)";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontFamily: "JetBrains Mono", color }}>
      <span>{TREND_GLYPH[trend]}</span>{TREND_LABEL[trend]}
    </span>
  );
}

/**
 * Tam birleşik risk kartı içeriği: gauge + sürücü + faktör kırılımı + öneri.
 * Sayfa kendi <div className="rc"> sarmalayıcısını + başlığını sağlar; bu bileşen
 * iç gövdeyi render eder (esnek yerleşim için).
 */
export function RiskIndexBody({ risk }: { risk: RiskIndex }) {
  if (!risk.evaluated) {
    return <div style={{ fontSize: 12, color: "var(--dim)" }}>Değerlendirilecek yük/test verisi yok — risk endeksi hesaplanamadı.</div>;
  }
  const color = LEVEL_VAR[risk.level];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <RiskGauge score={risk.score} level={risk.level} />
        <div style={{ flex: 1, minWidth: 180 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13, fontWeight: 700, color }}>{LEVEL_LABEL[risk.level]} risk</span>
            <TrendChip trend={risk.trend} />
            <span style={{ fontSize: 10.5, color: "var(--dim)" }}>· {risk.evaluated} sinyal füzyonu</span>
          </div>
          {risk.topDriver && (
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4, lineHeight: 1.5 }}>
              En büyük sürücü: <b style={{ color: "var(--ink)" }}>{risk.topDriver.label}</b> — {risk.topDriver.detail}
            </div>
          )}
          <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 6, fontStyle: "italic" }}>{risk.horizonNote}</div>
        </div>
      </div>

      <div>
        <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 2 }}>
          Faktör kırılımı <span style={{ textTransform: "none", letterSpacing: 0 }}>(ağırlıklı katkı)</span>
        </div>
        {risk.factors.map((f) => <FactorRow key={f.key} f={f} />)}
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "flex-start", background: "var(--panel3)", borderRadius: 7, padding: "9px 11px" }}>
        <span style={{ width: 4, alignSelf: "stretch", borderRadius: 2, background: color, flexShrink: 0 }} />
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 2 }}>Öncelikli aksiyon</div>
          <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.5 }}>{risk.recommendation}</div>
        </div>
      </div>
    </div>
  );
}
