/**
 * Saf Poisson + Dixon-Coles tahmin matematiği — VERİ İÇERMEZ (client'a güvenle
 * import edilir, 1.4MB sonuç JSON'u bundle'a girmez). calibration.ts (server) ve
 * FixturePredictor (client) ikisi de bunu kullanır → tek doğrulanmış motor.
 */

const fact = (n: number) => { let f = 1; for (let i = 2; i <= n; i++) f *= i; return f; };
export const pois = (k: number, l: number) => (Math.exp(-l) * Math.pow(l, k)) / fact(k);
export const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** Dixon-Coles düşük-skor düzeltme faktörü τ. */
export function dcTau(i: number, j: number, lH: number, lA: number, rho: number): number {
  if (i === 0 && j === 0) return 1 - lH * lA * rho;
  if (i === 0 && j === 1) return 1 + lH * rho;
  if (i === 1 && j === 0) return 1 + lA * rho;
  if (i === 1 && j === 1) return 1 - rho;
  return 1;
}

export interface Prediction {
  pH: number; pD: number; pA: number;     // 1 / X / 2
  over: number; btts: number;             // üst 2.5 · karşılıklı gol
  top: { score: string; p: number }[];    // en olası skorlar
  lH: number; lA: number;                 // beklenen goller
}

/** λ_ev, λ_dep → tam tahmin (sonuç + gol marketleri + en olası skorlar). */
export function predictFromLambda(lH: number, lA: number, rho: number): Prediction {
  const M: number[][] = [];
  let s = 0;
  for (let i = 0; i <= 8; i++) { M[i] = []; for (let j = 0; j <= 8; j++) { let p = pois(i, lH) * pois(j, lA); if (i <= 1 && j <= 1) p *= Math.max(1e-4, dcTau(i, j, lH, lA, rho)); M[i][j] = p; s += p; } }
  let pH = 0, pD = 0, pA = 0, over = 0, btts = 0;
  const cells: { score: string; p: number }[] = [];
  for (let i = 0; i <= 8; i++) for (let j = 0; j <= 8; j++) {
    const p = M[i][j] / s;
    if (i > j) pH += p; else if (i === j) pD += p; else pA += p;
    if (i + j >= 3) over += p;
    if (i >= 1 && j >= 1) btts += p;
    if (i <= 5 && j <= 5) cells.push({ score: `${i}-${j}`, p });
  }
  const top = cells.sort((a, b) => b.p - a.p).slice(0, 4);
  return { pH, pD, pA, over, btts, top, lH, lA };
}

export interface LivePrediction {
  pH: number; pD: number; pA: number;       // KALAN maça göre nihai 1/X/2
  remH: number; remA: number;               // kalan sürede beklenen gol (her takım)
  curH: number; curA: number; minute: number;
}

/**
 * MAÇ-İÇİ tahmin — şu anki dakika + skordan nihai sonuç olasılığı.
 *
 * Mantık (sızıntısız, basit ve savunulabilir): maç-öncesi λ'lar tüm 90 dk içindi.
 * Dakika t'de kalan süre oranı f=(90−t)/90 → kalan beklenen gol = λ·f. Kalan golleri
 * Poisson ile dağıt (düşük hücrelerde DC düzeltmesi), mevcut skora EKLE, nihai
 * sonucu sınıfla. Skor öndeyken/geride iken olasılık otomatik kayar — antrenörün
 * "şu an ne durumdayım" sorusunun cevabı.
 *
 * lambdaH/A = maç-öncesi (kadro düzeltmeli) beklenen goller; curH/A = şu anki skor.
 *
 * remFrac (opsiyonel) = "bu dakikadan SONRA atılan gol oranı" — GERÇEK gol-zamanlaması
 * eğrisinden (out-of-sample doğrulandı: goller geç gelir, eşit-dağılımdan daha isabetli).
 * Verilmezse naif eşit dağılım (90−t)/90 kullanılır (geriye-uyum).
 */
export function predictLive(
  lambdaH: number, lambdaA: number, rho: number,
  minute: number, curH: number, curA: number,
  remFrac?: number,
): LivePrediction {
  const m = clamp(minute, 0, 90);
  const f = remFrac != null ? clamp(remFrac, 0, 1) : (90 - m) / 90;   // kalan gol oranı
  const remH = clamp(lambdaH * f, 0.0001, 7);       // kalan sürede beklenen gol
  const remA = clamp(lambdaA * f, 0.0001, 7);
  // Kalan gollerin ortak dağılımı (DC düzeltmesi düşük kalan-skor hücrelerinde).
  const M: number[][] = []; let s = 0;
  for (let i = 0; i <= 8; i++) { M[i] = []; for (let j = 0; j <= 8; j++) { let p = pois(i, remH) * pois(j, remA); if (i <= 1 && j <= 1) p *= Math.max(1e-4, dcTau(i, j, remH, remA, rho)); M[i][j] = p; s += p; } }
  let pH = 0, pD = 0, pA = 0;
  for (let i = 0; i <= 8; i++) for (let j = 0; j <= 8; j++) {
    const p = M[i][j] / s;
    const fh = curH + i, fa = curA + j;             // nihai skor = mevcut + kalan
    if (fh > fa) pH += p; else if (fh === fa) pD += p; else pA += p;
  }
  return { pH, pD, pA, remH, remA, curH, curA, minute: m };
}

/** Takım gücünden (log-ölçek atk/def) + lig tabanından λ + tahmin. */
export function predictFixture(
  atkH: number, defH: number, atkA: number, defA: number,
  muH: number, muA: number, rho: number,
): Prediction {
  const lH = clamp(Math.exp(muH + atkH - defA), 0.05, 7);
  const lA = clamp(Math.exp(muA + atkA - defH), 0.05, 7);
  return predictFromLambda(lH, lA, rho);
}

/** Elo rating çiftinden (ev/dep) düz-Poisson λ'ları — backtest Elo bileşeniyle aynı. */
export function eloLambdas(
  eloH: number, eloA: number, ha: number, epg: number, avg: number,
): { lH: number; lA: number } {
  const drift = eloH + ha - eloA;
  const sup = (drift * 0.8) / epg;   // SHRINK=0.8 (backtest ile aynı)
  return { lH: clamp((avg + sup) / 2, 0.15, 6), lA: clamp((avg - sup) / 2, 0.15, 6) };
}

/** ENSEMBLE tahmini — AD-xG modeli (%ensW) + Elo (%1-ensW), olasılık düzeyinde
 *  harman. /calibration'da out-of-sample doğrulanan üretim modelinin aynısı. */
export function predictEnsemble(
  atkH: number, defH: number, atkA: number, defA: number,
  muH: number, muA: number, rho: number,
  eloH: number, eloA: number, ensW: number,
  eloHA: number, eloEPG: number, eloAvg: number,
): Prediction {
  const ad = predictFixture(atkH, defH, atkA, defA, muH, muA, rho);
  const el = eloLambdas(eloH, eloA, eloHA, eloEPG, eloAvg);
  const elo = predictFromLambda(el.lH, el.lA, 0);   // eski Elo modeli DC kullanmaz
  const w = clamp(ensW, 0, 1), v = 1 - w;
  return {
    pH: w * ad.pH + v * elo.pH, pD: w * ad.pD + v * elo.pD, pA: w * ad.pA + v * elo.pA,
    over: w * ad.over + v * elo.over, btts: w * ad.btts + v * elo.btts,
    top: ad.top, lH: ad.lH, lA: ad.lA,
  };
}
