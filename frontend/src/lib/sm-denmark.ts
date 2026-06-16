/**
 * GERÇEK VERİ — Danimarka Superliga + İskoçya Premiership (Sportmonks).
 * Bizim doğrulanmış goals-only modelimizi (atak/savunma + Dixon-Coles) GERÇEK
 * sonuçlarda çalıştırır. İKİ lig × 12 sezon = 5000+ gerçek maç → daha dar güven
 * bandı, daha sağlam trust.
 *
 * Token xG/predictions vermiyor → sadece gerçek goller. Walk-forward (sızıntısız):
 * her lig KENDİ tabanıyla (muH/muA) öğrenilir (lig-bazlı), takım güçleri lig içinde
 * kıyaslanır. Manşet trust = iki ligin son sezonu (görülmemiş test). Bu, Süper Lig
 * bağlanınca ne olacağının birebir önizlemesi.
 *
 * Veri sm-denmark.json (ingest-sportmonks.mjs, build-time; token frontend'e girmez).
 */

import raw from "./sm-denmark.json";
import fixturesRaw from "./sm-denmark-fixtures.json";
import lineupsRaw from "./sm-lineups.json";
import namesRaw from "./sm-player-names.json";
import timingRaw from "./sm-timing.json";
import statsRaw from "./sm-stats.json";
import formationsRaw from "./sm-formations.json";
import { predictFromLambda, clamp, type Prediction } from "./poisson-predict";
import type { LeagueRatings } from "./calibration";

const PLAYER_NAMES = namesRaw as Record<string, { n: string; t: string; p?: string }>;

interface DkRow { date: string; home: string; away: string; hg: number; ag: number; comp: string; season: string }
const ALL = (raw as DkRow[]).slice().sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
// Maç-öncesi kadro sinyali: gerçek ilk-11 (player_id) maç anahtarına göre.
// Bazı maçlarda player_id null olabilir → yükleme anında temizle.
const LU: Record<string, { h: number[]; a: number[] }> = {};
for (const [k, v] of Object.entries(lineupsRaw as Record<string, { h: (number | null)[]; a: (number | null)[] }>)) {
  const h = v.h.filter((x): x is number => x != null), a = v.a.filter((x): x is number => x != null);
  if (h.length >= 9 && a.length >= 9) LU[k] = { h, a };
}
const luKey = (m: { date: string; home: string; away: string }) => `${m.date}|${m.home}|${m.away}`;
// Gol-zamanlaması + devre skoru (ingest-timing.mjs): key=date|home|away.
const TIMING = timingRaw as Record<string, { h1?: number; a1?: number; mins?: number[][] }>;
// Maç istatistiği (ingest-stats.mjs): comp|team → topla-oynama % + korner ort. BETİMLEYİCİ
// (takım stili) — possession sonuç-tahmininde zayıf, motora SOKULMAZ, sadece bağlam.
const STATS = statsRaw as Record<string, { poss: number | null; corners: number | null; games: number }>;
/** Takım stili: topa-sahip / dengeli / direkt-temkinli (gerçek possession ort.). */
export function denmarkStyle(comp: string, team: string): { poss: number | null; corners: number | null; tag: string } {
  const s = STATS[comp + "|" + team];
  if (!s || s.poss == null) return { poss: null, corners: s?.corners ?? null, tag: "veri yok" };
  const tag = s.poss >= 53 ? "topa sahip" : s.poss <= 47 ? "direkt / temkinli" : "dengeli";
  return { poss: s.poss, corners: s.corners, tag };
}

// Gerçek diziliş (ingest-formations.mjs): resmi formation string'leri (4-3-3 vb).
const FORMATIONS = formationsRaw as unknown as Record<string, { top: string | null; topPct: number; games: number; dist: [string, number][]; home: string | null; away: string | null }>;
/** Takımın gerçek diziliş profili: en sık diziliş + esneklik + ev/dep farkı. */
export function denmarkFormation(comp: string, team: string): {
  top: string | null; topPct: number; dist: [string, number][]; home: string | null; away: string | null; varied: boolean; venueShift: boolean;
} {
  const f = FORMATIONS[comp + "|" + team];
  if (!f) return { top: null, topPct: 0, dist: [], home: null, away: null, varied: false, venueShift: false };
  return { top: f.top, topPct: f.topPct, dist: f.dist, home: f.home, away: f.away, varied: f.topPct < 45, venueShift: !!(f.home && f.away && f.home !== f.away) };
}

/** GERÇEK gol-zamanlaması eğrisi (lig-bazlı, SADECE train gollerinden = sızıntısız):
 *  fracAfter[t] = "t dakikadan SONRA atılan gol oranı". Maç-içi motorun naif eşit
 *  dağılım (90−t)/90 yerine bunu kullanması out-of-sample doğrulandı (goller geç gelir;
 *  dk75 logLoss +0.049). Dakika 0..90 → 91 elemanlı dizi. */
function timingCurve(comp: string): number[] {
  const bins = new Array(92).fill(0); let total = 0;
  for (const m of ALL) {
    if (m.comp !== comp || isTest(m)) continue;                 // train-only
    const t = TIMING[luKey(m)];
    if (t?.mins) for (const [min] of t.mins) { const b = Math.min(90, Math.max(1, min)); bins[b]++; total++; }
  }
  const suffix = new Array(93).fill(0);
  for (let x = 90; x >= 0; x--) suffix[x] = suffix[x + 1] + (bins[x + 1] || 0);
  const out = new Array(91);
  for (let t = 0; t <= 90; t++) out[t] = total ? round(suffix[t] / total, 4) : round((90 - t) / 90, 4);
  return out;
}

