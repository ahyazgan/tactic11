"use client";

/**
 * MAÇ-ÖNCESİ KARAR PANELİ (client) — bir maç seç, antrenör için gerçek-veri brifingi:
 *  #5 maç güveni (tahmine ne kadar yaslan), #4 iki takımın kilit oyuncuları (markaj),
 *  #8 ev/dep avantajı, #7 kadro kırılganlığı, #10 sürpriz-11 (rakip rotasyon yaptı mı).
 * Hepsi gerçek öğrenilen değerlerden — uydurma yok. Tahmin client'ta saf matematikle.
 */

import React from "react";
import { predictFromLambda, clamp } from "@/lib/poisson-predict";
import type { SquadImpactData, TeamSquadData } from "./squad-impact";

export interface DecisionTeam {
  name: string;
  fragility: { level: "kırılgan" | "dengeli" | "dağınık"; topShare: number; drop3: number; keyPlayers: { id: number; name: string; value: number; apps: number }[] };
  surprise: { rotated: boolean; delta: number; note: string; lastValue: number; expectedValue: number };
  split: { homeGD: number; awayGD: number; homeN: number; awayN: number };
  threats: { id: number; name: string; value: number; apps: number; pos?: string }[];
  pairs: { a: string; b: string; together: number; gdWith: number }[];
  gameState: { startTag: string; finishTag: string; lateLeak: boolean; htLeadHoldPct: number; htBehindRecoverPct: number; htLeadGames: number; htBehindGames: number };
  style: { poss: number | null; corners: number | null; tag: string };
  formation: { top: string | null; topPct: number; dist: [string, number][]; home: string | null; away: string | null; varied: boolean; venueShift: boolean };
}
export interface DecisionData { comp: string; teams: DecisionTeam[] }
/** Kontrollü seçim (Maç Merkezi paylaşımlı maç state'i geçince kullanılır). */
export interface MatchControl { hi: number; ai: number; onHome: (i: number) => void; onAway: (i: number) => void }

const surname = (n: string) => n.split(" ").slice(-1)[0];

// Mevki rozeti rengi: GK gri · DEF mavi-yeşil · MID amber · ATT kırmızı.
const POS_COLOR: Record<string, string> = { GK: "var(--dim)", DEF: "var(--low)", MID: "var(--mid)", ATT: "var(--high)" };
const posTag = (p: string) => ({ fontSize: 9, fontWeight: 800, letterSpacing: 0.3, color: "#fff", background: POS_COLOR[p] ?? "var(--dim)", borderRadius: 3, padding: "1px 5px", flexShrink: 0 } as const);

