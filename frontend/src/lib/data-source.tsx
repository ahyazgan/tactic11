/**
 * Veri-kaynağı atıf bileşenleri — bir sayfanın/özelliğin verisini KİMDEN aldığını
 * görsel olarak işaretler (canlı maçtaki "Veri Sağlayıcıları" kartıyla aynı dil).
 *
 * Logo işaretleri INLINE SVG'dir; CDN'den veya üçüncü-parti dosyadan ÇEKİLMEZ
 * (self-host kuralı). Bunlar resmi marka logoları değil, marka-çağrışımlı
 * stilize geometrik glyph + wordmark'lardır (hexagon/halka/chevron/top/yıldız).
 */

import type { CSSProperties } from "react";

export type SourceId =
  | "statsbomb"
  | "opta"
  | "stats_perform"
  | "api_football"
  | "statsbomb_360"
  | "claude"
  | "xg_model"
  | "perf_lab";

export interface SourceMeta { id: SourceId; name: string; accent: string; kind: string }

export const SOURCES: Record<SourceId, SourceMeta> = {
  statsbomb:     { id: "statsbomb",     name: "StatsBomb",      accent: "#E5197D", kind: "event verisi" },
  opta:          { id: "opta",          name: "Opta",           accent: "#2BA8E0", kind: "event verisi" },
  stats_perform: { id: "stats_perform", name: "Stats Perform",  accent: "#E6007E", kind: "event verisi" },
  api_football:  { id: "api_football",  name: "API-Football",   accent: "#16a34a", kind: "fikstür & kadro" },
  statsbomb_360: { id: "statsbomb_360", name: "StatsBomb 360",  accent: "#E5197D", kind: "tracking" },
  claude:        { id: "claude",        name: "Claude",         accent: "#d97757", kind: "AI yorum" },
  xg_model:      { id: "xg_model",      name: "xG Modeli",      accent: "#d97706", kind: "türetilmiş model" },
  perf_lab:      { id: "perf_lab",      name: "Performans Lab", accent: "#0e7490", kind: "saha & lab ölçümü" },
};

