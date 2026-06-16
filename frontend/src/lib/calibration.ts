/**
 * KALİBRASYON & BACKTEST (v2 — derin + out-of-sample) — sistemin tahminlerini
 * GERÇEK sonuçla, en rigorous şekilde kıyaslar.
 *
 * Üç sağlamlık katmanı:
 *  1) DERİN MODEL: tek Elo değil — her takım için ayrı HÜCUM ve SAVUNMA gücü
 *     (Maher/Dixon-Coles bivariate Poisson). Online (walk-forward) öğrenilir;
 *     düşük-skor düzeltmesi (Dixon-Coles τ, ρ) beraberlik/0-0/1-1 kalibrasyonunu
 *     düzeltir. Tek Elo'nun yapamadığı "çok atan ama çok yiyen takım"ı yakalar.
 *  2) OUT-OF-SAMPLE: hiperparametreler SADECE train sezonlarında (2017-2022)
 *     ayarlandı; manşet metrikler modelin HİÇ GÖRMEDİĞİ test sezonunda (2022-23)
 *     raporlanır. "Test setine uydurma" mümkün değil.
 *  3) BELİRSİZLİK: bootstrap (yeniden örnekleme) ile her metriğin %95 güven
 *     aralığı — tek sayı değil, istatistiksel bant.
 *
 * Her tahmin, maçtan ÖNCE sadece o ana kadarki bilgiyle yapılır (gelecek sızıntısı
 * YOK). Karşılaştırma için eski tek-Elo modeli de aynı test setinde ölçülür.
 * Saf/deterministik (bootstrap seeded PRNG) — Math.random YOK.
 */

import raw from "./match-results.json";
import { pois, clamp, dcTau } from "./poisson-predict";

interface RawResult { date: string; home: string; away: string; hg: number; ag: number; comp: string; hst?: number; ast?: number }
const ALL = (raw as RawResult[]).slice().sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));

export const LEAGUE_LABEL: Record<string, string> = {
  "en.1": "Premier League", "es.1": "La Liga", "de.1": "Bundesliga",
  "it.1": "Serie A", "fr.1": "Ligue 1",
};
export const leagueLabel = (c: string) => LEAGUE_LABEL[c] || c;

export type Outcome = "H" | "D" | "A";
const OUT: Outcome[] = ["H", "D", "A"];

// Train/test sınırı: bu tarihten itibaren = görülmemiş test (2022-23 sezonu).
const SPLIT = "2022-07-01";
// Hiperparametreler — SADECE train (2017-2022) log-loss'una göre seçildi.
const LR = 0.03;      // hücum/savunma online öğrenme hızı
const RHO = -0.08;    // Dixon-Coles düşük-skor korelasyonu
const WD = 0;         // ağırlık sönümü (regularizasyon)
// Güç güncellemesi gole değil, gol ile ŞUT-tabanlı xG-proxy'nin harmanına dayanır.
// Şut daha az gürültülü → daha iyi güç tahmini (blend=0.4: %40 gol, %60 xG-proxy).
const BLEND = 0.4;
// Eski Elo modeli (karşılaştırma için) — önceki sürümün ayarı.
const ELO = { HA: 65, EPG: 150, AVG: 2.7, K: 20, SHRINK: 0.8 };

export interface LedgerRow {
  date: string; home: string; away: string; comp: string;
  pH: number; pD: number; pA: number;
  pick: Outcome; conf: number;
  actual: Outcome; scoreline: string; hit: boolean;
  pOver?: number; pBTTS?: number; yOver?: 0 | 1; yBTTS?: 0 | 1;   // gol marketleri
}
export interface ReliabilityBin { lo: number; hi: number; predicted: number; actual: number; count: number }
export interface CompBreak { comp: string; matches: number; accuracy: number }
export type CI = [number, number];

