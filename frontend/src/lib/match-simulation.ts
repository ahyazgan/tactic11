/**
 * Maç Simülasyonu — Poisson + Dixon-Coles olasılık modeli (backend engine.predict aynası).
 *
 * Takımların sezon xG güçlerinden (xgf/xga, lib/demo-teams) beklenen gol oranları
 * (λ) türetir, tam skor dağılımını (Dixon-Coles düşük-skor düzeltmesiyle) çıkarır:
 * galibiyet/beraberlik/mağlubiyet olasılığı, en olası skorlar, üst/alt 2.5, KG var.
 *
 * Skor matrisi ANALİTİK olarak hesaplanır (deterministik, Math.random YOK) — bu,
 * sonsuz Monte Carlo örneklemesinin tam limiti. Ham xG oranları tek sezonda
 * gürültülü olduğu için güçler ortalamaya doğru SHRINK ile çekilir (regresyon).
 *
 * Çıktı tahmin defterine (lib/track-record) "match" tahmini olarak yazılabilir.
 */

import { DEMO_TEAM_ROWS, demoTeamById, type DemoTeamRow } from "@/lib/demo-teams";

// ── Model sabitleri (backend ρ=-0.12 ile hizalı) ────────────────────────────
const RHO = -0.12;          // Dixon-Coles düşük-skor korelasyon düzeltmesi
const HOME_ADV = 1.05;      // iç saha çarpanı (λ_home'a, λ_away'e ters)
const SHRINK = 0.45;        // güçleri lig ortalamasına çekme (0=tam ort, 1=ham)
const MAXG = 8;             // skor ızgarası 0..8 gol/takım

// Lig ortalaması maç başı xG (tek kaynak: demo takım dizini).
const LEAGUE_AVG_XG = (() => {
  const totalXgf = DEMO_TEAM_ROWS.reduce((s, t) => s + t.xgf, 0);
  const totalMatches = DEMO_TEAM_ROWS.reduce((s, t) => s + t.played, 0);
  return totalMatches > 0 ? totalXgf / totalMatches : 1.3;
})();

const fact = (n: number): number => { let f = 1; for (let i = 2; i <= n; i++) f *= i; return f; };
const poisson = (k: number, lambda: number): number =>
  (Math.pow(lambda, k) * Math.exp(-lambda)) / fact(k);

export interface TeamStrength {
  attack: number;   // lige göre hücum gücü (1 = ortalama), shrink uygulanmış
  defense: number;  // lige göre savunma gücü (1 = ortalama, düşük = iyi savunma)
}

/** Bir takımın sezon xG'sinden hücum/savunma gücü (ortalamaya çekilmiş). */
export function strengthOf(t: DemoTeamRow): TeamStrength {
  const attRaw = (t.xgf / t.played) / LEAGUE_AVG_XG;
  const defRaw = (t.xga / t.played) / LEAGUE_AVG_XG;
  return {
    attack: 1 + (attRaw - 1) * SHRINK,
    defense: 1 + (defRaw - 1) * SHRINK,
  };
}

export interface ScoreCell { home: number; away: number; prob: number }

export interface MatchSimulation {
  homeTeam: string;
  awayTeam: string;
  lambdaHome: number;          // beklenen iç saha golü
  lambdaAway: number;
  probHomeWin: number;
  probDraw: number;
  probAwayWin: number;
  mostLikelyScore: [number, number];
  mostLikelyScoreProb: number;
  topScores: ScoreCell[];      // en olası 6 skor
  over25: number;              // üst 2.5 gol olasılığı
  bttsYes: number;             // karşılıklı gol (KG var)
  homeCleanSheet: number;      // iç saha gol yemeden
  awayCleanSheet: number;
  rho: number;
  leagueAvgXg: number;
}

/** Dixon-Coles τ düzeltmesi — düşük skorlu hücreleri korelasyon için ayarlar. */
function dcTau(x: number, y: number, lh: number, la: number, rho: number): number {
  if (x === 0 && y === 0) return 1 - lh * la * rho;
  if (x === 0 && y === 1) return 1 + lh * rho;
  if (x === 1 && y === 0) return 1 + la * rho;
  if (x === 1 && y === 1) return 1 - rho;
  return 1;
}

/** λ_home, λ_away → tam skor dağılımı + özet olasılıklar (analitik). */
export function simulateFromLambdas(
  homeTeam: string, awayTeam: string, lambdaHome: number, lambdaAway: number,
): MatchSimulation {
  const cells: ScoreCell[] = [];
  let total = 0;
  for (let x = 0; x <= MAXG; x++) {
    for (let y = 0; y <= MAXG; y++) {
      const p = poisson(x, lambdaHome) * poisson(y, lambdaAway) * dcTau(x, y, lambdaHome, lambdaAway, RHO);
      cells.push({ home: x, away: y, prob: p });
      total += p;
    }
  }
  // τ normalizasyonu kırdığı için tekrar 1'e ölçekle.
  for (const c of cells) c.prob /= total;

  let homeWin = 0, draw = 0, awayWin = 0, over25 = 0, btts = 0, homeCS = 0, awayCS = 0;
  for (const c of cells) {
    if (c.home > c.away) homeWin += c.prob;
    else if (c.home === c.away) draw += c.prob;
    else awayWin += c.prob;
    if (c.home + c.away > 2.5) over25 += c.prob;
    if (c.home > 0 && c.away > 0) btts += c.prob;
    if (c.away === 0) homeCS += c.prob;
    if (c.home === 0) awayCS += c.prob;
  }

  const sorted = [...cells].sort((a, b) => b.prob - a.prob);
  const top = sorted[0];

  const r3 = (n: number) => Math.round(n * 1000) / 1000;
  return {
    homeTeam, awayTeam,
    lambdaHome: Math.round(lambdaHome * 100) / 100,
    lambdaAway: Math.round(lambdaAway * 100) / 100,
    probHomeWin: r3(homeWin), probDraw: r3(draw), probAwayWin: r3(awayWin),
    mostLikelyScore: [top.home, top.away], mostLikelyScoreProb: r3(top.prob),
    topScores: sorted.slice(0, 6).map((c) => ({ home: c.home, away: c.away, prob: r3(c.prob) })),
    over25: r3(over25), bttsYes: r3(btts),
    homeCleanSheet: r3(homeCS), awayCleanSheet: r3(awayCS),
    rho: RHO, leagueAvgXg: Math.round(LEAGUE_AVG_XG * 100) / 100,
  };
}

/** İki takım id'sinden maç simülasyonu (güç → λ → dağılım). */
export function simulateMatch(homeId: number | string, awayId: number | string): MatchSimulation | null {
  const home = demoTeamById(homeId);
  const away = demoTeamById(awayId);
  if (!home || !away) return null;
  const hs = strengthOf(home);
  const as = strengthOf(away);
  // λ = lig ort × hücum gücü × rakip savunma zaafı × iç saha avantajı.
  const lambdaHome = LEAGUE_AVG_XG * hs.attack * as.defense * HOME_ADV;
  const lambdaAway = LEAGUE_AVG_XG * as.attack * hs.defense / HOME_ADV;
  return simulateFromLambdas(home.name, away.name, lambdaHome, lambdaAway);
}

/** Sıradaki maç: Beşiktaş (iç) vs Antalyaspor. */
export function demoNextMatchSimulation(): MatchSimulation {
  return simulateMatch(100, 101)!;
}
