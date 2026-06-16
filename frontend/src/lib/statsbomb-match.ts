/**
 * GERÇEK VERİ — StatsBomb Open Data maç kütüphanesi.
 *
 * 4 ünlü maç (statsbomb-matches.json), her biri 2.4-3.4MB ham event dosyasından
 * parse edildi: ortalama pozisyonlar, pas ağı, şut haritası, savunma bloğu, faz
 * metrikleri (PPDA, blok yüksekliği, koridor, build-up direktliği). Demo türetme
 * DEĞİL — gerçek maç event'lerinden. Production'da backend ingest aynısını üretir.
 *   • 2022 DK Finali: Arjantin 3-3 Fransa
 *   • 2018 DK Finali: Fransa 4-2 Hırvatistan
 *   • Euro 2024 Finali: İspanya 2-1 İngiltere
 *   • El Clásico: Real Madrid 2-1 Barcelona
 */

import raw from "./statsbomb-matches.json";
import type {
  PassNetwork, NetNode, NetEdge, DeepTactical, PhaseStat, RoleNote, Tendency, PitchSpot,
} from "./deep-tactical";

interface RawNode { num: number; name?: string; pos: string; x: number; y: number; passes: number }
interface RawEdge { from: number; to: number; count: number }
export interface RawShot { x: number; y: number; xg: number; goal: boolean; minute: number }
export interface ProgPass { x1: number; y1: number; x2: number; y2: number; xt: number }
export interface RawPlayer {
  num: number; name: string; pos: string; touches: number;
  passC: number; passAcc: number; prog: number; xt: number;
  shots: number; xg: number; keyP: number; def: number; carries: number;
  heat?: number[][];        // 12×8 dokunuş ısısı (oyuncu)
  passes?: number[][];      // [x1,y1,x2,y2][] tamamlanan paslar (en ileri 18)
}
interface RawTeam {
  team: string; formation: number;
  lineup: { num: number; name: string; pos: string }[];
  nodes: RawNode[]; edges: RawEdge[]; shots: RawShot[];
  metrics: { passes: number; shots: number; xg: number; goals: number; possession: number };
  defShape: PitchSpot[];
  blockHeightM: number;
  ppda: number;
  channels: { left: number; center: number; right: number };
  directPct: number;
  heat: number[][];   // 12 sütun (x) × 8 satır (y) dokunuş yoğunluğu
  xt: number;         // toplam üretilen tehdit (Expected Threat)
  defHeat: number[][];      // savunma aksiyon yoğunluğu (pres bölgeleri)
  progPasses: ProgPass[];   // en tehditli ilerleme pasları (oklar)
  players: RawPlayer[];     // oyuncu-seviyesi teknik metrikler (gerçek event'lerden)
}
interface RawMatch { match: string; comp: string; matchId: number; teams: RawTeam[] }

const lib = raw as unknown as RawMatch[];

export interface MatchInfo { idx: number; match: string; comp: string; matchId: number; teams: string[] }

/** Kütüphanedeki maçlar (dropdown için). */
export function matchList(): MatchInfo[] {
  return lib.map((m, i) => ({ idx: i, match: m.match, comp: m.comp, matchId: m.matchId, teams: m.teams.map((t) => t.team) }));
}
export function matchInfo(mi: number): MatchInfo {
  const m = lib[mi];
  return { idx: mi, match: m.match, comp: m.comp, matchId: m.matchId, teams: m.teams.map((t) => t.team) };
}

const tm = (mi: number, ti: number) => lib[mi].teams[ti];
const fmt = (f: number) => String(f).split("").join("-");
/** "Lionel Andrés Messi Cuccittini" → "Messi" — saha/tablo için kısa ad. */
const surname = (name?: string): string | undefined => {
  if (!name) return undefined;
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? parts[parts.length - 1] : parts[0];
};