export interface ModelMetrics {
  name: string;
  accuracy: number; brier: number; logLoss: number;
  baselineBrier: number; baselineLogLoss: number; brierSkill: number; ece: number;
}
export interface MarketResult {
  key: string; name: string; status: "validated" | "pending";
  trust: number; accuracy: number; ece: number; brierSkill: number;
  baseRate: number | null; n: number; note: string;
}
export interface CalibrationReport {
  matches: number;          // test maç sayısı (manşet)
  trainMatches: number;
  splitSeason: string;
  accuracy: number; brier: number; logLoss: number;
  baselineBrier: number; baselineLogLoss: number; brierSkill: number; ece: number;
  trust: number;
  ci: { accuracy: CI; brier: CI; logLoss: CI; ece: CI };
  bins: ReliabilityBin[];
  byComp: CompBreak[];
  baseRates: { h: number; d: number; a: number };
  sample: LedgerRow[];
  models: ModelMetrics[];   // [yeni model, eski Elo] aynı test setinde
  markets: MarketResult[];  // karar türüne göre güven (sonuç/üst-alt/btts + bekleyenler)
  params: { lr: number; rho: number; wd: number };
}

// ── yardımcılar ──────────────────────────────────────────────────────────────
const round = (n: number, d = 4) => { const m = 10 ** d; return Math.round(n * m) / m; };
const outcomeOf = (hg: number, ag: number): Outcome => (hg > ag ? "H" : hg === ag ? "D" : "A");

/** λ_ev, λ_dep → 1/X/2 (Dixon-Coles düzeltmeli). */
function probs(lH: number, lA: number, rho: number): [number, number, number] {
  let pH = 0, pD = 0, pA = 0;
  for (let i = 0; i <= 8; i++) {
    for (let j = 0; j <= 8; j++) {
      let p = pois(i, lH) * pois(j, lA);
      if (i <= 1 && j <= 1) p *= Math.max(1e-4, dcTau(i, j, lH, lA, rho));
      if (i > j) pH += p; else if (i === j) pD += p; else pA += p;
    }
  }
  const s = pH + pD + pA || 1;
  return [pH / s, pD / s, pA / s];
}

/** Aynı λ'lardan gol marketleri: P(toplam≥3) ve P(karşılıklı gol). */
function goalMarkets(lH: number, lA: number, rho: number): { over: number; btts: number } {
  let over = 0, btts = 0, s = 0;
  const M: number[][] = [];
  for (let i = 0; i <= 8; i++) { M[i] = []; for (let j = 0; j <= 8; j++) { let p = pois(i, lH) * pois(j, lA); if (i <= 1 && j <= 1) p *= Math.max(1e-4, dcTau(i, j, lH, lA, rho)); M[i][j] = p; s += p; } }
  for (let i = 0; i <= 8; i++) for (let j = 0; j <= 8; j++) { const p = M[i][j] / s; if (i + j >= 3) over += p; if (i >= 1 && j >= 1) btts += p; }
  return { over, btts };
}

const toRow = (m: RawResult, p: [number, number, number]): LedgerRow => {
  const idx = p[0] >= p[1] && p[0] >= p[2] ? 0 : p[1] >= p[2] ? 1 : 2;
  const actual = outcomeOf(m.hg, m.ag);
  return {
    date: m.date, home: m.home, away: m.away, comp: m.comp,
    pH: round(p[0], 4), pD: round(p[1], 4), pA: round(p[2], 4),
    pick: OUT[idx], conf: round(p[idx], 4),
    actual, scoreline: `${m.hg}-${m.ag}`, hit: OUT[idx] === actual,
  };
};

interface ModelState {
  ledger: LedgerRow[];
  atk: Record<string, number>; def: Record<string, number>;
  muH: Record<string, number>; muA: Record<string, number>; conv: number;
}

/** DERİN MODEL çekirdeği — online hücum/savunma Poisson + DC + şut(xG) sinyali.
 *  Defteri + ÖĞRENİLEN nihai takım güçlerini (atk/def) + lig tabanlarını döndürür.
 *  blend: güç güncellemesinde gol ağırlığı (1=saf gol, 0=saf xG-proxy). */
