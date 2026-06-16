/**
 * Canlı Kazanma Olasılığı — maç simülasyonunun IN-GAME hali.
 *
 * Her dakika için: mevcut skor + KALAN süre + canlı xG temposundan, kalan maçta
 * atılacak ek golleri Poisson ile modeller ve galibiyet/beraberlik/mağlubiyet
 * olasılığını çıkarır. Skor değiştikçe (gol) eğri sıçrar; süre azaldıkça olasılık
 * mevcut sonuca yakınsar. Maç öncesi λ (lib/match-simulation) taban beklenti,
 * canlı xG temposu ile harmanlanır. Saf+deterministik.
 */

import { demoLive } from "@/lib/demo-data";
import { demoNextMatchSimulation } from "@/lib/match-simulation";

const fact = (n: number): number => { let f = 1; for (let i = 2; i <= n; i++) f *= i; return f; };
const poisson = (k: number, l: number) => (Math.pow(l, k) * Math.exp(-l)) / fact(k);
const MAXX = 6;   // kalan maçta takım başına en çok 6 ek gol

export interface WinProb {
  minute: number;
  scoreHome: number;
  scoreAway: number;
  pHome: number;
  pDraw: number;
  pAway: number;
  lambdaHomeRem: number;   // kalan sürede beklenen ev golü
  lambdaAwayRem: number;
}

/**
 * Anlık kazanma olasılığı — mevcut skor (h,a) sabit, kalan sürede ek goller Poisson.
 * effλ = maç-öncesi tam-90 beklenti ile canlı tempo harmanı; kalan = effλ × (90-dk)/90.
 */
export function liveWinProb(
  h: number, a: number, minute: number,
  lambdaHomeFull: number, lambdaAwayFull: number,
  liveXgHome?: number, liveXgAway?: number,
): WinProb {
  const m = Math.max(0, Math.min(90, minute));
  const remFrac = Math.max(0, (90 - m) / 90);

  // Canlı tempo (mevcut xG'yi tam maça projekte et); maç-öncesiyle 50/50 harmanla.
  const paceHome = m > 5 && liveXgHome != null ? (liveXgHome / m) * 90 : lambdaHomeFull;
  const paceAway = m > 5 && liveXgAway != null ? (liveXgAway / m) * 90 : lambdaAwayFull;
  const effHome = 0.5 * lambdaHomeFull + 0.5 * paceHome;
  const effAway = 0.5 * lambdaAwayFull + 0.5 * paceAway;

  const lambdaHomeRem = effHome * remFrac;
  const lambdaAwayRem = effAway * remFrac;

  let pHome = 0, pDraw = 0, pAway = 0;
  for (let i = 0; i <= MAXX; i++) {
    const ph = poisson(i, lambdaHomeRem);
    for (let j = 0; j <= MAXX; j++) {
      const p = ph * poisson(j, lambdaAwayRem);
      const fh = h + i, fa = a + j;
      if (fh > fa) pHome += p; else if (fh === fa) pDraw += p; else pAway += p;
    }
  }
  const tot = pHome + pDraw + pAway || 1;
  const r3 = (x: number) => Math.round((x / tot) * 1000) / 1000;
  return {
    minute: m, scoreHome: h, scoreAway: a,
    pHome: r3(pHome), pDraw: r3(pDraw), pAway: r3(pAway),
    lambdaHomeRem: Math.round(lambdaHomeRem * 100) / 100,
    lambdaAwayRem: Math.round(lambdaAwayRem * 100) / 100,
  };
}

// ── Demo: canlı maçtan (demoLive) win-prob eğrisi ────────────────────────────
const asOfScore = (minute: number): [number, number] => {
  let h = 0, a = 0;
  for (const e of demoLive.events) {
    if (e.minute <= minute && e.type === "gol") { if (e.team === "home") h++; else a++; }
  }
  return [h, a];
};

/** demoLive serisindeki her nokta için anlık kazanma olasılığı (eğri). */
export function demoWinProbCurve(): WinProb[] {
  const sim = demoNextMatchSimulation();
  return demoLive.series.map((p) => {
    const [h, a] = asOfScore(p.minute);
    return liveWinProb(h, a, p.minute, sim.lambdaHome, sim.lambdaAway, p.home, p.away);
  });
}

/** Şu anki (demoLive.minute) anlık kazanma olasılığı. */
export function demoWinProbNow(): WinProb {
  const sim = demoNextMatchSimulation();
  const cur = demoLive.series[demoLive.series.length - 1];
  const [h, a] = asOfScore(demoLive.minute);
  return liveWinProb(h, a, demoLive.minute, sim.lambdaHome, sim.lambdaAway, cur.home, cur.away);
}
