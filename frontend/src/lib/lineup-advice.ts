/**
 * Kadro Reçetesi — modelin TAHMİNİNİ KARARA çeviren reçete katmanı.
 *
 * Her oyuncu için sıradaki maça uygunluk verdisi (başla / dakika sınırı / rotasyon
 * / dinlendir) + bu haftaki antrenman yükü azaltma yüzdesi, birleşik sakatlık risk
 * endeksinden (lib/injury-risk) + kondisyondan füzyonlanır. Üstüne 4-3-3 önerilen
 * 11: her mevkiye uygun + en yüksek seçilebilirlik skorlu OYNAYABİLİR oyuncuyu
 * yerleştirir; riskli yıldızları dinlendirir ve GEREKÇESİNİ yazar.
 *
 * Saf hesap — DEMO_MODE'da burada; production'da aynı endeks + kadro verisiyle backend.
 */

import { demoSquad, demoAttributesFor, type SquadPlayer } from "@/lib/demo-data";
import { computeRiskFor, type RiskIndex } from "@/lib/injury-risk";

export type Verdict = "başla" | "dakika_sınırı" | "rotasyon" | "dinlendir";

export const VERDICT_LABEL: Record<Verdict, string> = {
  "başla": "Başla", "dakika_sınırı": "Dakika Sınırı", "rotasyon": "Rotasyon", "dinlendir": "Dinlendir",
};
export const VERDICT_VAR: Record<Verdict, string> = {
  "başla": "var(--low)", "dakika_sınırı": "var(--mid)", "rotasyon": "var(--accent)", "dinlendir": "var(--crit)",
};

export interface Availability {
  player: SquadPlayer;
  verdict: Verdict;
  minutesCap: number | null;   // dakika sınırı varsa (örn 60)
  deloadPct: number;           // bu hafta antrenman yükü azaltma %
  reasons: string[];
  risk: RiskIndex;
  quality: number;             // 1-20 genel (özellik ortalaması)
  selectionScore: number;      // 11 seçimi için sıralama skoru
}

const DELOAD_BY_LEVEL: Record<RiskIndex["level"], number> = { crit: 40, high: 25, mid: 12, low: 0 };

/** Oyuncunun genel kalitesi (1-20) — özellik gruplarının ortalaması (oyuncu sayfasıyla aynı).
 *  Veri statik+deterministik olduğu için cache'lenir (demoAttributesFor ağır). */
const _qualityCache = new Map<number, number>();
function qualityOf(playerId: number): number {
  const hit = _qualityCache.get(playerId);
  if (hit !== undefined) return hit;
  const groups = demoAttributesFor(playerId);
  const all = groups.flatMap((g) => g.attrs);
  const q = all.length ? all.reduce((s, a) => s + a.value, 0) / all.length : 10;
  _qualityCache.set(playerId, q);
  return q;
}

/** Bir oyuncunun maça uygunluk reçetesi (risk endeksi + kondisyon füzyonu). */
export function availabilityOf(player: SquadPlayer): Availability {
  const risk = computeRiskFor(player.player_id);
  const cond = player.condition;
  const quality = qualityOf(player.player_id);

  let verdict: Verdict;
  let minutesCap: number | null = null;
  const reasons: string[] = [];

  if (risk.level === "crit" || cond < 60) {
    verdict = "dinlendir";
    reasons.push(`Kritik sakatlık riski (endeks ${risk.score}/100) — tekrar-sakatlanma tehlikesi`);
    if (cond < 60) reasons.push(`Kondisyon ${cond} — yorgunluk bandının altında`);
  } else if (risk.level === "high" || cond < 70) {
    verdict = "dakika_sınırı";
    minutesCap = 60;
    reasons.push(`Yüksek risk (endeks ${risk.score}/100) — ~60 dk sonrası değişiklik planla`);
    if (cond < 70) reasons.push(`Kondisyon ${cond} — tam maç yükü riskli`);
  } else if (risk.level === "mid") {
    verdict = "rotasyon";
    reasons.push(`Orta risk (endeks ${risk.score}/100) — rotasyona uygun, gerekirse başlar`);
  } else {
    verdict = "başla";
    reasons.push(`Düşük risk (endeks ${risk.score}/100), kondisyon ${cond} — tam maça hazır`);
  }
  if (risk.topDriver && verdict !== "başla") reasons.push(risk.topDriver.detail);

  // Seçilebilirlik skoru: kalite × kondisyon ağırlığı − risk cezası.
  const riskPenalty: Record<RiskIndex["level"], number> = { crit: 40, high: 16, mid: 5, low: 0 };
  const selectionScore = Math.round(
    (quality * 5) * (0.62 + 0.38 * cond / 100) - riskPenalty[risk.level],
  );

  return {
    player, verdict, minutesCap, deloadPct: DELOAD_BY_LEVEL[risk.level],
    reasons, risk, quality: Math.round(quality * 10) / 10, selectionScore,
  };
}

/** Tüm kadronun uygunluk reçetesi (riskli/dinlendir önce sıralı değil — id sıralı). */
export function squadAvailability(): Availability[] {
  return demoSquad.map(availabilityOf);
}

// ── Önerilen 11 (4-3-3) ──────────────────────────────────────────────────────

export interface FormationSlot {
  slot: string;           // GK/LB/CB/RB/DM/CM/AM/LW/ST/RW
  label: string;
  eligible: string[];     // uygun pos_detail listesi
  x: number; y: number;   // saha koordinatı (% — y büyük = kendi kalemiz)
}

