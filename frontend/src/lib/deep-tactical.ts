/**
 * Saha-Üstü Derin Taktik Analiz — radar "stil"in ötesinde, GERÇEK taktik analiz.
 *
 * Rakibin savunma bloğunu SAHADA konumlandırır (11 ortalama pozisyon, formasyon +
 * blok yüksekliği + genişlikten), faz-faz spesifik metrik üretir (build-up tipi,
 * blok yüksekliği metre, PPDA, top kazanma bölgesi, koridor dağılımı), oyuncu
 * taktik rollerini ve SAYISAL kalıpları çıkarır.
 *
 * Demo'da takım DNA'sından (lib/tactical-dna) + karakterinden deterministik türetilir;
 * gerçek modda StatsBomb/tracking event verisi aynı yapıyı besler. Math.random YOK.
 */

import { demoTeamById } from "@/lib/demo-teams";
import { tacticalDna } from "@/lib/tactical-dna";

export interface PitchSpot { x: number; y: number; num: number; pos: string }  // x,y: 0-100 saha
export interface PhaseStat { label: string; value: string; bar?: number }       // bar: 0-100 opsiyonel
export interface RoleNote { num: number; role: string; note: string; threat: boolean }
export interface Tendency { text: string; stat: string }

export interface DeepTactical {
  name: string;
  formation: string;
  blockHeightM: number;        // savunma bloğu yüksekliği (metre, kendi kalesinden)
  blockShape: PitchSpot[];     // savunma anı 11 ortalama pozisyon (sahada)
  buildUp: PhaseStat[];
  attack: PhaseStat[];
  defense: PhaseStat[];
  roles: RoleNote[];
  tendencies: Tendency[];
  attackChannels: { left: number; center: number; right: number };
}

// Formasyon şablonları — x: 0 kendi kalesi → 100 rakip kale; y: 0 üst → 100 alt çizgi.
const FORMATIONS: Record<string, { num: number; pos: string; x: number; y: number }[]> = {
  "4-4-2": [
    { num: 1, pos: "GK", x: 7, y: 50 },
    { num: 2, pos: "RB", x: 24, y: 84 }, { num: 5, pos: "CB", x: 18, y: 62 }, { num: 4, pos: "CB", x: 18, y: 38 }, { num: 3, pos: "LB", x: 24, y: 16 },
    { num: 7, pos: "RM", x: 46, y: 84 }, { num: 8, pos: "CM", x: 42, y: 60 }, { num: 6, pos: "CM", x: 42, y: 40 }, { num: 11, pos: "LM", x: 46, y: 16 },
    { num: 9, pos: "ST", x: 64, y: 58 }, { num: 10, pos: "ST", x: 64, y: 42 },
  ],
  "4-3-3": [
    { num: 1, pos: "GK", x: 7, y: 50 },
    { num: 2, pos: "RB", x: 26, y: 84 }, { num: 5, pos: "CB", x: 18, y: 60 }, { num: 4, pos: "CB", x: 18, y: 40 }, { num: 3, pos: "LB", x: 26, y: 16 },
    { num: 6, pos: "DM", x: 38, y: 50 }, { num: 8, pos: "CM", x: 48, y: 64 }, { num: 10, pos: "CM", x: 48, y: 36 },
    { num: 7, pos: "RW", x: 66, y: 82 }, { num: 9, pos: "ST", x: 70, y: 50 }, { num: 11, pos: "LW", x: 66, y: 18 },
  ],
  "4-2-3-1": [
    { num: 1, pos: "GK", x: 7, y: 50 },
    { num: 2, pos: "RB", x: 26, y: 84 }, { num: 5, pos: "CB", x: 18, y: 60 }, { num: 4, pos: "CB", x: 18, y: 40 }, { num: 3, pos: "LB", x: 26, y: 16 },
    { num: 6, pos: "DM", x: 36, y: 58 }, { num: 8, pos: "DM", x: 36, y: 42 },
    { num: 7, pos: "RW", x: 58, y: 82 }, { num: 10, pos: "AM", x: 56, y: 50 }, { num: 11, pos: "LW", x: 58, y: 18 }, { num: 9, pos: "ST", x: 72, y: 50 },
  ],
  "5-3-2": [
    { num: 1, pos: "GK", x: 7, y: 50 },
    { num: 2, pos: "RWB", x: 30, y: 88 }, { num: 5, pos: "CB", x: 16, y: 66 }, { num: 4, pos: "CB", x: 14, y: 50 }, { num: 6, pos: "CB", x: 16, y: 34 }, { num: 3, pos: "LWB", x: 30, y: 12 },
    { num: 8, pos: "CM", x: 42, y: 64 }, { num: 7, pos: "CM", x: 40, y: 50 }, { num: 10, pos: "CM", x: 42, y: 36 },
    { num: 9, pos: "ST", x: 62, y: 58 }, { num: 11, pos: "ST", x: 62, y: 42 },
  ],
};

