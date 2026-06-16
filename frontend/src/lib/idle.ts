/**
 * useIdleTimer — kullanıcı etkileşim yokluğunu izle, callback'leri tetikle.
 * 14 dk: uyarı; 15 dk: logout.
 *
 * Mousemove/keydown/click/scroll/touchstart event'leri activity sayar.
 */
"use client";

import * as React from "react";

const EVENTS = [
  "mousemove",
  "keydown",
  "click",
  "scroll",
  "touchstart",
] as const;

export interface IdleOptions {
  /** Toplam idle eşik (ms). Default 15 dk. */
  timeout?: number;
  /** Timeout'tan kaç ms önce warn callback'i. Default 60sn. */
  warnBefore?: number;
  onWarn?: () => void;
  onIdle?: () => void;
}

export function useIdleTimer({
  timeout = 15 * 60 * 1000,
  warnBefore = 60 * 1000,
  onWarn,
  onIdle,
}: IdleOptions) {
  React.useEffect(() => {
    let warnTimer: ReturnType<typeof setTimeout>;
    let idleTimer: ReturnType<typeof setTimeout>;

    const reset = () => {
      clearTimeout(warnTimer);
      clearTimeout(idleTimer);
      // timeout sonlu değilse (Infinity = "devre dışı") timer kurma.
      // setTimeout(fn, Infinity) geçersiz delay → tarayıcıda ANINDA tetiklenir;
      // kullanıcı yokken hatalı logout + /login yönlendirme döngüsüne yol açıyordu.
      if (!Number.isFinite(timeout)) return;
      warnTimer = setTimeout(() => onWarn?.(), Math.max(0, timeout - warnBefore));
      idleTimer = setTimeout(() => onIdle?.(), timeout);
    };

    reset();
    for (const ev of EVENTS) {
      window.addEventListener(ev, reset, { passive: true });
    }
    return () => {
      clearTimeout(warnTimer);
      clearTimeout(idleTimer);
      for (const ev of EVENTS) {
        window.removeEventListener(ev, reset);
      }
    };
  }, [timeout, warnBefore, onWarn, onIdle]);
}
