/**
 * Haftalık Otomatik İçgörüler — dört motoru çapraz tarayıp "bu hafta en kritik
 * N şey"i ÖNCELİKLENDİREN sentez katmanı (retention motoru).
 *
 * Kaynak motorlar:
 *   • Sakatlık risk endeksi   (lib/injury-risk via lib/lineup-advice availability)
 *   • Maç simülasyonu          (lib/match-simulation)
 *   • Track record             (lib/track-record)
 *   • Kadro reçetesi           (lib/lineup-advice)
 *
 * Tek bir uygunluk geçişini paylaşır (avail → hem risk hem kadro), ekstra ağır
 * hesap yapmaz. Çıktı önceliğe göre sıralı; kullanıcı uygulamayı açmasa bile
 * (haftalık digest / overview akışı) en önemli sinyaller yukarı çıkar.
 */

import { squadAvailability, recommendedXI, type Availability } from "@/lib/lineup-advice";
import { demoNextMatchSimulation } from "@/lib/match-simulation";
import { demoTrackRecord } from "@/lib/track-record";
import { DEMO_OPPONENT } from "@/lib/demo-data";

export type InsightSeverity = "crit" | "high" | "info" | "good";

export const SEV_VAR: Record<InsightSeverity, string> = {
  crit: "var(--crit)", high: "var(--high)", info: "var(--accent)", good: "var(--low)",
};

export interface Insight {
  id: string;
  priority: number;          // 0..100 — sıralama
  severity: InsightSeverity;
  category: string;          // "Sakatlık" | "Maç" | "Kadro" | "Model" | "Yük"
  icon: string;              // tabler ikon sınıfı (ti-...)
  title: string;
  body: string;
  metric?: string;           // kısa sayısal vurgu ("%51", "78/100")
  href: string;
}

export interface WeeklyInsights {
  headline: string;
  insights: Insight[];       // önceliğe göre azalan
}

const SEV_BASE: Record<InsightSeverity, number> = { crit: 90, high: 70, info: 46, good: 42 };

/** Tüm motorlardan içgörü üret, önceliklendir, en kritik N'i döndür. */
export function weeklyInsights(opponent: string = DEMO_OPPONENT, limit = 6): WeeklyInsights {
  const avail = squadAvailability();
  const xi = recommendedXI(opponent, avail);
  const tr = demoTrackRecord();
  const sim = demoNextMatchSimulation();
  const out: Insight[] = [];

  // ── Sakatlık: en yüksek riskli oyuncu (trend yükseliyorsa aciliyet artar) ──
  const byRisk = [...avail].sort((a, b) => b.risk.score - a.risk.score);
  const top = byRisk[0];
  if (top && top.risk.score >= 45) {
    const rising = top.risk.trend === "rising";
    const sev: InsightSeverity = top.risk.level === "crit" ? "crit" : "high";
    out.push({
      id: `risk-${top.player.player_id}`,
      priority: SEV_BASE[sev] + (rising ? 8 : 0) + Math.round(top.risk.score / 20),
      severity: sev, category: "Sakatlık", icon: "ti-heart-rate-monitor",
      title: `${top.player.player_name} (${top.player.shirt}) sakatlık riskinde${rising ? " — yükseliyor" : ""}`,
      body: `${top.risk.topDriver?.detail ?? "Risk endeksi yüksek"}. ${top.risk.recommendation}`,
      metric: `${top.risk.score}/100`, href: `/players/${top.player.player_id}`,
    });
  }

  // ── Sakatlık: bant özeti (kaç oyuncu yüksek/kritik) ──
  const highCount = avail.filter((a) => a.risk.level === "high" || a.risk.level === "crit").length;
  if (highCount >= 2) {
    out.push({
      id: "risk-band",
      priority: 60 + highCount * 2,
      severity: highCount >= 4 ? "high" : "info", category: "Sakatlık", icon: "ti-activity",
      title: `${highCount} oyuncu yüksek/kritik risk bandında`,
      body: `Bu hafta yük yönetimi gerektiren ${highCount} oyuncu var — kadro reçetesi rotasyon öneriyor.`,
      metric: `${highCount} oyuncu`, href: "/squad",
    });
  }

  // ── Maç: sıradaki maç simülasyonu ──
  out.push({
    id: "match-sim",
    priority: 74,
    severity: "info", category: "Maç", icon: "ti-ball-football",
    title: `${sim.homeTeam} – ${sim.awayTeam}: %${Math.round(sim.probHomeWin * 100)} galibiyet`,
    body: `En olası skor ${sim.mostLikelyScore[0]}-${sim.mostLikelyScore[1]} · beklenen gol ${sim.lambdaHome.toFixed(1)}–${sim.lambdaAway.toFixed(1)} · KG var %${Math.round(sim.bttsYes * 100)}. Poisson-Dixon-Coles modeli.`,
    metric: `%${Math.round(sim.probHomeWin * 100)}`, href: "/match-plan",
  });

  // ── Kadro: dinlendirme önerileri ──
  const rested = avail.filter((a) => a.verdict === "dinlendir");
  if (rested.length > 0) {
    out.push({
      id: "lineup-rest",
      priority: 68 + rested.length * 3,
      severity: "high", category: "Kadro", icon: "ti-clipboard-list",
      title: `Kadro reçetesi: ${rested.map((a) => a.player.player_name.split(" ").slice(-1)[0]).join(", ")} dinlendirilmeli`,
      body: `${opponent} maçı için önerilen ${xi.formation} hazır (güven %${xi.confidence}); riskli oyuncuların yerine en yüksek skorlu uygun oyuncular yerleştirildi.`,
      metric: `${xi.formation}`, href: "/squad",
    });
  }

  // ── Yük: bu hafta antrenman yükü azaltılacaklar ──
  const deload = avail.filter((a) => a.deloadPct >= 25);
  if (deload.length > 0) {
    out.push({
      id: "load-deload",
      priority: 52 + deload.length,
      severity: "info", category: "Yük", icon: "ti-run",
      title: `${deload.length} oyuncuya bu hafta yük azaltma önerildi`,
      body: `Risk endeksi ${deload.map((a) => `${a.player.player_name.split(" ").slice(-1)[0]} −%${a.deloadPct}`).join(", ")} öneriyor.`,
      metric: `${deload.length} oyuncu`, href: "/squad",
    });
  }

  // ── Model: track record güven sinyali ──
  if (tr.resolved > 0) {
    const hot = tr.streak >= 3;
    out.push({
      id: "model-track",
      priority: 44 + (hot ? 10 : 0),
      severity: "good", category: "Model", icon: "ti-target-arrow",
      title: hot ? `Model son ${tr.streak} tahminde isabetli` : `Model isabet oranı %${Math.round(tr.hitRate * 100)}`,
      body: `${tr.resolved} değerlendirmede genel isabet %${Math.round(tr.hitRate * 100)} · Brier ${tr.brier ?? "—"}. Tahminler kayıt altında ve doğrulanıyor.`,
      metric: `%${Math.round(tr.hitRate * 100)}`, href: "/calibration",
    });
  }

  out.sort((a, b) => b.priority - a.priority);
  const insights = out.slice(0, limit);
  const headline = insights.length
    ? `Bu haftanın önceliği: ${insights[0].title}`
    : "Bu hafta kritik içgörü yok — kadro stabil.";
  return { headline, insights };
}