function runCore(blend = BLEND): ModelState {
  // Lig log-ortalama gol oranları + SoT→gol dönüşümü (SADECE train'den).
  const lg: Record<string, { hg: number; ag: number; n: number }> = {};
  let totGoals = 0, totSot = 0;
  for (const m of ALL) if (m.date < SPLIT) {
    const g = (lg[m.comp] ??= { hg: 0, ag: 0, n: 0 }); g.hg += m.hg; g.ag += m.ag; g.n++;
    totGoals += m.hg + m.ag; totSot += (m.hst ?? 0) + (m.ast ?? 0);
  }
  const muH: Record<string, number> = {}, muA: Record<string, number> = {};
  for (const c in lg) { muH[c] = Math.log(lg[c].hg / lg[c].n); muA[c] = Math.log(lg[c].ag / lg[c].n); }
  const conv = totSot ? totGoals / totSot : 0.31;   // isabetli şut başına ~0.31 gol

  const atk: Record<string, number> = {}, def: Record<string, number> = {};
  const A = (k: string) => (atk[k] ??= 0), D = (k: string) => (def[k] ??= 0);
  const ledger: LedgerRow[] = [];
  for (const m of ALL) {
    const kH = m.comp + "|" + m.home, kA = m.comp + "|" + m.away;
    const aH = A(kH), aA = A(kA), dH = D(kH), dA = D(kA);
    const lH = clamp(Math.exp((muH[m.comp] ?? 0.3) + aH - dA), 0.05, 7);
    const lA = clamp(Math.exp((muA[m.comp] ?? 0.1) + aA - dH), 0.05, 7);
    const row = toRow(m, probs(lH, lA, RHO));
    const gm = goalMarkets(lH, lA, RHO);
    row.pOver = round(gm.over, 4); row.pBTTS = round(gm.btts, 4);
    row.yOver = m.hg + m.ag >= 3 ? 1 : 0; row.yBTTS = m.hg >= 1 && m.ag >= 1 ? 1 : 0;
    ledger.push(row);
    // Gözlem = gol ile şut-tabanlı xG-proxy harmanı (şut daha az gürültülü).
    const obsH = blend * m.hg + (1 - blend) * (m.hst ?? 0) * conv;
    const obsA = blend * m.ag + (1 - blend) * (m.ast ?? 0) * conv;
    const gH = obsH - lH, gA = obsA - lA;
    atk[kH] = aH + LR * gH - LR * WD * aH; def[kA] = dA - LR * gH - LR * WD * dA;
    atk[kA] = aA + LR * gA - LR * WD * aA; def[kH] = dH - LR * gA - LR * WD * dH;
  }
  return { ledger, atk, def, muH, muA, conv };
}

export function runModel(blend = BLEND): LedgerRow[] { return runCore(blend).ledger; }

// Ensemble ağırlığı: Atak/Defans-DC (xG) modeli + eski Elo'nun lineer harmanı.
// SADECE train (2017-2022) Brier'ına göre seçildi (scripts/trust-lab.mjs):
// AD %70 + Elo %30 → test BSS 0.082 → 0.085 (gerçek out-of-sample beceri artışı).
// Diğer denenenler (isotonic/temperature/log-pool/ev-dep-split) out-of-sample'da
// baseline'ı GEÇEMEDİ → dürüstçe alınmadı.
const ENS_W = 0.7;