// Her lig için görülmemiş test = o ligin EN GÜNCEL sezonu. Tarih-bazlı tek sınır
// yerine sezon-bazlı: son sezonun ilk maç tarihinden itibaren test.
const COMP_LABEL: Record<string, string> = { "dk.1": "Danimarka Superliga", "sco.1": "İskoçya Premiership" };
const LR = 0.03, RHO = -0.08;
// Lineup (kadro sinyali) ayarları — SADECE train log-loss'unda seçildi (scripts/lineup-lab.mjs):
// beta=güç düzeltme kuvveti, PLR=oyuncu varlık-değeri öğrenme hızı. Out-of-sample
// doğrulandı: Danimarka trust 45→50, ECE her yerde düştü (overfit değil).
const LU_BETA = 0.1, LU_PLR = 0.012, LU_REG = 0.001;
const round = (n: number, d = 4) => { const m = 10 ** d; return Math.round(n * m) / m; };

// Her ligin en güncel (test) sezonu + o sezonun başlangıç tarihi.
function testSplits(): Record<string, string> {
  const latest: Record<string, string> = {};   // comp → en büyük sezon adı
  for (const m of ALL) { if (!latest[m.comp] || m.season > latest[m.comp]) latest[m.comp] = m.season; }
  const split: Record<string, string> = {};     // comp → test sezonunun ilk tarihi
  for (const m of ALL) if (m.season === latest[m.comp]) {
    if (!split[m.comp] || m.date < split[m.comp]) split[m.comp] = m.date;
  }
  return split;
}
const SPLIT = testSplits();
const isTest = (m: { comp: string; date: string }) => m.date >= (SPLIT[m.comp] ?? "9999");

interface CoreState {
  atk: Record<string, number>; def: Record<string, number>;   // key = comp|team
  muH: Record<string, number>; muA: Record<string, number>;   // lig-bazlı taban
  pv: Record<number, number>;                                  // player_id → varlık-değeri
  teamBase: Record<string, number>;                            // comp|team → ortalama-11 gücü (EMA)
  ledger: { date: string; comp: string; home: string; away: string; p: [number, number, number]; y: 0 | 1 | 2; hg: number; ag: number }[];
}

function runCore(): CoreState {
  // Lig-bazlı taban — SADECE o ligin train maçlarından.
  const lg: Record<string, { hg: number; ag: number; n: number }> = {};
  for (const m of ALL) if (!isTest(m)) { const x = (lg[m.comp] ??= { hg: 0, ag: 0, n: 0 }); x.hg += m.hg; x.ag += m.ag; x.n++; }
  const muH: Record<string, number> = {}, muA: Record<string, number> = {};
  for (const c in lg) { muH[c] = Math.log(lg[c].hg / lg[c].n); muA[c] = Math.log(lg[c].ag / lg[c].n); }

  const atk: Record<string, number> = {}, def: Record<string, number> = {};
  const A = (k: string) => (atk[k] ??= 0), D = (k: string) => (def[k] ??= 0);
  const pv: Record<number, number> = {};                       // oyuncu varlık-değeri
  const PV = (id: number) => (pv[id] ??= 0);
  const teamBase: Record<string, number> = {};                 // takımın normal-11 gücü (EMA)
  const ledger: CoreState["ledger"] = [];
  for (const m of ALL) {
    const kH = m.comp + "|" + m.home, kA = m.comp + "|" + m.away;
    const aH = A(kH), aA = A(kA), dH = D(kH), dA = D(kA);
    // Maç-öncesi kadro sinyali: sahadaki 11 takımın normalinden güçlü/zayıf mı → λ düzeltmesi.
    let bump = 0;
    const lu = LU[luKey(m)];
    if (lu) {
      const hVal = lu.h.reduce((s, id) => s + PV(id), 0) / lu.h.length;
      const aVal = lu.a.reduce((s, id) => s + PV(id), 0) / lu.a.length;
      bump = LU_BETA * ((hVal - (teamBase[kH] ?? 0)) - (aVal - (teamBase[kA] ?? 0)));
    }
    const lH = clamp(Math.exp((muH[m.comp] ?? 0.3) + aH - dA + bump), 0.05, 7);
    const lA = clamp(Math.exp((muA[m.comp] ?? 0.1) + aA - dH - bump), 0.05, 7);
    const pr = predictFromLambda(lH, lA, RHO);
    const y: 0 | 1 | 2 = m.hg > m.ag ? 0 : m.hg === m.ag ? 1 : 2;
    ledger.push({ date: m.date, comp: m.comp, home: m.home, away: m.away, p: [pr.pH, pr.pD, pr.pA], y, hg: m.hg, ag: m.ag });
    const gH = m.hg - lH, gA = m.ag - lA;
    atk[kH] = aH + LR * gH; def[kA] = dA - LR * gH;
    atk[kA] = aA + LR * gA; def[kH] = dH - LR * gA;
    // Oyuncu varlık-değeri: sahadaki 11, ev gol-farkı kadar ödül/ceza alır (regularize).
    if (lu) {
      const gd = m.hg - m.ag;
      for (const id of lu.h) pv[id] = PV(id) * (1 - LU_REG) + LU_PLR * gd;
      for (const id of lu.a) pv[id] = PV(id) * (1 - LU_REG) - LU_PLR * gd;
      const hVal = lu.h.reduce((s, id) => s + PV(id), 0) / lu.h.length;
      const aVal = lu.a.reduce((s, id) => s + PV(id), 0) / lu.a.length;
      teamBase[kH] = (teamBase[kH] ?? hVal) * 0.9 + hVal * 0.1;
      teamBase[kA] = (teamBase[kA] ?? aVal) * 0.9 + aVal * 0.1;
    }
  }
  return { atk, def, muH, muA, pv, teamBase, ledger };
}