// 4-3-3, dikey saha (kendi kalemiz altta y~90, hücum yukarı).
const SLOTS_433: FormationSlot[] = [
  { slot: "GK", label: "Kaleci", eligible: ["Kaleci"], x: 50, y: 90 },
  { slot: "LB", label: "Sol Bek", eligible: ["Sol Bek"], x: 16, y: 72 },
  { slot: "CB", label: "Stoper", eligible: ["Stoper"], x: 38, y: 77 },
  { slot: "CB", label: "Stoper", eligible: ["Stoper"], x: 62, y: 77 },
  { slot: "RB", label: "Sağ Bek", eligible: ["Sağ Bek"], x: 84, y: 72 },
  { slot: "DM", label: "Ön Libero", eligible: ["Ön Libero", "Merkez OS"], x: 50, y: 58 },
  { slot: "CM", label: "Merkez", eligible: ["Merkez OS", "Ön Libero", "10 Numara"], x: 28, y: 47 },
  { slot: "AM", label: "10 Numara", eligible: ["10 Numara", "Merkez OS"], x: 72, y: 47 },
  { slot: "LW", label: "Sol Kanat", eligible: ["Sol Kanat", "Sağ Kanat"], x: 20, y: 26 },
  { slot: "ST", label: "Santrfor", eligible: ["Santrfor"], x: 50, y: 18 },
  { slot: "RW", label: "Sağ Kanat", eligible: ["Sağ Kanat", "Sol Kanat"], x: 80, y: 26 },
];

export interface SlotPick extends FormationSlot {
  pick: Availability | null;
  forced: boolean;        // sadece riskli/uygunsuz oyuncu kaldıysa
}

export interface LineupAdvice {
  formation: string;
  picks: SlotPick[];
  benched: Availability[];      // 11 dışı, öne çıkan yedekler (skor sıralı)
  restedKey: Availability[];    // riski yüzünden dinlendirilen/sınırlı kilit oyuncular
  gaps: string[];               // zorlanan mevkiler
  confidence: number;           // 0..100 öneri güveni
  headline: string;
}

/** Sıradaki maç için önerilen 11 — uygunluk + kaliteye göre mevkilere yerleştir.
 *  avail önceden hesaplanmışsa tekrar hesaplamadan kullanır (çift iş önlenir). */
export function recommendedXI(opponent = "Antalyaspor", avail: Availability[] = squadAvailability()): LineupAdvice {
  const byId = new Map(avail.map((a) => [a.player.player_id, a]));
  const used = new Set<number>();
  const gaps: string[] = [];

  // Bir slota uygun, kullanılmamış adaylar (oynayabilir = dinlendir değil) skor sıralı.
  const candidatesFor = (slot: FormationSlot, allowRested: boolean) =>
    avail
      .filter((a) => !used.has(a.player.player_id)
        && slot.eligible.includes(a.player.pos_detail)
        && (allowRested || a.verdict !== "dinlendir"))
      .sort((x, y) => y.selectionScore - x.selectionScore);

  // Kıtlığa göre sırala: en az adayı olan slot önce dolsun (uzmanlık mevkilerini açlıktan koru).
  const order = [...SLOTS_433].sort((a, b) => candidatesFor(a, false).length - candidatesFor(b, false).length);

  const result = new Map<string, SlotPick>();
  for (const slot of order) {
    let pool = candidatesFor(slot, false);
    let forced = false;
    if (!pool.length) { pool = candidatesFor(slot, true); forced = true; }  // mecbur: riskliyi koy
    const pick = pool[0] ?? null;
    if (pick) used.add(pick.player.player_id);
    if (forced && pick) gaps.push(`${slot.label}: yalnız riskli/uygunsuz seçenek (${pick.player.player_name})`);
    if (!pick) gaps.push(`${slot.label}: uygun oyuncu yok`);
    result.set(`${slot.slot}-${slot.x}-${slot.y}`, { ...slot, pick, forced });
  }
  // Saha düzeni için orijinal sırada döndür.
  const picks = SLOTS_433.map((s) => result.get(`${s.slot}-${s.x}-${s.y}`)!);

  const benched = avail
    .filter((a) => !used.has(a.player.player_id) && a.verdict !== "dinlendir")
    .sort((x, y) => y.selectionScore - x.selectionScore)
    .slice(0, 7);

  const restedKey = avail
    .filter((a) => (a.verdict === "dinlendir" || a.verdict === "dakika_sınırı") && a.quality >= 11)
    .sort((x, y) => y.quality - x.quality);

  const confidence = Math.max(58, Math.min(94, 92 - gaps.length * 9 - restedKey.length * 2));

  const restedNames = avail.filter((a) => a.verdict === "dinlendir").map((a) => `${a.player.player_name} (${a.player.shirt})`);
  const headline = restedNames.length
    ? `${opponent} maçı için önerilen 11 hazır. ${restedNames.join(", ")} riski yüzünden dinlendirildi; yerlerine en yüksek skorlu uygun oyuncular yerleştirildi.`
    : `${opponent} maçı için kadro tam uygun — riskli oyuncu yok, en güçlü 11 öneriliyor.`;

  return { formation: "4-3-3", picks, benched, restedKey, gaps, confidence, headline };
}
