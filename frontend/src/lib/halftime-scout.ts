/**
 * Devre Arası Scout — 1. yarı sayıları + rakip okuması + 2. yarı taktik ayarları.
 *
 * Maç-öncesi rakip-okumanın devre-arası hâli: rakibin 1. yarıda ne yaptığı, devre
 * arasında neyi değiştireceği (DNA'dan), ve bizim 2. yarı şekil/pres ayarlarımız.
 * firstHalfSummary (gerçek 1. yarı) + tacticalDna(rakip)'tan türer.
 */

import { demoTeamById } from "./demo-teams";
import { tacticalDna } from "./tactical-dna";
import { firstHalfSummary } from "./halftime-advice";

export interface FirstHalfStats {
  possession: number; fieldTilt: number; ppda: number;
  xg: [number, number]; shots: [number, number]; momentum: number;
}
export interface OpponentHtRead { whatWorked: string[]; theyllLikely: string; ourCounter: string }
export interface HtAdjust { move: string; detail: string }

/** 1. yarı sayı şeridi (analitik halftime sayfasıyla tutarlı). */
export function firstHalfStats(): FirstHalfStats {
  const fh = firstHalfSummary();
  return {
    possession: 54, fieldTilt: 57, ppda: 9.4,        // 1. yarı motor çıktıları (FH_STATS ile aynı)
    xg: [fh.homeXg, fh.awayXg], shots: [fh.shotsHome, fh.shotsAway], momentum: fh.momentum,
  };
}

/** Rakibin 1. yarı okuması + devre arasında ne değiştireceği + önlemimiz. */
export function opponentHalftimeRead(themId = 101): OpponentHtRead {
  const row = demoTeamById(themId);
  const s = row ? tacticalDna(row).style : null;
  const fh = firstHalfSummary();
  const deepBlock = !s || s.lineHeight <= 46;
  const counter = !s || s.directness >= 52;

  const whatWorked: string[] = [];
  if (fh.concededSetPiece) whatWorked.push("Far-post duran toptan beraberlik — ilk yarı zaafımızı tam oradan cezalandırdılar.");
  if (counter) whatWorked.push("Kontra tehdidi: topu kazandıklarında 2-3 pasta hızlı çıktılar.");
  if (!whatWorked.length) whatWorked.push("Belirgin bir üstünlük kuramadılar; oyun bizim kontrolümüzde geçti.");

  const theyllLikely = deepBlock
    ? "Beraberlikle daha da geriye yaslanır; alanı kapatıp kontra + duran top fırsatı bekler. 2. yarı daha pasif başlayabilirler."
    : "Mevcut dengeyi koruyup eşleşme avantajlarını zorlamaya devam ederler.";

  const ourCounter = "Genişliği koru, far-post markajını adam-adamaya çevir, kontraya karşı ön libero dengesini bozma. Tempoyu biz dikte et.";
  return { whatWorked, theyllLikely, ourCounter };
}

/** 2. yarı taktik ayarları — değişiklik dışı şekil/pres hamleleri. */
export function secondHalfAdjustments(themId = 101): HtAdjust[] {
  const row = demoTeamById(themId);
  const s = row ? tacticalDna(row).style : null;
  const out: HtAdjust[] = [];
  if (!s || s.lineHeight <= 46) out.push({ move: "Pres tetiğini yükselt", detail: "Onları kendi yarısına hapset; geriye yaslanmalarına izin verme, duran top fırsatı azalt." });
  out.push({ move: "Sol koridora destek", detail: "Rıdvan (3) zorlanıyor — orta sahayı o tarafa kaydır ya da yardımcı gönder." });
  if (firstHalfSummary().concededSetPiece) out.push({ move: "Far-post adam-adama", detail: "Zonal'da yediğimiz golü tekrarlatma; en iyi hava topçuyu (Agbadou) far-post'a sabitle." });
  out.push({ move: "Tempoyu yükselt", detail: "Rakip 75+ tempo düşürüyor (zaaf) — 2. yarı ortasında baskıyı artırıp farkı ara." });
  return out;
}