const clampN = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const r1 = (n: number) => Math.round(n * 10) / 10;

/** Rakibin saha-üstü derin taktik profili (savunma bloğu + faz metrikleri + roller). */
export function deepProfile(teamId: number): DeepTactical | null {
  const row = demoTeamById(teamId);
  if (!row) return null;
  const dna = tacticalDna(row);
  const s = dna.style;
  const tmpl = FORMATIONS[dna.formation] ?? FORMATIONS["4-4-2"];

  // Blok yüksekliği: savunma hattı 0-100 → ~26-54 metre. Düşük hat = derin blok.
  const blockHeightM = r1(26 + s.lineHeight * 0.30);
  // Kompaktlık: derin/düşük blok daha dar ve sıkışık.
  const compact = 1 - (50 - s.lineHeight) / 140;          // <1 → sıkışık
  // x kaydırma: blok ne kadar derin (savunma anı tüm takım geri çekilir).
  const xShift = (s.lineHeight - 50) * 0.22;

  const blockShape: PitchSpot[] = tmpl.map((p) => ({
    num: p.num, pos: p.pos,
    x: clampN(p.x * 0.78 + xShift, 4, 78),                // savunma anı: herkes geride
    y: clampN(50 + (p.y - 50) * (s.width / 60) * compact, 8, 92),
  }));

  // Hücum koridoru dağılımı — karakterden (direkt takımlar genelde tek kanat ağırlıklı).
  const right = clampN(34 + (s.directness - 50) * 0.3, 24, 48);
  const left = clampN(33 - (s.directness - 50) * 0.1, 22, 44);
  const center = clampN(100 - right - left, 18, 44);
  const mainCh = right >= left && right >= center ? "sağ kanat" : left >= center ? "sol kanat" : "merkez";

  const ppda = r1(clampN(16 - s.pressing * 0.11, 6, 16));
  const ownHalfRecovery = Math.round(clampN(48 + (50 - s.lineHeight) * 0.55, 40, 82));
  const fromBack = Math.round(s.buildUp);
  const directPct = Math.round(clampN(s.directness * 0.9, 20, 80));

  const buildUp: PhaseStat[] = [
    { label: "Arkadan kuruluş", value: `%${fromBack}`, bar: fromBack },
    { label: "Uzun top / direkt", value: `%${directPct}`, bar: directPct },
    { label: "Ana çıkış koridoru", value: mainCh },
  ];
  const attack: PhaseStat[] = [
    { label: "Sağ koridor", value: `%${Math.round(right)}`, bar: right },
    { label: "Merkez", value: `%${Math.round(center)}`, bar: center },
    { label: "Sol koridor", value: `%${Math.round(left)}`, bar: left },
    { label: "Duran top bağımlılığı", value: `%${Math.round(s.setPiece)}`, bar: s.setPiece },
  ];
  const defense: PhaseStat[] = [
    { label: "Blok yüksekliği", value: `${blockHeightM} m`, bar: s.lineHeight },
    { label: "PPDA (pres)", value: `${ppda}`, bar: clampN((16 - ppda) * 9, 0, 100) },
    { label: "Kendi yarısında top kazanma", value: `%${ownHalfRecovery}`, bar: ownHalfRecovery },
    { label: "Pres yoğunluğu", value: s.pressing >= 62 ? "yüksek" : s.pressing >= 46 ? "orta" : "pasif", bar: s.pressing },
  ];

  // Oyuncu taktik rolleri — karakterden türetilen tipik roller (tehdit/zaaf işaretli).
  const roles: RoleNote[] = buildRoles(s);
  const tendencies: Tendency[] = buildTendencies(s, blockHeightM, ownHalfRecovery, mainCh, ppda);

  return {
    name: dna.name, formation: dna.formation, blockHeightM, blockShape,
    buildUp, attack, defense, roles, tendencies,
    attackChannels: { left: Math.round(left), center: Math.round(center), right: Math.round(right) },
  };
}

