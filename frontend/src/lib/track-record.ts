/**
 * Tahmin Defteri & Track Record — modelin SÖYLEDİĞİNİ kaydet, OLANLA karşılaştır.
 *
 * Unicorn farkı: "AI tahmin ediyor" ucuz; "tahminlerimiz son N değerlendirmede
 * %X tuttu" güven satar. Bu motor her tahmini (maç sonucu, sakatlık riski,
 * dönüş tarihi, scout uyumu) defterleştirir; sonuç gelince isabet/ıska işaretler;
 * isabet oranı + Brier + kalibrasyon bucket'ları + tür kırılımı + son seri çıkarır.
 *
 * DEMO_MODE'da defter localStorage'da (gerçek girilen tahminler) + zengin,
 * deterministik bir geçmiş tohumu (demoPredictionLedger). Production'da aynı
 * şekiller backend reconcile job'ından gelir. Saf hesap — Math.random YOK.
 */

import { demoNextMatchSimulation } from "@/lib/match-simulation";

export const LS_PRED_KEY = "fi_demo_predictions";

export type PredictionType = "match" | "injury" | "rtp" | "scout";

export const TYPE_LABEL: Record<PredictionType, string> = {
  match: "Maç Sonucu",
  injury: "Sakatlık Riski",
  rtp: "Dönüş Tahmini",
  scout: "Scout Uyumu",
};
export const TYPE_GLYPH: Record<PredictionType, string> = {
  match: "⚽", injury: "🩹", rtp: "↩", scout: "🔎",
};

export interface Prediction {
  id: number;
  type: PredictionType;
  subject: string;          // "Beşiktaş vs Trabzonspor" / "Orkun Kökçü (10)"
  claim: string;            // okunur tahmin: "Galibiyet" / "7 günde yüksek risk"
  confidence: number;       // 0..1 model güveni (kalibrasyonun ekseni)
  made_at: string;          // YYYY-MM-DD
  horizon: string;          // "maç günü" / "14 gün" gibi
  status: "open" | "resolved";
  outcome?: {
    actual: string;         // gerçekleşen: "Galibiyet" / "sakatlandı"
    hit: boolean;           // tahmin tuttu mu
    resolved_at: string;    // YYYY-MM-DD
  };
}

export interface TypeAccuracy {
  type: PredictionType;
  resolved: number;
  hits: number;
  hitRate: number;          // 0..1
}

export interface CalibrationBucket {
  lower: number;
  upper: number;
  expected: number;         // bucket ortası (beklenen isabet)
  actual: number;           // gerçek isabet oranı
  count: number;
}

export interface TrackRecord {
  total: number;
  open: number;
  resolved: number;
  hits: number;
  hitRate: number;          // 0..1 — manşet güven sayısı
  brier: number | null;     // ikili Brier (güven vs isabet); ↓ iyi
  byType: TypeAccuracy[];
  buckets: CalibrationBucket[];
  streak: number;           // en son ardışık isabet sayısı (resolved, tarih sıralı)
  rollingHitRate: number | null;  // son 20 resolved
}

const round2 = (n: number) => Math.round(n * 100) / 100;

/** Resolved tahminlerden track record istatistiği — saf, defter-agnostik. */
export function computeTrackRecord(preds: Prediction[]): TrackRecord {
  const resolved = preds.filter((p) => p.status === "resolved" && p.outcome);
  const open = preds.filter((p) => p.status === "open").length;
  const hits = resolved.filter((p) => p.outcome!.hit).length;
  const hitRate = resolved.length ? hits / resolved.length : 0;

  // İkili Brier: (güven − isabet)². Düşük = güven gerçeği iyi yansıtıyor.
  const brier = resolved.length
    ? resolved.reduce((s, p) => s + Math.pow(p.confidence - (p.outcome!.hit ? 1 : 0), 2), 0) / resolved.length
    : null;

  // Tür kırılımı.
  const byType: TypeAccuracy[] = (Object.keys(TYPE_LABEL) as PredictionType[])
    .map((type) => {
      const r = resolved.filter((p) => p.type === type);
      const h = r.filter((p) => p.outcome!.hit).length;
      return { type, resolved: r.length, hits: h, hitRate: r.length ? h / r.length : 0 };
    })
    .filter((t) => t.resolved > 0);

  // Kalibrasyon bucket'ları (güven aralığına göre gerçek isabet).
  const edges = [0, 0.2, 0.4, 0.6, 0.8, 1.0001];
  const buckets: CalibrationBucket[] = [];
  for (let i = 0; i < edges.length - 1; i++) {
    const lo = edges[i], hi = edges[i + 1];
    const inB = resolved.filter((p) => p.confidence >= lo && p.confidence < hi);
    if (!inB.length) continue;
    const actual = inB.filter((p) => p.outcome!.hit).length / inB.length;
    buckets.push({
      lower: lo, upper: Math.min(1, hi), expected: round2((lo + Math.min(1, hi)) / 2),
      actual: round2(actual), count: inB.length,
    });
  }

  // Tarih sıralı resolved (eski→yeni) üzerinden en son seri + rolling.
  const chrono = [...resolved].sort((a, b) =>
    a.outcome!.resolved_at.localeCompare(b.outcome!.resolved_at) || a.id - b.id);
  let streak = 0;
  for (let i = chrono.length - 1; i >= 0; i--) {
    if (chrono[i].outcome!.hit) streak++; else break;
  }
  const last20 = chrono.slice(-20);
  const rollingHitRate = last20.length ? last20.filter((p) => p.outcome!.hit).length / last20.length : null;

  return {
    total: preds.length, open, resolved: resolved.length, hits,
    hitRate, brier: brier != null ? round2(brier) : null,
    byType, buckets, streak, rollingHitRate,
  };
}

