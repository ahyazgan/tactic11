import type { MetadataRoute } from "next";

/** PWA manifest — kurulabilir uygulama. Tablet dikey de desteklenir (yatay kilit kalktı). */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "tactic11 — Teknik Ekip Konsolu",
    short_name: "tactic11",
    description: "Veriyle karar destek — kulüp teknik ekibi için co-pilot.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#eaf0ea",
    theme_color: "#1e6b41",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "maskable",
      },
    ],
  };
}