export interface DkReport {
  comp: string; league: string; seasons: number; matches: number; testSeason: string; testMatches: number;
  accuracy: number; brier: number; logLoss: number; baselineBrier: number; brierSkill: number; ece: number; trust: number;
  baseRates: { h: number; d: number; a: number };
}

const _state = runCore();

/** Bir maç-kümesi üzerinde tam metrik (lig başına çağrılır). */
function metricsFor(test: CoreState["ledger"]): Omit<DkReport, "comp" | "league" | "seasons" | "matches" | "testSeason"> {
  const n = test.length || 1;
  const cnt = [0, 0, 0]; for (const r of test) cnt[r.y]++;
  const base = cnt.map((c) => c / n);
  let acc = 0, brier = 0, ll = 0, bB = 0;
  for (const r of test) {
    if (r.p.indexOf(Math.max(...r.p)) === r.y) acc++;
    for (let k = 0; k < 3; k++) { brier += (r.p[k] - (k === r.y ? 1 : 0)) ** 2; bB += (base[k] - (k === r.y ? 1 : 0)) ** 2; }
    ll += -Math.log(Math.max(r.p[r.y], 1e-9));
  }
  acc /= n; brier /= n; ll /= n; bB /= n;
  const bss = bB ? 1 - brier / bB : 0;
  const eb = Array.from({ length: 10 }, () => ({ sp: 0, sy: 0, c: 0 }));
  for (const r of test) for (let k = 0; k < 3; k++) { const p = r.p[k], y = k === r.y ? 1 : 0; const bi = Math.min(9, Math.floor(p * 10)); eb[bi].sp += p; eb[bi].sy += y; eb[bi].c++; }
  let ece = 0; const tot = n * 3; for (const b of eb) if (b.c) ece += (b.c / tot) * Math.abs(b.sp / b.c - b.sy / b.c);
  const trust = Math.round(100 * (0.6 * (1 - Math.min(ece / 0.12, 1)) + 0.4 * clamp(bss / 0.15, 0, 1)));
  return {
    testMatches: test.length, accuracy: round(acc), brier: round(brier), logLoss: round(ll),
    baselineBrier: round(bB), brierSkill: round(bss), ece: round(ece), trust,
    baseRates: { h: round(base[0], 3), d: round(base[1], 3), a: round(base[2], 3) },
  };
}

/** Her lig için AYRI gerçek güven raporu (lig kendi gerçek değerini alır). */
export function denmarkReports(): DkReport[] {
  return Object.keys(COMP_LABEL).map((comp) => {
    const test = _state.ledger.filter((r) => r.comp === comp && isTest(r));
    const seasons = new Set(ALL.filter((m) => m.comp === comp).map((m) => m.season)).size;
    const matches = ALL.filter((m) => m.comp === comp).length;
    return { comp, league: COMP_LABEL[comp], seasons, matches, testSeason: "son sezon (görülmemiş)", ...metricsFor(test) };
  });
}

/** Tek lig raporu (geriye-uyum; varsayılan Danimarka). */
export function denmarkReport(comp = "dk.1"): DkReport {
  return denmarkReports().find((r) => r.comp === comp) ?? denmarkReports()[0];
}

export interface DkTeam { name: string; rating: number; atk: number; def: number; comp: string }
/** Öğrenilen güçler — son sezonda oynayan takımlar (güncel). comp filtreli. */
export function denmarkTeams(comp = "dk.1"): DkTeam[] {
  const last = new Set<string>();
  for (const m of ALL) if (isTest(m) && m.comp === comp) { last.add(m.home); last.add(m.away); }
  return [...last].map((name) => {
    const a = _state.atk[comp + "|" + name] ?? 0, d = _state.def[comp + "|" + name] ?? 0;
    return { name, atk: round(a, 3), def: round(d, 3), rating: round((a + d) * 100, 0), comp };
  }).sort((x, y) => y.rating - x.rating);
}

// ── KADRO ETKİSİ — gerçek oyuncu, öğrenilen değer, "yoksa ne olur" ──────────────

export interface SquadPlayer { id: number; name: string; value: number; apps: number; pos?: string }
/** Bir takımın son sezon kadrosu: oynayan oyuncular + öğrenilen varlık-değeri.
 *  Değer yüksek = takıma net pozitif (kilit oyuncu). En son sezonun 11'lerinden. */
