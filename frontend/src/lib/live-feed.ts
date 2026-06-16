/**
 * CANLI FEED ADAPTÖRÜ — maç-içi UI'nın tükettiği veri sözleşmesi (seam).
 *
 * Mimari ilke: Maç Modu / Devre Arası / Maç Değerlendirmesi ekranları YALNIZCA bu
 * arayüzü tüketir. Veri nereden geldiğini bilmezler. Bugün demo (kayıtlı zaman-
 * serisi) besler; production'da gerçek sağlayıcı (Sportmonks in-play, opsiyonel
 * tracking) AYNI arayüzü besler — UI tek satır değişmeden canlıya geçer.
 *
 *   UI bileşenleri  ──tüketir──>  LiveFeedSource  <──besler──  demo | sağlayıcı
 *
 * Geçiş tek noktadan: `activeFeed()`. Demo→canlı için sadece yeni bir
 * LiveFeedSource implementasyonu yazılır (websocket/poll), UI'ya dokunulmaz.
 */

import { demoLive } from "./demo-data";
import { demoWinProbNow, type WinProb } from "./live-win-probability";

export interface LiveEventLite { minute: number; type: string; text: string }
export interface LiveAlertLite { minute: number; severity: string; head: string; body: string }

/** Maç-içi ekranların ihtiyaç duyduğu TÜM canlı veri — tek anlık görüntü. */
export interface LiveSnapshot {
  minute: number;
  score: [number, number];
  winProb: WinProb;
  momentum: number;            // -100..100 (+ bize)
  events: LiveEventLite[];
  subsUsed: number;            // yapılan değişiklik sayısı
}

export interface LiveFeedSource {
  id: string;
  label: string;
  isLive: boolean;             // true = gerçek sağlayıcı, false = demo/kayıt
  latencyMs: number | null;    // canlı feed gecikmesi (demo: null)
  snapshot(): LiveSnapshot;
}

/** DEMO kaynağı — kayıtlı zaman-serisinden (demoLive) besler. */
export const demoFeed: LiveFeedSource = {
  id: "demo",
  label: "Demo · kayıtlı zaman-serisi",
  isLive: false,
  latencyMs: null,
  snapshot() {
    return {
      minute: demoLive.minute,
      score: demoLive.score,
      winProb: demoWinProbNow(),
      momentum: demoLive.series[demoLive.series.length - 1]?.momentum ?? 0,
      events: demoLive.events.map((e) => ({ minute: e.minute, type: e.type, text: e.text })),
      subsUsed: demoLive.events.filter((e) => e.type === "degisiklik").length,
    };
  },
};

/**
 * PRODUCTION kaynağı (stub) — gerçek sağlayıcı buraya. Aynı LiveFeedSource'u
 * implemente eder; UI değişmez. Örnek iskelet:
 *
 *   export function providerFeed(client: ProviderClient): LiveFeedSource {
 *     return {
 *       id: "sportmonks", label: "Sportmonks · canlı", isLive: true, latencyMs: 8000,
 *       snapshot() {
 *         const s = client.lastInplay();              // websocket/poll'dan son durum
 *         return {
 *           minute: s.minute, score: [s.home, s.away],
 *           winProb: liveWinProb(s.home, s.away, s.minute, λh, λa, s.xgHome, s.xgAway),
 *           momentum: deriveMomentum(s), events: mapEvents(s.events),
 *           subsUsed: s.substitutions.length,
 *         };
 *       },
 *     };
 *   }
 *
 * Gerekli: sağlayıcı abonelik (Sportmonks in-play + xG add-on). Derin sinyaller
 * (koridor/pres/hatlar-arası) için event-koordinat veya tracking feed'i gerekir
 * (bkz. /calibration sınırlar bölümü). Skor/xG/win-prob bu add-on ile çalışır.
 */

let _active: LiveFeedSource = demoFeed;
/** Aktif feed (tek geçiş noktası). Production: setActiveFeed(providerFeed(...)). */
export function activeFeed(): LiveFeedSource { return _active; }
export function setActiveFeed(src: LiveFeedSource): void { _active = src; }
