/**
 * Birleşik Sakatlık Risk Endeksi — tüm sinyalleri TEK 0-100 skora füzyonlar.
 *
 * `assessReadiness` (lib/readiness.ts) bir trafik ışığı + flag listesi verir;
 * bu motor onun ÜSTÜNE niceliksel bir katman koyar: her risk faktörünün
 * ağırlıklı katkısını ŞEFFAF olarak çıkarır (kaç puan, neden), tek bir birleşik
 * endeks + seviye + trend + en yüksek-kaldıraçlı öneri üretir.
 *
 * Faktör ağırlıkları literatüre dayalı (toplam 100):
 *   • Akut yük (ACWR)        28  — Gabbett: tatlı bölge 0.8–1.3, >1.5 kırmızı
 *   • H:Q oranı              18  — hamstring sakatlığının en güçlü tek belirteci
 *   • Bacak asimetrisi       14  — tekrar-sakatlanma belirteci (>%15 kırmızı)
 *   • Nöromusküler (CMJ)     12  — MD+1 sıçrama düşüşü = yorgunluk
 *   • Öznel hazırlık         12  — uyku/yorgunluk/ağrı (ACWR'yi 2-3 gün önceler)
 *   • Yaş                     8  — ≥30 belirgin risk artışı
 *   • Son regresyon/trend     8  — ani performans kırılması
 *
 * Eksik sinyaller atlanır; skor MEVCUT ağırlıklara göre normalize edilir; böylece
 * yalnız ACWR'si olan bir oyuncu da 0-100 endeks alır. Saf hesap — DEMO_MODE'da
 * burada, production'da aynı girdilerle backend'de çalışır (Math.random YOK).
 */

import { demoSquad, type RiskLabel, type SquadPlayer } from "@/lib/demo-data";
import { wellnessReadiness, type WellnessFields } from "@/lib/wellness";

export type RiskLevel = "low" | "mid" | "high" | "crit";
export type RiskTrend = "rising" | "stable" | "falling";

export const LEVEL_VAR: Record<RiskLevel, string> = {
  low: "var(--low)", mid: "var(--mid)", high: "var(--high)", crit: "var(--crit)",
};
export const LEVEL_LABEL: Record<RiskLevel, string> = {
  low: "Düşük", mid: "Orta", high: "Yüksek", crit: "Kritik",
};
export const TREND_LABEL: Record<RiskTrend, string> = {
  rising: "yükseliyor", stable: "sabit", falling: "geriliyor",
};
export const TREND_GLYPH: Record<RiskTrend, string> = {
  rising: "▲", stable: "▬", falling: "▼",
};

/** Endekse katkıda bulunan tek bir risk faktörü (şeffaf kırılım). */
export interface RiskFactor {
  key: string;
  label: string;     // "Akut yük (ACWR)"
  weight: number;    // bu faktörün katabileceği maks puan
  points: number;    // 0..weight gerçek katkı
  level: RiskLevel;
  detail: string;    // "ACWR 1.62 — tatlı bölge üstü (akut yük zirvede)"
}

export interface RiskIndex {
  score: number;            // 0..100 birleşik endeks
  level: RiskLevel;
  label: RiskLabel;         // demo-data RiskLabel ile hizalı (Düşük/Orta/Yüksek/Kritik)
  trend: RiskTrend;
  factors: RiskFactor[];    // katkıya göre azalan sıralı
  topDriver: RiskFactor | null;
  recommendation: string;   // en yüksek-kaldıraçlı tek aksiyon
  horizonNote: string;      // 14 günlük ileriye dönük yorum
  evaluated: number;        // değerlendirilen faktör sayısı
}

export interface RiskInput {
  age?: number;
  acwr?: number;
  prevAcwr?: number;                      // trend için (önceki pencere)
  hq?: { hamstring: number; quadriceps: number };
  asymmetry?: { left: number; right: number };
  cmj?: { current: number; baseline: number[] };
  wellness?: WellnessFields;
  regressionCount?: number;               // ani düşen protokol sayısı
}

