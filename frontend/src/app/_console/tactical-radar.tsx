"use client";

/**
 * Taktik DNA radar görselleştirmesi — lib/tactical-dna çıktısını gösterir:
 * 8 eksenli iki-takım radar (biz/rakip overlay) + stil kimlikleri + en büyük
 * kontrastlar + maç planı. Maç-öncesi taktik hazırlığın görsel merkezi.
 */

import * as React from "react";
import { AXES, type TacticalDNA, type DnaComparison, type MatchPlan } from "@/lib/tactical-dna";

const US = "var(--accent)";    // biz
const THEM = "var(--high)";    // rakip

/** 8 eksenli radar — iki takım overlay (saf SVG). */
export function TacticalRadar({ us, them, size = 300 }: { us: TacticalDNA; them: TacticalDNA; size?: number }) {
  const cx = size / 2, cy = size / 2, R = size / 2 - 46;
  const n = AXES.length;
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;   // tepeden başla
  const pt = (i: number, v: number) => {
    const r = (v / 100) * R;
    return [cx + r * Math.cos(angle(i)), cy + r * Math.sin(angle(i))];
  };
  const poly = (s: TacticalDNA["style"]) =>
    AXES.map((a, i) => pt(i, s[a.key]).map((x) => x.toFixed(1)).join(",")).join(" ");

  return (
    <svg viewBox={`0 0 ${size} ${size}`} width="100%" height={size} style={{ display: "block", maxWidth: size, margin: "0 auto" }}>
      {/* grid halkaları */}
      {[25, 50, 75, 100].map((g) => (
        <polygon key={g}
          points={AXES.map((_, i) => pt(i, g).map((x) => x.toFixed(1)).join(",")).join(" ")}
          fill="none" stroke="var(--line)" strokeWidth={g === 100 ? 1.2 : 0.7} />
      ))}
      {/* eksen çizgileri + etiketler */}
      {AXES.map((a, i) => {
        const [ex, ey] = pt(i, 100);
        const [lx, ly] = pt(i, 122);
        return (
          <g key={a.key}>
            <line x1={cx} y1={cy} x2={ex} y2={ey} stroke="var(--line)" strokeWidth={0.6} />
            <text x={lx} y={ly} fontSize={9.5} fill="var(--muted)" textAnchor={lx > cx + 4 ? "start" : lx < cx - 4 ? "end" : "middle"} dominantBaseline="middle">{a.label}</text>
          </g>
        );
      })}
      {/* rakip (altta) */}
      <polygon points={poly(them.style)} fill={THEM} fillOpacity={0.16} stroke={THEM} strokeWidth={2} />
      {/* biz (üstte) */}
      <polygon points={poly(us.style)} fill={US} fillOpacity={0.16} stroke={US} strokeWidth={2} />
      {/* köşe noktaları */}
      {AXES.map((a, i) => { const [x, y] = pt(i, us.style[a.key]); return <circle key={"u" + i} cx={x} cy={y} r={2.4} fill={US} />; })}
      {AXES.map((a, i) => { const [x, y] = pt(i, them.style[a.key]); return <circle key={"t" + i} cx={x} cy={y} r={2.4} fill={THEM} />; })}
    </svg>
  );
}

/** Tam karşılaştırma gövdesi: kimlikler + radar + kontrastlar + maç planı. */
export function DnaComparisonBody({ comparison }: { comparison: DnaComparison }) {
  const { us, them, contrasts, gamePlan } = comparison;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 18 }}>
      <div>
        {/* kimlik şeridi */}
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 10, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: US }}>{us.name} <span style={{ color: "var(--dim)", fontWeight: 400, fontSize: 11 }}>{us.formation}</span></div>
            <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{us.identity}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: THEM }}>{them.name} <span style={{ color: "var(--dim)", fontWeight: 400, fontSize: 11 }}>{them.formation}</span></div>
            <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{them.identity}</div>
          </div>
        </div>
        <TacticalRadar us={us} them={them} />
        <div style={{ display: "flex", justifyContent: "center", gap: 16, fontSize: 11, marginTop: 4 }}>
          <span style={{ color: US }}>● {us.name}</span>
          <span style={{ color: THEM }}>● {them.name}</span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>En Büyük Stil Farkları</div>
          {contrasts.slice(0, 4).map((c) => (
            <div key={c.axis} style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, marginBottom: 2 }}>
                <span style={{ color: "var(--ink)" }}>{c.axis}</span>
                <span style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}><span style={{ color: US }}>{c.us}</span> – <span style={{ color: THEM }}>{c.them}</span></span>
              </div>
              {/* iki yöne bar: ortadan biz sola/rakip sağa değil — basit: us yeşil, them turuncu yan yana */}
              <div style={{ display: "flex", height: 5, borderRadius: 3, overflow: "hidden", background: "var(--surface2)" }}>
                <div style={{ width: `${c.us / 2}%`, background: US }} />
                <div style={{ width: `${c.them / 2}%`, background: THEM, marginLeft: "auto" }} />
              </div>
              <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 2 }}>{c.note}</div>
            </div>
          ))}
        </div>

        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Bu Stile Karşı Maç Planı</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {gamePlan.map((p, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12, color: "var(--ink)", lineHeight: 1.5 }}>
                <span style={{ color: US, fontWeight: 700, flexShrink: 0 }}>{i + 1}.</span>
                <span>{p}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const SCEN_VAR: Record<string, string> = { "Öndeyiz": "var(--low)", "Berabere": "var(--mid)", "Geride": "var(--crit)" };

/** Önerilen oyun planı — diziliş + ilkeler + pres tetikleri + senaryolar. */
export function MatchPlanBody({ plan }: { plan: MatchPlan }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Diziliş + ilkeler */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Önerilen Diziliş</div>
          <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "JetBrains Mono", color: US, marginBottom: 6 }}>{plan.shape.formation}</div>
          <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{plan.shape.rationale}</div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Anahtar İlkeler</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {plan.principles.map((p, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12, color: "var(--ink)", lineHeight: 1.5 }}>
                <span style={{ color: US, fontWeight: 700, flexShrink: 0 }}>{i + 1}.</span><span>{p}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Pres tetikleri */}
      <div style={{ background: "var(--panel3)", borderRadius: 9, padding: "11px 13px" }}>
        <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Pres Tetikleri</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {plan.pressTriggers.map((t, i) => (
            <div key={i} style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.5 }}><span style={{ color: US }}>▸ </span>{t}</div>
          ))}
        </div>
      </div>

      {/* Senaryolar */}
      <div>
        <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>Durum Senaryoları</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
          {plan.scenarios.map((s) => (
            <div key={s.state} style={{ borderTop: `3px solid ${SCEN_VAR[s.state]}`, background: "var(--panel)", border: "1px solid var(--line)", borderTopWidth: 3, borderTopColor: SCEN_VAR[s.state], borderRadius: 9, padding: "10px 12px" }}>
              <div style={{ fontSize: 12.5, fontWeight: 800, color: SCEN_VAR[s.state], marginBottom: 5 }}>{s.state}</div>
              <div style={{ fontSize: 11.5, color: "var(--ink)", lineHeight: 1.5 }}>{s.plan}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
