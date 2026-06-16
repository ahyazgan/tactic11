"use client";

/**
 * MAÇ-İÇİ KARAR EKRANI (client) — "şu an dakika X, skor Y-Z, kim sakatlandı →
 * ne yapsam ne olur". Maç-öncesi λ (kadro düzeltmeli) hesaplanır, sonra mevcut
 * dakika+skora göre predictLive ile NİHAİ sonuç olasılığı çıkar. Oyuncu çıkarınca
 * (sakat/kart) etki anında görünür. Veri SquadImpact ile aynı (yeni prop yok).
 */

import React from "react";
import { predictLive, clamp } from "@/lib/poisson-predict";
import type { SquadImpactData, TeamSquadData } from "./squad-impact";

const surname = (n: string) => n.split(" ").slice(-1)[0];

// Kırmızı kart λ faktörleri (literatür-bazlı genel tahmin; kendi verimizde ayrıca
// doğrulanmadı). 10 kişi kalan takım kalan-λ ×0.82, rakibi ×1.12.
const RC_SELF = 0.82, RC_OPP = 1.12;

type EventKind = "goalH" | "goalA" | "redH" | "redA" | "obs";
interface LogEvent { kind: EventKind; icon: string; text: string; color: string; min: number }

const POS_COLOR: Record<string, string> = { GK: "var(--dim)", DEF: "var(--low)", MID: "var(--mid)", ATT: "var(--high)" };
const posTag = (p: string) => ({ fontSize: 9, fontWeight: 800, letterSpacing: 0.3, color: "#fff", background: POS_COLOR[p] ?? "var(--dim)", borderRadius: 3, padding: "1px 5px", flexShrink: 0 } as const);

export interface MatchControl { hi: number; ai: number; onHome: (i: number) => void; onAway: (i: number) => void }