// Marka-çağrışımlı glyph (resmi logo DEĞİL). height ölçeklenir; dim → soluk/gri.
export function SourceMark({ id, height = 18, dim = false }: { id: SourceId; height?: number; dim?: boolean }) {
  const wrap: CSSProperties = { display: "inline-flex", alignItems: "center", gap: 7, opacity: dim ? 0.4 : 1, filter: dim ? "grayscale(0.6)" : undefined };
  const word: CSSProperties = { fontWeight: 800, fontSize: height * 0.72, letterSpacing: "-0.02em", color: "var(--ink)", lineHeight: 1, whiteSpace: "nowrap" };
  const g = height;

  if (id === "opta") {
    return (
      <span style={wrap}>
        <svg width={g} height={g} viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="6.4" fill="none" stroke="#2BA8E0" strokeWidth="3" /></svg>
        <span style={{ ...word, color: "#2BA8E0" }}>Opta</span>
      </span>
    );
  }
  if (id === "stats_perform") {
    return (
      <span style={wrap}>
        <svg width={g} height={g * 0.9} viewBox="0 0 18 16" aria-hidden="true" fill="none" stroke="#E6007E" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 3 L8 8 L2 13" /><path d="M9 3 L15 8 L9 13" />
        </svg>
        <span style={word}>Stats<span style={{ color: "#E6007E" }}> Perform</span></span>
      </span>
    );
  }
  if (id === "api_football") {
    return (
      <span style={wrap}>
        <svg width={g} height={g} viewBox="0 0 18 18" aria-hidden="true" fill="none" stroke="#16a34a" strokeWidth="1.7">
          <circle cx="9" cy="9" r="7" />
          <circle cx="9" cy="9" r="2.4" fill="#16a34a" stroke="none" />
          <path d="M9 2 V5 M9 13 V16 M2 9 H5 M13 9 H16" strokeWidth="1.4" />
        </svg>
        <span style={word}>API<span style={{ color: "#16a34a" }}>-Football</span></span>
      </span>
    );
  }
  if (id === "claude") {
    return (
      <span style={wrap}>
        <svg width={g} height={g} viewBox="0 0 18 18" aria-hidden="true" stroke="#d97757" strokeWidth="1.7" strokeLinecap="round">
          <path d="M9 1.5 V16.5 M1.5 9 H16.5 M3.7 3.7 L14.3 14.3 M14.3 3.7 L3.7 14.3" />
        </svg>
        <span style={{ ...word, color: "#c2410c" }}>Claude</span>
      </span>
    );
  }
  if (id === "perf_lab") {
    // Kronometre glyph'i — kulübün kendi saha/lab ölçüm araçları (fotosel,
    // force plate, GPS, metabolik araba). Marka değil, kulüp-içi kaynak.
    return (
      <span style={wrap}>
        <svg width={g} height={g} viewBox="0 0 18 18" aria-hidden="true" fill="none" stroke="#0e7490" strokeWidth="1.7" strokeLinecap="round">
          <circle cx="9" cy="10.2" r="6.2" />
          <path d="M9 10.2 L12 7.6" />
          <path d="M7.4 1.6 H10.6" />
          <path d="M9 1.6 V4" />
        </svg>
        <span style={word}>Performans<span style={{ color: "#0e7490" }}> Lab</span></span>
      </span>
    );
  }
  if (id === "xg_model") {
    return (
      <span style={wrap}>
        <svg width={g} height={g} viewBox="0 0 18 18" aria-hidden="true" fill="none" stroke="#d97706" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 16 V2" /><path d="M2 16 H16" /><path d="M4.5 12 L8 8.5 L10.5 10.5 L15 5" /><circle cx="15" cy="5" r="1.6" fill="#d97706" stroke="none" />
        </svg>
        <span style={word}>xG<span style={{ color: "#d97706" }}> Modeli</span></span>
      </span>
    );
  }
  // statsbomb + statsbomb_360 (pembe hexagon)
  const is360 = id === "statsbomb_360";
  return (
    <span style={wrap}>
      <svg width={g * 0.88} height={g} viewBox="0 0 16 18" aria-hidden="true"><path d="M8 0 L16 4.5 L16 13.5 L8 18 L0 13.5 L0 4.5 Z" fill="#E5197D" /></svg>
      <span style={word}>Stats<span style={{ color: "#E5197D" }}>Bomb</span>{is360 && <span style={{ color: "var(--dim)", fontSize: height * 0.5, marginLeft: 3 }}>360</span>}</span>
    </span>
  );
}

// Bir veya birden çok kaynak rozetini, hafif altın çerçeveli pill içinde gösterir.
// Sayfa başlığının altına ("verisini kimden alıyor") yerleşir.
export function DataSourceStrip({ sources, label = "veri kaynağı" }: { sources: SourceId | SourceId[]; label?: string }) {
  const ids = Array.isArray(sources) ? sources : [sources];
  if (!ids.length) return null;
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
      <span style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", color: "var(--dim)", fontWeight: 600 }}>{label}</span>
      {ids.map((id) => (
        <span key={id} title={`${SOURCES[id]?.name ?? id} — ${SOURCES[id]?.kind ?? ""}`} style={{
          display: "inline-flex", alignItems: "center",
          padding: "4px 10px", borderRadius: 20,
          border: "1px solid rgba(212,175,55,0.55)",
          background: "linear-gradient(160deg, rgba(212,175,55,0.14), rgba(212,175,55,0.04))",
          boxShadow: "0 1px 4px -2px rgba(212,175,55,0.5)",
        }}>
          <SourceMark id={id} height={15} />
        </span>
      ))}
    </div>
  );
}
