"use client";

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from "recharts";

interface CoachingVector {
  press_intensity: number;
  defensive_line: number;
  compactness: number;
  transition_speed: number;
  directness: number;
  tempo: number;
  attacking_third_recovery: number;
  channel_balance: number;
}

export function CoachingIdentityRadar({
  vector,
  archetype,
}: {
  vector: CoachingVector;
  archetype?: string;
}) {
  const data = [
    { axis: "Press", value: vector.press_intensity },
    { axis: "Def Line", value: vector.defensive_line },
    { axis: "Compact", value: vector.compactness },
    { axis: "Trans", value: vector.transition_speed },
    { axis: "Direct", value: vector.directness },
    { axis: "Tempo", value: vector.tempo },
    { axis: "Att Rec", value: vector.attacking_third_recovery },
    { axis: "Channel", value: vector.channel_balance },
  ];
  return (
    <div className="card">
      <h3 className="text-sm uppercase text-muted mb-1">Koç Parmak İzi</h3>
      {archetype && (
        <div className="inline-block mb-2 px-2 py-0.5 rounded bg-accent/20 text-xs uppercase">
          {archetype}
        </div>
      )}
      <ResponsiveContainer width="100%" height={280}>
        <RadarChart data={data}>
          <PolarGrid stroke="#444" />
          <PolarAngleAxis dataKey="axis" tick={{ fontSize: 11, fill: "#bbb" }} />
          <PolarRadiusAxis
            domain={[0, 1]} tickCount={5}
            tick={{ fontSize: 9, fill: "#666" }}
          />
          <Radar
            name="Vector"
            dataKey="value"
            stroke="#3b82f6"
            fill="#3b82f6"
            fillOpacity={0.35}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
