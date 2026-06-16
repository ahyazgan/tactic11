/**
 * Komuta Merkezi sentez katmanı — motorları TEK brifinge, karar kuyruğuna ve
 * delta'lı KPI'lara füzyonlar; maç-durumuna (öncesi/canlı/sonrası) göre uyarlar.
 *
 * #1 executiveBrief  — 2-4 cümlelik yönetici özeti (tüm motorlar tek hikâye).
 * #2 commandDecisions— TD'nin vermesi gereken kararlar (önem sıralı + aksiyon).
 * #3 commandKpis     — manşet KPI + "geçen haftaya/maç-öncesine göre" delta.
 * #4 matchState      — demoLive.minute'a göre pre/live/post; içerik buna uyar.
 *
 * Tek paylaşılan motor geçişi (avail) — ekstra ağır hesap yok. Saf+deterministik.
 */

import { DEMO_OPPONENT, demoLive } from "@/lib/demo-data";
import { demoNextMatchSimulation } from "@/lib/match-simulation";
import { squadAvailability, recommendedXI, VERDICT_LABEL, type Availability } from "@/lib/lineup-advice";
import { LEVEL_LABEL } from "@/lib/injury-risk";
import { demoTrackRecord } from "@/lib/track-record";
import { defensiveSetPiece } from "@/lib/set-piece";
import { demoWinProbNow } from "@/lib/live-win-probability";

export type MatchState = "pre" | "live" | "post";

export function matchState(): MatchState {
  const m = demoLive.minute;
  return m <= 0 ? "pre" : m >= 90 ? "post" : "live";
}

const pct = (x: number) => Math.round(x * 100);
const lastName = (s: string) => s.split(" ").slice(-1)[0];

// ── #3 KPI'lar + delta ───────────────────────────────────────────────────────
export interface BriefKpi {
  key: string;
  label: string;
  value: string;
  sub: string;
  color: string;
  delta?: { text: string; good: boolean };   // geçen hafta / maç-öncesine göre
}

// Geçen haftanın anlık görüntüsü (deterministik baz) — delta hikâyesi için.
// risk yükseldi, model iyileşti, kadro güveni hafif düştü, dinlendirilecek arttı.
const PREV = { riskDelta: +6, modelDelta: -0.03, confDelta: +3, restedDelta: -1 };

function topRiskRow(avail: Availability[]) {
  return [...avail].sort((a, b) => b.risk.score - a.risk.score)[0] ?? null;
}

export interface CommandIntel {
  state: MatchState;
  kpis: BriefKpi[];
  decisions: CommandDecision[];
  brief: string[];
}

export interface CommandDecision {
  id: string;
  priority: number;
  category: string;     // "Sakatlık" | "Maç" | "Savunma" | "Kadro"
  severity: "kritik" | "yüksek" | "orta";
  title: string;        // ne
  action: string;       // önerilen aksiyon
  href: string;
}

const SEV_RANK = { kritik: 3, yüksek: 2, orta: 1 };

