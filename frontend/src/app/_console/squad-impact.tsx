"use client";

/**
 * KADRO ETKİSİ (client) — gerçek lineup'tan öğrenilen oyuncu değerleriyle
 * "şu oyuncular yoksa tahmin nasıl değişir" interaktif paneli. Veri sunucuda
 * hesaplanıp prop geçer (ağır JSON bundle'a girmez). Tahmin yeniden-hesabı
 * client'ta saf matematikle (poisson-predict) yapılır — anında.
 */

import React from "react";
import { predictFromLambda, clamp } from "@/lib/poisson-predict";

export interface SquadPlayer { id: number; name: string; value: number; apps: number; pos?: string }
const POS_COLOR: Record<string, string> = { GK: "var(--dim)", DEF: "var(--low)", MID: "var(--mid)", ATT: "var(--high)" };
const posTag = (p: string) => ({ fontSize: 9, fontWeight: 800, letterSpacing: 0.3, color: "#fff", background: POS_COLOR[p] ?? "var(--dim)", borderRadius: 3, padding: "1px 5px", flexShrink: 0 } as const);
export interface TeamSquadData {
  name: string; comp: string;
  atk: number; def: number;        // öğrenilen güç
  keyPlayers: SquadPlayer[];
}
export interface SquadImpactData {
  muH: number; muA: number; rho: number; beta: number;
  teams: TeamSquadData[];
  trust: number;
  timing?: number[];   // GERÇEK gol-zamanlaması eğrisi (fracAfter[dakika]) — maç-içi motor
  confTrack?: { level: "yüksek" | "orta" | "düşük"; n: number; hitRate: number; avgClaim: number }[];
}

const surname = (n: string) => n.split(" ").slice(-1)[0];

export interface MatchControl { hi: number; ai: number; onHome: (i: number) => void; onAway: (i: number) => void }

