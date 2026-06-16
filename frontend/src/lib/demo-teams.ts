/**
 * Demo Süper Lig takım dizini — TEK kaynak (id → takım satırı).
 *
 * `/leagues/[id]/teams` listesi ve `/teams/[id]` detayı aynı veriden beslenir;
 * böylece tıklanan takım, detay sayfasında da AYNI kimlik/istatistikle açılır
 * (önceden detay sayfası id'yi yok sayıp hep Beşiktaş gösteriyordu).
 *
 * "Süper Lig — 34. Hafta" evreni: Beşiktaş zirve yarışında 2., sıradaki rakip
 * Antalyaspor 11. Puanlar 3*G + B ile tutarlı.
 */

export type DemoForm = "G" | "B" | "M";

export interface DemoTeamRow {
  teamId: number;    // /teams/{id} rotası için sabit kimlik
  rank: number;
  name: string;
  short: string;
  city: string;
  founded: number;
  played: number;
  win: number;
  draw: number;
  loss: number;
  gf: number;
  ga: number;
  xgf: number;       // beklenen attığı gol (sezon)
  xga: number;       // beklenen yediği gol (sezon)
  form: DemoForm[];  // son 5 maç (en yeni en sağda)
  us?: boolean;      // Beşiktaş
  next?: boolean;    // sıradaki rakibimiz
}

export const DEMO_TEAM_ROWS: DemoTeamRow[] = [
  { teamId: 201, rank: 1, name: "Galatasaray", short: "GS", city: "İstanbul", founded: 1905, played: 33, win: 22, draw: 6, loss: 5, gf: 64, ga: 29, xgf: 60.4, xga: 31.2, form: ["G", "G", "B", "G", "G"] },
  { teamId: 100, rank: 2, name: "Beşiktaş", short: "BJK", city: "İstanbul", founded: 1903, played: 33, win: 21, draw: 7, loss: 5, gf: 61, ga: 28, xgf: 58.9, xga: 27.6, form: ["G", "B", "G", "G", "G"], us: true },
  { teamId: 202, rank: 3, name: "Fenerbahçe", short: "FB", city: "İstanbul", founded: 1907, played: 33, win: 20, draw: 6, loss: 7, gf: 58, ga: 33, xgf: 55.1, xga: 35.0, form: ["G", "G", "M", "G", "B"] },
  { teamId: 203, rank: 4, name: "Trabzonspor", short: "TS", city: "Trabzon", founded: 1967, played: 33, win: 18, draw: 8, loss: 7, gf: 52, ga: 34, xgf: 50.7, xga: 36.4, form: ["B", "G", "G", "B", "G"] },
  { teamId: 204, rank: 5, name: "Samsunspor", short: "SAM", city: "Samsun", founded: 1965, played: 33, win: 17, draw: 7, loss: 9, gf: 49, ga: 38, xgf: 47.8, xga: 39.9, form: ["G", "M", "G", "G", "B"] },
  { teamId: 205, rank: 6, name: "Başakşehir", short: "İBFK", city: "İstanbul", founded: 2014, played: 33, win: 16, draw: 8, loss: 9, gf: 47, ga: 40, xgf: 45.2, xga: 41.1, form: ["B", "B", "G", "M", "G"] },
  { teamId: 206, rank: 7, name: "Eyüpspor", short: "EYP", city: "İstanbul", founded: 1919, played: 33, win: 15, draw: 9, loss: 9, gf: 44, ga: 41, xgf: 43.6, xga: 42.0, form: ["G", "B", "M", "G", "B"] },
  { teamId: 207, rank: 8, name: "Göztepe", short: "GÖZ", city: "İzmir", founded: 1925, played: 33, win: 14, draw: 9, loss: 10, gf: 42, ga: 42, xgf: 41.0, xga: 43.5, form: ["M", "G", "B", "G", "M"] },
  { teamId: 208, rank: 9, name: "Kasımpaşa", short: "KSM", city: "İstanbul", founded: 1921, played: 33, win: 13, draw: 10, loss: 10, gf: 40, ga: 43, xgf: 39.7, xga: 44.2, form: ["B", "M", "G", "B", "G"] },
  { teamId: 209, rank: 10, name: "Konyaspor", short: "KON", city: "Konya", founded: 1922, played: 33, win: 12, draw: 11, loss: 10, gf: 39, ga: 41, xgf: 38.1, xga: 42.8, form: ["B", "G", "B", "M", "B"] },
  { teamId: 101, rank: 11, name: "Antalyaspor", short: "ANT", city: "Antalya", founded: 1966, played: 33, win: 12, draw: 9, loss: 12, gf: 41, ga: 44, xgf: 38.9, xga: 45.7, form: ["M", "B", "G", "M", "G"], next: true },
  { teamId: 210, rank: 12, name: "Çaykur Rizespor", short: "RİZ", city: "Rize", founded: 1953, played: 33, win: 11, draw: 10, loss: 12, gf: 37, ga: 45, xgf: 36.4, xga: 46.0, form: ["G", "M", "B", "M", "B"] },
  { teamId: 211, rank: 13, name: "Alanyaspor", short: "ALY", city: "Alanya", founded: 1948, played: 33, win: 10, draw: 11, loss: 12, gf: 35, ga: 46, xgf: 34.8, xga: 46.9, form: ["B", "M", "M", "B", "G"] },
  { teamId: 212, rank: 14, name: "Sivasspor", short: "SVS", city: "Sivas", founded: 1967, played: 33, win: 10, draw: 9, loss: 14, gf: 34, ga: 49, xgf: 33.2, xga: 50.3, form: ["M", "M", "B", "G", "M"] },
  { teamId: 213, rank: 15, name: "Kayserispor", short: "KAY", city: "Kayseri", founded: 1966, played: 33, win: 9, draw: 10, loss: 14, gf: 32, ga: 50, xgf: 31.9, xga: 51.1, form: ["M", "B", "M", "B", "M"] },
  { teamId: 214, rank: 16, name: "Gaziantep FK", short: "GFK", city: "Gaziantep", founded: 1969, played: 33, win: 8, draw: 9, loss: 16, gf: 30, ga: 54, xgf: 29.6, xga: 55.4, form: ["M", "G", "M", "M", "B"] },
  { teamId: 215, rank: 17, name: "Hatayspor", short: "HTY", city: "Hatay", founded: 1967, played: 33, win: 6, draw: 10, loss: 17, gf: 27, ga: 58, xgf: 26.8, xga: 57.9, form: ["M", "M", "B", "M", "M"] },
  { teamId: 216, rank: 18, name: "Bodrum FK", short: "BOD", city: "Bodrum", founded: 1931, played: 33, win: 5, draw: 8, loss: 20, gf: 24, ga: 63, xgf: 24.1, xga: 61.5, form: ["M", "M", "M", "B", "M"] },
];

const BY_ID: Record<number, DemoTeamRow> = Object.fromEntries(
  DEMO_TEAM_ROWS.map((t) => [t.teamId, t]),
);

/** id → takım satırı; bilinmeyen id'de undefined (çağıran Beşiktaş'a düşer). */
export function demoTeamById(id: number | string): DemoTeamRow | undefined {
  return BY_ID[Number(id)];
}

export function demoTeamPoints(t: DemoTeamRow): number {
  return t.win * 3 + t.draw;
}