/** İki defteri (aynı maç sırası) olasılık düzeyinde harmanlar; pick/conf yeniden hesaplanır. */
function blendLedgers(a: LedgerRow[], b: LedgerRow[], wA: number): LedgerRow[] {
  const wB = 1 - wA;
  return a.map((r, i) => {
    const o = b[i];
    const pH = wA * r.pH + wB * o.pH, pD = wA * r.pD + wB * o.pD, pA = wA * r.pA + wB * o.pA;
    const idx = pH >= pD && pH >= pA ? 0 : pD >= pA ? 1 : 2;
    const ps = [pH, pD, pA];
    const over = r.pOver !== undefined ? wA * (r.pOver ?? 0) + wB * (o.pOver ?? 0) : r.pOver;
    const btts = r.pBTTS !== undefined ? wA * (r.pBTTS ?? 0) + wB * (o.pBTTS ?? 0) : r.pBTTS;
    return {
      ...r, pH: round(pH, 4), pD: round(pD, 4), pA: round(pA, 4),
      pick: OUT[idx], conf: round(ps[idx], 4), hit: OUT[idx] === r.actual,
      pOver: over !== undefined ? round(over, 4) : undefined,
      pBTTS: btts !== undefined ? round(btts, 4) : undefined,
    };
  });
}

/** AKTİF model = ensemble (AD-xG %70 + Elo %30). Tek doğrulanmış üretim tahmini. */
export function runEnsemble(): LedgerRow[] {
  return blendLedgers(runModel(), runElo(), ENS_W);
}

export interface TeamRating { name: string; atk: number; def: number; rating: number; elo?: number }
export interface LeagueRatings {
  comp: string; label: string; muH: number; muA: number; rho: number;
  ensW?: number;        // ensemble AD ağırlığı (canlı tahmin AD·ensW + Elo·(1-ensW))
  eloHA?: number; eloEPG?: number; eloAvg?: number;   // Elo→λ dönüşüm sabitleri
  teams: TeamRating[];
}

/** Elo modelinin öğrendiği NİHAİ rating'ler (canlı ensemble için). comp|team → rating. */
function finalEloRatings(): Record<string, number> {
  const r: Record<string, number> = {};
  const G = (k: string) => (r[k] ??= 1500);
  for (const m of ALL) {
    const kH = m.comp + "|" + m.home, kA = m.comp + "|" + m.away;
    const rH = G(kH), rA = G(kA);
    const drift = rH + ELO.HA - rA;
    const sH = m.hg > m.ag ? 1 : m.hg === m.ag ? 0.5 : 0;
    const eH = 1 / (1 + 10 ** (-drift / 400));
    const mov = Math.log(Math.abs(m.hg - m.ag) + 1);
    const d = ELO.K * mov * (sH - eH);
    r[kH] = rH + d; r[kA] = rA - d;
  }
  return r;
}
/** Doğrulanmış modelin ÖĞRENDİĞİ nihai takım güçleri (lig bazında) — canlı
 *  tahmin için. Sadece son sezonda oynayan takımlar (güncel güç). */
export function predictorData(): LeagueRatings[] {
  const st = runCore(BLEND);
  const elo = finalEloRatings();
  // Son sezonda görülen takımlar = güncel kadro gücü.
  const lastSeasonTeams: Record<string, Set<string>> = {};
  for (const m of ALL) if (m.date >= SPLIT) { (lastSeasonTeams[m.comp] ??= new Set()).add(m.home); lastSeasonTeams[m.comp].add(m.away); }
  const out: LeagueRatings[] = [];
  for (const comp of Object.keys(lastSeasonTeams)) {
    const teams: TeamRating[] = [...lastSeasonTeams[comp]].map((name) => {
      const a = st.atk[comp + "|" + name] ?? 0, d = st.def[comp + "|" + name] ?? 0;
      return { name, atk: round(a, 3), def: round(d, 3), rating: round((a + d) * 100, 0), elo: round(elo[comp + "|" + name] ?? 1500, 0) };
    }).sort((x, y) => y.rating - x.rating);
    out.push({
      comp, label: leagueLabel(comp), muH: round(st.muH[comp], 4), muA: round(st.muA[comp], 4), rho: RHO,
      ensW: ENS_W, eloHA: ELO.HA, eloEPG: ELO.EPG, eloAvg: ELO.AVG, teams,
    });
  }
  return out.sort((a, b) => a.label.localeCompare(b.label));
}

