import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // DESIGN.md token'ları — FM 2010-15 estetik (tek doğruluk kaynağı)
        // Zeminler
        bg: "#14171c",
        surface: "#1a1d24",
        surface2: "#21252e",
        elevated: "#272c37",
        // Çizgiler
        border: "#2c3038",
        borderlt: "#3a3f4a",
        // Metin
        text: "#e4e7ec",
        textmut: "#9aa1ad",
        textdim: "#6b7280",
        // Marka
        accent: "#3d7eff",
        accenthov: "#5a92ff",
        // Durum
        win: "#3fb950",
        draw: "#d4a72c",
        loss: "#e5534b",
        warn: "#d4a72c",
        danger: "#e5534b",
        ok: "#3fb950",

        // Legacy aliases — mevcut sayfalar refactor edilene kadar geriye uyumluluk
        // Yeni kod DESIGN.md token'larını kullanır; aşağıdakiler kalsın
        // ki mevcut /matches, /chat, /login, /calibration sayfaları kırılmasın.
        panel: "#1a1d24",         // → surface
        fg: "#e4e7ec",            // → text
        muted: "#9aa1ad",         // → textmut
        good: "#3fb950",          // → win/ok
        bad: "#e5534b",           // → loss/danger
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
