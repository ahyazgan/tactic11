/**
 * StatTile — DESIGN.md §4.StatTile.
 *
 * Tek metrik kutusu (ppg, son N W/D/L, vb). Label + value + opsiyonel
 * delta + opsiyonel inline sparkline.
 */
"use client";

import * as React from "react";
import { cn } from "@/lib/cn";
import { Sparkline } from "./sparkline";

export interface StatTileProps {
  label: string;
  value: React.ReactNode;
  /** Pozitif değer win, negatif loss renkte. String ya da number. */
  delta?: string | number;
  sparkData?: number[];
  /** Sparkline yön override (yoksa otomatik). */
  sparkColor?: string;
  className?: string;
}

function formatDelta(d: string | number): { text: string; positive: boolean } {
  if (typeof d === "number") {
    const positive = d >= 0;
    return { text: positive ? `+${d}` : String(d), positive };
  }
  const positive = !d.trim().startsWith("-");
  return { text: d, positive };
}

export function StatTile({
  label,
  value,
  delta,
  sparkData,
  sparkColor,
  className,
}: StatTileProps) {
  const deltaInfo = delta !== undefined ? formatDelta(delta) : null;
  return (
    <div
      className={cn(
        "bg-surface border border-border rounded-md p-3",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wider text-textdim">
          {label}
        </span>
        {sparkData && sparkData.length > 0 && (
          <Sparkline data={sparkData} width={64} height={16} color={sparkColor} />
        )}
      </div>
      <div className="flex items-baseline gap-2 mt-1">
        <span className="text-xl font-semibold tabular-nums text-text">
          {value}
        </span>
        {deltaInfo && (
          <span
            className={cn(
              "text-[11px] tabular-nums",
              deltaInfo.positive ? "text-win" : "text-loss",
            )}
          >
            {deltaInfo.text}
          </span>
        )}
      </div>
    </div>
  );
}
