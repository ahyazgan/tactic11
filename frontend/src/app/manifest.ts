import type { MetadataRoute } from "next";

/** PWA manifest — kurulabilir uygulama. Telefon/tablet/PC aynı; yatay kilit. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "manager2 — Teknik Ekip Konsolu",
    short_name: "manager2",
    description: "Veriyle karar destek — kulüp teknik ekibi için co-pilot.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "landscape",
    background_color: "#0c0e14",
    theme_color: "#0c0e14",
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
