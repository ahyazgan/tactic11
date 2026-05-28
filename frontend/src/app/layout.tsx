import "./globals.css";
import type { Metadata } from "next";
import { AppShell } from "./shell-client";

export const metadata: Metadata = {
  title: "manager2 — Football Intelligence",
  description: "Veriyle karar destek — kulüp analiz şefi için co-pilot.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr" className="dark">
      <body className="bg-bg text-text">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
