"use client";

import * as React from "react";

/** Açık/Koyu tema düğmesi — html.light sınıfını toggle eder, localStorage'a yazar.
 *  Sabit konum (sağ alt) → hem shell hem standalone konsollarda görünür. */
export function ThemeToggle() {
  const [light, setLight] = React.useState(false);

  React.useEffect(() => {
    setLight(document.documentElement.classList.contains("light"));
  }, []);

  function toggle() {
    const next = !light;
    setLight(next);
    document.documentElement.classList.toggle("light", next);
    try {
      localStorage.setItem("m2-theme", next ? "light" : "dark");
    } catch {
      /* yut */
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title={light ? "Koyu temaya geç" : "Açık temaya geç"}
      aria-label="Tema değiştir"
      style={{
        position: "fixed",
        bottom: 14,
        right: 14,
        zIndex: 100000,
        width: 38,
        height: 38,
        borderRadius: 10,
        border: "1px solid var(--c-border)",
        background: "var(--c-surface)",
        color: "var(--c-text)",
        fontSize: 17,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 3px 12px rgba(0,0,0,0.3)",
      }}
    >
      {light ? "🌙" : "☀️"}
    </button>
  );
}
