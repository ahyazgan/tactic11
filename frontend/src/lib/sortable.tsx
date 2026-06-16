"use client";

/**
 * Paylaşılan tablo sıralama yardımcısı — başlığa tıkla → o sütuna göre sırala,
 * tekrar tıkla → yön değiştir. Aktif sütun accent + ▼/▲, pasif başlıkta soluk ⇅.
 *
 * Kullanım:
 *   const { key, dir, onSort } = useSort<"ad" | "puan">("puan");
 *   <SortableTh active={key === "puan"} dir={dir} label="Puan" align="r" onClick={() => onSort("puan")} />
 *   const sorted = [...rows].sort((a, b) => sortCompare(a[key], b[key], dir));
 */

import * as React from "react";

export type SortDir = "asc" | "desc";

export function useSort<K extends string>(initialKey: K, initialDir: SortDir = "desc") {
  const [key, setKey] = React.useState<K>(initialKey);
  const [dir, setDir] = React.useState<SortDir>(initialDir);
  const onSort = (k: K) => {
    if (k === key) setDir((d) => (d === "desc" ? "asc" : "desc"));
    else { setKey(k); setDir("desc"); }
  };
  return { key, dir, onSort };
}

/** Sayı veya metin için yön-duyarlı karşılaştırma (Türkçe sıralama dahil). */
export function sortCompare(a: unknown, b: unknown, dir: SortDir): number {
  let r: number;
  if (typeof a === "number" && typeof b === "number") r = a - b;
  else r = String(a ?? "").localeCompare(String(b ?? ""), "tr");
  return dir === "desc" ? -r : r;
}

export function SortableTh({
  active, dir, label, align, onClick,
}: {
  active: boolean;
  dir: SortDir;
  label: string;
  align?: "c" | "r";
  onClick: () => void;
}) {
  return (
    <th
      className={align}
      onClick={onClick}
      style={{ cursor: "pointer", userSelect: "none", color: active ? "var(--accent)" : undefined, whiteSpace: "nowrap" }}
      title="Sıralamak için tıkla"
    >
      {label}{active ? (dir === "desc" ? " ▼" : " ▲") : <span style={{ opacity: 0.35 }}> ⇅</span>}
    </th>
  );
}
