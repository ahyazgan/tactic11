"use client";

/**
 * Konsol veri-görselleştirme bileşenleri (saf SVG, tema-değişkenli renkler).
 * Gerçek anlık veriyle çalışır — uydurma seri yok.
 */

import * as React from "react";

/** Donut/segment halkası — risk/durum dağılımı için. */
export function RiskDonut({
  segments,
  size = 122,
  thickness = 15,
  centerLabel,
  centerSub,
}: {
  segments: { value: number; color: string }[];
  size?: number;
  thickness?: number;
  centerLabel?: React.ReactNode;
  centerSub?: string;
}) {
  const total = segments.reduce((a, s) => a + s.value, 0);
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  let offset = 0;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block" }}>
      <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--panel3)" strokeWidth={thickness} />
        {total > 0 &&
          segments.map((s, i) => {
            if (s.value <= 0) return null;
            const len = (s.value / total) * c;
            const el = (
              <circle
                key={i}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth={thickness}
                strokeDasharray={`${len} ${c - len}`}
                strokeDashoffset={-offset}
              />
            );
            offset += len;
            return el;
          })}
      </g>
      {centerLabel != null && (
        <text x="50%" y="47%" textAnchor="middle" dominantBaseline="middle" fill="var(--ink)" style={{ fontSize: size * 0.27, fontWeight: 800, fontFamily: "JetBrains Mono" }}>
          {centerLabel}
        </text>
      )}
      {centerSub && (
        <text x="50%" y="63%" textAnchor="middle" fill="var(--dim)" style={{ fontSize: size * 0.092, textTransform: "uppercase", letterSpacing: 1 }}>
          {centerSub}
        </text>
      )}
    </svg>
  );
}

/** 270° gauge — 0..100 değer (ör. ortalama kondisyon). */
export function Gauge({
  value,
  color,
  size = 112,
  label,
}: {
  value: number;
  color: string;
  size?: number;
  label?: string;
}) {
  const v = Math.max(0, Math.min(100, value));
  const thickness = 11;
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const track = c * 0.75; // 270°
  const fill = track * (v / 100);

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block" }}>
      <g transform={`rotate(135 ${size / 2} ${size / 2})`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--panel3)" strokeWidth={thickness} strokeDasharray={`${track} ${c}`} strokeLinecap="round" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={thickness} strokeDasharray={`${fill} ${c}`} strokeLinecap="round" />
      </g>
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle" fill="var(--ink)" style={{ fontSize: size * 0.25, fontWeight: 800, fontFamily: "JetBrains Mono" }}>
        {Math.round(v)}
        <tspan style={{ fontSize: size * 0.13, fill: "var(--dim)" }}>%</tspan>
      </text>
      {label && (
        <text x="50%" y="70%" textAnchor="middle" fill="var(--dim)" style={{ fontSize: size * 0.1, textTransform: "uppercase", letterSpacing: 1 }}>
          {label}
        </text>
      )}
    </svg>
  );
}

/** Donut + legend için tek satır gösterge. */
export function LegendRow({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0", fontSize: 12 }}>
      <span style={{ width: 9, height: 9, borderRadius: 3, background: color, flexShrink: 0 }} />
      <span style={{ color: "var(--muted)" }}>{label}</span>
      <span style={{ marginLeft: "auto", fontFamily: "JetBrains Mono", fontWeight: 700, color: "var(--ink)" }}>{value}</span>
    </div>
  );
}
