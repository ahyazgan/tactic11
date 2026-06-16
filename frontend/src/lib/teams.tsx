/**
 * Takım kütüğü + arma (crest) bileşeni — gerçek Süper Lig takımları.
 *
 * Armalar INLINE SVG'dir; CDN'den ya da üçüncü-parti dosyadan ÇEKİLMEZ (self-host
 * kuralı — jsdelivr vb. kullanıcı ortamında engelli). Bunlar resmî kulüp armaları
 * DEĞİL; her kulübün gerçek renklerini + monogramını kullanan marka-çağrışımlı,
 * özgün, stilize geometrik rozetlerdir (data-source.tsx'teki SourceMark deseniyle
 * aynı yaklaşım). Renk + monogram ile kulüp anında tanınır, telif sorunu yoktur.
 *
 * Tek kaynak: tüm demo sayfaları takımı ADIYLA arar (teamMeta) ve <Crest> ile
 * armasını gösterir. Yeni takım eklemek = SUPER_LIG'e bir satır.
 */

export interface TeamMeta {
  name: string;       // tam ad (demo verisinde kullanılan kanonik ad)
  short: string;      // arma monogramı / kısa kod (2-4 karakter)
  city: string;
  founded: number;
  primary: string;    // arma zemini (kulübün ana rengi)
  secondary: string;  // arma halkası / ikincil renk
  ink: string;        // monogram metin rengi (zemine kontrast)
  aliases?: string[]; // alternatif yazımlar (lookup için)
}

// Gerçek Süper Lig (18 takım). Renkler kulüplerin gerçek renkleridir.
export const SUPER_LIG: TeamMeta[] = [
  { name: "Galatasaray",      short: "GS",   city: "İstanbul", founded: 1905, primary: "#A4282E", secondary: "#F7B500", ink: "#F7B500", aliases: ["Galatasaray SK"] },
  { name: "Beşiktaş",         short: "BJK",  city: "İstanbul", founded: 1903, primary: "#16181C", secondary: "#FFFFFF", ink: "#FFFFFF", aliases: ["Beşiktaş JK"] },
  { name: "Fenerbahçe",       short: "FB",   city: "İstanbul", founded: 1907, primary: "#14254C", secondary: "#FFE000", ink: "#FFE000", aliases: ["Fenerbahçe SK"] },
  { name: "Trabzonspor",      short: "TS",   city: "Trabzon",  founded: 1967, primary: "#6E1330", secondary: "#2C6BBF", ink: "#FFFFFF" },
  { name: "Samsunspor",       short: "SAM",  city: "Samsun",   founded: 1965, primary: "#C8102E", secondary: "#FFFFFF", ink: "#FFFFFF" },
  { name: "Başakşehir",       short: "İBFK", city: "İstanbul", founded: 2014, primary: "#143A66", secondary: "#F47B20", ink: "#F47B20", aliases: ["İstanbul Başakşehir", "Istanbul Basaksehir"] },
  { name: "Eyüpspor",         short: "EYP",  city: "İstanbul", founded: 1919, primary: "#4B2A7B", secondary: "#F4C20D", ink: "#F4C20D" },
  { name: "Göztepe",          short: "GÖZ",  city: "İzmir",    founded: 1925, primary: "#B8121B", secondary: "#FFD200", ink: "#FFD200", aliases: ["Göztepe SK"] },
  { name: "Kasımpaşa",        short: "KSM",  city: "İstanbul", founded: 1921, primary: "#0B4DA2", secondary: "#FFFFFF", ink: "#FFFFFF" },
  { name: "Konyaspor",        short: "KON",  city: "Konya",    founded: 1922, primary: "#0E7C3A", secondary: "#FFFFFF", ink: "#FFFFFF" },
  { name: "Antalyaspor",      short: "ANT",  city: "Antalya",  founded: 1966, primary: "#C8102E", secondary: "#FFFFFF", ink: "#FFFFFF" },
  { name: "Çaykur Rizespor",  short: "RİZ",  city: "Rize",     founded: 1953, primary: "#0A7A3F", secondary: "#1C73C2", ink: "#FFFFFF", aliases: ["Rizespor"] },
  { name: "Alanyaspor",       short: "ALY",  city: "Alanya",   founded: 1948, primary: "#E7691B", secondary: "#0B6B3A", ink: "#FFFFFF" },
  { name: "Sivasspor",        short: "SVS",  city: "Sivas",    founded: 1967, primary: "#B8121B", secondary: "#FFFFFF", ink: "#FFFFFF" },
  { name: "Kayserispor",      short: "KAY",  city: "Kayseri",  founded: 1966, primary: "#C8102E", secondary: "#FFD200", ink: "#FFD200" },
  { name: "Gaziantep FK",     short: "GFK",  city: "Gaziantep",founded: 1969, primary: "#C8102E", secondary: "#16181C", ink: "#FFFFFF", aliases: ["Gaziantep"] },
  { name: "Hatayspor",        short: "HTY",  city: "Hatay",    founded: 1967, primary: "#6E1330", secondary: "#FFFFFF", ink: "#FFFFFF" },
  { name: "Bodrum FK",        short: "BOD",  city: "Bodrum",   founded: 1931, primary: "#0E7C3A", secondary: "#FFFFFF", ink: "#FFFFFF", aliases: ["Bodrumspor"] },
];

