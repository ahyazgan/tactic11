/**
 * Devre Arası Asistanı — İLK YARI verisinden 2. yarı hamle reçetesi.
 *
 * demoLive'ın yalnız ≤45' kesitinden (event/xG/momentum/saha-içi kadro) + birleşik
 * sakatlık risk endeksinden (lib/injury-risk) + kadro uygunluğundan (lib/lineup-advice)
 * CANLI türetir: önleyici/zorunlu değişiklik önerileri (kondisyon + risk + sarı kart),
 * öncelikli taktik hamleler (momentum + rakip zaafı + eşleşme + duran top zaafı) ve
 * otomatik brief. Sabit metin değil — ilk yarıda OLANDAN hesaplanır.
 *
 * Önemli: sakatlık event'i (Orkun 52') 2. yarıda; devre arasında YOK. Bu yüzden
 * Orkun önerisi "reaktif sakatlık" değil, kondisyon+risk endeksinden ÖNLEYİCİ çıkar.
 */

import {
  demoLive, demoWeaknesses, demoMatchups, demoSquad, type SquadPlayer,
} from "@/lib/demo-data";
import { computeRiskFor, LEVEL_LABEL } from "@/lib/injury-risk";
import { squadAvailability, type Availability } from "@/lib/lineup-advice";

const HT = 45;
const norm = (s: string) => s.toLocaleLowerCase("tr");

export interface FirstHalfSummary {
  score: [number, number];
  homeXg: number;
  awayXg: number;
  shotsHome: number;
  shotsAway: number;
  momentum: number;        // 45' anı momentumu (+ bize)
  goals: number;
  bigChances: number;
  concededSetPiece: boolean;
}

/** İlk yarı (≤45') özetini event/xG serisinden çıkar. */
export function firstHalfSummary(): FirstHalfSummary {
  const ev = demoLive.events.filter((e) => e.minute <= HT);
  const fhSeries = demoLive.series.filter((p) => p.minute <= HT);
  const last = fhSeries[fhSeries.length - 1];
  const goalsHome = ev.filter((e) => e.type === "gol" && e.team === "home").length;
  const goalsAway = ev.filter((e) => e.type === "gol" && e.team === "away").length;
  // İlk yarıda yenilen gol duran toptan mı (köşe/far-post/korner)?
  const concededSetPiece = ev.some((e) =>
    e.type === "gol" && e.team === "away"
    && /köşe|korner|far-post|duran/.test(norm(e.text)));
  return {
    score: [goalsHome, goalsAway],
    homeXg: last.home, awayXg: last.away,
    shotsHome: 8, shotsAway: 6,            // demo şut sayısı (event akışıyla tutarlı)
    momentum: last.momentum,
    goals: goalsHome + goalsAway,
    bigChances: ev.filter((e) => e.type === "buyuk_firsat").length,
    concededSetPiece,
  };
}

// ── Saha-içi kadro (45' anı) ────────────────────────────────────────────────
function onPitchAt45(): { shirt: number; name: string }[] {
  return demoLive.lineup
    .filter((p) =>
      (p.subbedInMinute == null || p.subbedInMinute <= HT)
      && (p.subbedOutMinute == null || p.subbedOutMinute > HT))
    .map((p) => ({ shirt: p.shirt, name: p.name }));
}

// İlk yarı sarı kart gören oyuncuların forma no'su (event metninden ad eşleştir).
function firstHalfYellowShirts(): Set<number> {
  const out = new Set<number>();
  for (const e of demoLive.events) {
    if (e.minute > HT || e.type !== "sari_kart") continue;
    const t = norm(e.text);
    for (const p of demoSquad) {
      if (norm(p.player_name).split(/\s+/).some((tok) => tok.length >= 4 && t.includes(tok))) {
        out.add(p.shirt); break;
      }
    }
  }
  return out;
}

export type HtUrgency = "kritik" | "yüksek" | "orta";

export interface HtSub {
  out: string;             // "Orkun Kökçü (10)"
  in: string;              // "Junior Olaitan (14)"
  outShirt: number;
  urgency: HtUrgency;
  score: number;           // 0..1 aciliyet
  reasons: string[];
}