function teamSquad(comp: string, team: string): SquadPlayer[] {
  const key = comp + "|" + team;
  const apps: Record<number, number> = {};
  for (const m of ALL) {
    if (m.comp !== comp || !isTest(m)) continue;
    const lu = LU[luKey(m)]; if (!lu) continue;
    if (m.home === team) for (const id of lu.h) apps[id] = (apps[id] ?? 0) + 1;
    else if (m.away === team) for (const id of lu.a) apps[id] = (apps[id] ?? 0) + 1;
  }
  return Object.keys(apps).map(Number)
    .filter((id) => PLAYER_NAMES[id]?.t === key || PLAYER_NAMES[id])   // ada sahip
    .map((id) => ({ id, name: PLAYER_NAMES[id]?.n ?? `#${id}`, value: round(_state.pv[id] ?? 0, 4), apps: apps[id], pos: PLAYER_NAMES[id]?.p || "" }))
    .sort((a, b) => b.value - a.value);
}

/** Takımın normal-11 güç tabanı (EMA, öğrenilen) — kadro-etki referansı. */
const teamBaseOf = (comp: string, team: string) => _state.teamBase[comp + "|" + team] ?? 0;

export interface SquadImpact {
  team: string; keyPlayers: SquadPlayer[];      // en değerli oyuncular (kilit)
  fullStrength: number;                          // tam-kadro güç tabanı
}
/** Bir takımın kilit oyuncuları + tam-kadro referansı (UI kadro seçici için). */
export function denmarkSquad(team: string, comp = "dk.1"): SquadImpact {
  const squad = teamSquad(comp, team);
  return { team, keyPlayers: squad.slice(0, 14), fullStrength: round(teamBaseOf(comp, team), 4) };
}

/** Kadro-farkında tahmin: bazı oyuncular EKSİK iken (out=player_id) güç düzeltmeli
 *  tahmin. Eksik oyuncuların değeri tam-kadro tabanından düşülür → λ bump. */
export function denmarkPredictWithSquad(
  home: string, away: string, comp = "dk.1",
  outHome: number[] = [], outAway: number[] = [],
): Prediction & { bump: number } {
  // Tam kadro (eksiksiz) sahadaki 11 ≈ takımın en değerli 11'i; eksikler çıkınca
  // sahadaki ortalama değer düşer → normalden zayıf kadro.
  const avgOut = (team: string, outs: number[]): number => {
    if (!outs.length) return 0;
    // eksik oyuncuların ortalama değeri kadar 11-ortalaması düşer (11'de n eksik).
    const sum = outs.reduce((s, id) => s + (_state.pv[id] ?? 0), 0);
    return sum / 11;   // 11 kişilik kadroda bu kadar ortalama düşüş
  };
  const hDrop = avgOut(home, outHome), aDrop = avgOut(away, outAway);
  // bump: ev kadrosu düşüşü gücü azaltır, dep düşüşü ev lehine.
  const bump = LU_BETA * ((-hDrop) - (-aDrop));
  const lH = clamp(Math.exp((_state.muH[comp] ?? 0.3) + (_state.atk[comp + "|" + home] ?? 0) - (_state.def[comp + "|" + away] ?? 0) + bump), 0.05, 7);
  const lA = clamp(Math.exp((_state.muA[comp] ?? 0.1) + (_state.atk[comp + "|" + away] ?? 0) - (_state.def[comp + "|" + home] ?? 0) - bump), 0.05, 7);
  return { ...predictFromLambda(lH, lA, RHO), bump: round(bump, 4) };
}

/** Kadro-etkisi UI verisi (Danimarka): takımlar + güç + kilit oyuncular. */
export function denmarkSquadImpact(comp = "dk.1"): {
  muH: number; muA: number; rho: number; beta: number;
  teams: { name: string; comp: string; atk: number; def: number; keyPlayers: SquadPlayer[] }[];
  timing: number[];
} {
  const teams = denmarkTeams(comp).map((t) => ({
    name: t.name, comp, atk: t.atk, def: t.def,
    keyPlayers: teamSquad(comp, t.name).slice(0, 12),
  }));
  return { muH: round(_state.muH[comp] ?? 0.3, 4), muA: round(_state.muA[comp] ?? 0.1, 4), rho: RHO, beta: LU_BETA, teams, timing: timingCurve(comp) };
}

/** Canlı tahmin için veri — her lig ayrı LeagueRatings. */
export function denmarkPredictorData(): LeagueRatings[] {
  return Object.keys(COMP_LABEL).map((comp) => ({
    comp, label: COMP_LABEL[comp], muH: round(_state.muH[comp] ?? 0.3, 4), muA: round(_state.muA[comp] ?? 0.1, 4),
    rho: RHO, teams: denmarkTeams(comp).map((t) => ({ name: t.name, atk: t.atk, def: t.def, rating: t.rating })),
  }));
}

/** İki takım → gerçek güçlerden tahmin (bizim motor, gerçek veri). comp gerekli. */
export function denmarkPredict(home: string, away: string, comp = "dk.1"): Prediction {
  const lH = clamp(Math.exp((_state.muH[comp] ?? 0.3) + (_state.atk[comp + "|" + home] ?? 0) - (_state.def[comp + "|" + away] ?? 0)), 0.05, 7);
  const lA = clamp(Math.exp((_state.muA[comp] ?? 0.1) + (_state.atk[comp + "|" + away] ?? 0) - (_state.def[comp + "|" + home] ?? 0)), 0.05, 7);
  return predictFromLambda(lH, lA, RHO);
}

