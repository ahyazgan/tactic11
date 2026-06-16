/**
 * Maç Değerlendirmesi — kanıt döngüsünü kapatan retrospektif (niceliksel + dürüst).
 *
 * Sistem maç boyunca uyarılar yaptı; bunların kaçı GERÇEKTEN oldu, ne kadar
 * ÖNEMLİYDİ, ve neyi KAÇIRDI? Her uyarı gerçek timeline olayına bağlanır (uydurma
 * değil), doğrulanan kritik olayların win-prob bedeli ölçülür, motor-bazlı isabet
 * çıkarılır ve sistemin uyarmadığı tehlikeli anlar (false negative) dürüstçe
 * listelenir. Analist kararı (uygulandı/atlandı) UI'da action-log'dan bindirilir.
 */

import { demoLive } from "@/lib/demo-data";
import { demoWinProbCurve } from "@/lib/live-win-probability";

export type ReviewVerdict = "validated" | "monitoring" | "pending";

export interface ReviewItem {
  minute: number;
  engine: string;          // kaynağı (Duran Top / Sakatlık / Momentum …)
  recommendation: string;
  verdict: ReviewVerdict;
  evidence: string;
  winProbCost?: number;    // doğrulanan olayın kazanma olasılığına etkisi (puan, işaretli)
  actionId?: string;
}

export interface MissedItem { minute: number; text: string; note: string }
export interface EngineScore { engine: string; hit: number; graded: number }

export const VERDICT_LABEL: Record<ReviewVerdict, string> = {
  validated: "Doğrulandı", monitoring: "İzlemede", pending: "Karar bekliyor",
};

export interface MatchReview {
  matchId: string;
  label: string;
  items: ReviewItem[];
  misses: MissedItem[];
  byEngine: EngineScore[];
  validated: number; monitoring: number; total: number;
  curve: { minute: number; pHome: number }[];
  goals: { minute: number; team: "home" | "away" }[];
  finalNote: string;
}

export function matchReview(): MatchReview {
  const curveRaw = demoWinProbCurve();
  const pAt = (minute: number) => {
    // verilen dakikadaki (≤) en yakın eğri noktasının ev galibiyet olasılığı
    let best = curveRaw[0];
    for (const c of curveRaw) if (c.minute <= minute) best = c;
    return best.pHome;
  };
  const curve = curveRaw.map((c) => ({ minute: c.minute, pHome: c.pHome }));
  const goals = demoLive.events.filter((e) => e.type === "gol").map((e) => ({ minute: e.minute, team: e.team as "home" | "away" }));

  const hasFarPostGoal = demoLive.events.some((e) => e.minute === 45 && e.type === "gol");
  const djaloCard = demoLive.events.find((e) => e.type === "sari_kart" && /djal/i.test(e.text));
  const kokcuInjury = demoLive.events.find((e) => e.type === "sakatlik" && /orkun|kökçü/i.test(e.text));
  const lastMom = demoLive.series[demoLive.series.length - 1]?.momentum ?? 0;

  // far-post golünün win-prob bedeli: gol öncesi (40') vs sonrası (45').
  const farPostCost = Math.round((pAt(45) - pAt(40)) * 100);

  const items: ReviewItem[] = [
    {
      minute: 45, engine: "Duran Top", recommendation: "Far-post zaafı — ikinci direği örtün",
      verdict: hasFarPostGoal ? "validated" : "monitoring",
      evidence: hasFarPostGoal ? "45' köşe vuruşunda tam far-post'tan gol yedik — uyarı birebir gerçekleşti." : "Henüz duran toptan gol yok.",
      winProbCost: hasFarPostGoal ? farPostCost : undefined,
    },
    {
      minute: 31, engine: "Kart / Disiplin", recommendation: "Tiago Djaló kart riski — ikinci sarı tehlikesi",
      verdict: djaloCard ? "validated" : "monitoring",
      evidence: djaloCard ? "31' sarı kart gördü; risk gerçekti (67'ye dek ikinciyi görmedi — yönetildi)." : "Kart riski materyalize olmadı.",
      actionId: "alert-31",
    },
    {
      minute: 52, engine: "Sakatlık Riski", recommendation: "Orkun Kökçü yorgunluk/sakatlık eşiği — değiştir",
      verdict: kokcuInjury ? "validated" : "monitoring",
      evidence: kokcuInjury ? "52' arka adale sinyali — yorgunluk uyarısı sakatlığı erken yakaladı." : "Yorgunluk eşiği aşılmadı.",
      actionId: "alert-52",
    },
    {
      minute: 58, engine: "Momentum", recommendation: "Momentum rakibe döndü — pres hattını düşür",
      verdict: lastMom < -15 ? "validated" : "monitoring",
      evidence: lastMom < -15 ? `55-67' momentum sürekli rakipte (${lastMom}); 64' rakip üst üste 2 korner.` : "Momentum dengelendi.",
      actionId: "alert-58",
    },
    {
      minute: 57, engine: "Eşleşme", recommendation: "Sol koridor zaafı (Rıdvan Yılmaz) — yardımcı gönder",
      verdict: "monitoring",
      evidence: "Düello kayıpları sürüyor; o koridordan henüz gol yemedik — açık risk, izlemede.",
      actionId: "alert-57",
    },
    {
      minute: 67, engine: "Kadro", recommendation: "Önerilen değişiklik — Kökçü → Junior",
      verdict: "pending",
      evidence: "İleriye dönük öneri: payoff (işe yaradı mı) maç sonu gerçek sonuçla kapanır.",
      actionId: "sub-Orkun Kökçü (10)",
    },
  ];

  // Sistemin KAÇIRDIKLARI — uyarmadığı tehlikeli anlar (false negative, dürüstlük).
  const misses: MissedItem[] = demoLive.events
    .filter((e) => e.type === "buyuk_firsat" && e.team === "away")
    .map((e) => ({ minute: e.minute, text: e.text, note: "Sistem bu rakip fırsatını ÖNCEDEN flag'lemedi — anlık tehlike tespiti henüz yok (canlı tracking ile eklenir)." }));

  // Motor-bazlı isabet (pending hariç).
  const eng: Record<string, { hit: number; graded: number }> = {};
  for (const it of items) {
    if (it.verdict === "pending") continue;
    const e = (eng[it.engine] ??= { hit: 0, graded: 0 });
    e.graded++; if (it.verdict === "validated") e.hit++;
  }
  const byEngine = Object.entries(eng).map(([engine, v]) => ({ engine, hit: v.hit, graded: v.graded }));

  const validated = items.filter((i) => i.verdict === "validated").length;
  const monitoring = items.filter((i) => i.verdict === "monitoring").length;
  const label = `${demoLive.home} ${demoLive.score[0]}-${demoLive.score[1]} ${demoLive.away}`;
  const matchId = `demo-${demoLive.home}-${demoLive.away}`.toLowerCase().replace(/\s+/g, "-");
  const finalNote = `${demoLive.minute}' itibarıyla ${label}`;
  return { matchId, label, items, misses, byEngine, validated, monitoring, total: items.length, curve, goals, finalNote };
}
