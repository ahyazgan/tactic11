import { cn } from "@/lib/cn";

/**
 * ConditionBar — kondisyon/yük dolum çubuğu. Eşik renkleri:
 * ≥85 yeşil (ok), ≥72 sarı (warn), altı turuncu (high).
 */
export function ConditionBar({
  value,
  max = 100,
  className,
}: {
  value: number;
  max?: number;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / (max || 1)) * 100));
  const color = pct >= 85 ? "bg-ok" : pct >= 72 ? "bg-warn" : "bg-high";
  return (
    <div className={cn("h-2 rounded bg-elevated overflow-hidden", className)}>
      <div
        className={cn("h-full rounded transition-all", color)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
