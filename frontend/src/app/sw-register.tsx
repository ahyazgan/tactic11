"use client";

import * as React from "react";

/** Service worker kaydı — PWA kurulabilirliği için. */
export function SwRegister() {
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* sessizce yut — SW kaydı kritik değil */
    });
  }, []);
  return null;
}