const clamp01 = (n: number) => Math.max(0, Math.min(1, n));
const levelOfUtil = (u: number): RiskLevel =>
  u >= 0.7 ? "crit" : u >= 0.45 ? "high" : u >= 0.22 ? "mid" : "low";

// ── Faktör başına util (0..1) + okunur açıklama ─────────────────────────────
// util = faktörün ağırlığını ne kadar doldurduğu (1 = tam risk).

function acwrUtil(acwr: number): { u: number; detail: string } {
  let u: number, why: string;
  if (acwr >= 1.5) { u = Math.min(1, 0.8 + (acwr - 1.5) * 0.6); why = "tatlı bölge çok üstü — akut yük zirvede"; }
  else if (acwr > 1.3) { u = 0.5 + ((acwr - 1.3) / 0.2) * 0.25; why = "yük artışı dik — dikkat bölgesi"; }
  else if (acwr >= 0.8) { u = 0.18 - ((acwr - 0.8) / 0.5) * 0.08; why = "ideal yük bandı"; }
  else { u = Math.min(0.8, 0.42 + (0.8 - acwr) * 0.7); why = "düşük yük — maç temposuna hazır değil (detraining)"; }
  return { u: clamp01(u), detail: `ACWR ${acwr.toFixed(2)} — ${why}` };
}

function hqUtil(hamstring: number, quadriceps: number): { u: number; detail: string } {
  const ratio = quadriceps > 0 ? hamstring / quadriceps : 0;
  let u: number, why: string;
  if (ratio >= 0.6) { u = clamp01(0.16 - (ratio - 0.6) * 0.4); why = "ideal denge"; }
  else if (ratio >= 0.47) { u = 0.4 + ((0.6 - ratio) / 0.13) * 0.3; why = "sınırda — eksantrik hamstring çalışması"; }
  else { u = Math.min(1, 0.72 + (0.47 - ratio) * 1.6); why = "yüksek hamstring sakatlık riski"; }
  return { u: clamp01(u), detail: `H:Q ${ratio.toFixed(2)} — ${why}` };
}

function asymUtil(left: number, right: number): { u: number; detail: string } {
  const hi = Math.max(left, right);
  const pct = hi > 0 ? (Math.abs(left - right) / hi) * 100 : 0;
  let u: number, why: string;
  if (pct <= 10) { u = (pct / 10) * 0.22; why = "denge kabul edilebilir"; }
  else if (pct <= 15) { u = 0.35 + ((pct - 10) / 5) * 0.33; why = "izlenmeli — tek-bacak düzeltici program"; }
  else { u = Math.min(1, 0.7 + (pct - 15) * 0.03); why = "tekrar-sakatlanma riski yüksek"; }
  return { u: clamp01(u), detail: `Bacak asimetrisi %${pct.toFixed(0)} — ${why}` };
}

function cmjUtil(current: number, baseline: number[]): { u: number; detail: string } {
  const base = baseline.length ? baseline.reduce((a, b) => a + b, 0) / baseline.length : current;
  const drop = base > 0 ? ((base - current) / base) * 100 : 0;
  const u = clamp01(drop / 15);
  const why = drop > 10 ? "nöromusküler yorgunluk — yükü azalt"
    : drop > 5 ? "hafif yorgunluk izi" : "toparlanma tam";
  return { u, detail: `CMJ baseline'a göre ${drop > 0 ? "-" : "+"}%${Math.abs(drop).toFixed(0)} — ${why}` };
}

function wellnessUtil(w: WellnessFields): { u: number; detail: string } {
  const readiness = wellnessReadiness(w);
  const u = clamp01((0.8 - readiness) / 0.45);
  const why = readiness >= 0.7 ? "öznel hazırlık iyi"
    : readiness >= 0.55 ? "uyku/yorgunluk izlemede" : "öznel hazırlık düşük — yükü gözden geçir";
  return { u, detail: `Hazırlık anketi %${Math.round(readiness * 100)} — ${why}` };
}

