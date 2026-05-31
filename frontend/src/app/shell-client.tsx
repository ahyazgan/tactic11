/**
 * Shell wrapper — /login için sidebar+topbar gizler; diğer rotalarda sarar.
 * Client-side çünkü usePathname client hook'u.
 *
 * i18n: tüm ağaç I18nProvider ile sarılır (login dahil dil tercihi geçerli).
 * Mobil: <md ekranda sidebar drawer (hamburger ile aç/kapa); ≥md sabit.
 */
"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { Sidebar, TopBar } from "@/components/shell";
import { I18nProvider } from "@/lib/i18n";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isAuthRoute = pathname === "/login" || pathname.startsWith("/login/");
  const [mobileNavOpen, setMobileNavOpen] = React.useState(false);

  // Rota değişince mobil drawer'ı kapat.
  React.useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  if (isAuthRoute) {
    return <I18nProvider>{children}</I18nProvider>;
  }

  return (
    <I18nProvider>
      <TopBar onMenuClick={() => setMobileNavOpen((v) => !v)} />
      <Sidebar
        mobileOpen={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
      />
      <main className="pl-0 md:pl-56 pt-12 min-h-screen bg-bg">
        <div className="p-3 sm:p-4">{children}</div>
      </main>
    </I18nProvider>
  );
}
