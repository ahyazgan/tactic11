/**
 * Pill + FormStrip — DESIGN.md §4.PillBadge.
 */
import * as React from "react";
import { cn } from "@/lib/cn";

type PillVariant = "win" | "draw" | "loss" | "neutral" | "warn" | "danger";

const VARIANT_CLASSES: Record<PillVariant, string> = {
  win: "bg-win/15 text-win",
  draw: "bg-draw/15 text-draw",
  loss: "bg-loss/15 text-loss",
  neutral: "bg-surface2 text-textmut",
  warn: "bg-warn/15 text-warn",
  danger: "bg-danger/15 text-danger",
};

export interface PillProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: PillVariant;
}

export function Pill({
  variant = "neutral",
  className,
  children,
  ...props
}: PillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase",
        VARIANT_CLASSES[variant],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

/**
 * W/D/L tek harf, w-4 h-4 kare — tablo içine sıkışan form göstergesi.
 */
export function ResultDot({ result }: { result: "W" | "D" | "L" }) {
  const variant: PillVariant =
    result === "W" ? "win" : result === "L" ? "loss" : "draw";
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center w-4 h-4 rounded text-[10px] font-bold",
        VARIANT_CLASSES[variant],
      )}
    >
      {result}
    </span>
  );
}

/**
 * Form şeridi — sağdan sola en yeni. DESIGN.md §4.
 */
export function FormStrip({
  results,
  max = 5,
}: {
  results: ("W" | "D" | "L")[];
  max?: number;
}) {
  // En son N, sağdan sola en yeni (caller kronolojik gönderir, biz reverse)
  const shown = results.slice(-max).reverse();
  return (
    <span className="inline-flex gap-0.5">
      {shown.map((r, i) => (
        <ResultDot key={i} result={r} />
      ))}
    </span>
  );
}