/** Scout Özeti — gerçek sayıları OKUYUP maçın taktik hikâyesini anlatır (içgörü). */
export function realScoutSummary(mi: number): string[] {
  const a = tm(mi, 0), b = tm(mi, 1);
  const dom = a.xt >= b.xt ? a : b;            // tehdit üreten
  const oth = dom === a ? b : a;
  const winner = a.metrics.goals > b.metrics.goals ? a : b.metrics.goals > a.metrics.goals ? b : null;
  const lines: string[] = [];

  lines.push(`${dom.team} oyuna hâkim oldu: %${dom.metrics.possession} topa sahiplik, üretilen tehdit (xT) ${dom.xt} — rakibinin (${oth.xt}) belirgin üstünde.`);

  if (winner === dom) {
    lines.push(`Ve bu üstünlüğü ${dom.metrics.goals}-${oth.metrics.goals} galibiyete çevirdi; hâkimiyet skora yansıdı.`);
  } else if (winner === oth) {
    lines.push(`AMA ${oth.team} daha klinikti ve ${oth.metrics.goals}-${dom.metrics.goals} kazandı — daha az tehditle daha çok gol (xG ${oth.metrics.xg} vs ${dom.metrics.xg}). "Domine etti ama kaybetti" maçı.`);
  } else {
    lines.push(`Ama skor ${a.metrics.goals}-${b.metrics.goals} eşit kaldı; hâkimiyet tam karşılığını bulamadı.`);
  }

  const presser = a.ppda < b.ppda ? a : b;
  const direct = a.directPct > b.directPct ? a : b;
  const deep = a.blockHeightM < b.blockHeightM ? a : b;
  lines.push(`Taktik okuma: ${presser.team} daha yüksek pres yaptı (PPDA ${presser.ppda}), ${direct.team} daha direkt oynadı (%${direct.directPct} uzun top), ${deep.team} daha derin blok kurdu (${deep.blockHeightM}m).`);

  return lines;
}

/** Gerçek pas ağı (tamamlanan paslardan) → PassNetwork bileşeni şekli. */
export function realPassNetwork(mi: number, ti: number): PassNetwork {
  const t = tm(mi, ti);
  const maxPass = Math.max(...t.nodes.map((n) => n.passes), 1);
  const maxEdge = Math.max(...t.edges.map((e) => e.count), 1);
  const nodes: NetNode[] = t.nodes.map((n) => ({ num: n.num, name: surname(n.name), pos: n.pos, x: n.x, y: n.y, involvement: Math.round((n.passes / maxPass) * 100) }));
  const edges: NetEdge[] = t.edges.map((e) => ({ from: e.from, to: e.to, weight: Math.round((e.count / maxEdge) * 100) }));
  const hub = [...nodes].sort((a, b) => b.involvement - a.involvement)[0];
  const hubName = hub.name ? `${hub.name} (#${hub.num})` : `#${hub.num}`;
  const insight = `Gerçek event verisi: ${t.metrics.passes} pas tamamlandı, oyun ${hubName} ${hub.pos} merkezli kuruldu. ${t.team} maçta %${t.metrics.possession} topa sahip oldu.`;
  return { name: t.team, formation: fmt(t.formation), nodes, edges, hubNum: hub.num, insight };
}

export interface RealTeamSummary {
  team: string; formation: string; shots: RawShot[]; metrics: RawTeam["metrics"];
  heat: number[][]; xt: number; defHeat: number[][]; progPasses: ProgPass[];
}
export function realTeam(mi: number, ti: number): RealTeamSummary {
  const t = tm(mi, ti);
  return { team: t.team, formation: fmt(t.formation), shots: t.shots, metrics: t.metrics, heat: t.heat, xt: t.xt, defHeat: t.defHeat, progPasses: t.progPasses };
}

export interface KeyPlayer extends RawPlayer {
  short: string;      // saha/tablo için kısa ad (soyad)
  impact: number;     // bileşik teknik etki skoru (0-100, takım içi göreceli)
  tag: string;        // baskın katkı etiketi (ör. "Tehdit üreten", "Oyun kurucu")
}

