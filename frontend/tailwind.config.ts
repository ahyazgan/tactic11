import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // DESIGN.md token'ları — tema-değişkenli (açık/koyu). Değerler
        // globals.css'te :root (koyu) + html.light (açık) altında.
        // Zeminler
        bg: "var(--c-bg)",
        surface: "var(--c-surface)",
        surface2: "var(--c-surface2)",
        elevated: "var(--c-elevated)",
        // Çizgiler
        border: "var(--c-border)",
        borderlt: "var(--c-borderlt)",
        // Metin
        text: "var(--c-text)",
        textmut: "var(--c-textmut)",
        textdim: "var(--c-textdim)",
        // Marka
        accent: "#3d7eff",
        accenthov: "#5a92ff",
        // Kulüp markası — CSS değişkeninden (tenant'a göre dinamik), varsayılan kırmızı
        brand: "var(--brand, #e30613)",
        // Durum
        win: "#3fb950",
        draw: "#d4a72c",
        loss: "#e5534b",
        warn: "#d4a72c",
        danger: "#e5534b",
        ok: "#3fb950",
        // 4-kademe risk skalası (FM): high turuncu (yeni), diğerleri mevcut.
        high: "#f97316",

        // Legacy aliases — mevcut sayfalar refactor edilene kadar geriye uyumluluk
        // Yeni kod DESIGN.md token'larını kullanır; aşağıdakiler kalsın
        // ki mevcut /matches, /chat, /login, /calibration sayfaları kırılmasın.
        panel: "var(--c-surface)",   // → surface
        fg: "var(--c-text)",         // → text
        muted: "var(--c-textmut)",   // → textmut
        good: "#3fb950",          // → win/ok
        bad: "#e5534b",           // → loss/danger
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