export function MatchBrief({ impact, decision, control }: { impact: SquadImpactData; decision: DecisionData; control?: MatchControl }) {
  const teams = impact.teams;
  const [iHi, setHi] = React.useState(0);
  const [iAi, setAi] = React.useState(1);
  const hi = control ? control.hi : iHi, ai = control ? control.ai : iAi;
  const home = teams[hi], away = teams[ai];
  const onHome = control ? control.onHome : (i: number) => { setHi(i); if (i === ai) setAi((i + 1) % teams.length); };
  const onAway = control ? control.onAway : (i: number) => { setAi(i); if (i === hi) setHi((i + 1) % teams.length); };

  const dec = (name: string) => decision.teams.find((t) => t.name === name);
  const decH = dec(home.name), decA = dec(away.name);

  // tahmin (kadro bump yok — maç-öncesi tam kadro varsayımı)
  const predOf = (h: TeamSquadData, a: TeamSquadData) => {
    const lH = clamp(Math.exp(impact.muH + h.atk - a.def), 0.05, 7);
    const lA = clamp(Math.exp(impact.muA + a.atk - h.def), 0.05, 7);
    return predictFromLambda(lH, lA, impact.rho);
  };
  const pr = predOf(home, away);
  const probs: [string, number][] = [["1", pr.pH], ["X", pr.pD], ["2", pr.pA]];
  probs.sort((x, y) => y[1] - x[1]);
  const gap = probs[0][1] - probs[1][1];
  // #5 maç güveni: favori açıklığı × lig skill (impact.trust 0..100 → faktör)
  const ligFactor = clamp(0.4 + (impact.trust / 100) * 0.8, 0.4, 1);
  const cScore = clamp(gap * 1.6, 0, 1) * ligFactor;
  const cLevel = cScore >= 0.55 ? "yüksek" : cScore >= 0.3 ? "orta" : "düşük";
  const cColor = cLevel === "yüksek" ? "var(--low)" : cLevel === "düşük" ? "var(--high)" : "var(--mid)";
  const cReason = cLevel === "yüksek" ? "Favori net + lig tahmin edilebilir — tahmine yaslanabilirsin."
    : cLevel === "düşük" ? "İki takım denk / lig dengeli — sürpriz riski yüksek, temkinli ol."
    : "Orta belirginlik — tahmin yol gösterir ama kesin değil.";

  // B — maç-tipi parmak izi (motorun over/btts'i, gerçek kalibre)
  const goalType = pr.over >= 0.58 ? "BOL GOLLÜ" : pr.over <= 0.45 ? "AZ GOLLÜ" : "DENGELİ";
  const goalColor = pr.over >= 0.58 ? "var(--high)" : pr.over <= 0.45 ? "var(--accent)" : "var(--mid)";
  const goalNote = goalType === "BOL GOLLÜ" ? "Açık geçmesi beklenir — kontra riski yüksek, savunma dengesi önemli."
    : goalType === "AZ GOLLÜ" ? "Kapalı/düşük tempo beklenir — tek gol ve duran top belirleyici."
    : "Orta tempo — duruma göre açılır.";

  const sel = { padding: "7px 10px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontSize: 12.5, fontWeight: 600 } as const;
  const fragColor = (l: string) => l === "kırılgan" ? "var(--high)" : l === "dağınık" ? "var(--low)" : "var(--mid)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* maç seçimi — kontrollü modda Maç Merkezi gösterir, burada gizli */}
      {!control && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <select value={hi} onChange={(e) => onHome(Number(e.target.value))} style={sel}>
            {teams.map((t, i) => <option key={t.name} value={i} disabled={i === ai}>{t.name}</option>)}
          </select>
          <span style={{ color: "var(--dim)", fontSize: 12, fontWeight: 700 }}>(ev) vs</span>
          <select value={ai} onChange={(e) => onAway(Number(e.target.value))} style={sel}>
            {teams.map((t, i) => <option key={t.name} value={i} disabled={i === hi}>{t.name}</option>)}
          </select>
          <span style={{ color: "var(--dim)", fontSize: 12, fontWeight: 700 }}>(dep)</span>
        </div>
      )}

      {/* #5 — maç güveni etiketi + tahmin barı */}
      <div style={{ borderRadius: 10, border: `1px solid ${cColor}`, padding: 14, background: `color-mix(in srgb, ${cColor} 6%, var(--panel))` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
          <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.5, color: "#fff", background: cColor, borderRadius: 4, padding: "2px 9px" }}>{cLevel.toUpperCase()} GÜVEN</span>
          <span style={{ fontSize: 12.5, color: "var(--ink)" }}>{cReason}</span>
          <span style={{ marginLeft: "auto", fontFamily: "JetBrains Mono", fontWeight: 800, color: cColor }}>{probs[0][0]} %{Math.round(probs[0][1] * 100)}</span>
        </div>
        <div style={{ display: "flex", height: 22, borderRadius: 6, overflow: "hidden", border: "1px solid var(--line)" }}>
          <span style={{ width: `${pr.pH * 100}%`, background: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 10, fontWeight: 800 }}>{Math.round(pr.pH * 100)}</span>
          <span style={{ width: `${pr.pD * 100}%`, background: "var(--dim)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 9 }}>{Math.round(pr.pD * 100)}</span>
          <span style={{ width: `${pr.pA * 100}%`, background: "var(--high)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 10, fontWeight: 800 }}>{Math.round(pr.pA * 100)}</span>
        </div>
        <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 5, fontFamily: "JetBrains Mono" }}>beklenen skor {pr.lH.toFixed(1)}–{pr.lA.toFixed(1)} · en olası {pr.top[0]?.score}</div>
      </div>

      {/* B — maç-tipi parmak izi (gol karakteri) */}
      <div style={{ borderRadius: 10, border: "1px solid var(--line)", padding: 14, background: "var(--panel)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
          <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700 }}>MAÇ TİPİ</span>
          <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.5, color: "#fff", background: goalColor, borderRadius: 4, padding: "2px 9px" }}>{goalType}</span>
          <span style={{ fontSize: 12, color: "var(--ink)" }}>{goalNote}</span>
        </div>
        <div style={{ display: "flex", gap: 18, fontSize: 12, flexWrap: "wrap" }}>
          <span>Üst 2.5 gol: <b style={{ fontFamily: "JetBrains Mono", color: "var(--ink)" }}>%{Math.round(pr.over * 100)}</b></span>
          <span>Karşılıklı gol: <b style={{ fontFamily: "JetBrains Mono", color: pr.btts >= 0.55 ? "var(--high)" : "var(--ink)" }}>%{Math.round(pr.btts * 100)}</b> {pr.btts >= 0.55 ? "(olası)" : "(tek taraf kapanabilir)"}</span>
        </div>
        <div style={{ fontSize: 10, color: "var(--dim)", marginTop: 6, lineHeight: 1.5 }}>
          Gerçek son sezonda kalibre: karşılıklı gol <b>iyi isabetli</b> (ECE 0.025), üst 2.5 <b>kabaca doğru</b> (yüksek olasılıkları hafif şişirir — kesin değil, eğilim).
        </div>
      </div>

      {/* DİZİLİŞ EŞLEŞMESİ — gerçek formation (iki takım) */}
      {decH?.formation.top && decA?.formation.top && (
        <div style={{ borderRadius: 10, border: "1px solid var(--line)", padding: "11px 14px", background: "var(--panel)", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700 }}>DİZİLİŞ EŞLEŞMESİ</span>
          <span style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto", flexWrap: "wrap" }}>
            <span style={{ fontWeight: 700, color: "var(--accent)" }}>{surname(home.name)}</span>
            <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 14, color: "var(--accent)" }}>{decH.formation.venueShift ? decH.formation.home : decH.formation.top}</span>
            <span style={{ color: "var(--dim)", fontWeight: 700 }}>vs</span>
            <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 14, color: "var(--high)" }}>{decA.formation.venueShift ? decA.formation.away : decA.formation.top}</span>
            <span style={{ fontWeight: 700, color: "var(--high)" }}>{surname(away.name)}</span>
          </span>
          <div style={{ flexBasis: "100%", fontSize: 10.5, color: "var(--dim)", lineHeight: 1.5 }}>
            Gerçek resmi diziliş (en sık kullanılan{decH.formation.venueShift || decA.formation.venueShift ? ", ev/dep&apos;e göre" : ""}).
            {decH.formation.varied || decA.formation.varied ? " Esnek takım dizilişi maça göre değişebilir — kesin değil, eğilim." : ""}
          </div>
        </div>
      )}

      {/* iki takım kartı: #4 tehditler + #8 ev/dep + #7 kırılganlık + #10 sürpriz */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
        {[{ t: home, d: decH, side: "home" as const, color: "var(--accent)", lbl: "EV" }, { t: away, d: decA, side: "away" as const, color: "var(--high)", lbl: "DEP" }].map(({ t, d, side, color, lbl }) => {
          if (!d) return <div key={t.name} />;
          const splitV = side === "home" ? d.split.homeGD : d.split.awayGD;
          const splitN = side === "home" ? d.split.homeN : d.split.awayN;
          const splitTxt = splitN < 8 ? `az veri (${splitN} maç)` : splitV > 0.4 ? `güçlü (+${splitV})` : splitV < -0.4 ? `zayıf (${splitV})` : `nötr (${splitV})`;
          const splitCol = splitV > 0.4 ? "var(--low)" : splitV < -0.4 ? "var(--high)" : "var(--dim)";
          return (
            <div key={t.name} style={{ borderRadius: 10, border: "1px solid var(--line)", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 9, fontWeight: 800, color: "#fff", background: color, borderRadius: 3, padding: "1px 6px" }}>{lbl}</span>
                <span style={{ fontSize: 13, fontWeight: 800 }}>{t.name}</span>
              </div>

              {/* #4 kilit oyuncular */}
              <div>
                <div style={{ fontSize: 10.5, color: "var(--muted)", fontWeight: 700, marginBottom: 4 }}>EN TEHLİKELİ OYUNCULAR (markaj önceliği)</div>
                {d.threats.length ? d.threats.map((p) => (
                  <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, padding: "2px 0" }}>
                    {p.pos && <span style={{ ...posTag(p.pos) }}>{p.pos}</span>}
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</span>
                    <span style={{ fontFamily: "JetBrains Mono", fontSize: 10.5, color: "var(--low)" }}>+{p.value.toFixed(2)}</span>
                  </div>
                )) : <span style={{ fontSize: 11, color: "var(--dim)" }}>belirgin kilit oyuncu yok (dağınık güç)</span>}
              </div>

              {/* #8 ev/dep */}
              <div style={{ fontSize: 11.5, display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ color: "var(--muted)", fontWeight: 700 }}>{side === "home" ? "EVİNDE" : "DEPLASMANDA"}:</span>
                <span style={{ color: splitCol, fontWeight: 700 }}>{splitTxt}</span>
              </div>

              {/* #7 kırılganlık */}
              <div style={{ fontSize: 11.5, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ color: "var(--muted)", fontWeight: 700 }}>KADRO:</span>
                <span style={{ color: fragColor(d.fragility.level), fontWeight: 800 }}>{d.fragility.level}</span>
                <span style={{ color: "var(--dim)", fontFamily: "JetBrains Mono", fontSize: 10.5 }}>(değerin %{Math.round(d.fragility.topShare * 100)}&apos;i ilk 3 oyuncuda)</span>
              </div>

              {/* #4 gerçek diziliş */}
              {d.formation.top && (
                <div style={{ fontSize: 11.5, display: "flex", gap: 5, alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ color: "var(--muted)", fontWeight: 700 }}>DİZİLİŞ:</span>
                  <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, color: "var(--accent)" }}>{d.formation.top}</span>
                  <span style={{ color: "var(--dim)", fontSize: 10.5 }}>
                    %{d.formation.topPct}{d.formation.varied ? " · esnek" : ""}
                    {d.formation.venueShift ? ` · ev ${d.formation.home}/dep ${d.formation.away}` : ""}
                  </span>
                </div>
              )}

              {/* #3 takım stili (possession) */}
              {d.style.poss != null && (
                <div style={{ fontSize: 11.5, display: "flex", gap: 5, alignItems: "center", flexWrap: "wrap" }}>
                  <span style={{ color: "var(--muted)", fontWeight: 700 }}>STİL:</span>
                  <span style={{ color: "var(--ink)" }}>{d.style.tag}</span>
                  <span style={{ color: "var(--dim)", fontFamily: "JetBrains Mono", fontSize: 10.5 }}>(top %{d.style.poss}{d.style.corners != null ? ` · ${d.style.corners} korner` : ""})</span>
                </div>
              )}

              {/* #1 game-state / yarı profili */}
              <div style={{ fontSize: 11.5, display: "flex", gap: 5, alignItems: "center", flexWrap: "wrap" }}>
                <span style={{ color: "var(--muted)", fontWeight: 700 }}>RİTİM:</span>
                <span style={{ color: "var(--ink)" }}>{d.gameState.startTag} · {d.gameState.finishTag}{d.gameState.lateLeak ? " · ⚠️ geç-yer" : ""}</span>
              </div>
              <div style={{ fontSize: 10.5, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>
                devre önde→tutar %{d.gameState.htLeadHoldPct} · geride→puan %{d.gameState.htBehindRecoverPct}
              </div>

              {/* #10 sürpriz-11 */}
              {d.surprise.rotated && (
                <div style={{ fontSize: 11, borderRadius: 7, border: "1px solid var(--mid)", padding: "6px 9px", background: "color-mix(in srgb, var(--mid) 10%, var(--panel))", color: "var(--ink)" }}>
                  ⚠️ <b>Son maçta beklenenden zayıf 11</b> ({d.surprise.delta}) — bu takım rotasyon yapmış olabilir.
                </div>
              )}

              {/* A — uyumlu ikili (betimleyici) */}
              {d.pairs.length > 0 && (
                <div>
                  <div style={{ fontSize: 10.5, color: "var(--muted)", fontWeight: 700, marginBottom: 4 }}>EN UYUMLU İKİLİ (birlikteyken takım daha iyi)</div>
                  {d.pairs.filter((p) => p.gdWith > 0).slice(0, 2).map((p, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, padding: "2px 0" }}>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{surname(p.a)} + {surname(p.b)}</span>
                      <span style={{ fontFamily: "JetBrains Mono", fontSize: 10, color: "var(--low)" }}>+{p.gdWith}</span>
                      <span style={{ fontFamily: "JetBrains Mono", fontSize: 9.5, color: "var(--dim)" }}>{p.together} maç</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div style={{ fontSize: 10.5, color: "var(--dim)", lineHeight: 1.5 }}>
        Tümü <b>gerçek sonuçlardan öğrenilmiş</b>: kilit oyuncu = takıma net katkı (markaj) · güven = favori açıklığı × lig isabeti ·
        maç tipi = motorun gol tahmini (kalibre) · ev/dep = takımın kendi gol farkı · kırılganlık = değer kaç oyuncuya bağlı ·
        sürpriz-11 = son kadro beklenenden zayıf mı · uyumlu ikili = birlikteyken takım gol-farkı (<b>betimleyici</b> — tahmini
        değiştirmez, çünkü out-of-sample testte ek bilgi katmadı; dürüstçe sadece bağlam). Karar antrenörün.
      </div>
    </div>
  );
}