// ── localStorage deposu (gerçek girilen tahminler) ──────────────────────────
export function loadPredictions(): Prediction[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LS_PRED_KEY);
    return raw ? (JSON.parse(raw) as Prediction[]) : [];
  } catch {
    return [];
  }
}

export function savePredictions(preds: Prediction[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_PRED_KEY, JSON.stringify(preds));
  } catch {
    /* kota/erişim — yoksay */
  }
}

/** Yeni tahmin defterle (open). Çağıran taraf id'yi benzersiz verir. */
export function logPrediction(p: Omit<Prediction, "status" | "outcome">): Prediction {
  const rec: Prediction = { ...p, status: "open" };
  savePredictions([rec, ...loadPredictions()]);
  return rec;
}

/** Açık bir tahmini sonuçla kapat. */
export function resolvePrediction(id: number, actual: string, hit: boolean, resolvedAt: string): void {
  const all = loadPredictions().map((p) =>
    p.id === id ? { ...p, status: "resolved" as const, outcome: { actual, hit, resolved_at: resolvedAt } } : p);
  savePredictions(all);
}

// ── Demo defter tohumu — deterministik, inandırıcı geçmiş ────────────────────
// ~72% isabet, kalibre (yüksek güven bucket'ı daha çok tutar). Math.random YOK:
// indeks tabanlı sinüs hash ile hit kararı güvene göre kalibre edilir.