export function LiveMatch({ data, control }: { data: SquadImpactData; control?: MatchControl }) {
  const teams = data.teams;
  const [iHi, setHi] = React.useState(0);
  const [iAi, setAi] = React.useState(1);
  const [minute, setMinute] = React.useState(60);
  const [curH, setCurH] = React.useState(1);
  const [curA, setCurA] = React.useState(0);
  const [outH, setOutH] = React.useState<Set<number>>(new Set());
  const [outA, setOutA] = React.useState<Set<number>>(new Set());
  // Canlı gözlem: kırmızı kartlar (tahmini ETKİLER) + olay günlüğü (zaman çizelgesi).
  const [rcH, setRcH] = React.useState(0);
  const [rcA, setRcA] = React.useState(0);
  const [events, setEvents] = React.useState<LogEvent[]>([]);
  const hi = control ? control.hi : iHi, ai = control ? control.ai : iAi;

  const home = teams[hi], away = teams[ai];
  const onHome = control ? control.onHome : (i: number) => { setHi(i); setOutH(new Set()); if (i === ai) { const j = (i + 1) % teams.length; setAi(j); setOutA(new Set()); } };
  const onAway = control ? control.onAway : (i: number) => { setAi(i); setOutA(new Set()); if (i === hi) { const j = (i + 1) % teams.length; setHi(j); setOutH(new Set()); } };
  // Kontrollü modda takım değişince eksik-kadro + gözlem state'ini sıfırla.
  React.useEffect(() => { setOutH(new Set()); setOutA(new Set()); setRcH(0); setRcA(0); setEvents([]); }, [hi, ai]);
  const toggle = (set: Set<number>, setSet: (s: Set<number>) => void, id: number) => {
    const n = new Set(set); n.has(id) ? n.delete(id) : n.add(id); setSet(n);
  };

  // Kadro düşüşü → maç-öncesi λ bump (SquadImpact ile aynı matematik).
  const dropOf = (team: TeamSquadData, out: Set<number>) =>
    [...out].reduce((s, id) => s + (team.keyPlayers.find((p) => p.id === id)?.value ?? 0), 0) / 11;

  // Herhangi dakika+skor için tahmin (what-if senaryoları bunu kullanır). Kırmızı
  // kart etkisi: 10 kişi kalan takımın kalan-λ'sı düşer, rakibinki artar (RC_SELF/
  // RC_OPP). Bu faktörler futbol literatüründen GENEL tahmin — kendi gol-verimizde
  // ayrıca doğrulanmadı (dürüstçe işaretli); gol/skor etkisi ise tam doğrulanmıştır.
  const predAt = (oh: Set<number>, oa: Set<number>, m: number, h: number, a: number) => {
    const bump = data.beta * ((-dropOf(home, oh)) - (-dropOf(away, oa)));
    let lH = clamp(Math.exp(data.muH + home.atk - away.def + bump), 0.05, 7);
    let lA = clamp(Math.exp(data.muA + away.atk - home.def - bump), 0.05, 7);
    lH = clamp(lH * Math.pow(RC_SELF, rcH) * Math.pow(RC_OPP, rcA), 0.05, 7);
    lA = clamp(lA * Math.pow(RC_SELF, rcA) * Math.pow(RC_OPP, rcH), 0.05, 7);
    // GERÇEK gol-zamanlaması eğrisi: "m dk'dan sonra gol oranı" (varsa); yoksa eşit.
    const remFrac = data.timing?.[Math.round(clamp(m, 0, 90))];
    return predictLive(lH, lA, data.rho, m, h, a, remFrac);
  };
  const liveOf = (oh: Set<number>, oa: Set<number>) => predAt(oh, oa, minute, curH, curA);

  const before = liveOf(new Set(), new Set());  // bu skor/dakikada, kimse çıkmadan
  const now = liveOf(outH, outA);
  const dH = Math.round((now.pH - before.pH) * 100);
  const dD = Math.round((now.pD - before.pD) * 100);
  const dA = Math.round((now.pA - before.pA) * 100);
  const anyOut = outH.size + outA.size > 0;
  const remTxt = minute >= 90 ? "maç bitti" : `${90 - minute} dk kaldı`;

  // #2 — kalan sürede gol beklentisi (predictLive'ın remH/remA'sından).
  const remTot = now.remH + now.remA;
  const pNewGoal = Math.round((1 - Math.exp(-remTot)) * 100);     // ≥1 yeni gol olasılığı
  const pHomeScore = Math.round((1 - Math.exp(-now.remH)) * 100);
  const pAwayScore = Math.round((1 - Math.exp(-now.remA)) * 100);

  // #3 — maç-içi risk: önde olan taraf için "kazanamama" (berabere+kayıp) riski.
  const leading = curH > curA ? "home" : curH < curA ? "away" : "draw";
  const leaderName = leading === "home" ? surname(home.name) : leading === "away" ? surname(away.name) : null;
  const notWinRisk = leading === "home" ? Math.round((now.pD + now.pA) * 100)
    : leading === "away" ? Math.round((now.pD + now.pH) * 100) : 0;
  const riskLevel = notWinRisk >= 30 ? "kırılgan" : notWinRisk >= 12 ? "dikkat" : "güvenli";
  const riskColor = riskLevel === "kırılgan" ? "var(--high)" : riskLevel === "dikkat" ? "var(--mid)" : "var(--low)";

  // #1 — what-if senaryoları (skoru değiştirmeden önizleme).
  const scNow = now.pH;
  const scConcede = predAt(outH, outA, minute, curH, curA + 1).pH;   // 1 gol yersen
  const scScore = predAt(outH, outA, minute, curH + 1, curA).pH;     // 1 gol atarsan

  // ── CANLI GÖZLEM — antrenör maçı izler, olayı işaretler (insan = sensör) ──
  const log = (kind: EventKind, icon: string, text: string, color: string) =>
    setEvents((e) => [{ kind, icon, text, color, min: minute }, ...e].slice(0, 40));
  const goalH = () => { setCurH((v) => v + 1); log("goalH", "⚽", `GOL · ${surname(home.name)}`, "var(--accent)"); };
  const goalA = () => { setCurA((v) => v + 1); log("goalA", "⚽", `GOL · ${surname(away.name)}`, "var(--high)"); };
  const redH = () => { setRcH((v) => v + 1); log("redH", "🟥", `Kırmızı · ${surname(home.name)}`, "var(--crit)"); };
  const redA = () => { setRcA((v) => v + 1); log("redA", "🟥", `Kırmızı · ${surname(away.name)}`, "var(--crit)"); };
  const chanceH = () => log("obs", "🎯", `Net şans · ${surname(home.name)}`, "var(--dim)");
  const chanceA = () => log("obs", "🎯", `Net şans · ${surname(away.name)}`, "var(--dim)");
  const momoH = () => log("obs", "🔺", `Baskı · ${surname(home.name)}`, "var(--dim)");
  const momoA = () => log("obs", "🔺", `Baskı · ${surname(away.name)}`, "var(--dim)");
  const undo = () => setEvents((prev) => {
    const [last, ...rest] = prev;
    if (!last) return prev;
    if (last.kind === "goalH") setCurH((v) => Math.max(0, v - 1));
    else if (last.kind === "goalA") setCurA((v) => Math.max(0, v - 1));
    else if (last.kind === "redH") setRcH((v) => Math.max(0, v - 1));
    else if (last.kind === "redA") setRcA((v) => Math.max(0, v - 1));
    return rest;
  });
  const anyRed = rcH + rcA > 0;

  // #4 — çıkan oyuncuların TAM MAÇ değeri (referans): maç-içi etki küçük çıkıyorsa
  // bunun "az süre kaldı"dan olduğunu göster — oyuncu tam maçta çok daha değerli.
  const dFull = anyOut ? Math.round((predAt(outH, outA, 0, 0, 0).pH - predAt(new Set(), new Set(), 0, 0, 0).pH) * 100) : 0;

  // ÖNERİ — ev takımı için: sahadaki en düşük katkılı kilit oyuncuyu, yedekteki
  // en yüksek değerli (henüz sahada olmayan) oyuncuyla değiştirirsen kazanma
  // ihtimalin ne olur? Tamamen gerçek öğrenilen değerlerden — uydurma yok.
  const onPitchH = home.keyPlayers.slice(0, 8);                 // sahadaki kilitler (ekrandakiler)
  const benchH = home.keyPlayers.slice(8).filter((p) => !outH.has(p.id));  // yedek havuzu (değer sıralı)
  const bestSub = benchH[0];                                    // yedekteki en değerli
  // değiştirilecek aday: sahada (çıkmamış) en düşük değerli kilit
  const weakest = onPitchH.filter((p) => !outH.has(p.id)).sort((a, b) => a.value - b.value)[0];
  let suggestion: { in: typeof bestSub; out: typeof weakest; gain: number } | null = null;
  if (bestSub && weakest && bestSub.value > weakest.value && minute < 88) {
    // değişiklik: weakest çıkar (değeri düşer), bestSub'ın değeri kadrolaşır.
    // net etki ≈ (bestSub.value − weakest.value)/11 kadar ev gücüne katkı → ihtimal kayması.
    const oh2 = new Set(outH); oh2.add(weakest.id);
    const baseP = liveOf(oh2, outA).pH;                          // sadece weakest çıkmış
    // bestSub girince düşüş telafi + fazlası: değer farkı kadar negatif drop ekle (güç artar)
    const extra = data.beta * ((bestSub.value - weakest.value) / 11);  // pozitif bump
    const lH = clamp(Math.exp(data.muH + home.atk - away.def + (data.beta * ((-(dropOf(home, oh2))) - (-dropOf(away, outA)))) + extra), 0.05, 7);
    const lA = clamp(Math.exp(data.muA + away.atk - home.def - (data.beta * ((-(dropOf(home, oh2))) - (-dropOf(away, outA)))) - extra), 0.05, 7);
    const withSub = predictLive(lH, lA, data.rho, minute, curH, curA).pH;
    const gain = Math.round((withSub - now.pH) * 100);
    if (gain > 0) suggestion = { in: bestSub, out: weakest, gain };
  }

  const sel = { padding: "7px 10px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontSize: 12.5, fontWeight: 600 } as const;
  const chip = (active: boolean) => ({ padding: "5px 11px", borderRadius: 7, cursor: "pointer", fontSize: 12, fontWeight: 700, border: `1px solid ${active ? "var(--accent)" : "var(--line)"}`, background: active ? "color-mix(in srgb, var(--accent) 14%, var(--panel))" : "var(--panel)", color: active ? "var(--accent)" : "var(--ink)" } as const);
  const evBtn = (color: string) => ({ padding: "5px 10px", borderRadius: 7, cursor: "pointer", fontSize: 11.5, fontWeight: 700, border: `1px solid ${color}`, background: "var(--panel)", color, whiteSpace: "nowrap" } as const);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* takım seçimi — kontrollü modda Maç Merkezi gösterir, burada gizli */}
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

      {/* maç durumu: skor + dakika */}
      <div style={{ borderRadius: 10, border: "1px solid var(--line)", padding: 14, background: "var(--panel)", display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700 }}>CANLI SKOR</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 12.5, fontWeight: 700, width: 110, textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{surname(home.name)}</span>
            <Stepper value={curH} set={setCurH} />
            <span style={{ color: "var(--dim)", fontWeight: 800 }}>–</span>
            <Stepper value={curA} set={setCurA} />
            <span style={{ fontSize: 12.5, fontWeight: 700, width: 110, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{surname(away.name)}</span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700 }}>DAKİKA</span>
          <input type="range" min={0} max={90} step={5} value={minute} onChange={(e) => setMinute(Number(e.target.value))} style={{ flex: 1, minWidth: 160, accentColor: "var(--accent)" }} />
          <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 15, width: 44, textAlign: "right" }}>{minute}&apos;</span>
          <span style={{ fontSize: 11, color: "var(--dim)" }}>{remTxt}</span>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          {[["HT", 45, undefined], ["60'", 60, undefined], ["75'", 75, undefined], ["85'", 85, undefined]].map(([lbl, mn]) => (
            <span key={lbl as string} onClick={() => setMinute(mn as number)} style={chip(minute === mn)}>{lbl as string}</span>
          ))}
          {anyRed && (
            <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, color: "var(--crit)" }}>
              🟥 {rcH > 0 ? `${surname(home.name)} ${rcH > 1 ? `×${rcH}` : ""}` : ""}{rcH > 0 && rcA > 0 ? " · " : ""}{rcA > 0 ? `${surname(away.name)} ${rcA > 1 ? `×${rcA}` : ""}` : ""}
            </span>
          )}
        </div>
      </div>

      {/* CANLI GÖZLEM — antrenör maçı izler, olayı işaretler (insan = sensör) */}
      {minute < 90 && (
        <div style={{ borderRadius: 10, border: "1px solid var(--accent)", padding: 13, background: "color-mix(in srgb, var(--accent) 5%, var(--panel))" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 9 }}>
            <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.5, color: "#fff", background: "var(--accent)", borderRadius: 4, padding: "2px 8px" }}>CANLI GÖZLEM</span>
            <span style={{ fontSize: 11.5, color: "var(--muted)" }}>maçı izle → olayı işaretle (dk {minute}&apos;)</span>
            {events.length > 0 && <button onClick={undo} style={{ marginLeft: "auto", ...sel, padding: "4px 10px", fontSize: 11, cursor: "pointer" }}>↶ geri al</button>}
          </div>
          {/* ev / dep olay butonları */}
          {[{ t: home, color: "var(--accent)", g: goalH, r: redH, c: chanceH, m: momoH }, { t: away, color: "var(--high)", g: goalA, r: redA, c: chanceA, m: momoA }].map(({ t, color, g, r, c, m }) => (
            <div key={t.name} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, flexWrap: "wrap" }}>
              <span style={{ width: 88, fontSize: 11.5, fontWeight: 700, color, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{surname(t.name)}</span>
              <button onClick={g} style={evBtn("var(--low)")}>⚽ Gol</button>
              <button onClick={r} style={evBtn("var(--crit)")}>🟥 Kırmızı</button>
              <button onClick={c} style={evBtn("var(--dim)")}>🎯 Şans</button>
              <button onClick={m} style={evBtn("var(--dim)")}>🔺 Baskı</button>
            </div>
          ))}
          <div style={{ fontSize: 10, color: "var(--dim)", marginTop: 4, lineHeight: 1.5 }}>
            <b style={{ color: "var(--low)" }}>Gol</b> ve <b style={{ color: "var(--crit)" }}>Kırmızı</b> tahmini <b>değiştirir</b> (gol=doğrulanmış · kırmızı=literatür tahmini).
            <b style={{ color: "var(--dim)" }}> Şans/Baskı</b> sadece <b>zaman çizelgesine yazılır</b>, tahmini değiştirmez — çünkü kaçan şans skoru değiştirmez (dürüst sınır).
          </div>
        </div>
      )}

      {/* OLAY ZAMAN ÇİZELGESİ */}
      {events.length > 0 && (
        <div style={{ borderRadius: 10, border: "1px solid var(--line)", padding: "10px 13px", background: "var(--panel)" }}>
          <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700, marginBottom: 7 }}>MAÇ AKIŞI</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 160, overflowY: "auto" }}>
            {events.map((e, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 12 }}>
                <span style={{ fontFamily: "JetBrains Mono", fontSize: 10.5, color: "var(--dim)", width: 30, textAlign: "right" }}>{e.min}&apos;</span>
                <span style={{ width: 16, textAlign: "center" }}>{e.icon}</span>
                <span style={{ color: e.kind === "obs" ? "var(--muted)" : "var(--ink)", fontWeight: e.kind === "obs" ? 400 : 600 }}>{e.text}</span>
                {e.kind === "obs" && <span style={{ marginLeft: "auto", fontSize: 9.5, color: "var(--dim)" }}>gözlem</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* nihai sonuç olasılığı — şu an */}
      <div style={{ borderRadius: 10, border: "1px solid var(--line)", padding: 14, background: "var(--panel)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>
          <span>{minute >= 90 ? "Sonuç" : "Buradan sonu — nihai sonuç ihtimali"}</span>
          <span style={{ fontFamily: "JetBrains Mono" }}>kalan beklenen {now.remH.toFixed(2)}–{now.remA.toFixed(2)}</span>
        </div>
        <div style={{ display: "flex", height: 26, borderRadius: 6, overflow: "hidden", border: "1px solid var(--line)" }}>
          <span style={{ width: `${now.pH * 100}%`, background: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 11, fontWeight: 800 }}>{Math.round(now.pH * 100)}%</span>
          <span style={{ width: `${now.pD * 100}%`, background: "var(--dim)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 10 }}>{Math.round(now.pD * 100)}%</span>
          <span style={{ width: `${now.pA * 100}%`, background: "var(--high)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 11, fontWeight: 800 }}>{Math.round(now.pA * 100)}%</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginTop: 5 }}>
          <span style={{ fontWeight: 700 }}>{surname(home.name)} kazanır {anyOut && delta(dH)}</span>
          <span style={{ color: "var(--dim)" }}>berabere {anyOut && delta(dD)}</span>
          <span style={{ fontWeight: 700 }}>{surname(away.name)} kazanır {anyOut && delta(dA)}</span>
        </div>
        {anyOut && (
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.5, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
            Çıkardığın oyuncu(lar)la, bu dakikadan sonu için {surname(home.name)} kazanma ihtimali <b style={{ color: dH < 0 ? "var(--high)" : "var(--low)" }}>{delta(dH)}</b>.
            {Math.abs(dFull) > Math.abs(dH) && <> Aynı oyuncu(lar) <b>tam maç</b> boyunca yok olsaydı etki <b style={{ color: dFull < 0 ? "var(--high)" : "var(--low)" }}>{delta(dFull)}</b> olurdu — şu an küçük çünkü sadece {90 - minute} dk kaldı.</>}
          </div>
        )}
        {anyRed && (
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.5, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
            🟥 Kırmızı kart hesaba katıldı: 10 kişi kalan takımın kalan-sürede gol beklentisi düştü, rakibininki arttı.
            <i> (Bu etki futbol literatüründen genel tahmin — kendi gol-verimizde ayrıca doğrulanmadı.)</i>
          </div>
        )}
      </div>

      {/* #3 risk + #2 kalan gol — maç durumu okuması */}
      {minute < 90 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
          {/* #3 risk uyarısı (önde olan taraf varsa) */}
          {leaderName && (
            <div style={{ borderRadius: 10, border: `1px solid ${riskColor}`, padding: 12, background: `color-mix(in srgb, ${riskColor} 7%, var(--panel))` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.5, color: "#fff", background: riskColor, borderRadius: 4, padding: "2px 8px" }}>{riskLevel.toUpperCase()}</span>
                <span style={{ fontSize: 12.5, fontWeight: 700 }}>{leaderName} önde</span>
                <span style={{ marginLeft: "auto", fontFamily: "JetBrains Mono", fontWeight: 800, color: riskColor }}>%{notWinRisk}</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>
                {leaderName} için <b>kazanamama riski %{notWinRisk}</b> (berabere + kayıp).
                {riskLevel === "kırılgan" ? " Skor hâlâ kırılgan — savunmayı sağlama al." : riskLevel === "dikkat" ? " Kontrollü oyna, kapatmaya yakınsın." : " Büyük ölçüde güvende."}
              </div>
            </div>
          )}
          {/* #2 kalan sürede gol */}
          <div style={{ borderRadius: 10, border: "1px solid var(--line)", padding: 12, background: "var(--panel)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
              <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700 }}>KALAN SÜREDE GOL</span>
              <span style={{ marginLeft: "auto", fontFamily: "JetBrains Mono", fontWeight: 800, color: pNewGoal >= 60 ? "var(--high)" : "var(--ink)" }}>%{pNewGoal}</span>
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>
              Bu dakikadan sonra <b>yeni gol</b> olasılığı %{pNewGoal}. {surname(home.name)} atar %{pHomeScore} · {surname(away.name)} atar %{pAwayScore}.
              {pNewGoal >= 60 ? " Maç hâlâ açık — gol beklentisi yüksek." : pNewGoal <= 30 ? " Düşük gol beklentisi — skor donmaya yakın." : ""}
            </div>
          </div>
        </div>
      )}

      {/* #1 what-if senaryoları — skoru değiştirmeden önizle */}
      {minute < 90 && (
        <div style={{ borderRadius: 10, border: "1px solid var(--line)", padding: 12, background: "var(--panel)" }}>
          <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700, marginBottom: 8 }}>SENARYO — {surname(home.name)} kazanma ihtimali nasıl değişir</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
            {[
              { lbl: "şu an böyle kalırsa", v: scNow, c: "var(--dim)" },
              { lbl: `+1 ${surname(home.name)} atarsa`, v: scScore, c: "var(--low)" },
              { lbl: `+1 ${surname(away.name)} atarsa`, v: scConcede, c: "var(--high)" },
            ].map((s) => (
              <div key={s.lbl} style={{ textAlign: "center", borderRadius: 8, border: `1px solid ${s.c}`, padding: "8px 6px", background: `color-mix(in srgb, ${s.c} 6%, var(--panel))` }}>
                <div style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 20, color: s.c === "var(--dim)" ? "var(--ink)" : s.c }}>%{Math.round(s.v * 100)}</div>
                <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2, lineHeight: 1.3 }}>{s.lbl}</div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 10, color: "var(--dim)", marginTop: 7, lineHeight: 1.5 }}>
            Bir sonraki gol maçı nasıl çevirir — önceden gör, ona göre risk al/kapat. (Skoru değiştirmez, sadece önizler.)
          </div>
        </div>
      )}

      {/* ÖNERİ — en iyi hamle (gerçek öğrenilen değerlerden) */}
      {suggestion && (
        <div style={{ borderRadius: 10, border: "1px solid var(--low)", padding: "11px 14px", background: "color-mix(in srgb, var(--low) 7%, var(--panel))" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.5, color: "#fff", background: "var(--low)", borderRadius: 4, padding: "2px 8px" }}>EN İYİ HAMLE</span>
            <span style={{ fontSize: 12.5, color: "var(--ink)" }}>
              <b style={{ color: "var(--high)" }}>{surname(suggestion.out.name)}</b> çık → <b style={{ color: "var(--low)" }}>{surname(suggestion.in.name)}</b> gir
            </span>
            <span style={{ marginLeft: "auto", fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 14, color: "var(--low)" }}>kazanma +{suggestion.gain} puan</span>
          </div>
          <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
            Yedekteki <b>{surname(suggestion.in.name)}</b> ({suggestion.in.value.toFixed(2)}), sahadaki en düşük katkılı kilit
            <b> {surname(suggestion.out.name)}</b> ({suggestion.out.value.toFixed(2)}) yerine girerse — gerçek sonuçlardan öğrenilen değer farkı kadar
            ev gücü artar. Karar senin; bu sadece <b>verinin işaret ettiği</b> en yüksek-getirili değişiklik (kalan {90 - minute} dk için).
          </div>
        </div>
      )}

      {/* sahadaki oyuncu — çıkar (sakat/kart) */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
        {[{ t: home, out: outH, set: setOutH, color: "var(--accent)" }, { t: away, out: outA, set: setOutA, color: "var(--high)" }].map(({ t, out, set, color }) => (
          <div key={t.name}>
            <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 6, color }}>{t.name} · sahadaki kilitler</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {t.keyPlayers.slice(0, 8).map((p) => {
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
                    <span style={{ fontSize: 9.5, color: isOut ? "var(--high)" : "var(--dim)", fontWeight: 700, width: 44, textAlign: "right" }}>{isOut ? "ÇIKTI" : "sahada"}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div style={{ fontSize: 10.5, color: "var(--dim)", lineHeight: 1.5 }}>
        {data.timing && <><b style={{ color: "var(--low)" }}>✓ Gerçek gol-zamanlaması:</b> motor &quot;goller geç gelir&quot; eğrisini kullanır (5.000+ maçtan, out-of-sample doğrulandı) — naif eşit-dağılımdan daha isabetli, özellikle geç dakikada. </>}
        Dakika + skoru gerçek maça göre ayarla → ekran nihai sonuç ihtimalini gösterir. Bir oyuncu sakatlanır/kart görürse
        <b> ÇIKTI</b> işaretle → bu dakikadan sonu için tahmin anında güncellenir. <b>Geç dakikalarda</b> bir oyuncunun etkisi
        küçülür — çünkü değişecek az süre kaldı; model bunu otomatik yapar. Antrenörün &quot;şimdi kimi sokayım, riski ne&quot; kararına canlı sayı.
      </div>
    </div>
  );
}

function Stepper({ value, set }: { value: number; set: (n: number) => void }) {
  const b = { width: 24, height: 26, borderRadius: 6, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", cursor: "pointer", fontWeight: 800, fontSize: 14 } as const;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <button style={b} onClick={() => set(Math.max(0, value - 1))}>−</button>
      <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 18, width: 22, textAlign: "center" }}>{value}</span>
      <button style={b} onClick={() => set(Math.min(15, value + 1))}>+</button>
    </span>
  );
}

function delta(d: number) {
  if (d === 0) return <span style={{ color: "var(--dim)" }}>±0</span>;
  return <span style={{ color: d > 0 ? "var(--low)" : "var(--high)" }}>{d > 0 ? "+" : ""}{d} puan</span>;
}