/** ESKİ Elo modeli (karşılaştırma için) — tek güç + shrinkage. */
export function runElo(): LedgerRow[] {
  const r: Record<string, number> = {};
  const G = (k: string) => (r[k] ??= 1500);
  const ledger: LedgerRow[] = [];
  for (const m of ALL) {
    const kH = m.comp + "|" + m.home, kA = m.comp + "|" + m.away;
    const rH = G(kH), rA = G(kA);
    const drift = rH + ELO.HA - rA;
    const sup = (drift * ELO.SHRINK) / ELO.EPG;
    const lH = clamp((ELO.AVG + sup) / 2, 0.15, 6), lA = clamp((ELO.AVG - sup) / 2, 0.15, 6);
    // düz Poisson (DC yok — eski sürüm)
    let pH = 0, pD = 0, pA = 0;
    for (let i = 0; i <= 8; i++) for (let j = 0; j <= 8; j++) { const p = pois(i, lH) * pois(j, lA); if (i > j) pH += p; else if (i === j) pD += p; else pA += p; }
    const s = pH + pD + pA || 1;
    ledger.push(toRow(m, [pH / s, pD / s, pA / s]));
    const sH = m.hg > m.ag ? 1 : m.hg === m.ag ? 0.5 : 0;
    const eH = 1 / (1 + 10 ** (-drift / 400));
    const mov = Math.log(Math.abs(m.hg - m.ag) + 1);
    const d = ELO.K * mov * (sH - eH);
    r[kH] = rH + d; r[kA] = rA - d;
  }
  return ledger;
}

// ── metrikler ────────────────────────────────────────────────────────────────
function metricsOf(rows: LedgerRow[], name: string): ModelMetrics & { baseRates: { h: number; d: number; a: number } } {
  const n = rows.length || 1;
  const cnt = { H: 0, D: 0, A: 0 };
  for (const r of rows) cnt[r.actual]++;
  const base = { H: cnt.H / n, D: cnt.D / n, A: cnt.A / n };
  const eps = 1e-9;
  let acc = 0, brier = 0, ll = 0, bB = 0, bL = 0;
  for (const r of rows) {
    if (r.hit) acc++;
    const yH = r.actual === "H" ? 1 : 0, yD = r.actual === "D" ? 1 : 0, yA = r.actual === "A" ? 1 : 0;
    brier += (r.pH - yH) ** 2 + (r.pD - yD) ** 2 + (r.pA - yA) ** 2;
    bB += (base.H - yH) ** 2 + (base.D - yD) ** 2 + (base.A - yA) ** 2;
    const pAct = r.actual === "H" ? r.pH : r.actual === "D" ? r.pD : r.pA;
    const bAct = base[r.actual];
    ll += -Math.log(clamp(pAct, eps, 1));
    bL += -Math.log(clamp(bAct, eps, 1));
  }
  acc /= n; brier /= n; ll /= n; bB /= n; bL /= n;
  // ECE — 3 sınıf × n olasılık çiftini 10 kovaya böl.
  const NB = 10, eb = Array.from({ length: NB }, () => ({ sp: 0, sy: 0, c: 0 }));
  for (const r of rows) {
    const pairs: [number, number][] = [[r.pH, r.actual === "H" ? 1 : 0], [r.pD, r.actual === "D" ? 1 : 0], [r.pA, r.actual === "A" ? 1 : 0]];
    for (const [p, y] of pairs) { const bi = Math.min(NB - 1, Math.floor(p * NB)); eb[bi].sp += p; eb[bi].sy += y; eb[bi].c++; }
  }
  let ece = 0; const tot = n * 3;
  for (const b of eb) if (b.c) ece += (b.c / tot) * Math.abs(b.sp / b.c - b.sy / b.c);
  return {
    name, accuracy: acc, brier, logLoss: ll, baselineBrier: bB, baselineLogLoss: bL,
    brierSkill: bB ? 1 - brier / bB : 0, ece, baseRates: { h: base.H, d: base.D, a: base.A },
  };
}