function ageUtil(age: number): { u: number; detail: string } {
  const u = age <= 28 ? clamp01(0.1 + Math.max(0, 23 - age) * 0.02)
    : Math.min(0.92, 0.12 + (age - 28) * 0.14);
  const why = age >= 32 ? "ileri yaş — toparlanma yavaş"
    : age >= 29 ? "30+ risk bandı" : age <= 21 ? "genç — kemik/büyüme yükü" : "zirve yaş";
  return { u: clamp01(u), detail: `${age} yaş — ${why}` };
}

function regressionUtil(count: number): { u: number; detail: string } {
  const u = count >= 2 ? 0.85 : count === 1 ? 0.5 : 0.1;
  const why = count >= 2 ? "birden fazla metrik ani düştü"
    : count === 1 ? "bir metrikte ani kırılma" : "performans trendi stabil";
  return { u, detail: `Son test trendi — ${why}` };
}

// ── Trend: akut yük yönü + regresyon ────────────────────────────────────────
function deriveTrend(input: RiskInput): RiskTrend {
  const { acwr, prevAcwr, regressionCount = 0 } = input;
  if (acwr != null && prevAcwr != null) {
    const d = acwr - prevAcwr;
    if (d > 0.08 || (regressionCount > 0 && d >= 0)) return "rising";
    if (d < -0.08 && regressionCount === 0) return "falling";
    return "stable";
  }
  if (acwr != null) {
    if (acwr > 1.3 || regressionCount >= 1) return "rising";
    if (acwr < 0.95 && regressionCount === 0) return "falling";
  }
  return "stable";
}

// ── Faktör → öneri (en yüksek-kaldıraçlı aksiyon) ───────────────────────────
const REC_BY_FACTOR: Record<string, Record<RiskLevel, string>> = {
  acwr: {
    crit: "Akut yük zirvede — bu hafta yüksek şiddetli koşuyu %40 azalt, maçta 60. dk sonrası değişiklik planla.",
    high: "Yük artışı dik — antrenmanda sprint hacmini sınırla, maç-içi dakika sınırı düşün.",
    mid: "Yükü kademeli ayarla; bir sonraki mikro-döngüde akut pencereyi izle.",
    low: "Yük dengeli — mevcut programa devam.",
  },
  hq: {
    crit: "H:Q kritik — eksantrik hamstring bloğu (Nordic) başlat, oran ≥0.60'a çıkana dek tam sprint yükünü sınırla.",
    high: "Eksantrik hamstring çalışması ekle; izokinetik re-test planla.",
    mid: "Hamstring kuvvet dengesini izle; eksantrik hacmi koru.",
    low: "Kas dengesi iyi — koruyucu eksantrik rutine devam.",
  },
  asymmetry: {
    crit: "Asimetri kırmızı — tek-bacak güç programı şart, oyun süresini sınırla (tekrar-sakatlanma riski).",
    high: "Tek-bacak düzeltici program; zayıf tarafı hedefleyen kuvvet bloğu.",
    mid: "Bacak simetrisini izle; tek-taraflı çalışmalar ekle.",
    low: "Simetri iyi.",
  },
  cmj: {
    crit: "Nöromusküler yorgunluk yüksek — 48 saat yükü düşür, uyku/HRV takibi.",
    high: "Sıçrama düşüşü belirgin — toparlanma günü ekle, pliometrik hacmi kes.",
    mid: "Hafif yorgunluk — yoğunluğu ölçülü tut.",
    low: "Toparlanma tam.",
  },
  wellness: {
    crit: "Öznel hazırlık çok düşük — bugün yükü ciddi azalt, uyku/stres kaynağını araştır.",
    high: "Uyku/yorgunluk düşük — antrenman yükünü hafiflet.",
    mid: "Wellness izlemede — günlük anketi takip et.",
    low: "Öznel hazırlık iyi.",
  },
  age: {
    crit: "İleri yaş + yük — maç sıklığını yönet, dönüş arası toparlanmayı uzat.",
    high: "30+ bandı — ardışık maçlarda rotasyon planla.",
    mid: "Yaşa uygun toparlanma penceresi koru.",
    low: "Yaş profili düşük risk.",
  },
  regression: {
    crit: "Birden fazla metrik düştü — aşırı yük/sakatlık taraması yap, test penceresini öne al.",
    high: "Performans kırılması — yükü gözden geçir, erken re-test.",
    mid: "Bir metrikte düşüş — trendi yakın izle.",
    low: "Trend stabil.",
  },
};

