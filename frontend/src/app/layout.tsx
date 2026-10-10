import "./globals.css";
import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { Analytics } from "@vercel/analytics/next";
import { AppShell } from "./shell-client";
import { SwRegister } from "./sw-register";

// Official IBM Plex files include Turkish glyphs. Both build and runtime work
// without Google Fonts; upstream commit and OFL license are stored with files.
const sans = localFont({
  src: [
    { path: "../../public/fonts/ibm-plex-sans/IBMPlexSans-Regular.woff2", weight: "400", style: "normal" },
    { path: "../../public/fonts/ibm-plex-sans/IBMPlexSans-Medium.woff2", weight: "500", style: "normal" },
    { path: "../../public/fonts/ibm-plex-sans/IBMPlexSans-SemiBold.woff2", weight: "600", style: "normal" },
    { path: "../../public/fonts/ibm-plex-sans/IBMPlexSans-Bold.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-sans",
  display: "swap",
});

// Yenilemede tema flaşı olmasın: render'dan önce kaydedilen temayı uygula.
// Varsayılan AÇIK tema (kulüp demosu): kayıtlı tema "dark" DEĞİLSE light kalır.
const THEME_SCRIPT = `(function(){try{if(localStorage.getItem("m2-theme")==="dark")document.documentElement.classList.remove("light");else document.documentElement.classList.add("light")}catch(e){document.documentElement.classList.add("light")}})()`;

export const metadata: Metadata = {
  metadataBase: new URL("https://tactic11.com"),
  title: "tactic11 — Teknik Ekip Konsolu",
  description: "Veriyle karar destek — kulüp teknik ekibi için co-pilot.",
  applicationName: "tactic11",
  appleWebApp: {
    capable: true,
    title: "tactic11",
    statusBarStyle: "black-translucent",
  },
  openGraph: {
    type: "website",
    siteName: "tactic11",
    title: "tactic11 — Teknik Ekip Konsolu",
    description: "Veriyle karar destek — kulüp teknik ekibi için co-pilot.",
    url: "https://tactic11.com",
    locale: "tr_TR",
  },
  twitter: {
    card: "summary",
    title: "tactic11 — Teknik Ekip Konsolu",
    description: "Veriyle karar destek — kulüp teknik ekibi için co-pilot.",
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
    <html lang="tr" className={`light ${sans.variable}`}>
      <head>
        {/* FM26 shell ikonları — Tabler webfont SELF-HOSTED (public/tabler-icons.css +
            public/fonts/). CDN'e (jsdelivr) bağlı DEĞİL: offline/firewall/TR-engeli
            durumunda da ikonlar gelir; "ikonlar görünmüyor" tuzağı biter. */}
        <link rel="stylesheet" href="/tabler-icons.css" />
        <link
          rel="preload"
          as="font"
          type="font/woff2"
          href="/fonts/tabler-icons.woff2"
          crossOrigin="anonymous"
        />
      </head>
      <body className="bg-bg text-text">
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <AppShell>{children}</AppShell>
        <SwRegister />
        <Analytics />
      </body>
    </html>
  );
}
