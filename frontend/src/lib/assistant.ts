/**
 * AI Asistan yönlendirme motoru — doğal-dil soruyu MOTORLARA bağlar.
 *
 * Demo'da canlı LLM yok; bunun yerine deterministik niyet-yönlendirme + varlık
 * çıkarımı yapar: soruyu sınıflar (risk/kadro/maç/track-record/haftalık/yük),
 * oyuncu/rakip adını çıkarır, İLGİLİ MOTORU çağırır ve CANLI hesaplanan veriden
 * cevap derler. Çağrılan motorların adı `tools` olarak döner (UI "çağrıldı" izi).
 *
 * Hazır metin değil — gerçek çıktı. Eşleşme yoksa çağıran taraf demoChatQA'ya düşer.
 */

import { demoSquad, type SquadPlayer } from "@/lib/demo-data";
import { DEMO_TEAM_ROWS } from "@/lib/demo-teams";
import { computeRiskFor, squadRiskRanked, LEVEL_LABEL, TREND_LABEL } from "@/lib/injury-risk";
import {
  recommendedXI, squadAvailability, availabilityOf, VERDICT_LABEL, type Availability,
} from "@/lib/lineup-advice";
import { demoNextMatchSimulation, simulateMatch, type MatchSimulation } from "@/lib/match-simulation";
import { demoTrackRecord, TYPE_LABEL } from "@/lib/track-record";
import { weeklyInsights } from "@/lib/weekly-insights";
import { computeDevelopmentFor, PHASE_LABEL } from "@/lib/player-development";

export interface AssistantContext {
  lastPlayerShirt?: number;   // son bahsedilen oyuncu (takip soruları için)
  lastOpponentId?: number;    // son bahsedilen rakip
}

export interface AssistantReply {
  text: string;
  tools: string[];
  matched: boolean;   // motor eşleşti mi (false → çağıran demoChatQA'ya düşer)
  context?: AssistantContext;  // bir sonraki tur için güncellenmiş bağlam
}

const norm = (s: string) => s.toLocaleLowerCase("tr");
const pct = (x: number) => `%${Math.round(x * 100)}`;

// ── Varlık çıkarımı ──────────────────────────────────────────────────────────
function findPlayer(q: string): SquadPlayer | null {
  const n = norm(q);
  let best: SquadPlayer | null = null;
  let bestLen = 0;
  for (const p of demoSquad) {
    for (const tok of norm(p.player_name).split(/\s+/)) {
      if (tok.length >= 4 && n.includes(tok) && tok.length > bestLen) {
        best = p; bestLen = tok.length;
      }
    }
  }
  return best;
}

/** Soruda geçen TÜM kadro oyuncuları (karşılaştırma için), uzun token önce. */
function findPlayers(q: string): SquadPlayer[] {
  const n = norm(q);
  const hits: { p: SquadPlayer; len: number }[] = [];
  for (const p of demoSquad) {
    let len = 0;
    for (const tok of norm(p.player_name).split(/\s+/)) {
      if (tok.length >= 4 && n.includes(tok)) len = Math.max(len, tok.length);
    }
    if (len) hits.push({ p, len });
  }
  return hits.sort((a, b) => b.len - a.len).map((h) => h.p);
}

function findOpponent(q: string): { id: number; name: string } | null {
  const n = norm(q);
  for (const t of DEMO_TEAM_ROWS) {
    if (t.teamId === 100) continue; // biz (Beşiktaş)
    if (n.includes(norm(t.name)) || n.includes(norm(t.short))) return { id: t.teamId, name: t.name };
  }
  return null;
}

const has = (q: string, words: string[]) => { const n = norm(q); return words.some((w) => n.includes(w)); };

// ── Cevap derleyiciler ───────────────────────────────────────────────────────

function playerRiskAnswer(p: SquadPlayer): AssistantReply {
  const r = computeRiskFor(p.player_id);
  const lines = [
    `${p.player_name} (${p.shirt}) sakatlık risk endeksi ${r.score}/100 — ${LEVEL_LABEL[r.level]} (trend ${TREND_LABEL[r.trend]}).`,
    r.topDriver ? `En büyük sürücü: ${r.topDriver.label} — ${r.topDriver.detail}.` : "",
    `Öneri: ${r.recommendation}`,
    r.horizonNote,
  ].filter(Boolean);
  return { text: lines.join("\n"), tools: ["injury_risk_index", "load_risk_monitor"], matched: true };
}