/** Tüm komuta-merkezi zekası tek geçişte — KPI + karar + brifing, duruma uyarlı. */
export function commandIntel(): CommandIntel {
  const state = matchState();
  const sim = demoNextMatchSimulation();
  const avail = squadAvailability();
  const xi = recommendedXI(DEMO_OPPONENT, avail);
  const tr = demoTrackRecord();
  const def = defensiveSetPiece();
  const top = topRiskRow(avail);
  const rested = avail.filter((a) => a.verdict === "dinlendir");
  const win = state === "live" ? demoWinProbNow() : null;
  const momentum = demoLive.series[demoLive.series.length - 1]?.momentum ?? 0;

  // ── KPI'lar ──
  const rateColor = (r: number) => r >= 0.7 ? "var(--low)" : r >= 0.55 ? "var(--mid)" : "var(--high)";
  const matchKpi: BriefKpi = win
    ? {
      key: "match", label: "Canlı Galibiyet", value: `%${pct(win.pHome)}`,
      sub: `${win.minute}' · ${win.scoreHome}-${win.scoreAway} · ${DEMO_OPPONENT}`,
      color: rateColor(win.pHome),
      delta: { text: `maç-öncesi %${pct(sim.probHomeWin)} → şu an %${pct(win.pHome)}`, good: win.pHome >= sim.probHomeWin },
    }
    : {
      key: "match", label: "Galibiyet Olasılığı", value: `%${pct(sim.probHomeWin)}`,
      sub: `${DEMO_OPPONENT} · en olası ${sim.mostLikelyScore[0]}-${sim.mostLikelyScore[1]}`, color: "var(--low)",
    };

  const kpis: BriefKpi[] = [
    matchKpi,
    top ? {
      key: "risk", label: "En Kritik Risk", value: `${top.risk.score}`, sub: top.player.player_name,
      color: top.risk.level === "crit" ? "var(--crit)" : "var(--high)",
      delta: { text: `geçen hafta ${top.risk.score - PREV.riskDelta} → ${top.risk.score} ▲`, good: false },
    } : { key: "risk", label: "En Kritik Risk", value: "—", sub: "yok", color: "var(--low)" },
    {
      key: "model", label: "Model İsabet", value: `%${pct(tr.hitRate)}`,
      sub: `${tr.resolved} değerlendirme · seri ${tr.streak}✓`, color: rateColor(tr.hitRate),
      delta: { text: `geçen hafta %${pct(tr.hitRate + PREV.modelDelta)} → %${pct(tr.hitRate)} ▲`, good: true },
    },
    {
      key: "conf", label: "Kadro Güveni", value: `%${xi.confidence}`,
      sub: `${xi.formation} · ${rested.length} dinlendir`, color: xi.confidence >= 80 ? "var(--low)" : "var(--mid)",
      delta: { text: `geçen hafta %${xi.confidence + PREV.confDelta} → %${xi.confidence} ▼`, good: false },
    },
    {
      key: "rested", label: "Dinlendirilecek", value: `${rested.length}`,
      sub: rested.length ? rested.map((a) => lastName(a.player.player_name)).join(", ") : "yok",
      color: rested.length ? "var(--high)" : "var(--low)",
      delta: { text: `geçen hafta ${rested.length + PREV.restedDelta} → ${rested.length} ▲`, good: false },
    },
  ];

  // ── Kararlar (duruma göre) ──
  const decisions: CommandDecision[] = [];
  if (state === "live") {
    if (top) decisions.push({
      id: "live-sub", priority: 95, category: "Sakatlık", severity: "kritik",
      title: `${top.player.player_name} (${top.player.shirt}) sahada — risk ${top.risk.score}/100, kondisyon ${top.player.condition}`,
      action: `Şimdi değiştir → en uygun taze oyuncu. Tekrar-sakatlanma riski yüksek.`, href: "/matches/demo/live",
    });
    decisions.push({
      id: "live-setpiece", priority: 84, category: "Savunma", severity: "yüksek",
      title: `Far-post duran top zaafı — 1. yarı golü buradan geldi`,
      action: `Markajı zonal'dan adam-adamaya çevir; ${def.markers[0]?.player ?? "en iyi hava topçu"} far-post'u tutsun.`, href: "/teams/100/set-piece-routine",
    });
    if (momentum <= -10) decisions.push({
      id: "live-momentum", priority: 72, category: "Maç", severity: "yüksek",
      title: `Momentum rakipte (${momentum}) — kontrol kayboluyor`,
      action: `Bloğu topla, ikinci topları al; 75. dakikadan sonra riski artır.`, href: "/matches/demo/live",
    });
  } else {
    rested.slice(0, 2).forEach((a, i) => decisions.push({
      id: `rest-${a.player.shirt}`, priority: 90 - i * 3, category: "Sakatlık", severity: "kritik",
      title: `${a.player.player_name} (${a.player.shirt}) — ${VERDICT_LABEL[a.verdict]} (risk ${a.risk.score}/100)`,
      action: a.reasons[0], href: "/squad",
    }));
    decisions.push({
      id: "pre-setpiece", priority: 70, category: "Savunma", severity: "yüksek",
      title: `Far-post duran top zaafı (son ${def.matchesN} maçta ${def.concededLastN} gol)`,
      action: `Markajı adam-adamaya çevir; ${def.markers[0]?.player ?? "en iyi hava topçu"} far-post'u markala.`, href: "/teams/100/set-piece-routine",
    });
    decisions.push({
      id: "pre-lineup", priority: 60, category: "Kadro", severity: "orta",
      title: `${DEMO_OPPONENT} için önerilen ${xi.formation} hazır (güven %${xi.confidence})`,
      action: `Kadroyu onayla; riskli oyuncuların yerine en yüksek skorlu uygunlar yerleşti.`, href: "/squad",
    });
  }
  decisions.sort((a, b) => SEV_RANK[b.severity] - SEV_RANK[a.severity] || b.priority - a.priority);

  // ── #1 Yönetici brifingi (duruma göre) ──
  const brief: string[] = [];
  if (win) {
    brief.push(
      `${sim.homeTeam} – ${sim.awayTeam} ${win.minute}' · ${win.scoreHome}-${win.scoreAway}. Model ${win.pDraw >= win.pHome ? `beraberliği %${pct(win.pDraw)}` : `galibiyeti %${pct(win.pHome)}`} görüyor (maç-öncesi %${pct(sim.probHomeWin)} favoriydik); kazanmak için baskı şart.`);
    if (top) brief.push(`En acil karar: ${top.player.player_name} sahada (risk ${top.risk.score}/100, kondisyon ${top.player.condition}) — şimdi değiştir.`);
    brief.push(`Far-post savunma zaafını adam-adamaya çevir (1. yarı golü oradan). Model bu sezon %${pct(tr.hitRate)} isabetli.`);
  } else {
    brief.push(`${sim.homeTeam}, ${DEMO_OPPONENT}'a %${pct(sim.probHomeWin)} favori (en olası ${sim.mostLikelyScore[0]}-${sim.mostLikelyScore[1]}).`);
    if (top) brief.push(`En büyük risk ${top.player.player_name} (${top.risk.score}/100, ${LEVEL_LABEL[top.risk.level]}) — ${rested.length ? "dinlendirin" : "izleyin"}.`);
    brief.push(`Kadro reçetesi hazır (${xi.formation}, güven %${xi.confidence}). Model bu sezon %${pct(tr.hitRate)} isabetli (son ${tr.streak} tahmin tuttu).`);
  }

  return { state, kpis, decisions, brief };
}
