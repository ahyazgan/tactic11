/**
 * Oyuncu Gelişim Projeksiyonu — "6-18 ay sonra nerede olur, tavanı ne".
 *
 * Her özellik grubu FARKLI yaş eğrisine uyar (futbol literatürü):
 *   • Fiziksel  → zirve ~24, erken ve dik düşüş (hız/güç önce gider)
 *   • Teknik    → zirve ~28, yavaş düşüş
 *   • Zihinsel  → zirve ~30, çok yavaş düşüş (tecrübe yaşla artar)
 *   • Kaleci    → zirve ~30, geç düşüş (kaleciler uzun zirve)
 *
 * Oyuncunun MEVCUT 1-20 seviyesini (demoAttributesFor) kendi yaş eğrisine sabitler,
 * ileri/geri projekte eder: kariyer arkı + tavan (potansiyel) + zirve yaşı + faz +
 * scout/transfer reçetesi. Saf+deterministik. Scout/transfer modülünün satış noktası.
 */

import { demoSquad, demoAttributesFor, type SquadPlayer } from "@/lib/demo-data";

export type DevPhase = "gelişim" | "zirveye_yakın" | "zirvede" | "plato" | "düşüş";
export type DevTrend = "rising" | "stable" | "declining";

export const PHASE_LABEL: Record<DevPhase, string> = {
  "gelişim": "Gelişim", "zirveye_yakın": "Zirveye Yakın", "zirvede": "Zirvede",
  "plato": "Plato", "düşüş": "Düşüş",
};
export const PHASE_VAR: Record<DevPhase, string> = {
  "gelişim": "var(--low)", "zirveye_yakın": "var(--accent)", "zirvede": "var(--low)",
  "plato": "var(--mid)", "düşüş": "var(--high)",
};

// Grup adı → yaş eğrisi parametreleri: zirve yaşı + zirve öncesi/sonrası yıllık katsayı.
interface AgeCurve { peak: number; kPre: number; kPost: number }
const CURVES: Record<string, AgeCurve> = {
  "Fiziksel": { peak: 24, kPre: 0.030, kPost: 0.040 },
  "Teknik": { peak: 28, kPre: 0.022, kPost: 0.013 },
  "Zihinsel": { peak: 30, kPre: 0.025, kPost: 0.007 },
  "Kaleci": { peak: 30, kPre: 0.020, kPost: 0.010 },
};
const DEFAULT_CURVE: AgeCurve = { peak: 27, kPre: 0.024, kPost: 0.018 };

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** Yaş-performans faktörü (zirvede 1.0, iki yana doğru azalır), 0.45..1.0. */
function ageFactor(age: number, c: AgeCurve): number {
  const drop = age < c.peak ? c.kPre * (c.peak - age) : c.kPost * (age - c.peak);
  return clamp(1 - drop, 0.45, 1);
}

export interface DevPoint { age: number; overall: number; physical: number; technical: number; mental: number }
export interface GroupProjection { group: string; now: number; future: number; delta: number }

export interface PlayerDevelopment {
  currentAge: number;
  currentOverall: number;   // 1-20
  potential: number;        // gelecekteki tavan (1-20)
  peakAge: number;
  phase: DevPhase;
  trend: DevTrend;
  trajectory: DevPoint[];   // 18..34 yaş kariyer arkı
  groups: GroupProjection[];// +18 ay projeksiyonu (now → future)
  verdict: string;          // scout/transfer reçetesi
  confidence: number;       // 0..100 projeksiyon güveni
}

const AGE_MIN = 18, AGE_MAX = 34, HORIZON_AGE = 1.5; // +18 ay

/** Grup adını eğri anahtarına eşle (Teknik/Zihinsel/Fiziksel/Kaleci). */
const curveFor = (group: string) => CURVES[group] ?? DEFAULT_CURVE;

