/**
 * Duran Top Zekası — set-piece xG modeli + SAVUNMA analizi.
 *
 * Mevcut set-piece sayfası hücum rutinlerini gösteriyordu; eksik olan yarı:
 * BİZİM savunma zaafımız (demoLive: 45' far-post korner golü yendi) + rakip tehdidi
 * + önerilen markaj şeması + far-post'u kimin markalayacağı. Aerial güç kadronun
 * gerçek özelliklerinden (demoAttributesFor: Güç/Zıplama/Pozisyon Alma) türer.
 *
 * Saf+deterministik. Demo'da burada; production'da aynı model rakip/kadro verisiyle.
 */

import { demoSquad, demoAttributesFor, type SquadPlayer } from "@/lib/demo-data";

export interface ZoneXg { zone: string; label: string; xg: number }

// Set-piece xG modeli — bölge başına beklenen gol (korner gönderimi tabanı).
export const SET_PIECE_XG: ZoneXg[] = [
  { zone: "far_post", label: "Uzak direk", xg: 0.19 },
  { zone: "central_6yd", label: "Kale ağzı (6 yd)", xg: 0.16 },
  { zone: "near_post", label: "Yakın direk", xg: 0.11 },
  { zone: "penalty_arc", label: "Ceza yayı", xg: 0.08 },
  { zone: "outside_box", label: "Ceza dışı", xg: 0.05 },
];
export const setPieceXg = (zone: string) => SET_PIECE_XG.find((z) => z.zone === zone)?.xg ?? 0.06;

// ── Aerial (hava topu) gücü — POZİSYON baskın + özellik düzeltmesi ────────────
// Hava hakimiyeti ≈ boy/pozisyon (stoper); fitness değil. Pozisyon tabanı baskın,
// gerçek özellikler (Güç/Zıplama/Pozisyon Alma) küçük düzeltme yapar. Böylece fit
// bir bek, stoperlerin üstüne çıkıp far-post markajını çalmaz.
const POS_AERIAL_BASE: Record<string, number> = {
  "Stoper": 16, "Santrfor": 14, "Ön Libero": 12.5, "Sağ Bek": 10, "Sol Bek": 10, "Merkez OS": 10,
};
function aerialScore(p: SquadPlayer): number {
  const base = POS_AERIAL_BASE[p.pos_detail] ?? 9;
  const groups = demoAttributesFor(p.player_id);
  const find = (g: string, n: string) =>
    groups.find((x) => x.group === g)?.attrs.find((a) => a.name === n)?.value ?? 10;
  const attr = (find("Fiziksel", "Güç") + find("Fiziksel", "Zıplama") + find("Zihinsel", "Pozisyon Alma")) / 3;
  return Math.max(1, Math.min(20, base + (attr - 10) * 0.25));   // pozisyon baskın, özellik ±2.5
}

export interface ZoneRisk { zone: string; label: string; risk: number }  // 0..1 yeme riski
export interface Marker { player: string; shirt: number; assignment: string; aerial: number }

export type SpRiskLevel = "düşük" | "orta" | "yüksek";

export interface DefensiveSetPiece {
  weakZone: string;
  weakZoneLabel: string;
  concededLastN: number;       // son N maçta duran toptan yenen gol
  matchesN: number;
  zoneRisks: ZoneRisk[];       // bölge başına yeme riski (yüksekten düşüğe)
  scheme: string;              // önerilen markaj şeması
  recommendation: string;
  markers: Marker[];           // far-post/kale-ağzı/yakın-direk görevlileri
  opponentThreat: number;      // 0..1 rakip duran top tehlikesi
  riskLevel: SpRiskLevel;
  expectedConcedeXg: number;   // bu maçta duran toptan beklenen yenen xG
}

// Bizim savunma zaafımız: far-post (demoLive 45' korner golü). Bölge yeme riski
// dağılımı — ÖNCEDEN zonal dizilimin bıraktığı boşluklar.
const OUR_ZONE_RISK: Record<string, number> = {
  far_post: 0.82,        // ana zaaf — ikinci direk örtülemiyor
  central_6yd: 0.44,
  near_post: 0.28,
  penalty_arc: 0.22,
  outside_box: 0.12,
};

/**
 * Savunma duran top analizi — bizim zaafımız + rakip tehdidi + markaj reçetesi.
 * opponentThreat: rakibin duran top tehlikesi (0..1; demo Antalyaspor orta-üstü).
 */
export function defensiveSetPiece(opponentThreat = 0.56): DefensiveSetPiece {
  const zoneRisks: ZoneRisk[] = SET_PIECE_XG
    .map((z) => ({ zone: z.zone, label: z.label, risk: OUR_ZONE_RISK[z.zone] ?? 0.2 }))
    .sort((a, b) => b.risk - a.risk);
  const weak = zoneRisks[0];

  // En iyi hava topçu savunmacılar → kritik bölgelere ata (far-post en zayıf yere en iyi).
  const defenders = demoSquad
    .filter((p) => p.position === "DF" || p.pos_detail === "Ön Libero")
    .map((p) => ({ p, aerial: aerialScore(p) }))
    .sort((a, b) => b.aerial - a.aerial);

  const a = (p: SquadPlayer, aer: number, assignment: string): Marker =>
    ({ player: p.player_name, shirt: p.shirt, assignment, aerial: Math.round(aer * 10) / 10 });

  const markers: Marker[] = [];
  if (defenders[0]) markers.push(a(defenders[0].p, defenders[0].aerial, "Uzak direk (adam-adama) — en yüksek riskli bölge"));
  if (defenders[1]) markers.push(a(defenders[1].p, defenders[1].aerial, "Kale ağzı — ikinci dalga / rakip santrfor"));
  if (defenders[2]) markers.push(a(defenders[2].p, defenders[2].aerial, "Yakın direk + ilk temas"));
  if (defenders[3]) markers.push(a(defenders[3].p, defenders[3].aerial, "Ceza yayı — temizlenen top / kontra emniyeti"));

  // Bu maçta duran toptan beklenen yenen xG ≈ ana-zaaf xG × rakip tehdidi × ort. korner sayısı.
  const cornersExpected = 4.5;
  const expectedConcedeXg = Math.round(setPieceXg(weak.zone) * opponentThreat * cornersExpected * 100) / 100;

  const composite = weak.risk * opponentThreat;
  const riskLevel: SpRiskLevel = composite >= 0.45 ? "yüksek" : composite >= 0.28 ? "orta" : "düşük";

  return {
    weakZone: weak.zone,
    weakZoneLabel: weak.label,
    concededLastN: 4,
    matchesN: 8,
    zoneRisks,
    scheme: "Zonal → adam-adama (hibrit): far-post ve kale ağzında adam-adama, ilk direkte zonal blok.",
    recommendation: `${weak.label} ana zaafımız — son ${8} maçta duran toptan ${4} gol yedik, çoğu buradan. Zonal dizilimi bırak; ${markers[0]?.player ?? "en iyi hava topçu"} ile far-post'u adam-adama markala, kale ağzına ikinci güçlü stoperi koy. Rakip tehdidi ${Math.round(opponentThreat * 100)}%.`,
    markers,
    opponentThreat,
    riskLevel,
    expectedConcedeXg,
  };
}
