/**
 * Shell wrapper. Tüm ekranlar artık ConsoleShell'i (kendi tam-ekran header+nav)
 * kullanır; eski TopBar+Sidebar kaldırıldı. Bu sarmalayıcı yalnızca I18nProvider
 * bağlamını sağlar (login dahil her rota kendi düzenini çizer).
 */
"use client";

import * as React from "react";
import { I18nProvider } from "@/lib/i18n";

export function AppShell({ children }: { children: React.ReactNode }) {
  return <I18nProvider>{children}</I18nProvider>;
}
