/**
 * Doğrulanmış güven anlık-değeri (snapshot) — /calibration'daki out-of-sample
 * backtest'in özet sonuçları. Diğer sayfalar (command/match-plan) bu sabiti
 * referans gösterir; böylece 1.4MB sonuç JSON'u o sayfaların bundle'ına girmez.
 *
 * KAYNAK: lib/calibration.computeCalibration() — görülmemiş 2022-23 sezonu (1826
 * maç), top-5 Avrupa ligi. Veri/model değişirse buradaki rakamlar /calibration ile
 * yeniden senkronlanmalı (oradaki canlı hesap tek gerçek kaynaktır).
 */

export const VALIDATED_TRUST = {
  result: 76,   // Maç Sonucu (1/X/2)
  over: 56,     // Üst/Alt 2.5 gol
  btts: 45,     // Karşılıklı gol
} as const;

export const VALIDATED_META = {
  season: "2022-23",
  matches: 1826,
  method: "Ensemble: Atak/Defans·xG·Dixon-Coles (%70) + Elo (%30)",
  outOfSample: true,
} as const;

export type TrustMarket = keyof typeof VALIDATED_TRUST;
