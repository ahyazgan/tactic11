/**
 * SPORTMONKS MATCHDAY BAĞLANTI PLANI — matchday motorunu gerçek veriye bağlama
 * haritası (kod + görünür plan). Her matchday özelliğini bir Sportmonks ucuna +
 * add-on'a + duruma eşler. Abonelik gelince "fill-in-the-blanks": adapter
 * fonksiyonları gerçek /sm/* çağrılarıyla doldurulur, MOTOR ve UI değişmez.
 *
 * Mevcut (bağlı): /sm/standings, /sm/squad, /sm/schedule (sportmonks.ts).
 * Bu modül EKLENECEK uçları + her özelliğin gerçekçilik durumunu tanımlar.
 *
 * Durumlar:
 *   ready    → temel Sportmonks ile çalışır (bazıları zaten bağlı)
 *   addon    → belirli bir Sportmonks add-on'u gerekir (xG / Predictions / Livescores)
 *   derived  → gerçek AGREGAT istatistikten HESAPLARIZ (demo'nun event-temelli
 *              halinden daha sığ ama gerçek; motor hazır)
 *   premium  → Sportmonks'ta YOK; event-koordinat/tracking feed'i (Wyscout/Opta)
 *              gerekir → bu öğe projeksiyon kalır, dürüstçe işaretli
 */

export type SmStatus = "ready" | "addon" | "derived" | "premium";

export interface MatchdayDataItem {
  screen: "Maç Öncesi" | "Maç Modu" | "Devre Arası" | "Değerlendirme";
  feature: string;
  smSource: string;       // hangi Sportmonks ucu / add-on
  status: SmStatus;
  note: string;
}

/** Matchday motorunun her parçası → Sportmonks kaynağı + durum. */
export const MATCHDAY_DATA_MAP: MatchdayDataItem[] = [
  // ── Maç Öncesi ──
  { screen: "Maç Öncesi", feature: "Fikstür + takımlar", smSource: "/sm/schedule (BAĞLI)", status: "ready", note: "Zaten bağlı — gerçek Süper Lig fikstürü." },
  { screen: "Maç Öncesi", feature: "Maç tahmini (1/X/2, skor, üst/btts)", smSource: "Predictions add-on · veya kendi modelimiz + xG add-on", status: "addon", note: "Kendi doğrulanmış modelimizi gerçek xGF/xGA ile besleriz; güven rakamı Süper Lig'de yeniden ölçülür." },
  { screen: "Maç Öncesi", feature: "Rakip muhtemel 11 + diziliş", smSource: "Fixtures + lineups (probable)", status: "ready", note: "Sportmonks maç-öncesi olası diziliş verir → projeksiyon yerine gerçek." },
  { screen: "Maç Öncesi", feature: "Rakip form", smSource: "/sm/schedule (sonuçlar)", status: "ready", note: "Son maç sonuçları zaten erişilebilir." },
  { screen: "Maç Öncesi", feature: "Rakip zaafları", smSource: "Team statistics (sezon agregat)", status: "derived", note: "Yenilen set-piece golü, zayıf kanat vb. agregat statten — event-seviyesi değil." },
  { screen: "Maç Öncesi", feature: "Taktik DNA (8 eksen)", smSource: "Team statistics", status: "derived", note: "Possession/directness/duran top agregat statten türetilir (demo'daki gibi ama gerçek girdiyle)." },
  { screen: "Maç Öncesi", feature: "Dangerman'ler", smSource: "Topscorers + player statistics", status: "derived", note: "Gol/asist/şut liderlerinden; ısı/dokunuş-payı için event verisi gerekir." },
  { screen: "Maç Öncesi", feature: "Önerilen 11 + dinlendirme", smSource: "/sm/squad + injuries", status: "ready", note: "Gerçek kadro + sakatlık/ceza listesi (haber düzeyi); yük-temelli risk için Tier 3." },

  // ── Maç Modu ──
  { screen: "Maç Modu", feature: "Canlı skor / dakika / olaylar", smSource: "Livescores (in-play) add-on", status: "addon", note: "Canlı feed add-on'u — gerçek maç-içi akış (gecikme ~saniyeler)." },
  { screen: "Maç Modu", feature: "Canlı xG", smSource: "xG add-on (in-play)", status: "addon", note: "Şut-bazlı canlı xG → win-prob ve momentum gerçek girdiyle." },
  { screen: "Maç Modu", feature: "Kazanma olasılığı / momentum", smSource: "Kendi modelimiz (skor + canlı xG)", status: "ready", note: "liveWinProb motoru hazır; gerçek skor+xG girince çalışır." },
  { screen: "Maç Modu", feature: "Değişiklik / kart bütçesi", smSource: "In-play events", status: "addon", note: "Sub/kart olayları canlı feed'den → bütçe gerçek sayılır." },
  { screen: "Maç Modu", feature: "Rakip canlı okuma (şekil, hatlar arası)", smSource: "— (event-koordinat/tracking)", status: "premium", note: "Mekânsal sinyaller Sportmonks'ta yok → projeksiyon kalır; Tier 2 feed gerekir." },
  { screen: "Maç Modu", feature: "Canlı taktik ayarlar (pres/koridor)", smSource: "— (kısmen in-play stat)", status: "premium", note: "Momentum-tetikli öneri canlı stattan kısmen; tam mekânsal için tracking." },

  // ── Devre Arası ──
  { screen: "Devre Arası", feature: "1. yarı sayıları (poss/şut/xG)", smSource: "In-play statistics (HT)", status: "addon", note: "Devre arası istatistik snapshot'ı — gerçek." },
  { screen: "Devre Arası", feature: "Rakip 1. yarı okuması", smSource: "1. yarı stat + DNA", status: "derived", note: "Gerçek 1. yarı statten + DNA; spatial detay premium." },
  { screen: "Devre Arası", feature: "2. yarı ayar/hamle önerileri", smSource: "Kendi motorumuz", status: "ready", note: "halftime-advice/scout motoru gerçek 1. yarı verisini okur." },

  // ── Değerlendirme ──
  { screen: "Değerlendirme", feature: "Final sonuç + olaylar", smSource: "Fixture result + events", status: "ready", note: "Maç bitince gerçek sonuç/olaylar." },
  { screen: "Değerlendirme", feature: "Uyarı-sonuç reconcile", smSource: "Kendi mantığımız + gerçek olaylar", status: "ready", note: "Event-temelli reconcile gerçek olaylarla otomatik dolar." },
  { screen: "Değerlendirme", feature: "Motor sicili (sezon isabet)", smSource: "Her maç birikir", status: "ready", note: "Gerçek sezonda otomatik dolar → her motorun gerçek isabet oranı." },
];

