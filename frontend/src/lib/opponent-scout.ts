/**
 * Rakip Scout — maç-öncesi "onları oku" motoru. Rakibin taktik DNA'sından
 * (tactical-dna) türetir: muhtemel 11 + diziliş, dangerman'ler (markaj talimatıyla),
 * ve rakibin bize karşı planı + her birine önlemimiz. Demo'da rakip kadrosu yok →
 * 11 pozisyon+rol+tehdit PROJEKSİYONUDUR (gerçek veride sağlayıcı diziliş besler).
 * Tehditler canlı referanslara bağlı (sıcak sağ kanat #23, kontra motoru #6).
 */

import { demoTeamById } from "./demo-teams";
import { tacticalDna } from "./tactical-dna";

export interface OppPlayer { num: number; pos: string; x: number; y: number; tier?: "high" | "mid" }
export interface Dangerman { num: number; pos: string; label: string; threat: string; marking: string; tier: "high" | "mid" }
export interface TheirIntent { theyWill: string; because: string; counter: string }

// Diziliş şablonu — rakip soldan sağa (bize doğru) hücum eder; 0-100 (x=derinlik, y=genişlik).
const FORMATIONS: Record<string, { num: number; pos: string; x: number; y: number }[]> = {
  "4-4-2": [
    { num: 1, pos: "GK", x: 8, y: 50 },
    { num: 2, pos: "RB", x: 30, y: 84 }, { num: 4, pos: "CB", x: 24, y: 62 }, { num: 5, pos: "CB", x: 24, y: 38 }, { num: 3, pos: "LB", x: 30, y: 16 },
    { num: 23, pos: "RM", x: 58, y: 86 }, { num: 6, pos: "CM", x: 50, y: 60 }, { num: 8, pos: "CM", x: 50, y: 40 }, { num: 11, pos: "LM", x: 58, y: 14 },
    { num: 9, pos: "ST", x: 80, y: 58 }, { num: 19, pos: "ST", x: 80, y: 42 },
  ],
  "5-3-2": [
    { num: 1, pos: "GK", x: 8, y: 50 },
    { num: 2, pos: "RWB", x: 34, y: 88 }, { num: 4, pos: "CB", x: 22, y: 66 }, { num: 5, pos: "CB", x: 20, y: 50 }, { num: 6, pos: "CB", x: 22, y: 34 }, { num: 3, pos: "LWB", x: 34, y: 12 },
    { num: 8, pos: "CM", x: 52, y: 66 }, { num: 10, pos: "CM", x: 50, y: 50 }, { num: 7, pos: "CM", x: 52, y: 34 },
    { num: 9, pos: "ST", x: 80, y: 58 }, { num: 19, pos: "ST", x: 80, y: 42 },
  ],
};

export function opponentXI(themId = 101): { formation: string; players: OppPlayer[]; note: string } {
  const row = demoTeamById(themId);
  const dna = row ? tacticalDna(row) : null;
  const formation = dna?.formation && FORMATIONS[dna.formation] ? dna.formation : "4-4-2";
  const tpl = FORMATIONS[formation];
  const dm = new Set(dangermen(themId).map((d) => d.num));
  const players: OppPlayer[] = tpl.map((p) => ({ ...p, tier: dm.has(p.num) ? "high" : undefined }));
  return {
    formation,
    players,
    note: `Muhtemel 11 — projeksiyon (rakibin tipik ${formation} dizilişi). Gerçek veride sağlayıcı kadro/diziliş besler.`,
  };
}

export function dangermen(themId = 101): Dangerman[] {
  const row = demoTeamById(themId);
  const s = row ? tacticalDna(row).style : null;
  const out: Dangerman[] = [];
  // Sıcak kanat (canlı: rakip sağ kanat bizim sol bekten sürekli giriyor).
  out.push({ num: 23, pos: "RM", label: "Sıcak kanat", threat: "1v1 hız + dripling; son maçlarda %42 dokunuş payı, o koridordan sürekli giriyor.", marking: "Rıdvan'a (3) içe-kapatma desteği gönder; çift markaj, dış ayağa zorla.", tier: "high" });
  // Duran top / hava topu (rakip setPiece bağımlı).
  if (!s || s.setPiece >= 50) out.push({ num: 9, pos: "ST", label: "Hedef santrfor", threat: "Hava topu + far-post tehdidi; duran topların ana hedefi.", marking: "Agbadou (5) far-post'ta adam-adama beğenmesin; ikinci top temizle.", tier: "high" });
  // Kontra motoru (rakip direkt/kontra).
  if (!s || s.directness >= 52) out.push({ num: 6, pos: "CM", label: "Kontra motoru", threat: "Top kazanınca ilk dikine pası atan oyuncu; kontraları o başlatıyor.", marking: "Salih (8) / Ndidi (6) pres tetiği — ileri pasını kes, geçişi yavaşlat.", tier: "mid" });
  return out;
}

export function theirGamePlan(themId = 101): TheirIntent[] {
  const row = demoTeamById(themId);
  const s = row ? tacticalDna(row).style : null;
  if (!s) return [];
  const out: TheirIntent[] = [];
  if (s.lineHeight <= 46) out.push({
    theyWill: "Derin blok kurup arkalarında boşluk vermeyecekler",
    because: `Savunma hattı düşük (yükseklik ${s.lineHeight}) — geriye yaslanıp alan kapatıyorlar.`,
    counter: "Genişlik aç, far-post'a santrfor sabit, yarı-alanda 10 numara; sabırlı kuruluş, acele şut yok.",
  });
  if (s.directness >= 52) out.push({
    theyWill: "Top kazanınca 2-3 pasta hızlı kontra çıkacaklar",
    because: `Direkt oyun yüksek (${s.directness}) — kontra atak ana silahları.`,
    counter: "Top kaybında ön libero (Ndidi) kalsın, bekler aşırı çıkmasın; rest-defence dengesi şart.",
  });
  if (s.setPiece >= 50) out.push({
    theyWill: "Faul/korner kazanıp duran toptan gol arayacaklar",
    because: `Duran top bağımlılığı yüksek (${s.setPiece}) — son 8 maçta 4 set-piece golü.`,
    counter: "Gereksiz faul verme; köşelerde far-post adam-adama, ikinci topu garantile.",
  });
  if (s.pressing <= 48) out.push({
    theyWill: "Yüksek pres yapmayacaklar, orta blokta bekleyecekler",
    because: `Pres yoğunluğu düşük (${s.pressing}) — kendi yarılarında organize duruyorlar.`,
    counter: "Stoperler rahat kuracak — onları yukarı çek, arkadan sabırlı çıkıp blok önünde sayısal üstünlük ara.",
  });
  return out;
}
