/**
 * Sportmonks canlı veri yardımcıları — /sm/* uçlarının tipleri + ortak config.
 *
 * Lig/sezon/takım kimlikleri env'den gelir (NEXT_PUBLIC_SM_*); varsayılanlar
 * Türkiye evreni (Süper Lig 600, sezon 2025, Beşiktaş 554). Abonelik farklı
 * ligleri kapsıyorsa (ör. Danimarka 271 / Viborg 2447) env ile değiştirilir —
 * kod değişmez.
 *
 * Görseller: backend /media/sportmonks/... proxy'si self-host eder; tarayıcı
 * engelli cdn.sportmonks.com'a hiç gitmez. <img src> için smMediaUrl() kullan
 * (Next rewrite /api → backend).
 */

export const SM_LEAGUE_ID = Number(process.env.NEXT_PUBLIC_SM_LEAGUE_ID ?? "600");
export const SM_SEASON = Number(process.env.NEXT_PUBLIC_SM_SEASON ?? "2025");
export const SM_TEAM_ID = Number(process.env.NEXT_PUBLIC_SM_TEAM_ID ?? "554");

/** Backend StandingRow dataclass'ının JSON hali. */
export interface SmStandingRow {
  position: number;
  team_external_id: number;
  team_name: string;
  played: number;
  won: number;
  draw: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  goal_diff: number;
  points: number;
  xpoints: number | null;
  form: string[]; // eski→yeni "W"/"D"/"L"
  qualification: string | null;
}

export interface SmStandingsResp {
  season_id: number;
  rows: SmStandingRow[];
}

/** Backend SquadMember dataclass'ının JSON hali. */
export interface SmSquadMember {
  player_external_id: number;
  name: string;
  position: string | null; // G/D/M/F
  jersey: number | null;
  photo_url: string | null; // /media/sportmonks/... (proxy'li)
  birth_date: string | null;
  nationality: string | null;
  captain: boolean;
  season: Record<string, number>;
}

/** Backend Match domain modelinin JSON hali. */
export interface SmMatch {
  sport: string;
  external_id: number;
  league_external_id: number;
  season: number;
  kickoff: string; // ISO
  status: string;
  home_team_external_id: number;
  away_team_external_id: number;
  home_score: number | null;
  away_score: number | null;
}

export interface SmScheduleResp {
  finished: SmMatch[];   // yeni → eski
  upcoming: SmMatch[];   // yakın → uzak
  team_names: Record<string, string>;
}

/** /media yolu → tarayıcı URL'si (Next rewrite /api → backend). */
export function smMediaUrl(path: string | null): string | null {
  if (!path) return null;
  return path.startsWith("/media/") ? `/api${path}` : path;
}

/** Sportmonks form harfi → TR rozet harfi (W/D/L → G/B/M). */
export function smFormTr(letter: string): "G" | "B" | "M" {
  if (letter === "W") return "G";
  if (letter === "D") return "B";
  return "M";
}

/** Doğum tarihinden yaş (bugüne göre); geçersizse null. */
export function smAge(birthDate: string | null): number | null {
  if (!birthDate) return null;
  const d = new Date(birthDate);
  if (isNaN(d.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - d.getFullYear();
  const m = now.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) age--;
  return age;
}
