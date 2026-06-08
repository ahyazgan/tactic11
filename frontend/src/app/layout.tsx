import "./globals.css";
import type { Metadata, Viewport } from "next";
import { AppShell } from "./shell-client";
import { SwRegister } from "./sw-register";
import { ThemeToggle } from "./theme-toggle";

// Yenilemede tema flaşı olmasın: render'dan önce kaydedilen temayı uygula.
// Varsayılan AÇIK tema (kulüp demosu): kayıtlı tema "dark" DEĞİLSE light kalır.
const THEME_SCRIPT = `(function(){try{if(localStorage.getItem("m2-theme")==="dark")document.documentElement.classList.remove("light");else document.documentElement.classList.add("light")}catch(e){document.documentElement.classList.add("light")}})()`;

export const metadata: Metadata = {
  title: "manager2 — Teknik Ekip Konsolu",
  description: "Veriyle karar destek — kulüp teknik ekibi için co-pilot.",
  applicationName: "manager2",
  appleWebApp: {
    capable: true,
    title: "manager2",
    statusBarStyle: "black-translucent",
  },
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr" className="light">
      <body className="bg-bg text-text">
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <AppShell>{children}</AppShell>
        <ThemeToggle />
        <SwRegister />
      </body>
    </html>
  );
}
