"use client";

/**
 * Hafif i18n — context + `useI18n()` + `t(key)`.
 *
 * Varsayılan dil Türkçe; sözlükte karşılığı yoksa anahtar (TR metin) aynen
 * döner — yani additive, mevcut render'ı bozmaz. Dil seçimi localStorage'da
 * tutulur. SSR-güvenli: ilk render TR, dil tercihi mount sonrası okunur.
 */

import * as React from "react";

export type Lang = "tr" | "en";

const STORAGE_KEY = "manager2_lang";

// Anahtar = TR metin (default). İngilizce karşılık `en` altında.
// Karşılığı olmayan string `t()` ile aynen döner — kademeli çeviri mümkün.
const DICT: Record<string, Partial<Record<Lang, string>>> = {
  // Nav
  "Genel Bakış": { en: "Overview" },
  Ligler: { en: "Leagues" },
  Takımlar: { en: "Teams" },
  Maçlar: { en: "Matches" },
  Antrenman: { en: "Training" },
  "Performans Testi": { en: "Performance Test" },
  "Yük Riski": { en: "Load Risk" },
  Kararlar: { en: "Decisions" },
  Kalibrasyon: { en: "Calibration" },
  Asistan: { en: "Assistant" },
  Admin: { en: "Admin" },
  // TopBar / genel
  Çıkış: { en: "Log out" },
  Sezon: { en: "Season" },
  "Giriş yap": { en: "Sign in" },
  "Hızlı erişim": { en: "Quick access" },
  "Gösterge tablosu": { en: "Dashboard" },
  Dil: { en: "Language" },
};

interface I18nValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
}

const I18nContext = React.createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = React.useState<Lang>("tr");

  // Dil tercihini mount sonrası oku (SSR uyumu: ilk render her zaman TR).
  React.useEffect(() => {
    const saved = typeof window !== "undefined"
      ? window.localStorage.getItem(STORAGE_KEY)
      : null;
    if (saved === "tr" || saved === "en") {
      setLangState(saved);
    }
  }, []);

  const setLang = React.useCallback((l: Lang) => {
    setLangState(l);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, l);
    }
  }, []);

  const t = React.useCallback(
    (key: string) => {
      if (lang === "tr") return key;
      return DICT[key]?.[lang] ?? key;
    },
    [lang],
  );

  const value = React.useMemo(
    () => ({ lang, setLang, t }),
    [lang, setLang, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = React.useContext(I18nContext);
  if (ctx === null) {
    // Provider dışında çağrılırsa güvenli no-op (TR passthrough).
    return { lang: "tr", setLang: () => {}, t: (k: string) => k };
  }
  return ctx;
}