function topRiskAnswer(): AssistantReply {
  const top = squadRiskRanked().slice(0, 4);
  const lines = top.map((row, i) =>
    `${i + 1}. ${row.player.player_name} (${row.player.shirt}) — ${row.risk.score}/100 ${LEVEL_LABEL[row.risk.level]}` +
    (row.risk.topDriver ? ` · ${row.risk.topDriver.label}` : ""));
  const text = `Bu hafta en yüksek sakatlık riski taşıyan oyuncular:\n${lines.join("\n")}\n\nEn kritik isim ${top[0].player.player_name}: ${computeRiskFor(top[0].player.player_id).recommendation}`;
  return { text, tools: ["injury_risk_index", "squad_availability"], matched: true };
}

function lineupAnswer(q: string): AssistantReply {
  const opp = findOpponent(q);
  const player = findPlayer(q);
  if (player) {
    const a = availabilityOf(player);
    // Yerine en uygun oyuncu (aynı mevki, dinlendirilmeyen, en yüksek seçilebilirlik).
    const repl = squadAvailability()
      .filter((x) => x.player.pos_detail === player.pos_detail && x.player.player_id !== player.player_id && x.verdict !== "dinlendir")
      .sort((x, y) => y.selectionScore - x.selectionScore)[0];
    const text = [
      `${player.player_name} (${player.shirt}) için maç reçetesi: ${VERDICT_LABEL[a.verdict]}` +
      (a.minutesCap ? ` (~${a.minutesCap} dk)` : "") + `.`,
      a.reasons.join(" "),
      a.deloadPct > 0 ? `Bu hafta antrenman yükünü %${a.deloadPct} azaltmanı öneriyorum.` : "Bu hafta tam antrenman yüküne uygun.",
      repl ? `Yerine en uygun aday: ${repl.player.player_name} (${repl.player.shirt}) — aynı mevki, en yüksek seçilebilirlik.` : "",
    ].filter(Boolean).join("\n");
    return { text, tools: ["lineup_advice", "injury_risk_index", "squad_availability"], matched: true };
  }
  const avail = squadAvailability();
  const xi = recommendedXI(opp?.name, avail);
  const starters = xi.picks.filter((s) => s.pick).map((s) => `${s.label}: ${s.pick!.player.player_name.split(" ").slice(-1)[0]} (${s.pick!.player.shirt})`);
  const rested = avail.filter((a) => a.verdict === "dinlendir").map((a) => a.player.player_name);
  const text = [
    `${opp?.name ?? "sıradaki maç"} için önerilen ${xi.formation} (güven %${xi.confidence}):`,
    starters.join(" · "),
    rested.length ? `\nDinlendirilmeli: ${rested.join(", ")} — riski yüzünden.` : "\nRiskli oyuncu yok; en güçlü 11 hazır.",
    xi.gaps.length ? `Dikkat: ${xi.gaps.join("; ")}.` : "",
  ].filter(Boolean).join("\n");
  return { text, tools: ["lineup_advice", "squad_availability"], matched: true };
}

function matchAnswer(q: string): AssistantReply {
  const opp = findOpponent(q);
  const sim: MatchSimulation = opp ? (simulateMatch(100, opp.id) ?? demoNextMatchSimulation()) : demoNextMatchSimulation();
  const edge = sim.probHomeWin >= 0.5
    ? `${sim.homeTeam} favori; ev avantajı ve xG üstünlüğü lehimize.`
    : `Çekişmeli — net favori yok, ${sim.probDraw >= sim.probAwayWin ? "beraberlik" : "deplasman riski"} ihtimali yüksek.`;
  const text = [
    `${sim.homeTeam} – ${sim.awayTeam} simülasyonu (Poisson · Dixon-Coles):`,
    `Galibiyet ${pct(sim.probHomeWin)} · Beraberlik ${pct(sim.probDraw)} · Mağlubiyet ${pct(sim.probAwayWin)}.`,
    `En olası skor ${sim.mostLikelyScore[0]}-${sim.mostLikelyScore[1]} (${pct(sim.mostLikelyScoreProb)}) · beklenen gol ${sim.lambdaHome.toFixed(1)}–${sim.lambdaAway.toFixed(1)}.`,
    `Üst 2.5 ${pct(sim.over25)} · KG var ${pct(sim.bttsYes)} · ${sim.homeTeam} gol yemez ${pct(sim.homeCleanSheet)}.`,
    edge,
  ].join("\n");
  return { text, tools: ["match_simulation", "xg_model"], matched: true };
}