export function SquadImpact({ data, control }: { data: SquadImpactData; control?: MatchControl }) {
  const teams = data.teams;
  const [iHi, setHi] = React.useState(0);
  const [iAi, setAi] = React.useState(1);
  const [outH, setOutH] = React.useState<Set<number>>(new Set());
  const [outA, setOutA] = React.useState<Set<number>>(new Set());
  const hi = control ? control.hi : iHi, ai = control ? control.ai : iAi;

  const home = teams[hi], away = teams[ai];
  const onHome = control ? control.onHome : (i: number) => { setHi(i); setOutH(new Set()); if (i === ai) { const j = (i + 1) % teams.length; setAi(j); setOutA(new Set()); } };
  const onAway = control ? control.onAway : (i: number) => { setAi(i); setOutA(new Set()); if (i === hi) { const j = (i + 1) % teams.length; setHi(j); setOutH(new Set()); } };
  // Kontrollü modda takım değişince eksik-kadro seçimini sıfırla.
  React.useEffect(() => { setOutH(new Set()); setOutA(new Set()); }, [hi, ai]);

  const toggle = (set: Set<number>, setSet: (s: Set<number>) => void, id: number) => {
    const n = new Set(set); n.has(id) ? n.delete(id) : n.add(id); setSet(n);
  };

  // bump = β·((−evDüşüş) − (−depDüşüş)); düşüş = eksik oyuncuların değer toplamı / 11
  const dropOf = (team: TeamSquadData, out: Set<number>) =>
    [...out].reduce((s, id) => s + (team.keyPlayers.find((p) => p.id === id)?.value ?? 0), 0) / 11;

  const predOf = (oh: Set<number>, oa: Set<number>) => {
    const hDrop = dropOf(home, oh), aDrop = dropOf(away, oa);
    const bump = data.beta * ((-hDrop) - (-aDrop));
    const lH = clamp(Math.exp(data.muH + home.atk - away.def + bump), 0.05, 7);
    const lA = clamp(Math.exp(data.muA + away.atk - home.def - bump), 0.05, 7);
    return predictFromLambda(lH, lA, data.rho);
  };

  const full = predOf(new Set(), new Set());
  const now = predOf(outH, outA);
  const dH = Math.round((now.pH - full.pH) * 100);
  const dD = Math.round((now.pD - full.pD) * 100);
  const dA = Math.round((now.pA - full.pA) * 100);
  const anyOut = outH.size + outA.size > 0;

  const sel = { padding: "7px 10px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontSize: 12.5, fontWeight: 600 } as const;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* lig + takım seçimi — kontrollü modda Maç Merkezi gösterir */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {!control && <>
          <select value={hi} onChange={(e) => onHome(Number(e.target.value))} style={sel}>
            {teams.map((t, i) => <option key={t.name} value={i} disabled={i === ai}>{t.name}</option>)}
          </select>
          <span style={{ color: "var(--dim)", fontSize: 12, fontWeight: 700 }}>(ev) vs</span>
          <select value={ai} onChange={(e) => onAway(Number(e.target.value))} style={sel}>
            {teams.map((t, i) => <option key={t.name} value={i} disabled={i === hi}>{t.name}</option>)}
          </select>
          <span style={{ color: "var(--dim)", fontSize: 12, fontWeight: 700 }}>(dep)</span>
        </>}
        {anyOut && (
          <button onClick={() => { setOutH(new Set()); setOutA(new Set()); }}
            style={{ marginLeft: "auto", ...sel, cursor: "pointer", color: "var(--accent)", borderColor: "var(--accent)" }}>
            ↺ Tam kadroya dön
          </button>
        )}
      </div>

      {/* sonuç barı — tam kadro vs şimdi */}
      <div style={{ borderRadius: 10, border: "1px solid var(--line)", padding: 14, background: "var(--panel)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>
          <span>{anyOut ? "Eksik kadroyla tahmin" : "Tam kadro tahmini"}</span>
          <span style={{ fontFamily: "JetBrains Mono" }}>beklenen skor {now.lH.toFixed(1)}–{now.lA.toFixed(1)}</span>
        </div>
        <div style={{ display: "flex", height: 26, borderRadius: 6, overflow: "hidden", border: "1px solid var(--line)" }}>
          <span style={{ width: `${now.pH * 100}%`, background: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 11, fontWeight: 800 }}>{Math.round(now.pH * 100)}%</span>
          <span style={{ width: `${now.pD * 100}%`, background: "var(--dim)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 10 }}>{Math.round(now.pD * 100)}%</span>
          <span style={{ width: `${now.pA * 100}%`, background: "var(--high)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 11, fontWeight: 800 }}>{Math.round(now.pA * 100)}%</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginTop: 5 }}>
          <span style={{ fontWeight: 700 }}>{surname(home.name)} {delta(dH)}</span>
          <span style={{ color: "var(--dim)" }}>X {delta(dD)}</span>
          <span style={{ fontWeight: 700 }}>{surname(away.name)} {delta(dA)}</span>
        </div>
        {anyOut && (
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.5, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
            Tam kadroya göre değişim: {home.name} galibiyeti <b style={{ color: dH < 0 ? "var(--high)" : "var(--low)" }}>{delta(dH)}</b>.
            Çıkardığın oyuncuların gerçek sonuçlardan öğrenilen değeri yüksekse etki büyür.
          </div>
        )}
      </div>

      {/* iki takım kilit oyuncu listesi */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
        {[{ t: home, out: outH, set: setOutH, color: "var(--accent)" }, { t: away, out: outA, set: setOutA, color: "var(--high)" }].map(({ t, out, set, color }) => (
          <div key={t.name}>
            <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 6, color }}>{t.name} · kilit oyuncular</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {t.keyPlayers.slice(0, 10).map((p) => {
                const isOut = out.has(p.id);
                return (
                  <button key={p.id} onClick={() => toggle(out, set, p.id)}
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 9px", borderRadius: 7, cursor: "pointer", textAlign: "left",
                      border: `1px solid ${isOut ? "var(--high)" : "var(--line)"}`,
                      background: isOut ? "color-mix(in srgb, var(--high) 12%, var(--panel))" : "var(--panel)",
                      opacity: isOut ? 0.7 : 1, textDecoration: isOut ? "line-through" : "none" }}>
                    {p.pos && <span style={{ ...posTag(p.pos) }}>{p.pos}</span>}
                    <span style={{ fontSize: 12, fontWeight: 600, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</span>
                    <span style={{ fontFamily: "JetBrains Mono", fontSize: 10.5, color: p.value > 0 ? "var(--low)" : "var(--dim)" }}>{p.value > 0 ? "+" : ""}{p.value.toFixed(2)}</span>
                    <span style={{ fontSize: 9.5, color: isOut ? "var(--high)" : "var(--dim)", fontWeight: 700, width: 36, textAlign: "right" }}>{isOut ? "YOK" : "oynar"}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div style={{ fontSize: 10.5, color: "var(--dim)", lineHeight: 1.5 }}>
        Oyuncuya tıkla → o maçta <b>yok</b> say. Değer (+/−) = gerçek sonuçlardan öğrenilen takıma net katkı (yüksek = kilit). Bu, Süper Lig&apos;de
        sakat/cezalı yıldız çıkınca tahminin kendiliğinden düzelmesinin önizlemesi — uydurma değil, doğrulanmış kadro sinyali.
      </div>
    </div>
  );
}

function delta(d: number) {
  if (d === 0) return <span style={{ color: "var(--dim)" }}>±0</span>;
  return <span style={{ color: d > 0 ? "var(--low)" : "var(--high)" }}>{d > 0 ? "+" : ""}{d} puan</span>;
}
