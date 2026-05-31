/**
 * Hafif i18n (Faz 9 #i18n) — TR/EN, harici bağımlılık yok.
 *
 * `next-intl` yerine minimal context + sözlük: locale localStorage'da saklanır
 * (default "tr"), `useI18n().t(key)` çeviri döner, `setLocale` ile değişir.
 * Global pazara açılım + saha kenarında dil tercihi için yeterli; sayfalar
 * kademeli olarak `t()`'ye geçebilir (shell zaten i18n'li).
 */
"use client";

import * as React from "react";

export type Locale = "tr" | "en";

const STORAGE_KEY = "manager2.locale";

type Dict = Record<string, string>;

const MESSAGES: Record<Locale, Dict> = {
  tr: {
    "nav.leagues": "Ligler",
    "nav.teams": "Takımlar",
    "nav.h2h": "H2H",
    "nav.matches": "Maçlar",
    "nav.training": "Antrenman",
    "nav.decisions": "Kararlar",
    "nav.calibration": "Kalibrasyon",
    "nav.chat": "Asistan",
    "nav.admin": "Admin",
    "topbar.seasonLabel": "Sezon",
    "topbar.logout": "Çıkış",
    "topbar.quota": "Kota",
    "topbar.idleWarn": "1 dakikada otomatik çıkış",
    "topbar.offline": "Çevrimdışı — gösterilen veriler güncel olmayabilir",
    "topbar.menu": "Menü",
    "sidebar.lastSync": "Son sync",
    "common.language": "Dil",
  },
  en: {
    "nav.leagues": "Leagues",
    "nav.teams": "Teams",
    "nav.h2h": "H2H",
    "nav.matches": "Matches",
    "nav.training": "Training",
    "nav.decisions": "Decisions",
    "nav.calibration": "Calibration",
    "nav.chat": "Assistant",
    "nav.admin": "Admin",
    "topbar.seasonLabel": "Season",
    "topbar.logout": "Log out",
    "topbar.quota": "Quota",
    "topbar.idleWarn": "Auto logout in 1 minute",
    "topbar.offline": "Offline — displayed data may be stale",
    "topbar.menu": "Menu",
    "sidebar.lastSync": "Last sync",
    "common.language": "Language",
  },
};

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string) => string;
}

const I18nContext = React.createContext<I18nContextValue | null>(null);

function readStoredLocale(): Locale {
  if (typeof window === "undefined") return "tr";
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === "en" || v === "tr" ? v : "tr";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = React.useState<Locale>("tr");

  // İlk mount'ta saklı tercihi oku (SSR/CSR uyumu: default tr ile başla).
  React.useEffect(() => {
    setLocaleState(readStoredLocale());
  }, []);

  const setLocale = React.useCallback((l: Locale) => {
    setLocaleState(l);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, l);
      document.documentElement.lang = l;
    }
  }, []);

  const t = React.useCallback(
    (key: string) => MESSAGES[locale][key] ?? MESSAGES.tr[key] ?? key,
    [locale],
  );

  const value = React.useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = React.useContext(I18nContext);
  if (ctx === null) {
    // Provider yoksa güvenli fallback (test/izole render) — TR sözlüğü.
    return {
      locale: "tr",
      setLocale: () => undefined,
      t: (key: string) => MESSAGES.tr[key] ?? key,
    };
  }
  return ctx;
}