const HORIZON: Record<RiskLevel, (t: RiskTrend) => string> = {
  crit: (t) => t === "rising"
    ? "Önümüzdeki 14 gün: müdahale edilmezse akut sakatlık olasılığı yüksek — yük müdahalesi bu hafta."
    : "Önümüzdeki 14 gün: kritik bantta — yakın izlem ve kademeli yük şart.",
  high: (t) => t === "rising"
    ? "Önümüzdeki 14 gün: risk yükseliyor — yük yönetimi yapılmazsa kritik banda geçebilir."
    : "Önümüzdeki 14 gün: yüksek bant — kontrollü yükle stabilize edilebilir.",
  mid: (t) => t === "rising"
    ? "Önümüzdeki 14 gün: izlenmeli — akut yük yönü yukarı, erken müdahale ucuz."
    : "Önümüzdeki 14 gün: orta bant — rutin takip yeterli, trend olumlu.",
  low: () => "Önümüzdeki 14 gün: düşük risk — tam maç yüküne hazır, rutin haftalık takip.",
};

const labelFromLevel: Record<RiskLevel, RiskLabel> = {
  low: "Düşük", mid: "Orta", high: "Yüksek", crit: "Kritik",
};

/** Ana motor: sinyalleri ağırlıklı, şeffaf, normalize bir 0-100 endekse füzyonlar. */
export function computeRiskIndex(input: RiskInput): RiskIndex {
  const factors: RiskFactor[] = [];
  const push = (key: string, label: string, weight: number, r: { u: number; detail: string }) =>
    factors.push({ key, label, weight, points: Math.round(r.u * weight * 10) / 10, level: levelOfUtil(r.u), detail: r.detail });

  if (input.acwr != null) push("acwr", "Akut yük (ACWR)", 28, acwrUtil(input.acwr));
  if (input.hq) push("hq", "H:Q kas dengesi", 18, hqUtil(input.hq.hamstring, input.hq.quadriceps));
  if (input.asymmetry) push("asymmetry", "Bacak asimetrisi", 14, asymUtil(input.asymmetry.left, input.asymmetry.right));
  if (input.cmj) push("cmj", "Nöromusküler (CMJ)", 12, cmjUtil(input.cmj.current, input.cmj.baseline));
  if (input.wellness) push("wellness", "Öznel hazırlık", 12, wellnessUtil(input.wellness));
  if (input.age != null) push("age", "Yaş", 8, ageUtil(input.age));
  if (input.regressionCount != null) push("regression", "Son test trendi", 8, regressionUtil(input.regressionCount));

  const totalWeight = factors.reduce((s, f) => s + f.weight, 0);
  const totalPoints = factors.reduce((s, f) => s + f.points, 0);
  const score = totalWeight > 0 ? Math.round((totalPoints / totalWeight) * 100) : 0;
  const level = levelOfUtil(score / 100);

  // En büyük sürücü = endekse en çok PUAN katan faktör (mutlak katkı); eşitlikte
  // normalize doluluk. Böylece 28-puanlık ACWR, maksa yakın 8-puanlık bir faktörü geçer.
  const sorted = [...factors].sort((a, b) => b.points - a.points || (b.points / b.weight) - (a.points / a.weight));
  const topDriver = sorted[0] ?? null;
  const trend = deriveTrend(input);

  const recommendation = topDriver
    ? (REC_BY_FACTOR[topDriver.key]?.[topDriver.level] ?? "Rutin haftalık takip yeterli.")
    : "Değerlendirilecek veri yok — test/yük girişi bekleniyor.";

  return {
    score, level, label: labelFromLevel[level], trend,
    factors: sorted, topDriver, recommendation,
    horizonNote: HORIZON[level](trend),
    evaluated: factors.length,
  };
}

