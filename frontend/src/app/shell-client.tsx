/**
 * Shell wrapper. Tüm ekranlar artık ConsoleShell'i (kendi tam-ekran header+nav)
 * kullanır; eski TopBar+Sidebar kaldırıldı. Bu sarmalayıcı I18nProvider +
 * global SWR yapılandırması (B3) sağlar (login dahil her rota kendi düzenini çizer).
 */
"use client";

import * as React from "react";
import { SWRConfig } from "swr";
import { I18nProvider } from "@/lib/i18n";
import { ApiError } from "@/lib/api";

// Global SWR davranışı (Faz 3 / B3):
//  - 5xx ve ağ/parse hataları (status null) tekrar denenir; 4xx (kullanıcı/
//    yetki hatası) denenmez — boşuna istek yağdırmaz.
//  - errorRetryCount 3, sabit (linear) 2sn aralık.
//  - revalidateOnFocus default (açık) — sekmeye dönünce tazelenir.
// Sayfa-bazlı override (refreshInterval vb.) useSWR çağrılarında kalır.
const swrConfig = {
  errorRetryCount: 3,
  errorRetryInterval: 2000,
  shouldRetryOnError: true,
  onErrorRetry: (
    error: unknown,
    _key: string,
    config: Readonly<{ errorRetryCount?: number; errorRetryInterval?: number }>,
    revalidate: (opts: { retryCount: number }) => void,
    { retryCount }: { retryCount: number },
  ) => {
    // 4xx → tekrar deneme (kullanıcı/yetki hatası kalıcıdır).
    const status = error instanceof ApiError ? error.status : null;
    if (status != null && status >= 400 && status < 500) return;
    const max = config.errorRetryCount ?? 3;
    if (retryCount >= max) return;
    const interval = config.errorRetryInterval ?? 2000;
    setTimeout(() => revalidate({ retryCount }), interval);
  },
};

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={swrConfig}>
      <I18nProvider>{children}</I18nProvider>
    </SWRConfig>
  );
}