function trackAnswer(): AssistantReply {
  const tr = demoTrackRecord();
  const byType = tr.byType.map((t) => `${TYPE_LABEL[t.type]} ${pct(t.hitRate)}`).join(" · ");
  const text = [
    `Model track record: ${tr.resolved} değerlendirmede genel isabet ${pct(tr.hitRate)} (Brier ${tr.brier ?? "—"}).`,
    `Son seri ${tr.streak}✓ · açık tahmin ${tr.open}.`,
    `Tür bazında: ${byType}.`,
    `Tüm tahminler kayıt altında ve sonuçla karşılaştırılıyor — Kalibrasyon sayfasında makbuzlar görülebilir.`,
  ].join("\n");
  return { text, tools: ["track_record", "calibration"], matched: true };
}

function weeklyAnswer(): AssistantReply {
  const w = weeklyInsights();
  const lines = w.insights.slice(0, 4).map((ins) => `• [${ins.category}] ${ins.title}${ins.metric ? ` (${ins.metric})` : ""}`);
  return { text: `${w.headline}\n\nBu haftanın öncelikleri:\n${lines.join("\n")}`, tools: ["weekly_insights"], matched: true };
}

function loadAnswer(q: string): AssistantReply {
  const player = findPlayer(q);
  if (player) {
    const a = availabilityOf(player);
    const text = a.deloadPct > 0
      ? `${player.player_name} (${player.shirt}) için bu hafta antrenman yükünü %${a.deloadPct} azaltmanı öneriyorum. ${a.reasons[0]}`
      : `${player.player_name} (${player.shirt}) yük profili iyi — bu hafta tam antrenmana uygun (risk ${a.risk.score}/100).`;
    return { text, tools: ["load_monitor", "acwr_band"], matched: true };
  }
  const deload = squadAvailability().filter((a) => a.deloadPct >= 25).sort((x, y) => y.deloadPct - x.deloadPct);
  if (!deload.length) return { text: "Bu hafta belirgin yük azaltma gerektiren oyuncu yok; kadro yük dağılımı dengeli.", tools: ["load_monitor"], matched: true };
  const lines = deload.map((a) => `${a.player.player_name} (${a.player.shirt}) −%${a.deloadPct}`);
  return { text: `Bu hafta antrenman yükü azaltılması önerilen oyuncular:\n${lines.join("\n")}`, tools: ["load_monitor", "acwr_band"], matched: true };
}

const ln = (p: SquadPlayer) => p.player_name.split(" ").slice(-1)[0];

function developmentAnswer(player: SquadPlayer): AssistantReply {
  const d = computeDevelopmentFor(player.player_id);
  if (!d) return { text: "", tools: [], matched: false };
  const gap = Math.round((d.potential - d.currentOverall) * 10) / 10;
  const text = [
    `${player.player_name} (${player.shirt}) gelişim projeksiyonu: ${PHASE_LABEL[d.phase]} fazı, ${d.currentAge} yaş.`,
    `Mevcut seviye ${d.currentOverall.toFixed(1)}/20 → tavan ${d.potential.toFixed(1)} (zirve ${d.peakAge} yaş)${gap > 0.1 ? `, ${gap.toFixed(1)} puan büyüme alanı` : ""}.`,
    d.verdict,
  ].join("\n");
  return { text, tools: ["player_development"], matched: true };
}