// ── Demo: kadro risk profilinden deterministik girdi (readiness ile tutarlı) ─
// lib/readiness.ts demoInputFor ile AYNI türetme formülleri + yaş/wellness/regresyon.

function demoWellnessFields(r: number): WellnessFields {
  const v = (k: number) => Math.max(1, Math.min(7, Math.round(7 - r * 5 + Math.sin(k * 1.4) * 0.6)));
  return { sleep_quality: v(0), fatigue: v(1), muscle_soreness: v(2), stress: v(3), mood: v(4) };
}

export function demoRiskInputFor(p: SquadPlayer): RiskInput {
  const r = p.risk_score / 100;
  const hqRatio = 0.66 - r * 0.3;
  const asym = 3 + r * 16;
  const acwr = Math.round((0.85 + r * 0.8) * 100) / 100;
  const cmjDrop = r * 14;
  return {
    age: p.age,
    acwr,
    prevAcwr: Math.round((0.95 + r * 0.35) * 100) / 100,   // önceki pencere (riskli → akut sıçramış)
    hq: { hamstring: Math.round(hqRatio * 3.0 * 1000) / 1000, quadriceps: 3.0 },
    asymmetry: { left: 600, right: Math.round(600 * (1 - asym / 100) * 100) / 100 },
    cmj: { current: Math.round(50 * (1 - cmjDrop / 100) * 10) / 10, baseline: [50, 51, 49] },
    wellness: demoWellnessFields(r),
    regressionCount: r > 0.6 ? 2 : r > 0.4 ? 1 : 0,
  };
}

/** Birleşik endeksi kanonik risk_score'a sabitle — demo'da TEK görünen sayı tutarlı
 *  olsun (endeksin işi sayı uydurmak değil, kanonik skoru AÇIKLAMAK). Faktör
 *  katkıları orantılı ölçeklenir; seviye/öneri/ufuk kanonik skordan türer. */
function anchorToScore(idx: RiskIndex, target: number): RiskIndex {
  const raw = idx.score || 1;
  const k = target / raw;
  const factors = idx.factors
    .map((f) => ({ ...f, points: Math.min(f.weight, Math.round(f.points * k * 10) / 10) }))
    .sort((a, b) => b.points - a.points || (b.points / b.weight) - (a.points / a.weight));
  const level = levelOfUtil(target / 100);
  const topDriver = factors[0] ?? null;
  const recommendation = topDriver
    ? (REC_BY_FACTOR[topDriver.key]?.[level] ?? idx.recommendation)
    : idx.recommendation;
  return {
    ...idx, score: target, level, label: labelFromLevel[level],
    factors, topDriver, recommendation, horizonNote: HORIZON[level](idx.trend),
  };
}

/** Bir oyuncunun birleşik risk endeksi (demo: risk profilinden türev). */
export function computeRiskFor(playerId: number): RiskIndex {
  const p = demoSquad.find((s) => s.player_id === playerId);
  if (!p) return computeRiskIndex({});
  return anchorToScore(computeRiskIndex(demoRiskInputFor(p)), p.risk_score);
}

export interface SquadRiskRow { player: SquadPlayer; risk: RiskIndex }

/** Tüm kadro, birleşik endekse göre azalan sıralı (en riskli önce). */
export function squadRiskRanked(): SquadRiskRow[] {
  return demoSquad
    .map((player): SquadRiskRow => ({ player, risk: computeRiskFor(player.player_id) }))
    .sort((a, b) => b.risk.score - a.risk.score);
}

/** En riskli n oyuncu (medical uyarı paneli vb.). */
export function topRiskPlayers(n = 4): SquadRiskRow[] {
  return squadRiskRanked().slice(0, n);
}
