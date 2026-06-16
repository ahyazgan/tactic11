"use client";

/**
 * Maç Simülasyonu görselleştirmesi — lib/match-simulation çıktısını (MatchSimulation)
 * render eder: galibiyet/beraberlik/mağlubiyet olasılık barı, beklenen goller (λ),
 * en olası skorlar ve piyasa olasılıkları (üst 2.5 / KG var / clean sheet).
 * Track-record güven rozetiyle birlikte "model ne diyor + geçmişte ne kadar tuttu".
 */

import * as React from "react";
import type { MatchSimulation } from "@/lib/match-simulation";
import { TrustBadge } from "./trust-badge";

const pct = (x: number) => `%${Math.round(x * 100)}`;

/** W/D/L olasılık barı + yüzde lejantı. */
export function OutcomeBar({ sim }: { sim: MatchSimulation }) {
  return (
    <>
      <div className="probbar">
        <i style={{ width: `${sim.probHomeWin * 100}%`, background: "var(--low)" }} />
        <i style={{ width: `${sim.probDraw * 100}%`, background: "var(--dim)" }} />
        <i style={{ width: `${sim.probAwayWin * 100}%`, background: "var(--high)" }} />
      </div>
      <div className="probleg">
        <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>{pct(sim.probHomeWin)}</div><div className="pl">{sim.homeTeam}</div></div>
        <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>{pct(sim.probDraw)}</div><div className="pl">Berabere</div></div>
        <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>{pct(sim.probAwayWin)}</div><div className="pl">{sim.awayTeam}</div></div>
      </div>
    </>
  );
}

/** En olası skorlar — yatay çubuklu liste. */
export function TopScores({ sim }: { sim: MatchSimulation }) {
  const max = sim.topScores[0]?.prob ?? 1;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      {sim.topScores.map((s, i) => {
        const isML = s.home === sim.mostLikelyScore[0] && s.away === sim.mostLikelyScore[1];
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontFamily: "JetBrains Mono", fontSize: 12.5, fontWeight: 700, color: isML ? "var(--ink)" : "var(--muted)", width: 34 }}>
              {s.home}-{s.away}
            </span>
            <span className="mbar" style={{ flex: 1, margin: 0 }}>
              <i style={{ width: `${(s.prob / max) * 100}%`, background: isML ? "var(--accent)" : "color-mix(in srgb, var(--accent) 38%, transparent)" }} />
            </span>
            <span style={{ fontFamily: "JetBrains Mono", fontSize: 11.5, color: "var(--muted)", width: 38, textAlign: "right" }}>{pct(s.prob)}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Piyasa olasılıkları rozetleri (üst 2.5 / KG var / clean sheet). */
export function MarketChips({ sim }: { sim: MatchSimulation }) {
  const chips = [
    { label: "Üst 2.5 gol", v: sim.over25 },
    { label: "KG Var", v: sim.bttsYes },
    { label: `${sim.homeTeam} gol yemez`, v: sim.homeCleanSheet },
  ];
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {chips.map((c) => (
        <div key={c.label} style={{ flex: "1 1 100px", background: "var(--panel3)", borderRadius: 7, padding: "7px 10px" }}>
          <div style={{ fontFamily: "JetBrains Mono", fontSize: 15, fontWeight: 800, color: "var(--ink)" }}>{pct(c.v)}</div>
          <div style={{ fontSize: 10.5, color: "var(--dim)" }}>{c.label}</div>
        </div>
      ))}
    </div>
  );
}

/** Tam simülasyon gövdesi (kart sarmalayıcısını çağıran sağlar). */
export function MatchSimBody({ sim }: { sim: MatchSimulation }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div>
        <OutcomeBar sim={sim} />
        <div style={{ display: "flex", justifyContent: "center", gap: 16, marginTop: 8, fontFamily: "JetBrains Mono", fontSize: 11.5, color: "var(--muted)" }}>
          <span>beklenen gol <b style={{ color: "var(--ink)" }}>{sim.lambdaHome.toFixed(2)}</b> – <b style={{ color: "var(--ink)" }}>{sim.lambdaAway.toFixed(2)}</b></span>
          <span>en olası <b style={{ color: "var(--accent)" }}>{sim.mostLikelyScore[0]}-{sim.mostLikelyScore[1]}</b> ({pct(sim.mostLikelyScoreProb)})</span>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16 }}>
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>En olası skorlar</div>
          <TopScores sim={sim} />
        </div>
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Piyasa olasılıkları</div>
          <MarketChips sim={sim} />
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <TrustBadge note="demo güçler · gerçek veride senin ligin" />
        <span style={{ fontSize: 10.5, color: "var(--dim)", fontStyle: "italic" }}>
          Poisson · Dixon-Coles (ρ {sim.rho}) · takım sezon xG güçlerinden · lig ort. {sim.leagueAvgXg} gol/maç
        </span>
      </div>
    </div>
  );
}