function hash01(i: number): number {
  const x = Math.sin(i * 12.9898 + 4.1337) * 43758.5453;
  return x - Math.floor(x);
}
// İsabet çekilişi için AYRI (decorrelated) hash — güven hash'inden bağımsız olmalı
// ki kalibrasyon gerçekçi olsun (seçilen seed: bucket'lar monotonik, ECE ~0.07).
function hitHash01(i: number): number {
  const x = Math.sin(i * 78.233 + 39.42) * 43758.5453;
  return x - Math.floor(x);
}
function dateMinus(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

const MATCH_FIXTURES: { opp: string; ha: "İç" | "Dış" }[] = [
  { opp: "Trabzonspor", ha: "Dış" }, { opp: "Kasımpaşa", ha: "İç" },
  { opp: "Eyüpspor", ha: "İç" }, { opp: "Çaykur Rizespor", ha: "Dış" },
  { opp: "Gaziantep FK", ha: "İç" }, { opp: "Konyaspor", ha: "Dış" },
  { opp: "Samsunspor", ha: "İç" }, { opp: "Hatayspor", ha: "Dış" },
  { opp: "Sivasspor", ha: "İç" }, { opp: "Alanyaspor", ha: "Dış" },
  { opp: "Antalyaspor", ha: "İç" }, { opp: "Kayserispor", ha: "Dış" },
];
const MATCH_RESULTS = ["Galibiyet", "Beraberlik", "Mağlubiyet"] as const;
const INJURY_SUBJECTS = [
  "Orkun Kökçü (10)", "Rıdvan Yılmaz (3)", "Felix Uduokhai (15)",
  "Tiago Djaló (4)", "El Bilal Touré (19)", "Kristjan Asllani (16)",
];
const RTP_SUBJECTS = ["Kartal Yılmaz (18)", "Taylan Bulut (24)", "Kristjan Asllani (16)", "Tiago Djaló (4)"];
const SCOUT_SUBJECTS = ["Sol bek hedefi A", "10 numara hedefi B", "Stoper hedefi C", "Santrfor hedefi D"];

/** Inandırıcı, deterministik geçmiş defter (resolved) + birkaç açık tahmin. */
export function demoPredictionLedger(): Prediction[] {
  const out: Prediction[] = [];
  let id = 1000;

  // Güvene göre KALİBRE isabet: isabet çekilişi güven hash'inden BAĞIMSIZ.
  // hitHash < confidence ⇒ bucket başına gerçek isabet ≈ güven ortası (iyi kalibrasyon).
  const hit = (i: number, confidence: number) => hitHash01(i) < confidence;

  // Maç tahminleri (12 geçmiş).
  MATCH_FIXTURES.forEach((fx, k) => {
    const i = id++;
    const conf = round2(0.42 + (hash01(i) * 0.46));        // 0.42..0.88
    const claim = conf >= 0.6 ? "Galibiyet" : conf >= 0.45 ? "Beraberlik/Galibiyet" : "Çekişmeli";
    const h = hit(i, conf);
    const actual = h ? "Galibiyet" : MATCH_RESULTS[1 + (i % 2)];  // ıska → beraberlik/mağlubiyet
    const made = 6 + (MATCH_FIXTURES.length - k) * 6;
    out.push({
      id: i, type: "match", subject: `Beşiktaş vs ${fx.opp} (${fx.ha})`,
      claim: `${claim} · güven %${Math.round(conf * 100)}`, confidence: conf,
      made_at: dateMinus(made + 1), horizon: "maç günü",
      status: "resolved", outcome: { actual, hit: h, resolved_at: dateMinus(made) },
    });
  });

  // Sakatlık riski tahminleri (12 geçmiş) — "14 günde yüksek risk" iddiası.
  for (let k = 0; k < 12; k++) {
    const i = id++;
    const subj = INJURY_SUBJECTS[k % INJURY_SUBJECTS.length];
    const conf = round2(0.5 + hash01(i) * 0.4);            // 0.5..0.9
    const h = hit(i, conf);
    const made = 16 + k * 2;
    out.push({
      id: i, type: "injury", subject: subj,
      claim: `14 günde yüksek sakatlık riski · güven %${Math.round(conf * 100)}`, confidence: conf,
      made_at: dateMinus(made + 14), horizon: "14 gün",
      status: "resolved",
      outcome: { actual: h ? "kas/yük sorunu yaşadı" : "sorunsuz tamamladı", hit: h, resolved_at: dateMinus(made) },
    });
  }

  // Dönüş tahminleri (8 geçmiş) — "X tarihinde dönüş".
  for (let k = 0; k < 8; k++) {
    const i = id++;
    const subj = RTP_SUBJECTS[k % RTP_SUBJECTS.length];
    const conf = round2(0.55 + hash01(i) * 0.35);
    const h = hit(i, conf);
    const made = 10 + k * 3;
    out.push({
      id: i, type: "rtp", subject: subj,
      claim: `Tahmini dönüş ±3 gün · güven %${Math.round(conf * 100)}`, confidence: conf,
      made_at: dateMinus(made + 10), horizon: "pencere",
      status: "resolved",
      outcome: { actual: h ? "pencerede döndü" : "gecikti / erken döndü", hit: h, resolved_at: dateMinus(made) },
    });
  }

  // Scout uyumu (6 geçmiş) — "hedef şu profile uyar".
  for (let k = 0; k < 6; k++) {
    const i = id++;
    const subj = SCOUT_SUBJECTS[k % SCOUT_SUBJECTS.length];
    const conf = round2(0.48 + hash01(i) * 0.4);
    const h = hit(i, conf);
    const made = 30 + k * 8;
    out.push({
      id: i, type: "scout", subject: subj,
      claim: `Sistem uyumu yüksek · güven %${Math.round(conf * 100)}`, confidence: conf,
      made_at: dateMinus(made + 30), horizon: "sezon",
      status: "resolved",
      outcome: { actual: h ? "beklenen katkıyı verdi" : "beklentinin altında", hit: h, resolved_at: dateMinus(made) },
    });
  }

  // Açık tahminler (henüz sonuçlanmadı) — sıradaki maç + aktif risk izlemleri.
  // Maç tahmininin güveni DOĞRUDAN simülasyondan (Poisson-Dixon-Coles galibiyet olasılığı).
  const sim = demoNextMatchSimulation();
  out.push({
    id: id++, type: "match", subject: `${sim.homeTeam} vs ${sim.awayTeam} (İç)`,
    claim: `En olası ${sim.mostLikelyScore[0]}-${sim.mostLikelyScore[1]} · galibiyet güveni %${Math.round(sim.probHomeWin * 100)}`,
    confidence: sim.probHomeWin,
    made_at: dateMinus(0), horizon: "maç günü", status: "open",
  });
  out.push({
    id: id++, type: "injury", subject: "Orkun Kökçü (10)",
    claim: "14 günde yüksek sakatlık riski · güven %78", confidence: 0.78,
    made_at: dateMinus(0), horizon: "14 gün", status: "open",
  });
  out.push({
    id: id++, type: "rtp", subject: "Kartal Yılmaz (18)",
    claim: "2 gün içinde kadroya dönüş · güven %88", confidence: 0.88,
    made_at: dateMinus(0), horizon: "pencere", status: "open",
  });

  return out;
}

/** Demo track record (tohum + varsa localStorage girilen tahminler birleşik). */
export function demoTrackRecord(): TrackRecord {
  return computeTrackRecord([...demoPredictionLedger(), ...loadPredictions()]);
}
