import { cn } from "@/lib/cn";

/**
 * RiskPill — renkli nokta (glow) + monospace etiket. Hem risk seviyeleri
 * (Düşük/Orta/Yüksek/Kritik) hem norm dereceleri (elit/iyi/ortalama/zayıf)
 * için. Bilinmeyen etiket → nötr.
 */

// Etiket → (nokta bg+text, metin rengi). text-* + bg-* aynı olunca currentColor
// glow doğru renkte olur.
const STYLE: Record<string, { dot: string; text: string }> = {
  Düşük: { dot: "bg-ok text-ok", text: "text-ok" },
  elit: { dot: "bg-ok text-ok", text: "text-ok" },
  iyi: { dot: "bg-ok text-ok", text: "text-ok" },
  Orta: { dot: "bg-warn text-warn", text: "text-warn" },
  ortalama: { dot: "bg-warn text-warn", text: "text-warn" },
  Yüksek: { dot: "bg-high text-high", text: "text-high" },
  Kritik: { dot: "bg-danger text-danger", text: "text-danger" },
  zayıf: { dot: "bg-danger text-danger", text: "text-danger" },
};
const NEUTRAL = { dot: "bg-textdim text-textdim", text: "text-textmut" };

export function RiskPill({
  label,
  score,
  className,
}: {
  label: string;
  score?: number;
  className?: string;
}) {
  const s = STYLE[label] ?? NEUTRAL;
  return (
    <span className={cn("inline-flex items-center gap-2 text-[12px]", className)}>
      <span
        className={cn("w-2 h-2 rounded-full shrink-0", s.dot)}
        style={{ boxShadow: "0 0 7px currentColor" }}
      />
      <span className={cn("font-semibold", s.text)}>{label}</span>
      {score !== undefined && (
        <span className="font-mono text-textmut">{score}</span>
      )}
    </span>
  );
}
