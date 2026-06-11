"use client";

/**
 * Oyuncu avatarı — varsa gerçek oyuncu fotoğrafı, yoksa baş-harf rozeti.
 * Renk pozisyona göre (GK/DF/MF/FW) — listede oyuncuyu hızlı ayırt etmek için.
 */

import React, { useState } from "react";
import type { CSSProperties } from "react";

export type AvatarPos = "GK" | "DF" | "MF" | "FW" | string;

// Pozisyon → (zemin, metin) renkleri. Tema değişkenleriyle uyumlu, kontrastlı.
const POS_COLOR: Record<string, { bg: string; ink: string }> = {
  GK: { bg: "#d97706", ink: "#fff" },   // amber
  DF: { bg: "#0e7490", ink: "#fff" },   // cyan-koyu
  MF: { bg: "#15803d", ink: "#fff" },   // yeşil
  FW: { bg: "#b91c1c", ink: "#fff" },   // kırmızı
};
const FALLBACK = { bg: "#475569", ink: "#fff" };

// Oyuncu fotoğrafları kaldırıldı — herkes baş-harf rozetiyle gösterilir.
// Foto geri istenirse public/players/<id>.png ekleyip aşağıya "İsim": "id" satırı yaz.
const PLAYER_MAP: Record<string, string> = {};

/** İsimden 1-2 harfli baş-harf (Türkçe büyütme). */
function initialsOf(name: string): string {
  const w = name.replace(/[^\p{L}\s]/gu, " ").split(/\s+/).filter(Boolean);
  if (w.length === 0) return "?";
  if (w.length === 1) return w[0].slice(0, 2).toLocaleUpperCase("tr-TR");
  return (w[0][0] + w[w.length - 1][0]).toLocaleUpperCase("tr-TR");
}

function colorFor(position?: AvatarPos): { bg: string; ink: string } {
  if (!position) return FALLBACK;
  const key = position.toUpperCase().slice(0, 2);
  return POS_COLOR[key] ?? FALLBACK;
}

export interface PlayerAvatarProps {
  name: string;
  position?: AvatarPos;
  size?: number;        // px, varsayılan 26
  title?: string;
  className?: string;
  style?: CSSProperties;
}

/** Oyuncu avatarı: varsa foto, yoksa baş-harf rozeti (daire). */
export function PlayerAvatar({
  name, position, size = 26, title, className, style,
}: PlayerAvatarProps) {
  const [error, setError] = useState(false);
  const c = colorFor(position);
  const txt = initialsOf(name);
  const fs = txt.length <= 1 ? size * 0.46 : size * 0.4;
  const pid = PLAYER_MAP[name];

  if (pid && !error) {
    return (
      <img
        src={`/players/${pid}.png`}
        alt={title ?? name}
        width={size}
        height={size}
        className={className}
        style={{ display: "inline-block", flexShrink: 0, verticalAlign: "middle", objectFit: "cover", borderRadius: "50%", ...style }}
        onError={() => setError(true)}
      />
    );
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      role="img"
      aria-label={title ?? name}
      className={className}
      style={{ display: "inline-block", flexShrink: 0, verticalAlign: "middle", ...style }}
    >
      <title>{title ?? name}</title>
      <circle cx="20" cy="20" r="19" fill={c.bg} stroke="rgba(255,255,255,0.14)" strokeWidth="1" />
      <text
        x="20" y="20.5" textAnchor="middle" dominantBaseline="central"
        fontFamily="'Inter', system-ui, sans-serif" fontWeight={700}
        fontSize={(fs / size) * 40} fill={c.ink} letterSpacing="-0.3"
      >
        {txt}
      </text>
    </svg>
  );
}

/** Avatar + ad yan yana (tablo/liste satırı). */
export function PlayerAvatarName({
  name, position, size = 22, gap = 8, bold = false, color, style,
}: {
  name: string;
  position?: AvatarPos;
  size?: number;
  gap?: number;
  bold?: boolean;
  color?: string;
  style?: CSSProperties;
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap, minWidth: 0, ...style }}>
      <PlayerAvatar name={name} position={position} size={size} />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: bold ? 600 : undefined, color }}>
        {name}
      </span>
    </span>
  );
}