interface FxFile { season: string; fixtures: { date: string; home: string; away: string }[] }
export interface UpcomingPred {
  date: string; home: string; away: string;
  pH: number; pD: number; pA: number; pick: "1" | "X" | "2"; conf: number;
  expHome: number; expAway: number; topScore: string;
  knownHome: boolean; knownAway: boolean;
}
/** Yaklaşan GERÇEK maçlar (Danimarka) + bizim modelin tahmini (ileriye dönük). */
export function denmarkUpcoming(): { season: string; list: UpcomingPred[] } {
  const f = fixturesRaw as FxFile;
  const known = new Set(denmarkTeams("dk.1").map((t) => t.name));
  const list = f.fixtures.map((m) => {
    const pr = denmarkPredict(m.home, m.away, "dk.1");
    const probs: [string, number][] = [["1", pr.pH], ["X", pr.pD], ["2", pr.pA]];
    probs.sort((a, b) => b[1] - a[1]);
    return {
      date: m.date, home: m.home, away: m.away,
      pH: round(pr.pH, 3), pD: round(pr.pD, 3), pA: round(pr.pA, 3),
      pick: probs[0][0] as "1" | "X" | "2", conf: round(probs[0][1], 3),
      expHome: round(pr.lH, 1), expAway: round(pr.lA, 1), topScore: pr.top[0]?.score ?? "—",
      knownHome: known.has(m.home), knownAway: known.has(m.away),
    };
  });
  return { season: f.season, list };
}

/** Test sezonundan son N maç — tahmin vs gerçek (vitrin). */
export function denmarkSample(limit = 10): { date: string; home: string; away: string; pick: string; conf: number; scoreline: string; hit: boolean }[] {
  const L = ["1", "X", "2"];
  return _state.ledger.filter(isTest).slice(-limit).reverse().map((r) => {
    const idx = r.p.indexOf(Math.max(...r.p));
    return { date: r.date, home: r.home, away: r.away, pick: L[idx], conf: round(r.p[idx], 3), scoreline: `${r.hg}-${r.ag}`, hit: idx === r.y };
  });
}

// ── GÜVEN ETİKETİ KANITI — "YÜKSEK dediğimizde gerçekten daha mı isabetli?" ──────
// MatchBrief'teki güven seviyesini (favori açıklığı × lig isabeti) GÖRÜLMEMİŞ test
// maçlarında uygular, her seviyenin gerçek isabet oranını ölçer. Etiket anlamlıysa
// isabet YÜKSEK>ORTA>DÜŞÜK sırasıyla düşmeli. Tek satır uydurma yok — gerçek ledger.
export interface ConfBucket { level: "yüksek" | "orta" | "düşük"; n: number; hitRate: number; avgClaim: number }
export function denmarkConfidenceTrack(comp = "dk.1"): { buckets: ConfBucket[]; overall: number; n: number; monotonic: boolean } {
  const trust = denmarkReport(comp).trust;
  const ligFactor = clamp(0.4 + (trust / 100) * 0.8, 0.4, 1);
  const acc: Record<string, { n: number; hits: number; claim: number }> = {
    yüksek: { n: 0, hits: 0, claim: 0 }, orta: { n: 0, hits: 0, claim: 0 }, düşük: { n: 0, hits: 0, claim: 0 },
  };
  let allN = 0, allHits = 0;
  for (const r of _state.ledger) {
    if (r.comp !== comp || !isTest(r)) continue;
    const sorted = [...r.p].sort((a, b) => b - a);
    const gap = sorted[0] - sorted[1];
    const cScore = clamp(gap * 1.6, 0, 1) * ligFactor;
    const level = cScore >= 0.55 ? "yüksek" : cScore >= 0.3 ? "orta" : "düşük";
    const hit = r.p.indexOf(Math.max(...r.p)) === r.y;
    acc[level].n++; acc[level].hits += hit ? 1 : 0; acc[level].claim += sorted[0];
    allN++; allHits += hit ? 1 : 0;
  }
  const order: ("yüksek" | "orta" | "düşük")[] = ["yüksek", "orta", "düşük"];
  const buckets: ConfBucket[] = order.map((level) => {
    const a = acc[level]; const n = a.n || 1;
    return { level, n: a.n, hitRate: round(a.hits / n, 3), avgClaim: round(a.claim / n, 3) };
  });
  // monoton mu: yüksek ≥ orta ≥ düşük (yeterli örneklemli kovalar arasında)
  const valid = buckets.filter((b) => b.n >= 10);
  let monotonic = true;
  for (let i = 1; i < valid.length; i++) if (valid[i].hitRate > valid[i - 1].hitRate + 0.001) monotonic = false;
  return { buckets, overall: round(allHits / (allN || 1), 3), n: allN, monotonic };
}

// ── MAÇ-ÖNCESİ KARAR ZEKÂSI — hepsi GERÇEK öğrenilen veriden (uydurma yok) ──────

/** #8 — Takımın gerçek ev/deplasman gol farkı (kendi maçlarından). Lig-genel ev
 *  avantajından farkını verir: bazı takımlar evinde çok güçlü, bazıları nötr. */
function homeAwaySplit(comp: string, team: string): { homeGD: number; awayGD: number; homeN: number; awayN: number } {
  let hGD = 0, hN = 0, aGD = 0, aN = 0;
  for (const m of ALL) {
    if (m.comp !== comp) continue;
    if (m.home === team) { hGD += m.hg - m.ag; hN++; }
    else if (m.away === team) { aGD += m.ag - m.hg; aN++; }
  }
  return { homeGD: hN ? round(hGD / hN, 2) : 0, awayGD: aN ? round(aGD / aN, 2) : 0, homeN: hN, awayN: aN };
}

