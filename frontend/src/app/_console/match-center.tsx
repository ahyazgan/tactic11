"use client";

/**
 * MAÇ MERKEZİ (client) — antrenörün tek akıcı akışı: maç seç → maç-öncesi brifing
 * / kadro kararı → ⚽ başla → canlı karar. Dağınık üç paneli (MatchBrief, SquadImpact,
 * LiveMatch) TEK paylaşımlı maç seçimiyle sarmalar; her panel kendi seçicisini
 * gizler (control prop). Maç değişince hepsi senkron. Veri sunucudan prop (yeni yük yok).
 */

import React from "react";
import { MatchBrief, type DecisionData } from "./match-brief";
import { SquadImpact, type SquadImpactData } from "./squad-impact";
import { LiveMatch } from "./live-match";

const surname = (n: string) => n.split(" ").slice(-1)[0];

type Phase = "brief" | "squad" | "live";

export function MatchCenter({ impact, decision }: { impact: SquadImpactData; decision: DecisionData }) {
  const teams = impact.teams;
  const [hi, setHi] = React.useState(0);
  const [ai, setAi] = React.useState(1);
  const [phase, setPhase] = React.useState<Phase>("brief");

  const onHome = (i: number) => { setHi(i); if (i === ai) setAi((i + 1) % teams.length); };
  const onAway = (i: number) => { setAi(i); if (i === hi) setHi((i + 1) % teams.length); };
  const swap = () => { const h = hi; setHi(ai); setAi(h); };
  const control = { hi, ai, onHome, onAway };

  const home = teams[hi], away = teams[ai];
  const sel = { padding: "8px 11px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontSize: 13.5, fontWeight: 700 } as const;

  const tab = (p: Phase, label: string, sub: string, color: string) => {
    const on = phase === p;
    return (
      <button onClick={() => setPhase(p)} style={{
        flex: 1, minWidth: 130, textAlign: "left", cursor: "pointer", padding: "10px 13px", borderRadius: 10,
        border: `1px solid ${on ? color : "var(--line)"}`,
        background: on ? `color-mix(in srgb, ${color} 12%, var(--panel))` : "var(--panel)",
      }}>
        <div style={{ fontSize: 13, fontWeight: 800, color: on ? color : "var(--ink)" }}>{label}</div>
        <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 2 }}>{sub}</div>
      </button>
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ŞIK MAÇ SEÇİCİ — tek yer, tüm akış buna bağlı */}
      <div style={{ borderRadius: 12, border: "1px solid var(--line)", padding: 16, background: "color-mix(in srgb, var(--accent) 4%, var(--panel))" }}>
        <div style={{ fontSize: 10.5, color: "var(--muted)", fontWeight: 700, letterSpacing: 0.5, marginBottom: 8 }}>MAÇI SEÇ</div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <select value={hi} onChange={(e) => onHome(Number(e.target.value))} style={{ ...sel, flex: 1, minWidth: 150 }}>
            {teams.map((t, i) => <option key={t.name} value={i} disabled={i === ai}>{t.name}</option>)}
          </select>
          <button onClick={swap} title="ev/dep değiştir" style={{ ...sel, cursor: "pointer", padding: "8px 12px", color: "var(--accent)", borderColor: "var(--accent)" }}>⇄</button>
          <select value={ai} onChange={(e) => onAway(Number(e.target.value))} style={{ ...sel, flex: 1, minWidth: 150 }}>
            {teams.map((t, i) => <option key={t.name} value={i} disabled={i === hi}>{t.name}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginTop: 10, fontSize: 14, fontWeight: 800 }}>
          <span style={{ color: "var(--accent)" }}>{surname(home.name)}</span>
          <span style={{ color: "var(--dim)", fontSize: 11, fontWeight: 600 }}>(ev)</span>
          <span style={{ color: "var(--dim)" }}>vs</span>
          <span style={{ color: "var(--dim)", fontSize: 11, fontWeight: 600 }}>(dep)</span>
          <span style={{ color: "var(--high)" }}>{surname(away.name)}</span>
        </div>
      </div>

      {/* AKIŞ ADIMLARI — maç öncesi (brifing/kadro) → canlı */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {tab("brief", "1 · Brifing", "güven · tehdit · maç tipi", "var(--low)")}
        {tab("squad", "2 · Kadro Kararı", "kim yoksa ne olur", "var(--accent)")}
        {tab("live", "⚽ Canlı Karar", "dakika · skor · hamle", "var(--high)")}
      </div>

      {/* SEÇİLİ FAZ İÇERİĞİ */}
      <div className="rc" style={{ margin: 0 }}>
        {phase === "brief" && <MatchBrief impact={impact} decision={decision} control={control} />}
        {phase === "squad" && <SquadImpact data={impact} control={control} />}
        {phase === "live" && <LiveMatch data={impact} control={control} />}
      </div>

      {phase !== "live" && (
        <button onClick={() => setPhase("live")} style={{
          alignSelf: "center", cursor: "pointer", padding: "11px 22px", borderRadius: 10, fontSize: 13.5, fontWeight: 800,
          border: "1px solid var(--high)", color: "#fff", background: "var(--high)",
        }}>
          ⚽ Maç başladı → Canlı Karar&apos;a geç
        </button>
      )}
    </div>
  );
}
