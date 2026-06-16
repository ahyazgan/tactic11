/**
 * Maç-Öncesi Plan Derinliği — faz-faz plan + "ya olursa" hazır dalları.
 *
 * Rakibin taktik DNA'sından (tactical-dna) türer: oyunun dört fazı (kuruluş /
 * hücum / savunma / geçiş) için bizim yaklaşımımız, ve maç-içi durumlar için
 * önceden hazırlanmış cevaplar (erken gol yersek, 5-li savunmaya geçerlerse…).
 * Statik metin değil — rakibin stil eksenlerine (pres/hat/direkt/duran top) göre.
 */

import { demoTeamById } from "./demo-teams";
import { tacticalDna, type StyleProfile } from "./tactical-dna";

export interface PhasePlan { phase: string; icon: string; approach: string; key: string }
export interface Branch { trigger: string; response: string }

function themStyle(themId: number): StyleProfile | null {
  const row = demoTeamById(themId);
  return row ? tacticalDna(row).style : null;
}

/** Oyunun dört fazı için plan — rakip stiline uyarlı. */
export function phasePlan(themId = 101): PhasePlan[] {
  const s = themStyle(themId);
  const lowPress = !s || s.pressing <= 48;
  const deepBlock = !s || s.lineHeight <= 46;
  const counter = !s || s.directness >= 52;
  const setPiece = !s || s.setPiece >= 50;

  return [
    {
      phase: "Kuruluş", icon: "🧱",
      approach: lowPress
        ? "Rakip yüksek pres yapmıyor — stoperler topu rahat alır. Onları yukarı çek, kaleci-stoper sakin kursun, blok önünde sayısal üstünlük ara."
        : "Rakip presliyor — ilk pas hızlı ve güvenli; gerekirse kaleciden uzun seçenek açık tutulur.",
      key: lowPress ? "Acele uzun top yok; sabırla blok önüne taşı." : "Pres kırma: üçüncü adam koşusu.",
    },
    {
      phase: "Hücum", icon: "🎯",
      approach: deepBlock
        ? "Derin bloğa karşı GENİŞLİK + far-post: Rashica (7) sağda 1v1, ters kanat içe kat eder, santrfor far-post'ta sabit. Sağ bek arkası boşluğunu (rakip zaafı) hızlı beklet."
        : "Rakip yüksek hat tutuyor — arkası açık; hızlı santrfor + dikine pasla derinlik koşusu.",
      key: "Yarı-alanda 10 numara; ikinci dalga ceza yayında.",
    },
    {
      phase: "Savunma", icon: "🛡️",
      approach: `Rest-defence dengesi: top kaybında ön libero (Ndidi) kalır, bekler aşırı çıkmaz.${counter ? " Rakip kontracı — geçiş anında geri-kazanım hattı şart." : ""}${setPiece ? " Köşelerde far-post adam-adama, ikinci top garanti." : ""}`,
      key: counter || setPiece ? "İki ana tehdit: kontra + duran top." : "Organize blok, kompakt hatlar.",
    },
    {
      phase: "Geçiş", icon: "⚡",
      approach: "Top kazanınca 3 saniye kuralı: dikine ilk seçenek, rakip henüz şekillenmeden. Top kaybında 5 saniye agresif geri-kazanım, olmazsa hızlı geri çekil.",
      key: counter ? "Maçın en kırılgan fazı — rakip tam buradan vuruyor." : "Geçişte tempo bizim lehimize.",
    },
  ];
}

/** Maç-içi durumlar için önceden hazır dallar (scoreline ötesi taktik). */
export function whatIfBranches(themId = 101): Branch[] {
  const s = themStyle(themId);
  const deepBlock = !s || s.lineHeight <= 46;
  const lateDrop = true; // bilinen zaaf: 75+ tempo düşüşü
  const out: Branch[] = [];

  out.push({
    trigger: "Erken gol yersek (ilk 25')",
    response: "Panik yok — yapıyı koru, tempoyu sen belirle. Dizilişi bozma; xG akışı bizde kaldıkça gol gelir. Devre arasına kadar sabır.",
  });
  out.push({
    trigger: deepBlock ? "Daha da kapanıp 5-li savunmaya geçerlerse" : "Geriye yaslanıp alan kapatırlarsa",
    response: "Bek-içe kaydır (inverted FB), bir kanadı overload et, far-post varyasyonunu artır. Uzaktan şut + ceza yayında ikinci top avcısı.",
  });
  out.push({
    trigger: "Beklenmedik yüksek pres yaparlarsa",
    response: "Presi pasla değil sırtla aş: kaleci-stoper uzun seçeneği açsın, hızlı santrfora dikine — arkalarındaki boşluğu cezalandır.",
  });
  out.push({
    trigger: "60. dakikadan sonra öne geçersek",
    response: lateDrop
      ? "Oyun yönetimi + taze kanat: rakip 75+ tempo düşürüyor (bilinen zaaf). Hızlı bir kanat oyuncusuyla farkı büyütmeyi dene, ikinci topları topla."
      : "Oyun yönetimi: ikinci toplar, zaman, kontrollü düşürülen tempo; gereksiz risk yok.",
  });
  return out;
}