function compareAnswer(q: string): AssistantReply {
  const ps = findPlayers(q);
  if (ps.length < 2) return ps[0] ? playerRiskAnswer(ps[0]) : { text: "", tools: [], matched: false };
  const [a, b] = ps;
  const ra = computeRiskFor(a.player_id), rb = computeRiskFor(b.player_id);
  const aa = availabilityOf(a), ab = availabilityOf(b);
  const da = computeDevelopmentFor(a.player_id), db = computeDevelopmentFor(b.player_id);
  const riskier = ra.score >= rb.score ? a : b;
  const prefer = aa.selectionScore >= ab.selectionScore ? a : b;
  const lines = [
    `${a.player_name} (${a.shirt}) vs ${b.player_name} (${b.shirt}):`,
    `Sakatlık riski: ${ln(a)} ${ra.score}/100 (${LEVEL_LABEL[ra.level]}) — ${ln(b)} ${rb.score}/100 (${LEVEL_LABEL[rb.level]}). Daha riskli: ${ln(riskier)}.`,
    `Maç uygunluğu: ${ln(a)} ${VERDICT_LABEL[aa.verdict]} — ${ln(b)} ${VERDICT_LABEL[ab.verdict]}.`,
    da && db ? `Gelişim: ${ln(a)} ${PHASE_LABEL[da.phase]} (tavan ${da.potential.toFixed(1)}) — ${ln(b)} ${PHASE_LABEL[db.phase]} (tavan ${db.potential.toFixed(1)}).` : "",
    `Bu maç için önerim: ${ln(prefer)} — risk + kondisyon + kalite birleşik seçilebilirliği daha yüksek.`,
  ].filter(Boolean);
  return { text: lines.join("\n"), tools: ["injury_risk_index", "lineup_advice", "player_development"], matched: true };
}

function topPlayersAnswer(q: string): AssistantReply {
  if (has(q, ["potansiyel", "gelişen", "gelecek vaad", "genç yeten", "yükselen"])) {
    const ranked = demoSquad
      .map((p) => ({ p, d: computeDevelopmentFor(p.player_id)! }))
      .filter((x) => x.d)
      .map((x) => ({ ...x, gap: x.d.potential - x.d.currentOverall }))
      .sort((a, b) => b.gap - a.gap).slice(0, 4);
    const lines = ranked.map((x, i) =>
      `${i + 1}. ${x.p.player_name} (${x.p.shirt}) — ${x.p.age} yaş, ${x.d.currentOverall.toFixed(1)}→${x.d.potential.toFixed(1)} (${PHASE_LABEL[x.d.phase]})`);
    return { text: `En yüksek gelişim potansiyeli olan oyuncular:\n${lines.join("\n")}`, tools: ["player_development"], matched: true };
  }
  const ranked = [...demoSquad].sort((a, b) => b.condition - a.condition).slice(0, 4);
  const lines = ranked.map((p, i) => `${i + 1}. ${p.player_name} (${p.shirt}) — kondisyon ${p.condition}, ${p.risk_label.toLocaleLowerCase("tr")} risk`);
  return { text: `En formda / en taze oyuncular:\n${lines.join("\n")}`, tools: ["squad_availability", "load_monitor"], matched: true };
}

// ── Niyet skorlama + yönlendirme ─────────────────────────────────────────────
interface Intent { id: string; score: (q: string) => number; answer: (q: string) => AssistantReply }

const INTENTS: Intent[] = [
  {
    id: "compare",
    score: (q) => (findPlayers(q).length >= 2 ? 4 : 0),
    answer: compareAnswer,
  },
  {
    id: "development",
    score: (q) => (has(q, ["gelişim", "potansiyel", "gelecek", "kariyer", "tavan", "ne olur", "zirve", "gelişir mi"]) ? 2 : 0)
      + (findPlayer(q) ? 1 : 0),
    answer: (q) => { const p = findPlayer(q); return p ? developmentAnswer(p) : topPlayersAnswer(q); },
  },
  {
    id: "top",
    score: (q) => has(q, ["en formda", "en taze", "en yüksek potansiyel", "en gelişen", "kimler formda", "en iyi kondisyon", "gelecek vaad", "en yükselen"]) ? 3 : 0,
    answer: topPlayersAnswer,
  },
  {
    id: "lineup",
    score: (q) => (has(q, ["dinlendir", "rotasyon", "kimi oynat", "kadro öner", "11 öner", "diz", "ilk 11", "kimi dinlen", "kim oynas", "kim başlas", "değiştir", "yerine kim", "kimle değiş"]) ? 3 : 0)
      + (has(q, ["kadro", "diziliş", "formasyon"]) ? 1 : 0),
    answer: lineupAnswer,
  },
  {
    id: "risk",
    score: (q) => (has(q, ["risk", "sakat", "sakatlık", "sakatlanma"]) ? 2 : 0)
      + (findPlayer(q) ? 1 : 0) + (has(q, ["en riskli", "kim riskl"]) ? 1 : 0),
    answer: (q) => { const p = findPlayer(q); return p ? playerRiskAnswer(p) : topRiskAnswer(); },
  },
  {
    id: "track",
    score: (q) => has(q, ["isabet", "doğruluk", "ne kadar tut", "track record", "kalibrasyon", "model ne kadar", "güvenilir", "tutuyor mu"]) ? 3 : 0,
    answer: trackAnswer,
  },
  {
    id: "weekly",
    score: (q) => has(q, ["bu hafta", "öncelik", "özet", "neler önemli", "digest", "gündem", "haftalık"]) ? 2 : 0,
    answer: weeklyAnswer,
  },
  {
    id: "load",
    score: (q) => has(q, ["yük", "antrenman yük", "acwr", "deload", "yüklen", "kondisyon yönet"]) ? 2 : 0,
    answer: loadAnswer,
  },
  {
    id: "match",
    score: (q) => (has(q, ["maç", "kazan", "galibiyet", "skor", "tahmin", "olasılık", "sonuç ne", "yener", "yenebilir"]) ? 2 : 0)
      + (findOpponent(q) ? 2 : 0),
    answer: matchAnswer,
  },
];

