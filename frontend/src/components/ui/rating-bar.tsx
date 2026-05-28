/**
 * RatingBar — DESIGN.md §4.RatingBar.
 * FM attribute bar'ı: sayı + dolu çubuk.
 */
import * as React from "react";
import { cn } from "@/lib/cn";
import { ratingColor } from "@/lib/rating";

export interface RatingBarProps {
  value: number; // 0-100
  label?: string;
  max?: number;
  /** Tablo içi kompakt: sadece renkli sayı, çubuk yok. */
  dense?: boolean;
  className?: string;
}

export function RatingBar({
  value,
  label,
  max = 100,
  dense = false,
  className,
}: RatingBarProps) {
  const clamped = Math.max(0, Math.min(max, value));
  const pct = (clamped / max) * 100;
  const color = ratingColor((clamped / max) * 100);

  if (dense) {
    return (
      <span
        className={cn("font-semibold tabular-nums", className)}
        style={{ color }}
      >
        {clamped.toFixed(0)}
      </span>
    );
  }

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span
        className="text-[11px] font-semibold tabular-nums w-6 text-right"
        style={{ color }}
      >
        {clamped.toFixed(0)}
      </span>
      <div className="flex-1 bg-surface2 h-1.5 rounded overflow-hidden">
        <div
          className="h-full rounded transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      {label && (
        <span className="text-[10px] uppercase tracking-wider text-textdim w-16">
          {label}
        </span>
      )}
    </div>
  );
}
