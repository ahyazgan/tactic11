/**
 * MiniPitch — pas alternatives için saha mini-map.
 * 200×130 SVG, koyu yeşil zemin, beyaz çizgi.
 *
 * Props:
 *   start: [x,y] (0-100 normalize)
 *   actualEnd: [x,y]
 *   suggestedEnd?: [x,y]
 *
 * actual = kırmızı kesik çizgi (loss); suggested = yeşil düz (win).
 */
"use client";

import * as React from "react";

const W = 200;
const H = 130;
const PADDING = 4;

function toSvg(x: number, y: number): [number, number] {
  return [
    PADDING + (x / 100) * (W - 2 * PADDING),
    PADDING + (y / 100) * (H - 2 * PADDING),
  ];
}

export interface MiniPitchProps {
  start: [number, number];
  actualEnd: [number, number];
  suggestedEnd?: [number, number];
  label?: string;
}

export function MiniPitch({
  start,
  actualEnd,
  suggestedEnd,
  label,
}: MiniPitchProps) {
  const [sx, sy] = toSvg(start[0], start[1]);
  const [ax, ay] = toSvg(actualEnd[0], actualEnd[1]);
  const [su, su2] = suggestedEnd ? toSvg(suggestedEnd[0], suggestedEnd[1]) : [0, 0];

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      className="rounded border border-border"
      aria-label={label ?? "Saha mini-map"}
    >
      <defs>
        <marker
          id="arrow-loss"
          markerWidth="6"
          markerHeight="6"
          refX="5"
          refY="3"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0,0 L6,3 L0,6 z" fill="#e5534b" />
        </marker>
        <marker
          id="arrow-win"
          markerWidth="6"
          markerHeight="6"
          refX="5"
          refY="3"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0,0 L6,3 L0,6 z" fill="#3fb950" />
        </marker>
      </defs>
      {/* Pitch background */}
      <rect x={0} y={0} width={W} height={H} fill="#0d1f12" />
      {/* Outline */}
      <rect
        x={PADDING}
        y={PADDING}
        width={W - 2 * PADDING}
        height={H - 2 * PADDING}
        fill="none"
        stroke="#3a4f3a"
        strokeWidth={1}
      />
      {/* Center line */}
      <line
        x1={W / 2}
        y1={PADDING}
        x2={W / 2}
        y2={H - PADDING}
        stroke="#3a4f3a"
        strokeWidth={1}
      />
      {/* Center circle */}
      <circle
        cx={W / 2}
        cy={H / 2}
        r={12}
        fill="none"
        stroke="#3a4f3a"
        strokeWidth={1}
      />
      {/* Penalty boxes (sol + sağ) */}
      <rect
        x={PADDING}
        y={H / 2 - 30}
        width={28}
        height={60}
        fill="none"
        stroke="#3a4f3a"
        strokeWidth={1}
      />
      <rect
        x={W - PADDING - 28}
        y={H / 2 - 30}
        width={28}
        height={60}
        fill="none"
        stroke="#3a4f3a"
        strokeWidth={1}
      />

      {/* Actual pass — kırmızı kesik çizgi */}
      <line
        x1={sx}
        y1={sy}
        x2={ax}
        y2={ay}
        stroke="#e5534b"
        strokeWidth={1.5}
        strokeDasharray="3 2"
        markerEnd="url(#arrow-loss)"
      />
      {/* Suggested — yeşil düz */}
      {suggestedEnd && (
        <line
          x1={sx}
          y1={sy}
          x2={su}
          y2={su2}
          stroke="#3fb950"
          strokeWidth={1.5}
          markerEnd="url(#arrow-win)"
        />
      )}
      {/* Start dot */}
      <circle cx={sx} cy={sy} r={3} fill="#e4e7ec" />
      {/* Legend */}
      <text x={PADDING + 2} y={H - 4} fontSize={8} fill="#9aa1ad">
        {label ?? ""}
      </text>
    </svg>
  );
}