const SHIRT_TO_SQUAD = new Map(demoSquad.map((p) => [p.shirt, p]));

/** 45' değişiklik önerileri — saha-içi starter'lar için kondisyon+risk+kart füzyonu. */
export function halftimeSubs(avail: Availability[] = squadAvailability()): HtSub[] {
  const onPitch = onPitchAt45();
  const onPitchShirts = new Set(onPitch.map((p) => p.shirt));
  const yellow = firstHalfYellowShirts();
  const availByPos = (posDetail: string, excludeShirts: Set<number>) =>
    avail
      .filter((a) => a.player.pos_detail === posDetail && !excludeShirts.has(a.player.shirt) && a.verdict !== "dinlendir")
      .sort((x, y) => y.selectionScore - x.selectionScore)[0] ?? null;

  const subs: HtSub[] = [];
  for (const op of onPitch) {
    const p: SquadPlayer | undefined = SHIRT_TO_SQUAD.get(op.shirt);
    if (!p) continue;
    const risk = computeRiskFor(p.player_id);
    let score = 0;
    const reasons: string[] = [];

    if (p.condition < 60) { score += 0.4; reasons.push(`Kondisyon ${p.condition} kritik eşikte — 2. yarı sakatlık riski`); }
    else if (p.condition < 70) { score += 0.24; reasons.push(`Kondisyon ${p.condition} — yorgunluk bandında`); }

    if (risk.level === "crit") { score += 0.34; reasons.push(`Sakatlık risk endeksi ${risk.score}/100 (${LEVEL_LABEL[risk.level]})`); }
    else if (risk.level === "high") { score += 0.2; reasons.push(`Sakatlık risk endeksi ${risk.score}/100 (${LEVEL_LABEL[risk.level]})`); }

    if (yellow.has(p.shirt)) { score += 0.26; reasons.push("1. yarı sarı kart — ikinci sarı/kırmızı riski"); }

    if (score < 0.25) continue;  // önerilecek kadar aciliyet yok

    if (risk.topDriver && risk.level !== "low") reasons.push(risk.topDriver.detail);

    const replacement = availByPos(p.pos_detail, onPitchShirts);
    const urgency: HtUrgency = score >= 0.6 ? "kritik" : score >= 0.4 ? "yüksek" : "orta";
    subs.push({
      out: `${p.player_name} (${p.shirt})`,
      in: replacement ? `${replacement.player.player_name} (${replacement.player.shirt})` : "uygun yedek yok",
      outShirt: p.shirt,
      urgency, score: Math.round(score * 100) / 100,
      reasons,
    });
  }
  return subs.sort((a, b) => b.score - a.score).slice(0, 3);
}

export type HtMoveKind = "sub" | "attack" | "defense" | "tempo";

export interface HtMove {
  id: string;
  kind: HtMoveKind;
  urgency: HtUrgency;
  priority: number;
  title: string;
  detail: string;
}

const URG_RANK: Record<HtUrgency, number> = { kritik: 3, yüksek: 2, orta: 1 };

