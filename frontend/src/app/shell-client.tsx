/**
 * Shell wrapper — /login için sidebar+topbar gizler; diğer rotalarda sarar.
 * Client-side çünkü usePathname client hook'u.
 */
"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { Sidebar, TopBar } from "@/components/shell";
import { I18nProvider } from "@/lib/i18n";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAuthRoute = pathname === "/login" || pathname.startsWith("/login/");

  if (isAuthRoute) {
    return <I18nProvider>{children}</I18nProvider>;
  }

  return (
    <I18nProvider>
      <TopBar />
      <Sidebar />
      <main className="pl-56 pt-12 min-h-screen bg-bg">
        <div className="p-4">{children}</div>
      </main>
    </I18nProvider>
  );
}
