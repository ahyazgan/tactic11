/**
 * SetPieceZoneMap — kale önü 5 zone overlay.
 *
 * Zone'lar:
 *   near_post:   x ≥ 90, y < 33
 *   central_6yd: x ≥ 95, 33 ≤ y ≤ 67
 *   far_post:    x ≥ 90, y > 67
 *   penalty_arc: 80 ≤ x < 90
 *   outside_box: x < 80
 *
 * Renkler routine_score'a göre (kırmızı → sarı → yeşil).
 */
"use client";

import * as React from "react";
import { ratingColor } from "@/lib/rating";

const W = 280;
const H = 220;

// Saha 100×100 → koordinat çevirici (kale sağda)
// Sadece hücum yarısının son 1/3 üstüne odaklan (x: 66.7-100, y: 0-100)
function px(x: number, y: number): [number, number] {
  // x 66.7..100 → 0..W
  const normX = Math.max(0, Math.min(1, (x - 66.7) / 33.3));
  // y 0..100 → 0..H
  const normY = Math.max(0, Math.min(1, y / 100));
  return [normX * W, normY * H];
}

interface Zone {
  id: string;
  name: string;
  trLabel: string;
  /** Polygon corners in saha-uzayı (100×100). */
  points: [number, number][];
}

const ZONES: Zone[] = [
  {
    id: "outside_box",
    name: "outside_box",
    trLabel: "Ceza dışı",
    points: [[66.7, 0], [80, 0], [80, 100], [66.7, 100]],
  },
  {
    id: "penalty_arc",
    name: "penalty_arc",
    trLabel: "Ceza yayı",
    points: [[80, 0], [90, 0], [90, 100], [80, 100]],
  },
  {
    id: "near_post",
    name: "near_post",
    trLabel: "Yakın direk",
    points: [[90, 0], [100, 0], [100, 33.3], [90, 33.3]],
  },
  {
    id: "central_6yd",
    name: "central_6yd",
    trLabel: "Kale ağzı (6 yd)",
    points: [[90, 33.3], [100, 33.3], [100, 66.7], [90, 66.7],
             [95, 50]],
  },
  {
    id: "far_post",
    name: "far_post",
    trLabel: "Uzak direk",
    points: [[90, 66.7], [100, 66.7], [100, 100], [90, 100]],
  },
];

function pointsAttr(pts: [number, number][]): string {
  return pts.map((p) => {
    const [x, y] = px(p[0], p[1]);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

export interface SetPieceZoneMapProps {
  /** Zone başına routine_score (0-1). */
  scoresByZone?: Record<string, number>;
  /** Rakibin saldırgan most_threatening_zone — × işaretle. */
  avoidZone?: string;
  /** Vurgu için seçili zone. */
  selectedZone?: string;
  onSelectZone?: (zone: string) => void;
}

export function SetPieceZoneMap({
  scoresByZone = {},
  avoidZone,
  selectedZone,
  onSelectZone,
}: SetPieceZoneMapProps) {
  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      className="rounded border border-border bg-[#0d1f12]"
      role="img"
      aria-label="Set-piece zone heatmap"
    >
      {/* Pitch outline */}
      <rect x={0} y={0} width={W} height={H} fill="#0d1f12" />
      {/* Zone polygons */}
      {ZONES.map((z) => {
        const score = scoresByZone[z.id] ?? 0;
        // 0-1 score'u 0-100 normalize → ratingColor (kırmızıdan yeşile)
        const fill = score > 0 ? ratingColor(score * 100) : "#2c3038";
        const isSelected = z.id === selectedZone;
        return (
          <g
            key={z.id}
            onClick={() => onSelectZone?.(z.id)}
            style={{ cursor: onSelectZone ? "pointer" : "default" }}
          >
            <polygon
              points={pointsAttr(z.points)}
              fill={fill}
              fillOpacity={isSelected ? 0.65 : 0.4}
              stroke={isSelected ? "#3d7eff" : "#3a4f3a"}
              strokeWidth={isSelected ? 2 : 1}
            />
            <ZoneLabel zone={z} score={score} avoidZone={avoidZone} />
          </g>
        );
      })}
      {/* Kale çizgisi (en sağda) */}
      <line
        x1={W - 1}
        y1={0}
        x2={W - 1}
        y2={H}
        stroke="#e4e7ec"
        strokeWidth={1.5}
      />
    </svg>
  );
}

function ZoneLabel({
  zone,
  score,
  avoidZone,
}: {
  zone: Zone;
  score: number;
  avoidZone?: string;
}) {
  // Polygon centroid
  const cx = zone.points.reduce((s, p) => s + p[0], 0) / zone.points.length;
  const cy = zone.points.reduce((s, p) => s + p[1], 0) / zone.points.length;
  const [x, y] = px(cx, cy);
  const isAvoid = zone.id === avoidZone;
  return (
    <>
      <text
        x={x}
        y={y - 6}
        fontSize={9}
        textAnchor="middle"
        fill="#e4e7ec"
      >
        {zone.trLabel}
      </text>
      <text
        x={x}
        y={y + 6}
        fontSize={11}
        fontWeight="bold"
        textAnchor="middle"
        fill="#e4e7ec"
      >
        {(score * 100).toFixed(0)}
      </text>
      {isAvoid && (
        <text
          x={x}
          y={y + 18}
          fontSize={14}
          fontWeight="bold"
          textAnchor="middle"
          fill="#e5534b"
        >
          ✕
        </text>
      )}
    </>
  );
}
