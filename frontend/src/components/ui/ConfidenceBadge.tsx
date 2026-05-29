/**
 * ConfidenceBadge — güven skoru rozeti (Faz 8).
 *
 * Tekrar kullanılabilir: hem API'den gelen `{score, label, drivers}` güven
 * objesi (predict/form/rating/...), hem sub-chess'in legacy string label'ı
 * (high/medium/low) için çalışır.
 *
 * Renk DESIGN.md token'larıyla (yeni renk uydurulmadı):
 *   yüksek/high → good · orta/medium → warn · düşük → bad · low → neutral (legacy)
 */
import { cn } from "@/lib/cn";

export interface ConfidenceBadgeProps {
  /** 0..1 güven skoru. Yoksa (legacy sub-chess) yüzde gösterilmez. */
  score?: number;
  /** "yüksek" | "orta" | "düşük" (API) ya da "high" | "medium" | "low" (legacy). */
  label: string;
  /** Güveni neyin desteklediği — hover/tooltip + küçük liste. */
  drivers?: string[];
  className?: string;
}

const TONE: Record<string, string> = {
  yüksek: "bg-good/15 text-good",
  high: "bg-good/15 text-good",
  orta: "bg-warn/15 text-warn",
  medium: "bg-warn/15 text-warn",
  düşük: "bg-bad/15 text-bad",
  low: "bg-surface2 text-textmut", // legacy sub-chess: düşük güven nötr kalsın
};

export function ConfidenceBadge({
  score,
  label,
  drivers,
  className,
}: ConfidenceBadgeProps) {
  const key = (label ?? "").toLocaleLowerCase("tr");
  const tone = TONE[key] ?? "bg-surface2 text-textmut";
  const pct = typeof score === "number" ? `%${Math.round(score * 100)}` : null;
  const title =
    drivers && drivers.length ? drivers.join(" · ") : undefined;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase",
        tone,
        className,
      )}
      title={title}
    >
      {pct && <span>{pct}</span>}
      <span className={pct ? "opacity-80" : undefined}>{label}</span>
    </span>
  );
}