// Eksik-özne takip işaretçisi (zamir) — liste işaretini EZER.
const FOLLOWUP_RE = /(\bonu\b|\bona\b|\bonun\b|kendisi|aynı oyuncu|bu oyuncu|şu oyuncu|peki ya|o oyuncu)/;
// Liste/çoğul sorusu — varsa soru kadroya bakar ("en formda oyuncular kim?"); enjeksiyon yok.
const LIST_RE = /(\bkim|kimler|kimi|\ben |oyuncular|hangi oyuncu|listele|herkes|kadro)/;
// Karşılaştırma işaretçisi — tek oyuncu + bağlam oyuncusu → ikisini kıyasla.
const CMP_RE = /(karşılaştır|kıyas| ile |vs|hangisi|ikisinden)/;

/** Soruyu motorlara yönlendir; en yüksek skorlu niyet cevaplar. ctx ile takip
 *  soruları (eksik-özne → son oyuncu) çözülür; dönen context bir sonraki tura taşınır. */
export function answerQuestion(msg: string, ctx?: AssistantContext): AssistantReply {
  let q = msg;
  const n = norm(msg);
  const explicit = findPlayers(msg);
  const lp = ctx?.lastPlayerShirt ? demoSquad.find((p) => p.shirt === ctx.lastPlayerShirt) : null;
  if (lp) {
    if (explicit.length === 0 && (FOLLOWUP_RE.test(n) || !LIST_RE.test(n))) {
      // Eksik-özne takip → son oyuncuyu enjekte ("ya gelecekte nasıl?", "peki onu değiştir").
      q = `${msg} ${lp.player_name}`;
    } else if (explicit.length === 1 && CMP_RE.test(n) && explicit[0].player_id !== lp.player_id) {
      // Karşılaştırma takibi → bağlam oyuncusunu ikinci taraf yap ("Rıdvan ile karşılaştır").
      q = `${msg} ${lp.player_name}`;
    }
  }
  // Rakip de aynı şekilde taşınır (maç/karşılaştırma takipleri).
  if (!findOpponent(q) && ctx?.lastOpponentId && /(onlar|rakip|aynı takım|o takım)/.test(norm(msg))) {
    const t = DEMO_TEAM_ROWS.find((r) => r.teamId === ctx.lastOpponentId);
    if (t) q = `${q} ${t.name}`;
  }

  let bestScore = 0;
  let best: Intent | null = null;
  for (const it of INTENTS) {
    const s = it.score(q);
    if (s > bestScore) { bestScore = s; best = it; }
  }

  // Çözülen varlıkları bir sonraki tur için sakla (eşleşme olmasa bile koru).
  const resolvedPlayer = findPlayer(q);
  const resolvedOpp = findOpponent(q);
  const nextCtx: AssistantContext = {
    lastPlayerShirt: resolvedPlayer?.shirt ?? ctx?.lastPlayerShirt,
    lastOpponentId: resolvedOpp?.id ?? ctx?.lastOpponentId,
  };

  if (!best || bestScore < 2) return { text: "", tools: [], matched: false, context: nextCtx };
  return { ...best.answer(q), context: nextCtx };
}
