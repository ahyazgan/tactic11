/**
 * Sparkline — DESIGN.md §4.Sparkline.
 *
 * SVG polyline; eksen yok, grid yok. Yön-tabanlı renk default'u
 * (yükseliş=win, düşüş=loss, düz=textmut).
 */
"use client";

import * as React from "react";

export interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  /** Renk override; verilmezse trend yönü belirler. */
  color?: string;
  /** Son nokta vurgu dot'unu kaldır (default true). */
  dot?: boolean;
  className?: string;
}

const COLOR_WIN = "#3fb950";
const COLOR_LOSS = "#e5534b";
const COLOR_FLAT = "#9aa1ad";

function trendColor(data: number[]): string {
  if (data.length < 2) return COLOR_FLAT;
  const first = data[0];
  const last = data[data.length - 1];
  if (last > first) return COLOR_WIN;
  if (last < first) return COLOR_LOSS;
  return COLOR_FLAT;
}

export function Sparkline({
  data,
  width = 64,
  height = 18,
  color,
  dot = true,
  className,
}: SparklineProps) {
  if (data.length === 0) {
    return (
      <svg width={width} height={height} className={className} aria-hidden="true">
        <line
          x1={0} y1={height / 2} x2={width} y2={height / 2}
          stroke={COLOR_FLAT} strokeDasharray="2 2" strokeWidth={1}
        />
      </svg>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const padding = 2;
  const innerH = height - 2 * padding;
  const innerW = width - 2 * padding;
  const step = data.length > 1 ? innerW / (data.length - 1) : 0;

  const points = data
    .map((v, i) => {
      const x = padding + i * step;
      const y = padding + innerH - ((v - min) / range) * innerH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const last = data[data.length - 1];
  const lastX = padding + (data.length - 1) * step;
  const lastY = padding + innerH - ((last - min) / range) * innerH;
  const strokeColor = color ?? trendColor(data);

  return (
    <svg
      width={width}
      height={height}
      className={className}
      aria-hidden="true"
    >
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
      {dot && (
        <circle
          cx={lastX}
          cy={lastY}
          r={2}
          fill={strokeColor}
        />
      )}
    </svg>
  );
}
