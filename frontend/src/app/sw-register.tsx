"use client";

import * as React from "react";

/** Service worker kaydı — PWA kurulabilirliği için.
 *
 * Geliştirme (localhost) ve demo'da KAYIT YOK: aksi halde SW eski app shell'ini
 * önbelleğe alıp yeni sürümü göstermez (klasik "değişiklik gelmiyor" tuzağı).
 * Üstelik daha önce kaydolmuş bir SW varsa onu unregister edip cache'leri temizler.
 */
export function SwRegister() {
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;

    const isLocalhost = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);
    if (isLocalhost) {
      // Dev/demo: önceki SW kaydını ve cache'lerini temizle, yeni kayıt yapma.
      navigator.serviceWorker.getRegistrations()
        .then((regs) => regs.forEach((r) => r.unregister()))
        .catch(() => {});
      if (typeof caches !== "undefined") {
        caches.keys().then((keys) => keys.forEach((k) => caches.delete(k))).catch(() => {});
      }
      return;
    }

    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* sessizce yut — SW kaydı kritik değil */
    });
  }, []);
  return null;
}
