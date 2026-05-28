"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface TrendData {
  series: number[];
  direction: string;
  slope: number;
  mean: number;
}

export function TrendLineChart({
  title,
  trend,
  matches,
  higherIsBetter = true,
}: {
  title: string;
  trend: TrendData;
  matches: { match_id: number; score: string }[];
  higherIsBetter?: boolean;
}) {
  const data = trend.series.map((v, i) => ({
    label: matches[i] ? `M#${matches[i].match_id}` : `${i + 1}`,
    value: v,
  }));

  const directionColor =
    trend.direction === "improving"
      ? "#22c55e"
      : trend.direction === "worsening"
      ? "#ef4444"
      : "#888";

  return (
    <div className="card">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-sm uppercase text-muted">{title}</h3>
        <span
          className="text-xs uppercase px-2 py-0.5 rounded"
          style={{ backgroundColor: `${directionColor}33`, color: directionColor }}
        >
          {trend.direction}
        </span>
      </div>
      <div className="text-xs text-muted mb-2">
        Ortalama: <span className="font-mono">{trend.mean.toFixed(2)}</span> ·
        Slope: <span className="font-mono">{trend.slope.toFixed(3)}</span>
        {higherIsBetter ? " (yüksek=iyi)" : " (düşük=iyi)"}
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#888" }} />
          <YAxis tick={{ fontSize: 10, fill: "#888" }} />
          <Tooltip
            contentStyle={{ backgroundColor: "#1a1a1a", border: "1px solid #444" }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={directionColor}
            strokeWidth={2}
            dot={{ fill: directionColor, r: 3 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
