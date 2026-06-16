"use client";

/**
 * Yarım daire gauge — 0..100 health skoru.
 * Saf SVG; recharts'a gerek yok (basit + customizable).
 */

interface Props {
  score: number;            // 0..100
  label?: string;
}

export function TeamHealthGauge({ score, label = "Kadro Formu" }: Props) {
  const clamped = Math.max(0, Math.min(100, score));
  // Yarım daire: 180° → 0°; angle = 180 - score/100 * 180
  const angle = 180 - (clamped / 100) * 180;
  const radians = (angle * Math.PI) / 180;
  const cx = 100;
  const cy = 100;
  const r = 80;
  const x = cx + r * Math.cos(radians);
  const y = cy - r * Math.sin(radians);

  const color =
    clamped >= 70 ? "#22c55e" : clamped >= 50 ? "#f59e0b" : "#ef4444";
  const verdict =
    clamped >= 70 ? "SAĞLIKLI" : clamped >= 50 ? "ORTA" : "ZAYIF";

  // Arc path: large arc (180°)
  const arcPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  // Score arc (kısmi)
  const scoreArcPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x} ${y}`;

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 200 130" width="100%" style={{ maxWidth: 240 }}>
        {/* arka plan arc */}
        <path
          d={arcPath}
          fill="none"
          stroke="#333"
          strokeWidth={14}
          strokeLinecap="round"
        />
        {/* doluluk arc */}
        <path
          d={scoreArcPath}
          fill="none"
          stroke={color}
          strokeWidth={14}
          strokeLinecap="round"
        />
        {/* needle (ucta nokta) */}
        <circle cx={x} cy={y} r={6} fill={color} stroke="#fff" strokeWidth={2} />
        {/* skor metni */}
        <text
          x={cx}
          y={cy - 5}
          textAnchor="middle"
          fontSize={26}
          fontWeight="700"
          fill="#fff"
        >
          {clamped.toFixed(0)}
        </text>
        <text
          x={cx}
          y={cy + 14}
          textAnchor="middle"
          fontSize={9}
          fill="#888"
        >
          / 100
        </text>
      </svg>
      <div className="mt-1 flex flex-col items-center">
        <span className="text-[10px] uppercase text-muted">{label}</span>
        <span
          className="text-xs font-semibold mt-0.5"
          style={{ color }}
        >
          {verdict}
        </span>
      </div>
    </div>
  );
}