/** Özet sayım — planı tek bakışta. */
export function matchdaySummary(): Record<SmStatus, number> {
  const out: Record<SmStatus, number> = { ready: 0, addon: 0, derived: 0, premium: 0 };
  for (const i of MATCHDAY_DATA_MAP) out[i.status]++;
  return out;
}

export const STATUS_LABEL: Record<SmStatus, string> = {
  ready: "Hazır / bağlı",
  addon: "Add-on gerekir",
  derived: "Agregattan türetilir",
  premium: "Premium feed (Tier 2)",
};
export const STATUS_COLOR: Record<SmStatus, string> = {
  ready: "var(--low)", addon: "var(--mid)", derived: "var(--accent)", premium: "var(--high)",
};

/**
 * 3 FAZLI GEÇİŞ PLANI (abonelik sonrası):
 *
 *  Faz 1 — Temel gerçek (zaten kısmen bağlı): /sm/schedule + /sm/squad + standings.
 *    → Maç Öncesi'nde fikstür/form/kadro gerçek. Kalibrasyon backtest'i Süper Lig'de
 *      çalıştırılır → senin liginde kendi güven rakamı.
 *
 *  Faz 2 — Add-on'lar (xG + Predictions + Livescores): canlı skor/olay/xG + tahmin.
 *    → Maç Modu canlı feed'e bağlanır (live-feed.ts'teki providerFeed implemente edilir,
 *      UI değişmez). Win-prob/momentum/bütçe/devre-arası stat GERÇEK. Reconcile + motor
 *      sicili gerçek olaylarla dolmaya başlar.
 *
 *  Faz 3 — Derinlik: rakip zaafları/DNA/dangerman agregat statten gerçek girdiyle.
 *    → Mekânsal sinyaller (rakip canlı okuma, pas ağı, pres bölgesi) PROJEKSİYON kalır;
 *      bunlar için Tier 2 event/tracking feed (Wyscout/Opta) ayrı karar.
 *
 * Mimari hazır: adapter dikişi live-feed.ts (LiveFeedSource) + sportmonks.ts (/sm/*).
 * Bu modüldeki stub'lar gerçek çağrılarla doldurulunca motorlar değişmeden gerçeğe geçer.
 */

// ── Adapter stub'ları — abonelik gelince gerçek /sm/* çağrılarıyla doldurulur ──
// (Şu an demo motorları besliyor; bunlar "nereye ne bağlanacak"ı kodda sabitler.)

export interface SmFixturePrediction { pHome: number; pDraw: number; pAway: number; xgHome: number; xgAway: number }

/** TODO(faz2): GET /sm/fixtures/{id}?include=predictions,xgfixture → bizim modele besle. */
export async function smFixturePrediction(/* fixtureId: number */): Promise<SmFixturePrediction | null> {
  return null; // abonelik yok → demo motor devrede (match-simulation.demoNextMatchSimulation)
}

/** TODO(faz1): GET /sm/fixtures/{id}?include=lineups → rakip olası 11. */
export async function smProbableLineup(/* fixtureId, teamId */): Promise<{ num: number; pos: string }[] | null> {
  return null; // → opponent-scout.opponentXI projeksiyonu devrede
}

/** TODO(faz2): canlı in-play snapshot → live-feed.ts LiveSnapshot şekline map. */
export async function smLiveSnapshot(/* fixtureId */): Promise<null> {
  return null; // → live-feed.demoFeed devrede
}
