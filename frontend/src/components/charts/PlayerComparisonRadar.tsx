"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

interface PerKpi {
  kpi: string;
  values: Record<string, number>;
  normalized: Record<string, number>;
}

interface PlayerSummary {
  player_id: number;
  name: string;
}

interface Props {
  kpis: string[];
  perKpi: PerKpi[];
  perPlayer: PlayerSummary[];
}

const COLORS = ["#22c55e", "#3b82f6", "#f59e0b", "#a855f7", "#ec4899", "#06b6d4"];

export function PlayerComparisonRadar({ kpis, perKpi, perPlayer }: Props) {
  // axis başına bir nokta; her oyuncu için normalized 0..1
  const data = kpis.map((kpi) => {
    const row: Record<string, number | string> = { kpi };
    const kpiRow = perKpi.find((k) => k.kpi === kpi);
    if (kpiRow) {
      perPlayer.forEach((p) => {
        row[p.name] = kpiRow.normalized[p.player_id] ?? 0;
      });
    }
    return row;
  });

  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
        <PolarGrid stroke="#444" />
        <PolarAngleAxis
          dataKey="kpi"
          stroke="#888"
          fontSize={10}
        />
        <PolarRadiusAxis
          domain={[0, 1]}
          stroke="#444"
          tickCount={4}
          fontSize={9}
        />
        {perPlayer.map((p, i) => (
          <Radar
            key={p.player_id}
            name={p.name}
            dataKey={p.name}
            stroke={COLORS[i % COLORS.length]}
            fill={COLORS[i % COLORS.length]}
            fillOpacity={0.18}
            strokeWidth={2}
          />
        ))}
        <Tooltip
          contentStyle={{
            background: "#1a1a1a",
            border: "1px solid #444",
            fontSize: "11px",
          }}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}