/** Oyuncu-seviyesi teknik analiz — gerçek event'lerden, etki sırasına göre. */
export function realPlayers(mi: number, ti: number): KeyPlayer[] {
  const t = tm(mi, ti);
  const ps = t.players || [];
  // Ham etki: xT üretimi + ilerleme + kilit pas + şut tehdidi + savunma, alan-ağırlıklı.
  const rawImpact = (p: RawPlayer) =>
    p.xt * 8 + p.prog * 1.2 + p.keyP * 2.5 + p.xg * 6 + p.carries * 0.6 + p.def * 0.25 + p.passC * 0.04;
  const max = Math.max(...ps.map(rawImpact), 1);
  const tagFor = (p: RawPlayer): string => {
    if (p.xg >= 0.4 || p.shots >= 4) return "Bitirici";
    if (p.xt >= 0.8) return "Tehdit üreten";
    if (p.keyP >= 2) return "Asist tehdidi";
    if (p.prog >= 8 || p.carries >= 8) return "İlerleten";
    if (p.passC >= 60) return "Oyun kurucu";
    if (p.def >= 12) return "Top kazanan";
    return "Dengeleyici";
  };
  return ps
    .map((p) => ({ ...p, short: surname(p.name) || p.name, impact: clamp01((rawImpact(p) / max) * 100), tag: tagFor(p) }))
    .sort((a, b) => b.impact - a.impact);
}

const clamp01 = (v: number) => Math.max(0, Math.min(100, Math.round(v)));

/** Gerçek event'lerden saha-üstü derin profil. */
export function realDeepProfile(mi: number, ti: number): DeepTactical {
  const t = tm(mi, ti);
  const hub = [...t.nodes].sort((a, b) => b.passes - a.passes)[0];
  const ch = t.channels;
  const mainCh = ch.right >= ch.left && ch.right >= ch.center ? "sağ" : ch.left >= ch.center ? "sol" : "merkez";

  const buildUp: PhaseStat[] = [
    { label: "Direkt / uzun top", value: `%${t.directPct}`, bar: t.directPct },
    { label: "Topa sahiplik", value: `%${t.metrics.possession}`, bar: t.metrics.possession },
    { label: "Tamamlanan pas", value: `${t.metrics.passes}` },
  ];
  const attack: PhaseStat[] = [
    { label: "Sol koridor", value: `%${ch.left}`, bar: ch.left },
    { label: "Merkez", value: `%${ch.center}`, bar: ch.center },
    { label: "Sağ koridor", value: `%${ch.right}`, bar: ch.right },
    { label: "Üretilen tehdit (xT)", value: `${t.xt}` },
    { label: "Toplam xG", value: `${t.metrics.xg}` },
  ];
  const defense: PhaseStat[] = [
    { label: "Blok yüksekliği", value: `${t.blockHeightM} m`, bar: clamp01((t.blockHeightM / 60) * 100) },
    { label: "PPDA (pres)", value: `${t.ppda}`, bar: clamp01((14 - t.ppda) * 8) },
    { label: "Şut", value: `${t.metrics.shots}` },
  ];
  const roles: RoleNote[] = [
    { num: hub.num, role: `Oyun kurma merkezi (${hub.passes} pas)`, note: "Topa en çok dokunan oyuncu — oyun bu noktadan kuruluyor; baskı altına alınırsa ağ kesilir.", threat: true },
  ];
  const tendencies: Tendency[] = [
    { text: `Savunma bloğu ortalama ${t.blockHeightM}m yükseklikte (gerçek savunma aksiyonlarından).`, stat: `${t.blockHeightM}m` },
    { text: `PPDA ${t.ppda} — ${t.ppda < 6 ? "agresif yüksek pres" : t.ppda < 10 ? "orta yoğunlukta pres" : "pasif/derin blok"}.`, stat: `PPDA ${t.ppda}` },
    { text: `Kuruluşta %${t.directPct} direkt/uzun top; ${t.directPct < 25 ? "arkadan sabırlı kurar" : "dikine oynamayı sever"}.`, stat: `%${t.directPct}` },
    { text: `Hücum ${mainCh} koridor ağırlıklı (sol %${ch.left} · merkez %${ch.center} · sağ %${ch.right}).`, stat: mainCh },
  ];

  return { name: t.team, formation: fmt(t.formation), blockHeightM: t.blockHeightM, blockShape: t.defShape, buildUp, attack, defense, roles, tendencies, attackChannels: ch };
}