function buildRoles(s: ReturnType<typeof tacticalDna>["style"]): RoleNote[] {
  const out: RoleNote[] = [];
  if (s.directness >= 60) out.push({ num: 9, role: "Santrfor — kontra hedefi", note: "Derinlik koşuları ve sırtı dönük tutuş; geçiş anlarında ilk uzun topun adresi.", threat: true });
  if (s.lineHeight <= 44) out.push({ num: 6, role: "Ön libero — blok çapası", note: "Hat önünde sabit durur, alanı kapatır; ileriye az çıkar (geride kalır).", threat: false });
  out.push({ num: 2, role: s.width >= 55 ? "Sağ bek — yüksek/agresif" : "Sağ bek — tuck-in", note: s.width >= 55 ? "Hücumda 12. adam, arkasındaki koridor açılıyor (ZAAF)." : "İçe kapanır, kanat dar; orta sahaya destek.", threat: s.width >= 55 });
  if (s.setPiece >= 50) out.push({ num: 4, role: "Stoper — duran top hedefi", note: "Hem savunmada hem hücum duran toplarında kilit; far-post markajına dikkat.", threat: true });
  if (s.buildUp >= 58) out.push({ num: 8, role: "Derin oyun kurucu", note: "Stoperler arasına sarkıp 3'lü kuruluş yapar; presle hedefle.", threat: false });
  return out.slice(0, 4);
}

// ── Pas Ağı — topla oyun şekli + oyuncu bağlantıları ─────────────────────────

export interface NetNode { num: number; name?: string; pos: string; x: number; y: number; involvement: number }
export interface NetEdge { from: number; to: number; weight: number }
export interface PassNetwork {
  name: string;
  formation: string;
  nodes: NetNode[];
  edges: NetEdge[];
  hubNum: number;        // en çok top dokunan oyuncu (oyun kurma merkezi)
  insight: string;
}

const dist = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  Math.hypot(a.x - b.x, a.y - b.y);