export interface MatchBrief {
  home: string; away: string; comp: string;
  pH: number; pD: number; pA: number; pick: "1" | "X" | "2"; conf: number;
  lH: number; lA: number; topScore: string;
  // #5 maç güveni
  confidence: { level: "yüksek" | "orta" | "düşük"; score: number; reason: string };
  // #4 rakip kilit oyuncu (deplasman = rakip varsayımı; ikisi de döner)
  homeThreats: SquadPlayer[]; awayThreats: SquadPlayer[];
  // #8 ev/dep
  homeSplit: { homeGD: number; awayGD: number; note: string };
  awaySplit: { homeGD: number; awayGD: number; note: string };
}

/** #4+#5+#8 birleşik maç brifingi — iki gerçek takım için maç-öncesi karar kartı. */
export function denmarkMatchBrief(home: string, away: string, comp = "dk.1"): MatchBrief {
  const pr = denmarkPredict(home, away, comp);
  const probs: [("1" | "X" | "2"), number][] = [["1", pr.pH], ["X", pr.pD], ["2", pr.pA]];
  probs.sort((a, b) => b[1] - a[1]);
  const top = probs[0][1], second = probs[1][1];

  // #5 — maç güveni: favori ile ikincinin farkı + ligin gerçek BSS'i.
  const ligTrust = denmarkReport(comp).brierSkill;             // o ligin gerçek skill'i
  const gap = top - second;                                    // favori ne kadar net
  // skor: olasılık-açıklığı (0..1) × lig-skill faktörü
  const cScore = round(clamp(gap * 1.6, 0, 1) * clamp(0.5 + ligTrust * 3, 0.4, 1), 2);
  const level: "yüksek" | "orta" | "düşük" = cScore >= 0.55 ? "yüksek" : cScore >= 0.3 ? "orta" : "düşük";
  const reason =
    level === "yüksek" ? "Favori net + lig tahmin edilebilir — tahmine yaslanabilirsin."
    : level === "düşük" ? "İki takım denk / lig dengeli — sürpriz riski yüksek, temkinli ol."
    : "Orta belirginlik — tahmin yol gösterir ama kesin değil.";

  // #4 — kilit oyuncular (en değerli ilk 3, gerçek öğrenilen değer).
  const homeThreats = teamSquad(comp, home).filter((p) => p.value > 0).slice(0, 3);
  const awayThreats = teamSquad(comp, away).filter((p) => p.value > 0).slice(0, 3);

  // #8 — ev/dep avantajı.
  const hs = homeAwaySplit(comp, home), as = homeAwaySplit(comp, away);
  const splitNote = (s: { homeGD: number; awayGD: number; homeN: number; awayN: number }, side: "home" | "away") => {
    const v = side === "home" ? s.homeGD : s.awayGD;
    const lbl = side === "home" ? "evinde" : "deplasmanda";
    const n = side === "home" ? s.homeN : s.awayN;
    if (n < 8) return `${lbl} az veri (${n} maç)`;
    return v > 0.4 ? `${lbl} güçlü (gol farkı +${v})` : v < -0.4 ? `${lbl} zayıf (${v})` : `${lbl} nötr (${v})`;
  };

  return {
    home, away, comp,
    pH: round(pr.pH, 3), pD: round(pr.pD, 3), pA: round(pr.pA, 3),
    pick: probs[0][0], conf: round(top, 3), lH: round(pr.lH, 2), lA: round(pr.lA, 2), topScore: pr.top[0]?.score ?? "—",
    confidence: { level, score: cScore, reason },
    homeThreats, awayThreats,
    homeSplit: { homeGD: hs.homeGD, awayGD: hs.awayGD, note: splitNote(hs, "home") },
    awaySplit: { homeGD: as.homeGD, awayGD: as.awayGD, note: splitNote(as, "away") },
  };
}

// ── MAÇ-TİPİ PARMAK İZİ (B) — motorun ürettiği over/btts, GERÇEK kalibrasyonla ──
// Out-of-sample (son sezon) doğrulandı: KG ECE=0.025 (iyi kalibre), Üst2.5 ECE=0.059
// (orta; yüksek olasılıkları hafif şişirir → "kesin" demeyiz). Antrenöre maç karakteri.

export interface MatchType {
  over: number; btts: number;
  goalType: "bol gollü" | "dengeli" | "az gollü";
  bttsLabel: "karşılıklı gol olası" | "tek taraf kapanabilir";
  note: string;
}
/** Bir maçın gol-karakteri: bol/az gollü + karşılıklı gol olasılığı (gerçek kalibre). */
export function denmarkMatchType(home: string, away: string, comp = "dk.1"): MatchType {
  const pr = denmarkPredict(home, away, comp);
  const over = round(pr.over, 3), btts = round(pr.btts, 3);
  const goalType: MatchType["goalType"] = over >= 0.58 ? "bol gollü" : over <= 0.45 ? "az gollü" : "dengeli";
  const bttsLabel: MatchType["bttsLabel"] = btts >= 0.55 ? "karşılıklı gol olası" : "tek taraf kapanabilir";
  const note =
    goalType === "bol gollü" ? "Açık geçmesi beklenir — savunma dengesine dikkat, kontra riski yüksek."
    : goalType === "az gollü" ? "Kapalı/düşük tempolu beklenir — tek gol belirleyici olabilir, set-piece önemli."
    : "Orta tempo — duruma göre açılır.";
  return { over, btts, goalType, bttsLabel, note };
}