// Ad → meta hızlı arama tablosu (kanonik ad + alias'lar, normalize edilmiş).
const norm = (s: string) => s.trim().toLocaleLowerCase("tr-TR");
const BY_NAME = new Map<string, TeamMeta>();
for (const t of SUPER_LIG) {
  BY_NAME.set(norm(t.name), t);
  for (const a of t.aliases ?? []) BY_NAME.set(norm(a), t);
}

/** Bir takımın ilk anlamlı baş harflerinden monogram üret (bilinmeyen takımlar için). */
function initialsOf(name: string): string {
  const words = name.replace(/[^\p{L}\s]/gu, " ").split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 3).toLocaleUpperCase("tr-TR");
  return (words[0][0] + words[1][0]).toLocaleUpperCase("tr-TR");
}

/**
 * Ada göre takım meta'sı. Kütükte yoksa nötr renkli, baş-harf monogramlı bir
 * fallback üretir — böylece <Crest> hiçbir zaman kırılmaz/boş kalmaz.
 */
export function teamMeta(name: string | null | undefined): TeamMeta {
  const found = name ? BY_NAME.get(norm(name)) : undefined;
  if (found) return found;
  const safe = name?.trim() || "—";
  return {
    name: safe,
    short: initialsOf(safe),
    city: "",
    founded: 0,
    primary: "#2A2F3A",
    secondary: "#5A6270",
    ink: "#E7EAF0",
  };
}

export interface CrestProps {
  /** Takım adı (kütükte aranır) ya da doğrudan meta. */
  team: string | TeamMeta;
  /** Piksel boyutu (kare). Varsayılan 22. */
  size?: number;
  /** Erişilebilirlik için title; verilmezse takım adı kullanılır. */
  title?: string;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Kulüp arması — varsa gerçek logo, yoksa inline SVG rozet (zemin = ana renk, halka = ikincil renk,
 * ortada monogram).
 */
const LOGO_FILES: Record<string, string> = {
  "GS": "gs", "BJK": "bjk", "FB": "fb", "TS": "ts", "SAM": "sam",
  "İBFK": "ibfk", "EYP": "eyp", "GÖZ": "goz", "KSM": "ksm", "KON": "kon",
  "ANT": "ant", "RİZ": "riz", "ALY": "aly", "KAY": "kay", "GFK": "gfk"
};

export function Crest({ team, size = 22, title, className, style }: CrestProps) {
  const m = typeof team === "string" ? teamMeta(team) : team;
  const label = title ?? m.name;

  if (LOGO_FILES[m.short]) {
    return (
      <img
        src={`/logos/${LOGO_FILES[m.short]}.png`}
        alt={label}
        width={size}
        height={size}
        className={className}
        style={{ display: "inline-block", flexShrink: 0, verticalAlign: "middle", objectFit: "contain", ...style }}
      />
    );
  }

  const r = size / 2;
  const len = m.short.length;
  // Monogram font boyutu uzunluğa göre — daireye sığsın.
  const fs = len <= 2 ? size * 0.42 : len === 3 ? size * 0.34 : size * 0.27;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      role="img"
      aria-label={label}
      className={className}
      style={{ display: "inline-block", flexShrink: 0, verticalAlign: "middle", ...style }}
    >
      <title>{label}</title>
      {/* dış ince kontur — koyu armalar koyu zeminde de görünür kalsın */}
      <circle cx="20" cy="20" r="19" fill={m.primary} stroke="rgba(255,255,255,0.12)" strokeWidth="1" />
      {/* kulüp ikincil renginde halka */}
      <circle cx="20" cy="20" r="17" fill="none" stroke={m.secondary} strokeWidth="2.4" />
      <text
        x="20"
        y="20.5"
        textAnchor="middle"
        dominantBaseline="central"
        fontFamily="'Inter', system-ui, sans-serif"
        fontWeight={800}
        fontSize={(fs / size) * 40}
        fill={m.ink}
        letterSpacing="-0.3"
      >
        {m.short}
      </text>
    </svg>
  );
}

/** Arma + ad yan yana (tablolarda/listelerde kullanışlı satır öğesi). */
export function CrestName({
  team,
  size = 20,
  gap = 8,
  bold = false,
  color,
  style,
}: {
  team: string | TeamMeta;
  size?: number;
  gap?: number;
  bold?: boolean;
  color?: string;
  style?: React.CSSProperties;
}) {
  const m = typeof team === "string" ? teamMeta(team) : team;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap, minWidth: 0, ...style }}>
      <Crest team={m} size={size} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: bold ? 600 : undefined, color }}>
        {m.name}
      </span>
    </span>
  );
}