/** Topla-oyun pas ağı — formasyon + stilden bağlantı ağırlıkları türetir. */
export function passNetwork(teamId: number): PassNetwork | null {
  const row = demoTeamById(teamId);
  if (!row) return null;
  const dna = tacticalDna(row);
  const s = dna.style;
  const tmpl = FORMATIONS[dna.formation] ?? FORMATIONS["4-4-2"];

  // Topla oyun: takım yukarı ve geniş yayılır (savunma bloğunun tersi).
  const sideBias = (s.directness - 50) * 0.18;   // direkt takımlar tek kanat yüklenir
  const nodes0 = tmpl.map((p) => ({
    num: p.num, pos: p.pos,
    x: clampN(p.x * 1.04 + 14, 8, 92),
    y: clampN(50 + (p.y - 50) * (0.85 + s.width / 240) + (p.x > 30 ? sideBias : 0), 8, 92),
    involvement: 0,
  }));

  // Bağlantı ağırlığı: yakınlık × stil. Build-up yüksek → arka bölge bağlantıları güçlü;
  // direkt → kısa bağlantılar zayıf (uzun topa atlar).
  const edges: NetEdge[] = [];
  for (let i = 0; i < nodes0.length; i++) {
    for (let j = i + 1; j < nodes0.length; j++) {
      const a = nodes0[i], b = nodes0[j];
      const d = dist(a, b);
      let w = Math.max(0, 1 - d / 42) * 100;
      // Aynı hat (yakın x) → komşuluk bonusu.
      if (Math.abs(a.x - b.x) < 14) w *= 1.18;
      // Arka bölge (build-up): düşük x'li çiftler build-up'çı takımda güçlenir.
      if (a.x < 40 && b.x < 40) w *= 0.7 + (s.buildUp / 100) * 0.8;
      // Direkt takım: kısa bağları zayıflat (uzun top oynar).
      if (s.directness >= 60) w *= 0.78;
      w = Math.round(w);
      if (w >= 26) {
        edges.push({ from: a.num, to: b.num, weight: w });
        a.involvement += w; b.involvement += w;
      }
    }
  }
  // Involvement 0-100 normalize.
  const maxInv = Math.max(...nodes0.map((n) => n.involvement), 1);
  const nodes: NetNode[] = nodes0.map((n) => ({ ...n, involvement: Math.round((n.involvement / maxInv) * 100) }));
  const hub = [...nodes].sort((a, b) => b.involvement - a.involvement)[0];

  // İçgörü — ağ yapısından.
  const leftLoad = nodes.filter((n) => n.y < 42).reduce((s2, n) => s2 + n.involvement, 0);
  const rightLoad = nodes.filter((n) => n.y > 58).reduce((s2, n) => s2 + n.involvement, 0);
  const side = rightLoad > leftLoad * 1.15 ? "sağ" : leftLoad > rightLoad * 1.15 ? "sol" : "dengeli";
  const insight = s.directness >= 60
    ? `Pas ağı seyrek ve dikine — kısa kombinasyon az, oyun #${hub.num} (${hub.pos}) üzerinden ${side === "dengeli" ? "hızlı dikine" : side + " koridordan"} ilerliyor; uzun toplar ağı bölüyor.`
    : `Yoğun pas ağı — oyun #${hub.num} (${hub.pos}) merkezli kuruluyor; ${side === "dengeli" ? "iki kanat dengeli" : side + " koridor daha yüklü"}. Hub'ı baskı altına al, ağı kes.`;

  return { name: dna.name, formation: dna.formation, nodes, edges, hubNum: hub.num, insight };
}

function buildTendencies(s: ReturnType<typeof tacticalDna>["style"], blockM: number, recovery: number, mainCh: string, ppda: number): Tendency[] {
  const t: Tendency[] = [];
  if (s.lineHeight <= 44) {
    t.push({ text: `Savunma bloğu kendi yarısında ortalama ${blockM}m — ligin en derinlerinden; arka boşluk yok.`, stat: `${blockM}m` });
    t.push({ text: `Topların %${recovery}'ini kendi yarısında kazanıyor (alçak blok, geç pres).`, stat: `%${recovery}` });
  } else if (s.lineHeight >= 60) {
    t.push({ text: `Yüksek savunma hattı (${blockM}m) — stoperlerin arkası açık, derinlik koşusuna zayıf.`, stat: `${blockM}m` });
  }
  if (s.directness >= 60) t.push({ text: `Kuruluşta %${Math.round(s.directness * 0.9)} direkt — kısa pastan kaçınır, uzun topu ${mainCh}taki koşuya gönderir.`, stat: "direkt" });
  else if (s.buildUp >= 58) t.push({ text: `Sabırlı arkadan kuruluş; kaleci-stoper ilk pasında YÜKSEK BAS fırsatı (PPDA ${ppda}).`, stat: `PPDA ${ppda}` });
  if (s.setPiece >= 50) t.push({ text: `Tehdidin önemli kısmı duran toptan — köşelerde far-post, serbest vuruşlarda ikinci dalga.`, stat: `%${Math.round(s.setPiece)}` });
  if (s.width >= 55) t.push({ text: `Hücum ${mainCh} ağırlıklı; bekler yüksek konumlanınca o koridor maç başına 5-6 kez açılıyor.`, stat: mainCh });
  t.push({ text: `Geç dakikalarda (75+) blok yoruluyor — pres ${ppda < 11 ? "çözülüyor" : "daha da derinleşiyor"}, taze kanat/geçiş cezalandırır.`, stat: "75+ dk" });
  return t.slice(0, 5);
}
