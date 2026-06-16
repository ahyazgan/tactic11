"use client";

/**
 * Canlı Kazanma Olasılığı görselleştirmesi — lib/live-win-probability çıktısını
 * render eder: dakikaya göre yığılmış alan eğrisi (ev/berabere/deplasman, %100'e
 * tümler) + gol işaretleri + şu-an çizgisi, ve anlık W/D/L barı.
 */

import * as React from "react";
import type { WinProb } from "@/lib/live-win-probability";

const HOME = "var(--accent)";   // biz
const DRAW = "var(--dim)";
const AWAY = "var(--high)";     // rakip

/** Yığılmış alan win-prob eğrisi (saf SVG). goals = gol dakikaları. */
export function WinProbChart({ curve, goals }: {
  curve: WinProb[]; goals: { minute: number; team: "home" | "away" }[];
}) {
  const w = 560, h = 150, padL = 4, padR = 4, padT = 8, padB = 18;
  const maxMin = 90;
  const x = (m: number) => padL + (m / maxMin) * (w - padL - padR);
  const y = (v: number) => padT + (1 - v) * (h - padT - padB);

  // Bir bandın kapalı path'i: üst kenar (soldan sağa) + alt kenar (sağdan sola).
  const band = (topOf: (p: WinProb) => number, botOf: (p: WinProb) => number) => {
    const top = curve.map((p) => `${x(p.minute).toFixed(1)} ${y(topOf(p)).toFixed(1)}`);
    const bot = [...curve].reverse().map((p) => `${x(p.minute).toFixed(1)} ${y(botOf(p)).toFixed(1)}`);
    return `M ${top.join(" L ")} L ${bot.join(" L ")} Z`;
  };

  const pHomeTop = (p: WinProb) => p.pHome;
  const pDrawTop = (p: WinProb) => p.pHome + p.pDraw;

  const last = curve[curve.length - 1];

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} style={{ display: "block" }}>
      {/* bantlar: ev (alt) / berabere (orta) / deplasman (üst) */}
      <path d={band(pHomeTop, () => 0)} fill={HOME} opacity={0.85} />
      <path d={band(pDrawTop, pHomeTop)} fill={DRAW} opacity={0.55} />
      <path d={band(() => 1, pDrawTop)} fill={AWAY} opacity={0.7} />
      {/* %50 referans */}
      <line x1={padL} y1={y(0.5)} x2={w - padR} y2={y(0.5)} stroke="var(--ink)" strokeWidth={0.7} strokeDasharray="2 3" opacity={0.35} />
      {/* gol işaretleri */}
      {goals.map((g, i) => (
        <g key={i}>
          <line x1={x(g.minute)} y1={padT} x2={x(g.minute)} y2={h - padB} stroke="var(--ink)" strokeWidth={1.2} strokeDasharray="3 2" opacity={0.8} />
          <text x={x(g.minute)} y={padT + 8} fontSize={9} fill="var(--ink)" textAnchor="middle">⚽</text>
        </g>
      ))}
      {/* şu an çizgisi */}
      <line x1={x(last.minute)} y1={padT} x2={x(last.minute)} y2={h - padB} stroke="var(--ink)" strokeWidth={1.5} />
      {/* dakika ekseni */}
      {[0, 15, 30, 45, 60, 75, 90].map((m) => (
        <text key={m} x={x(m)} y={h - 5} fontSize={9} fill="var(--dim)" textAnchor="middle" fontFamily="JetBrains Mono">{m}&apos;</text>
      ))}
    </svg>
  );
}

const pct = (x: number) => `%${Math.round(x * 100)}`;

/** Anlık W/D/L barı + tam gövde (eğri + lejant). */
export function WinProbBody({ curve, now, homeName, awayName, goals }: {
  curve: WinProb[]; now: WinProb; homeName: string; awayName: string; goals: { minute: number; team: "home" | "away" }[];
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 16, color: "var(--ink)" }}>{now.minute}&apos;</span>
        <span style={{ fontFamily: "JetBrains Mono", fontSize: 14, color: "var(--ink)" }}>{now.scoreHome}-{now.scoreAway}</span>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>kalan beklenen gol {now.lambdaHomeRem.toFixed(2)}–{now.lambdaAwayRem.toFixed(2)}</span>
      </div>
      {/* anlık bar */}
      <div className="probbar">
        <i style={{ width: `${now.pHome * 100}%`, background: HOME }} />
        <i style={{ width: `${now.pDraw * 100}%`, background: DRAW }} />
        <i style={{ width: `${now.pAway * 100}%`, background: AWAY }} />
      </div>
      <div className="probleg">
        <div className="pi"><div className="pv" style={{ color: HOME }}>{pct(now.pHome)}</div><div className="pl">{homeName}</div></div>
        <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>{pct(now.pDraw)}</div><div className="pl">Berabere</div></div>
        <div className="pi"><div className="pv" style={{ color: AWAY }}>{pct(now.pAway)}</div><div className="pl">{awayName}</div></div>
      </div>
      {/* eğri */}
      <WinProbChart curve={curve} goals={goals} />
      <div style={{ fontSize: 10.5, color: "var(--dim)" }}>
        Mevcut skor + kalan süre + canlı xG temposundan Poisson modeli. Gol anlarında sıçrar; süre azaldıkça mevcut sonuca yakınsar.
      </div>
    </div>
  );
}
