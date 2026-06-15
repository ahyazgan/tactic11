"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Props {
  raw: number[];
  smoothed: number[];
  projection: number[];     // next 3 maç projeksiyonu
  peakIndex: number;
  dipIndex: number;
  direction: string;
}

export function PerformanceTrajectoryChart({
  raw,
  smoothed,
  projection,
  peakIndex,
  dipIndex,
  direction,
}: Props) {
  const data = raw.map((v, i) => ({
    label: `M${i + 1}`,
    raw: v,
    smoothed: smoothed[i] ?? null,
  }));
  // Projection olarak son N+1, N+2, N+3 puanı ekle
  const baseLen = raw.length;
  projection.forEach((v, i) => {
    data.push({
      label: `+${i + 1}`,
      raw: null as number | null as unknown as number,
      smoothed: null as number | null as unknown as number,
      // @ts-expect-error - dinamik field
      proj: v,
    });
  });

  const directionColor =
    direction === "improving"
      ? "#22c55e"
      : direction === "declining"
      ? "#ef4444"
      : "#888";

  const peakValue = raw[peakIndex];
  const dipValue = raw[dipIndex];

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#333" strokeDasharray="3 3" />
        <XAxis dataKey="label" stroke="#888" fontSize={10} />
        <YAxis stroke="#888" fontSize={10} domain={[0, 10]} />
        <Tooltip
          contentStyle={{
            background: "#1a1a1a",
            border: "1px solid #444",
            fontSize: "12px",
          }}
        />
        <Legend wrapperStyle={{ fontSize: "10px" }} />
        <Line
          name="Ham rating"
          dataKey="raw"
          stroke="#aaa"
          strokeWidth={1.5}
          dot={{ r: 2 }}
        />
        <Line
          name="Smoothed (3-MA)"
          dataKey="smoothed"
          stroke={directionColor}
          strokeWidth={2}
          dot={{ r: 3 }}
        />
        <Line
          name="Projeksiyon"
          dataKey="proj"
          stroke={directionColor}
          strokeWidth={2}
          strokeDasharray="5 5"
          dot={{ r: 3 }}
        />
        <ReferenceDot
          x={`M${peakIndex + 1}`}
          y={peakValue}
          r={6}
          fill="#22c55e"
          stroke="#fff"
          isFront
        />
        <ReferenceDot
          x={`M${dipIndex + 1}`}
          y={dipValue}
          r={6}
          fill="#ef4444"
          stroke="#fff"
          isFront
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