/** 2. yarı öncelikli hamleler — değişiklik + taktik + savunma, tek sıralı liste. */
export function halftimeMoves(subs: HtSub[] = halftimeSubs()): HtMove[] {
  const fh = firstHalfSummary();
  const moves: HtMove[] = [];

  // En acil değişiklik(ler) → hamle.
  for (const s of subs) {
    moves.push({
      id: `sub-${s.outShirt}`, kind: "sub", urgency: s.urgency,
      priority: 60 + URG_RANK[s.urgency] * 12 + Math.round(s.score * 10),
      title: `Değişiklik: ${s.out} → ${s.in}`,
      detail: s.reasons.slice(0, 2).join(" · "),
    });
  }

  // Rakip duran top zaafımız (gol yedikse) → savunma düzeltmesi.
  if (fh.concededSetPiece) {
    moves.push({
      id: "def-setpiece", kind: "defense", urgency: "yüksek", priority: 84,
      title: "Duran top savunmasını zonal'dan adam-adamaya çevir (far-post)",
      detail: "Beraberlik golü far-post köşesinden geldi; ikinci direk örtülmüyor — 2. yarı adam-adama markaj.",
    });
  }

  // Sömürülecek eşleşme (en yüksek avantaj) → hücum hamlesi.
  const mu = [...demoMatchups].sort((a, b) => b.advantage - a.advantage)[0];
  if (mu) {
    moves.push({
      id: "atk-matchup", kind: "attack", urgency: mu.advantage >= 65 ? "yüksek" : "orta",
      priority: 55 + Math.round(mu.advantage / 4),
      title: `${mu.ours} eşleşmesini ısrarla zorla (avantaj %${mu.advantage})`,
      detail: `${mu.note}. Hücum yükünü bu koridora kaydır.`,
    });
  }

  // Rakibin en zayıf kanalı → hücum hedefi.
  const wk = demoWeaknesses.find((w) => w.severity === "yüksek") ?? demoWeaknesses[0];
  if (wk) {
    moves.push({
      id: "atk-channel", kind: "attack", urgency: "orta", priority: 50,
      title: `Hedef: ${wk.title}`,
      detail: wk.detail,
    });
  }

  // Momentum yönü → tempo reçetesi.
  if (fh.momentum >= 10) {
    moves.push({
      id: "tempo", kind: "tempo", urgency: "orta", priority: 48,
      title: "Momentum bizde — tempoyu sürdür, pres hattını koru",
      detail: `45' momentum +${fh.momentum} lehimize; üstünlüğü golle ödüllendirmek için baskıyı bırakma.`,
    });
  } else if (fh.momentum <= -10) {
    moves.push({
      id: "tempo", kind: "tempo", urgency: "yüksek", priority: 58,
      title: "Momentum rakipte — bloğu topla, kontrolü geri al",
      detail: `45' momentum ${fh.momentum}; orta blokta dengeyi yeniden kur, ikinci topları topla.`,
    });
  }

  return moves.sort((a, b) => b.priority - a.priority);
}

export interface HalftimeBrief {
  summary: string;
  whatWorked: string;
  risk: string;
  plan: string;
}

/** Otomatik 2. yarı brief'i — ilk yarı özeti + en acil değişiklik + en iyi eşleşmeden. */
export function halftimeBrief(subs: HtSub[] = halftimeSubs()): HalftimeBrief {
  const fh = firstHalfSummary();
  const mu = [...demoMatchups].sort((a, b) => b.advantage - a.advantage)[0];
  const topSub = subs[0];
  const drawLevel = fh.score[0] === fh.score[1];
  const xgEdge = fh.homeXg - fh.awayXg;

  return {
    summary: `İlk yarı ${fh.score[0]}-${fh.score[1]} kapandı. xG ${fh.homeXg.toFixed(2)}–${fh.awayXg.toFixed(2)} (fark ${xgEdge >= 0 ? "+" : ""}${xgEdge.toFixed(2)})${xgEdge > 0.05 ? " — oyunun akışı bizdeydi" : ""}.${drawLevel && fh.concededSetPiece ? " Beraberlik golü oyundan değil, duran toptaki far-post zaafımızdan geldi." : ""}`,
    whatWorked: mu
      ? `${mu.ours} eşleşmesi net üstün (avantaj %${mu.advantage}); ${mu.note.toLocaleLowerCase("tr")}. O koridordan üretim 2. yarı da sürmeli.`
      : "İlk yarıda öne çıkan net bir eşleşme avantajı yok.",
    risk: topSub
      ? `${topSub.out} en acil müdahale (${topSub.urgency}): ${topSub.reasons[0]}.`
      : "Saha-içi acil sakatlık/yük riski yok.",
    plan: topSub
      ? `Devrede ${topSub.out} → ${topSub.in} ile tazele. ${fh.concededSetPiece ? "Duran top savunmasını adam-adamaya çevir. " : ""}${mu ? `${mu.ours.split("—")[0].trim()} 1v1'ini ısrarla zorla.` : ""}`
      : `${fh.concededSetPiece ? "Duran top savunmasını adam-adamaya çevir. " : ""}Mevcut planı koru, üstünlüğü golle ödüllendir.`,
  };
}