/** Bir oyuncunun gelişim projeksiyonu — mevcut özellikleri yaş eğrilerine sabitle. */
export function computeDevelopment(player: SquadPlayer): PlayerDevelopment {
  const a0 = player.age;
  const groups = demoAttributesFor(player.player_id);

  // Grup başına mevcut ortalama (1-20) + eğri.
  const grpNow = groups.map((g) => ({
    group: g.group,
    v0: g.attrs.reduce((s, x) => s + x.value, 0) / g.attrs.length,
    curve: curveFor(g.group),
  }));

  // Bir grubun a yaşındaki projeksiyonu: v0 × f(a)/f(a0), 1..20.
  const projGroup = (g: typeof grpNow[number], a: number) =>
    clamp(g.v0 * ageFactor(a, g.curve) / ageFactor(a0, g.curve), 1, 20);

  // Yaş eğrisinde "fiziksel/teknik/zihinsel" üçlüsünü ayıkla (Kaleci → teknik kovasına).
  const pick = (names: string[]) => grpNow.find((g) => names.includes(g.group));
  const phys = pick(["Fiziksel"]);
  const tech = pick(["Teknik", "Kaleci"]);
  const ment = pick(["Zihinsel"]);

  const overallAt = (a: number) =>
    grpNow.reduce((s, g) => s + projGroup(g, a), 0) / grpNow.length;

  // Kariyer arkı 18..34.
  const trajectory: DevPoint[] = [];
  for (let a = AGE_MIN; a <= AGE_MAX; a++) {
    trajectory.push({
      age: a,
      overall: Math.round(overallAt(a) * 10) / 10,
      physical: phys ? Math.round(projGroup(phys, a) * 10) / 10 : 0,
      technical: tech ? Math.round(projGroup(tech, a) * 10) / 10 : 0,
      mental: ment ? Math.round(projGroup(ment, a) * 10) / 10 : 0,
    });
  }

  const currentOverall = Math.round(overallAt(a0) * 10) / 10;
  const blendedPeak = grpNow.reduce((s, g) => s + g.curve.peak, 0) / grpNow.length;

  // Potansiyel = şimdiden ileri tavan (max overall). Zirve yaşı = eğrinin DOĞAL
  // tepe yaşı (clamp(20) artefaktıyla erkene kayan ilk-max değil); yaşlı oyuncuda
  // şimdiki yaşa sabitlenir (zaten düşüşte).
  let potential = currentOverall;
  for (let a = a0; a <= AGE_MAX; a++) potential = Math.max(potential, overallAt(a));
  potential = Math.round(potential * 10) / 10;
  const peakAge = clamp(Math.round(blendedPeak), a0, AGE_MAX);

  // +18 ay grup projeksiyonu.
  const groupsProj: GroupProjection[] = grpNow.map((g) => {
    const now = Math.round(g.v0 * 10) / 10;
    const future = Math.round(projGroup(g, a0 + HORIZON_AGE) * 10) / 10;
    return { group: g.group, now, future, delta: Math.round((future - now) * 10) / 10 };
  });

  // Trend: bir sonraki yıl overall yönü.
  const next = overallAt(a0 + 1);
  const trend: DevTrend = next - currentOverall > 0.1 ? "rising" : next - currentOverall < -0.1 ? "declining" : "stable";

  // Faz.
  let phase: DevPhase;
  if (a0 <= 21) phase = "gelişim";
  else if (a0 < blendedPeak - 1) phase = "zirveye_yakın";
  else if (a0 <= 28) phase = "zirvede";
  else if (a0 <= 31) phase = "plato";
  else phase = "düşüş";

  // Güven: zirve civarı tahmin daha kesin; çok genç/çok yaşlı belirsiz.
  const confidence = clamp(Math.round(90 - Math.abs(a0 - 26) * 1.3 - (a0 <= 20 ? 8 : 0)), 62, 90);

  // Scout/transfer reçetesi.
  const gap = Math.round((potential - currentOverall) * 10) / 10;
  let verdict: string;
  if (phase === "gelişim" || phase === "zirveye_yakın") {
    verdict = gap >= 1
      ? `Yükselen değer — tavan ~${potential.toFixed(1)} (${peakAge} yaş). Şimdi bağla/elde tut; piyasa değeri artacak.`
      : `Genç ve istikrarlı — düşük riskli yatırım, kademeli gelişim bekleniyor.`;
  } else if (phase === "zirvede") {
    verdict = `Zirve döneminde — en yüksek katkı yılları. Sözleşmeyi uzat, satış için erken.`;
  } else if (phase === "plato") {
    verdict = `Plato/hafif düşüş başlıyor — performansı izle; uzatmada süreyi sınırla, genç alternatif planla.`;
  } else {
    verdict = `Düşüş fazı — fiziksel gerileme hızlanıyor. Satış/rotasyon penceresi; halef hazırla.`;
  }

  return {
    currentAge: a0, currentOverall, potential, peakAge, phase, trend,
    trajectory, groups: groupsProj, verdict, confidence,
  };
}

/** Bir oyuncunun gelişim projeksiyonu (id'den). Deterministik → cache'li
 *  (computeDevelopment demoAttributesFor'u çağırır, ağır; komuta merkezi 24× çağırır). */
const _devCache = new Map<number, PlayerDevelopment>();
export function computeDevelopmentFor(playerId: number): PlayerDevelopment | null {
  const hit = _devCache.get(playerId);
  if (hit) return hit;
  const p = demoSquad.find((s) => s.player_id === playerId);
  if (!p) return null;
  const d = computeDevelopment(p);
  _devCache.set(playerId, d);
  return d;
}
