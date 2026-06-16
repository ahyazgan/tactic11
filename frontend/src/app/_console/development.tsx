"use client";

/**
 * Gelişim Projeksiyonu görselleştirmesi — lib/player-development çıktısını render eder:
 * yaş-tabanlı kariyer arkı (overall + grup eğrileri), şimdi/tavan/zirve işaretleri,
 * +18 ay grup projeksiyonu ve scout/transfer reçetesi.
 */

import * as React from "react";
import {
  PHASE_LABEL, PHASE_VAR, type PlayerDevelopment, type DevTrend,
} from "@/lib/player-development";

const attrVar = (v: number) => v >= 16 ? "var(--low)" : v >= 12 ? "var(--accent)" : v >= 8 ? "var(--mid)" : "var(--dim)";

/** Yaş-overall kariyer arkı + şimdi/zirve işaretleri (saf SVG). */
function CareerArc({ dev }: { dev: PlayerDevelopment }) {
  const w = 560, h = 168, padL = 28, padR = 12, padT = 14, padB = 24;
  const ages = dev.trajectory.map((p) => p.age);
  const aMin = ages[0], aMax = ages[ages.length - 1];
  const vals = dev.trajectory.flatMap((p) => [p.overall, p.physical, p.technical, p.mental]).filter((v) => v > 0);
  const yMin = Math.floor(Math.min(...vals) - 0.5), yMax = Math.ceil(Math.max(...vals, dev.potential) + 0.5);
  const x = (a: number) => padL + ((a - aMin) / (aMax - aMin)) * (w - padL - padR);
  const y = (v: number) => h - padB - ((v - yMin) / (yMax - yMin)) * (h - padT - padB);
  const line = (key: "overall" | "physical" | "technical" | "mental") =>
    dev.trajectory.filter((p) => p[key] > 0).map((p, i) => `${i ? "L" : "M"} ${x(p.age).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(" ");

  const nowPt = dev.trajectory.find((p) => p.age === dev.currentAge) ?? dev.trajectory[0];
  const peakPt = dev.trajectory.find((p) => p.age === dev.peakAge);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} style={{ display: "block" }}>
      {/* y gridleri */}
      {[yMin, Math.round((yMin + yMax) / 2), yMax].map((g, i) => (
        <g key={i}>
          <line x1={padL} y1={y(g)} x2={w - padR} y2={y(g)} stroke="var(--line)" strokeWidth={1} />
          <text x={4} y={y(g) + 3} fontSize={9} fill="var(--dim)" fontFamily="JetBrains Mono">{g}</text>
        </g>
      ))}
      {/* x ekseni yaşları */}
      {[aMin, dev.currentAge, dev.peakAge, aMax].filter((v, i, a) => a.indexOf(v) === i).map((a) => (
        <text key={a} x={x(a)} y={h - 7} fontSize={9} fill="var(--dim)" textAnchor="middle" fontFamily="JetBrains Mono">{a}</text>
      ))}
      {/* tavan referans çizgisi */}
      <line x1={padL} y1={y(dev.potential)} x2={w - padR} y2={y(dev.potential)} stroke="var(--low)" strokeWidth={1} strokeDasharray="3 3" opacity={0.5} />
      {/* şimdiki yaş dikey */}
      <line x1={x(dev.currentAge)} y1={padT} x2={x(dev.currentAge)} y2={h - padB} stroke="var(--accent)" strokeWidth={1} strokeDasharray="2 3" opacity={0.6} />
      {/* grup eğrileri (soluk) */}
      <path d={line("physical")} fill="none" stroke="var(--high)" strokeWidth={1.3} opacity={0.4} />
      <path d={line("technical")} fill="none" stroke="var(--mid)" strokeWidth={1.3} opacity={0.4} />
      <path d={line("mental")} fill="none" stroke="var(--accent)" strokeWidth={1.3} opacity={0.4} />
      {/* overall (belirgin) */}
      <path d={line("overall")} fill="none" stroke="var(--ink)" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      {/* zirve işareti */}
      {peakPt && <circle cx={x(peakPt.age)} cy={y(peakPt.overall)} r={4} fill="none" stroke="var(--low)" strokeWidth={2} />}
      {/* şimdiki nokta */}
      <circle cx={x(nowPt.age)} cy={y(nowPt.overall)} r={3.5} fill="var(--accent)" />
    </svg>
  );
}

function TrendGlyph({ trend }: { trend: DevTrend }) {
  const m: Record<DevTrend, { g: string; c: string }> = {
    rising: { g: "▲ yükseliyor", c: "var(--low)" },
    stable: { g: "▬ stabil", c: "var(--muted)" },
    declining: { g: "▼ geriliyor", c: "var(--high)" },
  };
  return <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: m[trend].c }}>{m[trend].g}</span>;
}

export function DevelopmentBody({ dev }: { dev: PlayerDevelopment }) {
  const gap = Math.round((dev.potential - dev.currentOverall) * 10) / 10;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Üst şerit: faz + metrikler */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
        <span className="risk" style={{ color: PHASE_VAR[dev.phase], fontSize: 12 }}>
          <span className="rd" style={{ background: PHASE_VAR[dev.phase] }} />{PHASE_LABEL[dev.phase]}
        </span>
        <TrendGlyph trend={dev.trend} />
        <div style={{ display: "flex", gap: 18, marginLeft: "auto", fontSize: 12 }}>
          <span style={{ color: "var(--muted)" }}>Mevcut <b style={{ fontFamily: "JetBrains Mono", color: attrVar(dev.currentOverall) }}>{dev.currentOverall.toFixed(1)}</b></span>
          <span style={{ color: "var(--muted)" }}>Tavan <b style={{ fontFamily: "JetBrains Mono", color: "var(--low)" }}>{dev.potential.toFixed(1)}</b>{gap > 0.1 ? <span style={{ color: "var(--low)", fontSize: 10.5 }}> (+{gap.toFixed(1)})</span> : null}</span>
          <span style={{ color: "var(--muted)" }}>Zirve <b style={{ fontFamily: "JetBrains Mono", color: "var(--ink)" }}>{dev.peakAge}</b> yaş</span>
          <span style={{ color: "var(--muted)" }}>Güven <b style={{ fontFamily: "JetBrains Mono", color: "var(--ink)" }}>%{dev.confidence}</b></span>
        </div>
      </div>

      {/* Kariyer arkı */}
      <CareerArc dev={dev} />
      <div style={{ display: "flex", gap: 14, fontSize: 10.5, color: "var(--dim)", flexWrap: "wrap" }}>
        <span style={{ color: "var(--ink)" }}>━ Genel</span>
        <span style={{ color: "var(--high)" }}>━ Fiziksel</span>
        <span style={{ color: "var(--mid)" }}>━ Teknik</span>
        <span style={{ color: "var(--accent)" }}>━ Zihinsel</span>
        <span style={{ marginLeft: "auto" }}>● şimdi · ○ zirve · ┈ tavan</span>
      </div>

      {/* +18 ay grup projeksiyonu */}
      <div>
        <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>+18 ay projeksiyonu</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
          {dev.groups.map((g) => {
            const up = g.delta > 0.05, down = g.delta < -0.05;
            const c = up ? "var(--low)" : down ? "var(--high)" : "var(--muted)";
            return (
              <div key={g.group} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: "var(--muted)" }}>{g.group}</span>
                <span style={{ fontFamily: "JetBrains Mono" }}>
                  {g.now.toFixed(1)} <span style={{ color: c }}>→ {g.future.toFixed(1)} {up ? "▲" : down ? "▼" : "▬"}{Math.abs(g.delta) >= 0.05 ? ` ${Math.abs(g.delta).toFixed(1)}` : ""}</span>
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Reçete */}
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start", background: "var(--panel3)", borderRadius: 7, padding: "9px 11px" }}>
        <span style={{ width: 4, alignSelf: "stretch", borderRadius: 2, background: PHASE_VAR[dev.phase], flexShrink: 0 }} />
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 2 }}>Scout / Transfer reçetesi</div>
          <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.5 }}>{dev.verdict}</div>
        </div>
      </div>
    </div>
  );
}