// ── UYUMLU İKİLİ (A, betimleyici) — kimya tahmine EKLENMEDİ (out-of-sample geçmedi),
// ama "şu ikili birlikte sahadayken takım gerçekten daha iyi" GERÇEK ve gösterilir.
export interface PlayerPair { a: string; b: string; together: number; gdWith: number }
/** Bir takımın en uyumlu ikilileri: birlikte ≥N maç oynamış + birlikteyken takım
 *  gol-farkı en yüksek. Betimleyici (tahmini değiştirmez) — antrenöre bağlam. */
export function denmarkTopPairs(team: string, comp = "dk.1", minTogether = 10): PlayerPair[] {
  const key = comp + "|" + team;
  const stat: Record<string, { n: number; gd: number }> = {};
  for (const m of ALL) {
    if (m.comp !== comp) continue;
    const lu = LU[luKey(m)]; if (!lu) continue;
    const isHome = m.home === team, isAway = m.away === team;
    if (!isHome && !isAway) continue;
    const xi = isHome ? lu.h : lu.a;
    const gd = isHome ? m.hg - m.ag : m.ag - m.hg;
    for (let i = 0; i < xi.length; i++) for (let j = i + 1; j < xi.length; j++) {
      const k = xi[i] < xi[j] ? `${xi[i]}_${xi[j]}` : `${xi[j]}_${xi[i]}`;
      const s = (stat[k] ??= { n: 0, gd: 0 }); s.n++; s.gd += gd;
    }
  }
  return Object.entries(stat)
    .filter(([, s]) => s.n >= minTogether)
    .map(([k, s]) => { const [x, y] = k.split("_").map(Number); return { x, y, n: s.n, avgGd: s.gd / s.n }; })
    .filter((p) => PLAYER_NAMES[p.x] && PLAYER_NAMES[p.y])
    .sort((a, b) => b.avgGd - a.avgGd)
    .slice(0, 5)
    .map((p) => ({ a: PLAYER_NAMES[p.x].n, b: PLAYER_NAMES[p.y].n, together: p.n, gdWith: round(p.avgGd, 2) }));
}

// ── GAME-STATE / YARI PROFİLİ (#1) — devre skorlarından (sm-timing.json) ──────────
// Betimleyici (gerçek devre skorları): takım hızlı mı başlıyor / güçlü mü bitiriyor,
// önde/geride iken ne yapıyor. Devre arası kararına bağlam.
export interface GameState {
  team: string; comp: string; games: number;
  h1For: number; h1Ag: number; h2For: number; h2Ag: number;   // yarı başına ort. gol
  startTag: "hızlı başlangıç" | "yavaş başlangıç" | "dengeli başlangıç";
  finishTag: "güçlü bitiş" | "sönük bitiş" | "dengeli bitiş";
  lateLeak: boolean;                                            // 2. yarı belirgin çok yer
  htLeadGames: number; htLeadHoldPct: number;                  // devre önde → kazanma %
  htBehindGames: number; htBehindRecoverPct: number;           // devre geride → en az 1 puan %
}

/** Bir takımın gerçek devre-skoru profili (tüm sezonlar = sabit betimleyici). */
export function denmarkGameState(team: string, comp = "dk.1"): GameState {
  let g = 0, h1f = 0, h1a = 0, h2f = 0, h2a = 0;
  let leadG = 0, leadHold = 0, behG = 0, behRec = 0;
  for (const m of ALL) {
    if (m.comp !== comp) continue;
    const isH = m.home === team, isA = m.away === team;
    if (!isH && !isA) continue;
    const t = TIMING[luKey(m)];
    if (t?.h1 == null || t?.a1 == null) continue;
    const htH = t.h1, htA = t.a1;
    // takım perspektifi
    const h1For = isH ? htH : htA, h1Ag = isH ? htA : htH;
    const ftFor = isH ? m.hg : m.ag, ftAg = isH ? m.ag : m.hg;
    const h2For = ftFor - h1For, h2Ag = ftAg - h1Ag;
    g++; h1f += h1For; h1a += h1Ag; h2f += Math.max(0, h2For); h2a += Math.max(0, h2Ag);
    if (h1For > h1Ag) { leadG++; if (ftFor > ftAg) leadHold++; }
    else if (h1For < h1Ag) { behG++; if (ftFor >= ftAg) behRec++; }
  }
  const n = g || 1;
  const H1F = h1f / n, H1A = h1a / n, H2F = h2f / n, H2A = h2a / n;
  const startTag: GameState["startTag"] = H1F - H1A > 0.2 ? "hızlı başlangıç" : H1F - H1A < -0.2 ? "yavaş başlangıç" : "dengeli başlangıç";
  const finishTag: GameState["finishTag"] = H2F - H2A > 0.2 ? "güçlü bitiş" : H2F - H2A < -0.2 ? "sönük bitiş" : "dengeli bitiş";
  return {
    team, comp, games: g,
    h1For: round(H1F, 2), h1Ag: round(H1A, 2), h2For: round(H2F, 2), h2Ag: round(H2A, 2),
    startTag, finishTag, lateLeak: H2A - H1A > 0.25,
    htLeadGames: leadG, htLeadHoldPct: leadG ? Math.round((leadHold / leadG) * 100) : 0,
    htBehindGames: behG, htBehindRecoverPct: behG ? Math.round((behRec / behG) * 100) : 0,
  };
}

