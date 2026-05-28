"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function RecoveryZoneStacked({
  defensive, middle, attacking,
}: {
  defensive: number;
  middle: number;
  attacking: number;
}) {
  const data = [
    { zone: "Savunma 1/3", value: Math.round(defensive * 100), fill: "#ef4444" },
    { zone: "Orta 1/3", value: Math.round(middle * 100), fill: "#eab308" },
    { zone: "Hücum 1/3", value: Math.round(attacking * 100), fill: "#22c55e" },
  ];
  return (
    <div className="card">
      <h3 className="text-sm uppercase text-muted mb-2">Recovery Zone (%)</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="zone" tick={{ fontSize: 10, fill: "#bbb" }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#888" }} />
          <Tooltip
            contentStyle={{ backgroundColor: "#1a1a1a", border: "1px solid #444" }}
          />
          <Bar dataKey="value">
            {data.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
