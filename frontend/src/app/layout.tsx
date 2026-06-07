import "./globals.css";
import type { Metadata, Viewport } from "next";
import { AppShell } from "./shell-client";
import { SwRegister } from "./sw-register";
import { ThemeToggle } from "./theme-toggle";

// Yenilemede tema flaşı olmasın: render'dan önce kaydedilen temayı uygula.
const THEME_SCRIPT = `(function(){try{if(localStorage.getItem("m2-theme")==="light")document.documentElement.classList.add("light")}catch(e){}})()`;

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
  themeColor: "#0c0e14",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr" className="dark">
      <body className="bg-bg text-text">
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <AppShell>{children}</AppShell>
        <ThemeToggle />
        <SwRegister />
      </body>
    </html>
  );
}