export interface FragilityReport {
  team: string; comp: string;
  totalValue: number; topShare: number;            // en değerli 3 oyuncunun toplam değer payı
  level: "kırılgan" | "dengeli" | "dağınık";
  drop3: number;                                    // en iyi 3 giderse güç düşüşü (0..1 yaklaşık)
  keyPlayers: SquadPlayer[];
}

/** #7 — Kadro kırılganlığı: takımın değeri kaç oyuncuya bağlı? Birkaç yıldıza
 *  bağlıysa "kırılgan" (biri sakatlanınca çok düşer); dağılmışsa "dayanıklı". */
export function denmarkFragility(team: string, comp = "dk.1"): FragilityReport {
  const squad = teamSquad(comp, team).filter((p) => p.value > 0 && p.apps >= 3);
  const total = squad.reduce((s, p) => s + p.value, 0) || 1e-6;
  const top3 = squad.slice(0, 3).reduce((s, p) => s + p.value, 0);
  const share = round(top3 / total, 2);
  // drop3: en iyi 3 çıkarsa bump üzerinden yaklaşık güç düşüşü (kadro sinyali matematiği).
  const drop3 = round(LU_BETA * (squad.slice(0, 3).reduce((s, p) => s + p.value, 0) / 11), 3);
  const level: "kırılgan" | "dengeli" | "dağınık" = share >= 0.55 ? "kırılgan" : share >= 0.38 ? "dengeli" : "dağınık";
  return { team, comp, totalValue: round(total, 2), topShare: share, level, drop3, keyPlayers: squad.slice(0, 5) };
}

/** Tüm takımlar için kırılganlık + sürpriz-11 + ev/dep özeti (UI prop'u, server'da
 *  bir kez hesaplanır). Maç-öncesi karar paneli bununla çalışır. */
export function denmarkDecisionData(comp = "dk.1") {
  const teams = denmarkTeams(comp).map((t) => t.name);
  return {
    comp,
    teams: teams.map((name) => {
      const fr = denmarkFragility(name, comp);
      const sx = denmarkSurpriseXI(name, comp);
      const hs = homeAwaySplit(comp, name);
      return {
        name,
        fragility: { level: fr.level, topShare: fr.topShare, drop3: fr.drop3, keyPlayers: fr.keyPlayers },
        surprise: { rotated: sx.rotated, delta: sx.delta, note: sx.note, lastValue: sx.lastValue, expectedValue: sx.expectedValue },
        split: { homeGD: hs.homeGD, awayGD: hs.awayGD, homeN: hs.homeN, awayN: hs.awayN },
        threats: teamSquad(comp, name).filter((p) => p.value > 0).slice(0, 3),
        pairs: denmarkTopPairs(name, comp, 10).slice(0, 3),   // A: uyumlu ikili (betimleyici)
        gameState: denmarkGameState(name, comp),              // #1 yarı profili
        style: denmarkStyle(comp, name),                      // #3 takım stili (possession)
        formation: denmarkFormation(comp, name),              // #4 gerçek diziliş
      };
    }),
  };
}

export interface SurpriseLineup {
  team: string; comp: string;
  expectedXI: SquadPlayer[];                         // en sık/en değerli beklenen 11
  expectedValue: number; lastValue: number; delta: number;
  rotated: boolean; note: string;
}

/** #10 — Sürpriz 11 dedektörü: bir takımın SON oynadığı 11, beklenen (en değerli/
 *  en sık) 11'inden ne kadar zayıf/güçlü? Rakip rotasyon yaptıysa "fırsat maçı". */
export function denmarkSurpriseXI(team: string, comp = "dk.1"): SurpriseLineup {
  const key = comp + "|" + team;
  // beklenen 11: bu takımın en sık sahaya çıkan, değeri yüksek oyuncuları.
  const expected = teamSquad(comp, team).slice(0, 11);
  const expVal = expected.reduce((s, p) => s + p.value, 0) / 11;
  // son maçtaki gerçek 11.
  let lastLu: number[] | null = null;
  for (const m of ALL) {
    if (m.comp !== comp || !isTest(m)) continue;
    const lu = LU[luKey(m)]; if (!lu) continue;
    if (m.home === team) lastLu = lu.h; else if (m.away === team) lastLu = lu.a;
  }
  const lastVal = lastLu ? lastLu.reduce((s, id) => s + (_state.pv[id] ?? 0), 0) / lastLu.length : expVal;
  const delta = round(lastVal - expVal, 3);
  const rotated = delta < -0.05;
  const note = !lastLu ? "son 11 verisi yok"
    : rotated ? `son maçta beklenenden zayıf 11 (rotasyon) — bu takım dinlendirmiş olabilir`
    : delta > 0.05 ? "son maçta en güçlü 11 — tam kadro" : "beklenen 11'e yakın";
  return {
    team, comp, expectedXI: expected, expectedValue: round(expVal, 3),
    lastValue: round(lastVal, 3), delta, rotated, note,
  };
}
