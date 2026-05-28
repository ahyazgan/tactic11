"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function ChannelPreferenceBar({
  left, central, right,
}: {
  left: number;
  central: number;
  right: number;
}) {
  const data = [
    { channel: "Sol", value: Math.round(left * 100) },
    { channel: "Orta", value: Math.round(central * 100) },
    { channel: "Sağ", value: Math.round(right * 100) },
  ];
  return (
    <div className="card">
      <h3 className="text-sm uppercase text-muted mb-2">Kanal Tercihi (%)</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis dataKey="channel" tick={{ fontSize: 11, fill: "#bbb" }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#888" }} />
          <Tooltip
            contentStyle={{ backgroundColor: "#1a1a1a", border: "1px solid #444" }}
          />
          <Bar dataKey="value" fill="#3b82f6" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