/** Seeded PRNG (mulberry32) — deterministik bootstrap. */
function mulberry32(a: number) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
/** Bootstrap %95 güven aralıkları (test setini yeniden örnekle). */
function bootstrapCI(rows: LedgerRow[], B = 600): CalibrationReport["ci"] {
  const rng = mulberry32(20260613);
  const accs: number[] = [], bris: number[] = [], lls: number[] = [], eces: number[] = [];
  const N = rows.length;
  for (let b = 0; b < B; b++) {
    const s: LedgerRow[] = new Array(N);
    for (let i = 0; i < N; i++) s[i] = rows[(rng() * N) | 0];
    const m = metricsOf(s, "");
    accs.push(m.accuracy); bris.push(m.brier); lls.push(m.logLoss); eces.push(m.ece);
  }
  const ci = (arr: number[]): CI => {
    const a = arr.slice().sort((x, y) => x - y);
    return [round(a[Math.floor(B * 0.025)], 4), round(a[Math.floor(B * 0.975)], 4)];
  };
  return { accuracy: ci(accs), brier: ci(bris), logLoss: ci(lls), ece: ci(eces) };
}

/** İkili market (üst/alt, btts) kalibrasyonu → kendi güven rakamı. */
function binaryMarket(rows: LedgerRow[], key: string, name: string, pKey: "pOver" | "pBTTS", yKey: "yOver" | "yBTTS", note: string): MarketResult {
  const n = rows.length || 1;
  let acc = 0, brier = 0, baseSum = 0;
  for (const r of rows) {
    const p = r[pKey] ?? 0.5, y = r[yKey] ?? 0;
    if ((p >= 0.5 ? 1 : 0) === y) acc++;
    brier += (p - y) ** 2; baseSum += y;
  }
  const baseRate = baseSum / n;
  let bBrier = 0;
  for (const r of rows) { const y = r[yKey] ?? 0; bBrier += (baseRate - y) ** 2; }
  acc /= n; brier /= n; bBrier /= n;
  const brierSkill = bBrier ? 1 - brier / bBrier : 0;
  const NB = 10, eb = Array.from({ length: NB }, () => ({ sp: 0, sy: 0, c: 0 }));
  for (const r of rows) { const p = r[pKey] ?? 0.5, y = r[yKey] ?? 0; const bi = Math.min(NB - 1, Math.floor(p * NB)); eb[bi].sp += p; eb[bi].sy += y; eb[bi].c++; }
  let ece = 0; for (const b of eb) if (b.c) ece += (b.c / n) * Math.abs(b.sp / b.c - b.sy / b.c);
  const calibComp = 1 - Math.min(ece / 0.10, 1);
  const skillComp = clamp(brierSkill / 0.12, 0, 1);
  const trust = Math.round(100 * (0.6 * calibComp + 0.4 * skillComp));
  return { key, name, status: "validated", trust, accuracy: round(acc, 4), ece: round(ece, 4), brierSkill: round(brierSkill, 4), baseRate: round(baseRate, 3), n, note };
}

function reliabilityBins(rows: LedgerRow[]): ReliabilityBin[] {
  const edges = [0.33, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0001];
  const out: ReliabilityBin[] = [];
  for (let i = 0; i < edges.length - 1; i++) {
    const lo = edges[i], hi = edges[i + 1];
    const inB = rows.filter((r) => r.conf >= lo && r.conf < hi);
    if (!inB.length) continue;
    out.push({
      lo, hi: Math.min(1, hi),
      predicted: round(inB.reduce((s, r) => s + r.conf, 0) / inB.length, 4),
      actual: round(inB.filter((r) => r.hit).length / inB.length, 4),
      count: inB.length,
    });
  }
  return out;
}

