/**
 * Antrenman Odağı — koç kimliği + kadro/taktik zaaflarından "bu hafta neyi çalış".
 *
 * Karar→aksiyon köprüsü: Teknik Direktör brifingindeki kimlik (tactical-dna) +
 * bilinen zaaflar (far-post duran top, geçiş) + kadro kondisyonu (yorgun oyuncu)
 * → önceliklendirilmiş antrenman temaları (neyi, neden, kim, hangi yoğunlukta).
 * Transfer/fikstür DEĞİL — eldeki takımı sahada çalıştırmak. Saf/deterministik.
 */

import { demoSquad } from "./demo-data";
import { demoTeamById } from "./demo-teams";
import { tacticalDna } from "./tactical-dna";

export type TrainCat = "Taktik" | "Savunma" | "Hücum" | "Fiziksel" | "Duran Top" | "Geçiş";
export type Intensity = "yüksek" | "orta" | "düşük";

export interface TrainingTheme {
  priority: number;
  category: TrainCat;
  title: string;
  why: string;          // veriye dayalı gerekçe
  focus: string;        // kim / ne
  intensity: Intensity;
}
export interface WeeklyTraining {
  themes: TrainingTheme[];
  summary: string;
  fatigued: { name: string; shirt: number; condition: number }[];
}

export function weeklyTraining(): WeeklyTraining {
  const s = tacticalDna(demoTeamById(100)!).style;
  const themes: TrainingTheme[] = [];

  // 1) Far-post duran top savunması — bilinen zaaf (45' yenen gol).
  themes.push({
    priority: 1, category: "Duran Top", intensity: "yüksek",
    title: "Far-post duran top savunması",
    why: "Son maçta 45' köşe vuruşunda far-post'tan gol yedik; ikinci direk örtülemiyor. Zonal→adam-adama geçişi ve far-post sorumlusu otomatikleşene dek tekrar.",
    focus: "En iyi hava topçu (Agbadou) far-post; tüm savunma bloğu markaj senkronu.",
  });

  // 2) Pres organizasyonu — kimlik yüksek pres ise.
  if (s.pressing >= 52) themes.push({
    priority: 2, category: "Taktik", intensity: "yüksek",
    title: "Pres organizasyonu & tetikleri",
    why: `Kimlik yüksek pres (DNA pres ${s.pressing}). Senkron baskı, tetik anları (geri pas / kötü ilk dokunuş) ve pres-sonrası ikinci dalga 11v11 çalışılmalı.`,
    focus: "Ön üçlü + orta saha blok hareketi; kompaktlık.",
  });

  // 3) Kanat 1v1 & genişlik — kimlik kanat ağırlıklı ise (güç sömürme).
  if (s.width >= 52) themes.push({
    priority: 3, category: "Hücum", intensity: "orta",
    title: "Kanat 1v1 & genişlik",
    why: `Kanat ağırlıklı kimlik (DNA genişlik ${s.width}); Rashica gibi 1v1 üstün kanatlar var. Krosla bitiriş, ters kanat içe kat ve far-post koşusu.`,
    focus: "Kanatlar + bek bindirmesi; ceza sahasında ikinci dalga.",
  });

  // 4) Arkadan kuruluş — topa sahip kimlik ise.
  if (s.possession >= 50 || s.buildUp >= 52) themes.push({
    priority: 4, category: "Taktik", intensity: "orta",
    title: "Arkadan kuruluş & pres kırma",
    why: `Topa sahip kimlik (sahiplik ${s.possession}). Kaleci-stoper-ön libero üçgeni, üçüncü adam koşusu ve yüksek prese karşı çıkış kalıpları.`,
    focus: "Stoperler + ön libero (Ndidi) + kaleci ayak.",
  });

  // 5) Geçiş savunması — direkt/kontra rakiplere karşı denge.
  if (s.directness <= 55) themes.push({
    priority: 5, category: "Geçiş", intensity: "orta",
    title: "Geçiş savunması (rest-defence)",
    why: "Yukarı basan kimlikte top kaybı kontra riski doğurur. Top kaybında ön libero kalması, beklerin aşırı çıkmaması ve 5 saniye geri-kazanım.",
    focus: "Ön libero + stoper ikilisi; geçiş anı pozisyonel disiplin.",
  });

  // 6) Kondisyon yönetimi — yorgun oyuncular.
  const fatigued = demoSquad.filter((p) => p.condition < 75).sort((a, b) => a.condition - b.condition)
    .map((p) => ({ name: p.player_name, shirt: p.shirt, condition: p.condition }));
  if (fatigued.length) themes.push({
    priority: 6, category: "Fiziksel", intensity: "düşük",
    title: "Kondisyon yönetimi & toparlanma",
    why: `${fatigued.length} oyuncu kondisyon eşiğinin (<75) altında. Onlara bireysel yük azaltma + toparlanma; gruba düşük-hacim yüksek-kalite.`,
    focus: fatigued.slice(0, 4).map((f) => `${f.name.split(" ").slice(-1)[0]} (${f.condition})`).join(", "),
  });

  themes.sort((a, b) => a.priority - b.priority);
  const top = themes.slice(0, 3).map((t) => t.title.toLowerCase());
  const summary = `Bu haftanın odağı: ${top.join(", ")}. Kimlik ${tacticalDna(demoTeamById(100)!).formation} · yüksek pres + kanat; en acil iş far-post duran top zaafını kapatmak. ${fatigued.length} yorgun oyuncu için yük ayrı yönetilecek.`;

  return { themes, summary, fatigued };
}