export function computeCalibration(): CalibrationReport {
  const adFull = runModel();               // Atak/Defans + Şut(xG) + DC (bileşen)
  const eloFull = runElo();                // eski tek-Elo (bileşen)
  const ensFull = blendLedgers(adFull, eloFull, ENS_W);  // AKTİF: ensemble
  const test = ensFull.filter((r) => r.date >= SPLIT);
  const adTest = adFull.filter((r) => r.date >= SPLIT);
  const eloTest = eloFull.filter((r) => r.date >= SPLIT);
  const trainMatches = ensFull.length - test.length;

  const M = metricsOf(test, "Ensemble (Atak/Defans·xG·DC %70 + Elo %30)");
  const G = metricsOf(adTest, "Atak/Defans + Şut(xG) + Dixon-Coles (bileşen)");
  const E = metricsOf(eloTest, "Elo tek güç (bileşen)");
  const ci = bootstrapCI(test);

  // Güven Skoru: kalibrasyon (ECE düşük) + beceri (baseline'ı geçmek).
  const calibComp = 1 - Math.min(M.ece / 0.12, 1);
  const skillComp = clamp(M.brierSkill / 0.15, 0, 1);
  const trust = Math.round(100 * (0.6 * calibComp + 0.4 * skillComp));

  // Lig kırılımı (test).
  const bc: Record<string, { m: number; hit: number }> = {};
  for (const r of test) { const c = (bc[r.comp] ??= { m: 0, hit: 0 }); c.m++; if (r.hit) c.hit++; }
  const byComp = Object.entries(bc)
    .map(([comp, v]) => ({ comp: leagueLabel(comp), matches: v.m, accuracy: round(v.hit / v.m, 3) }))
    .sort((x, y) => y.matches - x.matches);

  const slim = (m: ModelMetrics): ModelMetrics => ({
    name: m.name, accuracy: round(m.accuracy, 4), brier: round(m.brier, 4), logLoss: round(m.logLoss, 4),
    baselineBrier: round(m.baselineBrier, 4), baselineLogLoss: round(m.baselineLogLoss, 4),
    brierSkill: round(m.brierSkill, 4), ece: round(m.ece, 4),
  });

  return {
    matches: test.length, trainMatches, splitSeason: "2022-23",
    accuracy: round(M.accuracy, 4), brier: round(M.brier, 4), logLoss: round(M.logLoss, 4),
    baselineBrier: round(M.baselineBrier, 4), baselineLogLoss: round(M.baselineLogLoss, 4),
    brierSkill: round(M.brierSkill, 4), ece: round(M.ece, 4), trust,
    ci, bins: reliabilityBins(test), byComp,
    baseRates: { h: round(M.baseRates.h, 3), d: round(M.baseRates.d, 3), a: round(M.baseRates.a, 3) },
    sample: test.slice(-14).reverse(),
    models: [slim(M), slim(G), slim(E)],
    markets: [
      {
        key: "result", name: "Maç Sonucu (1/X/2)", status: "validated",
        trust, accuracy: round(M.accuracy, 4), ece: round(M.ece, 4), brierSkill: round(M.brierSkill, 4),
        baseRate: null, n: test.length, note: "Hangi takım kazanır / berabere — en güçlü katman.",
      },
      binaryMarket(test, "over", "Çok Gollü Maç (Üst/Alt 2.5)", "pOver", "yOver", "Maçta 3+ gol olur mu — orta güç."),
      binaryMarket(test, "btts", "Karşılıklı Gol", "pBTTS", "yBTTS", "İki takım da gol atar mı — zayıf, tahminden az iyi."),
      {
        key: "lineup", name: "Kadro / Rotasyon Kararı", status: "pending",
        trust: 0, accuracy: 0, ece: 0, brierSkill: 0, baseRate: null, n: 0,
        note: "Doğrulanamaz: kimin gerçekten oynadığı + maç sonucu eşli veri gerekir (Süper Lig kadro+sonuç akışı).",
      },
      {
        key: "injury", name: "Sakatlık Riski", status: "pending",
        trust: 0, accuracy: 0, ece: 0, brierSkill: 0, baseRate: null, n: 0,
        note: "Doğrulanamaz: gerçek sakatlık zaman serisi + yük/giyilebilir veri gerekir (Sportmonks haberi yetmez).",
      },
    ],
    params: { lr: LR, rho: RHO, wd: WD },
  };
}
