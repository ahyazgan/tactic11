/**
 * Taktik DNA — bir takımın NASIL oynadığını 8 eksende profilleyen motor.
 *
 * Maç-öncesi taktik hazırlığın temeli: oyun stilini (topa sahiplik / pres / oyun
 * kurma / direkt oyun / savunma hattı / kanat / tempo / duran top) karşılaştırılabilir
 * 0-100 profile çevirir + tek-satır "stil kimliği" + belirgin özellikler. Üstüne zaaf
 * haritası ve maç planı kurulur.
 *
 * Demo'da takım istatistiği (lib/demo-teams: xgf/xga/sıralama) + arketip karakterinden
 * deterministik türetilir; gerçek modda event/tracking verisinden (StatsBomb tarzı)
 * aynı eksenler beslenir. Math.random YOK.
 */

import { demoTeamById, DEMO_TEAM_ROWS, type DemoTeamRow } from "@/lib/demo-teams";

export interface StyleProfile {
  possession: number;   // topa sahiplik
  pressing: number;     // pres yoğunluğu (yüksek = agresif, düşük PPDA)
  buildUp: number;      // arkadan oyun kurma (yüksek = sabırlı/kısa pas)
  directness: number;   // dikey/direkt oyun (yüksek = uzun top/kontra)
  lineHeight: number;   // savunma hattı yüksekliği (yüksek = agresif/yüksek blok)
  width: number;        // kanat kullanımı (yüksek = geniş)
  tempo: number;        // oyun temposu
  setPiece: number;     // duran top bağımlılığı
}

export const AXES: { key: keyof StyleProfile; label: string }[] = [
  { key: "possession", label: "Topa Sahiplik" },
  { key: "pressing", label: "Pres" },
  { key: "buildUp", label: "Oyun Kurma" },
  { key: "directness", label: "Direkt Oyun" },
  { key: "lineHeight", label: "Savunma Hattı" },
  { key: "width", label: "Kanat Oyunu" },
  { key: "tempo", label: "Tempo" },
  { key: "setPiece", label: "Duran Top" },
];

export interface TacticalDNA {
  teamId: number;
  name: string;
  formation: string;
  style: StyleProfile;
  identity: string;     // "Topa sahip + yüksek pres"
  traits: string[];     // 2-3 belirgin özellik
}

// Arketip karakter ofsetleri — takımlara kimlik verir (rank/istatistik tabanının üstüne).
type Char = Partial<StyleProfile> & { formation?: string };
const ARCHETYPE: Record<number, Char> = {
  201: { possession: 12, pressing: 14, buildUp: 12, directness: -10, lineHeight: 12, formation: "4-2-3-1" },   // Galatasaray: topa sahip + yüksek pres
  100: { possession: 4, pressing: 12, width: 14, buildUp: 4, lineHeight: 6, formation: "4-3-3" },              // Beşiktaş (biz): pres + kanat
  202: { possession: 14, buildUp: 14, directness: -12, tempo: -4, formation: "4-3-3" },                        // Fenerbahçe: kontrollü topa sahip
  203: { tempo: 14, directness: 8, pressing: 6, width: 8, formation: "4-1-4-1" },                              // Trabzonspor: yüksek tempo, fiziksel
  101: { directness: 16, possession: -12, lineHeight: -14, setPiece: 16, pressing: -4, formation: "4-4-2" },   // Antalyaspor: derin blok + direkt kontra + duran top
  216: { directness: 18, possession: -18, lineHeight: -18, setPiece: 14, buildUp: -16, formation: "5-3-2" },   // Bodrum: çok derin blok
};

const clamp = (v: number) => Math.max(18, Math.min(88, Math.round(v)));
const seed = (id: number, k: number) => Math.sin(id * 1.7 + k * 3.1) * 6; // ±6 deterministik varyasyon

/** Bir takımın taktik DNA'sı — istatistik tabanı + arketip karakteri. */
export function tacticalDna(team: DemoTeamRow): TacticalDNA {
  const rank = team.rank;
  const attRate = team.xgf / team.played;   // hücum üretimi
  const defRate = team.xga / team.played;   // yenilen xG (düşük = iyi savunma)
  const topness = (18 - rank) / 17;         // 1 = lider, 0 = sonuncu
  const c = ARCHETYPE[team.teamId] ?? {};
  const ch = (k: keyof StyleProfile) => (c[k] ?? 0) + seed(team.teamId, AXES.findIndex((a) => a.key === k));

  // Taban değerler (istatistikten) + arketip + varyasyon.
  const possession = clamp(38 + topness * 34 + ch("possession"));
  const pressing = clamp(42 + topness * 26 + ch("pressing"));
  const buildUp = clamp(34 + topness * 30 + ch("buildUp"));
  const directness = clamp(70 - topness * 28 + ch("directness"));
  const lineHeight = clamp(40 + (1.3 - defRate) * 32 + topness * 10 + ch("lineHeight"));
  const width = clamp(50 + ch("width"));
  const tempo = clamp(44 + topness * 16 + ch("tempo"));
  const setPiece = clamp(36 + ch("setPiece"));

  const style: StyleProfile = { possession, pressing, buildUp, directness, lineHeight, width, tempo, setPiece };

  // Stil kimliği — en belirgin 2 ekseni cümleye çevir.
  const identity = styleIdentity(style);
  const traits = styleTraits(style);

  return { teamId: team.teamId, name: team.name, formation: c.formation ?? "4-3-3", style, identity, traits };
}

function styleIdentity(s: StyleProfile): string {
  const poss = s.possession >= 60 ? "topa sahip" : s.directness >= 62 ? "direkt/kontra" : "dengeli";
  const press = s.pressing >= 62 ? "yüksek pres" : s.lineHeight <= 40 ? "derin blok" : "orta blok";
  return `${poss.charAt(0).toUpperCase()}${poss.slice(1)} + ${press}`;
}

function styleTraits(s: StyleProfile): string[] {
  const t: { v: number; txt: string }[] = [
    { v: s.possession, txt: "Topa sahip oyun" },
    { v: s.pressing, txt: "Agresif pres" },
    { v: s.directness, txt: "Direkt/kontra tehdidi" },
    { v: s.width, txt: "Kanat ağırlıklı hücum" },
    { v: s.setPiece, txt: "Duran top tehlikesi" },
    { v: s.tempo, txt: "Yüksek tempo" },
    { v: 100 - s.lineHeight, txt: "Derin savunma bloğu" },
  ];
  return t.filter((x) => x.v >= 60).sort((a, b) => b.v - a.v).slice(0, 3).map((x) => x.txt);
}

export interface DnaContrast { axis: string; us: number; them: number; diff: number; note: string }
export interface DnaComparison {
  us: TacticalDNA;
  them: TacticalDNA;
  contrasts: DnaContrast[];   // en büyük farklar önce
  gamePlan: string[];         // bu kontrastlardan çıkan plan maddeleri
}

/** İki takımın DNA karşılaştırması + maç planı çıkarımı. */
export function compareDna(usId: number, themId: number): DnaComparison | null {
  const usRow = demoTeamById(usId), themRow = demoTeamById(themId);
  if (!usRow || !themRow) return null;
  const us = tacticalDna(usRow), them = tacticalDna(themRow);

  const contrasts: DnaContrast[] = AXES.map((a) => {
    const u = us.style[a.key], t = them.style[a.key];
    return { axis: a.label, us: u, them: t, diff: u - t, note: contrastNote(a.key, u, t) };
  }).sort((x, y) => Math.abs(y.diff) - Math.abs(x.diff));

  const gamePlan = buildGamePlan(us, them);
  return { us, them, contrasts, gamePlan };
}

function contrastNote(key: keyof StyleProfile, u: number, t: number): string {
  const d = u - t;
  const more = d > 0 ? "biz" : "rakip";
  const mag = Math.abs(d);
  if (mag < 8) return "benzer";
  const labels: Record<keyof StyleProfile, string> = {
    possession: "topa daha çok sahip", pressing: "daha agresif pres", buildUp: "daha sabırlı kuruyor",
    directness: "daha direkt oynuyor", lineHeight: "savunma hattı daha yüksek", width: "kanatları daha çok kullanıyor",
    tempo: "daha yüksek tempo", setPiece: "duran topa daha bağımlı",
  };
  return `${more === "biz" ? "Biz" : "Rakip"} ${labels[key]} (${mag} fark)`;
}

function buildGamePlan(us: TacticalDNA, them: TacticalDNA): string[] {
  const plan: string[] = [];
  // Topa sahiplik farkı → tempo/sabır.
  if (us.style.possession - them.style.possession >= 12)
    plan.push("Topa biz sahip olacağız — sabırlı kur, rakibi bloğunda yorup yanları aç; acele şut yerine üçüncü adam koşuları.");
  else if (them.style.possession - us.style.possession >= 12)
    plan.push("Rakip topa sahip olacak — kompakt orta blok kur, pres tetiğini kaleci-stoper ilk pasına ayarla, kazanınca hızlı çık.");
  // Rakip derin blok → kanat + duran top.
  if (them.style.lineHeight <= 42)
    plan.push(`Rakip derin blokta (hattı ${them.style.lineHeight}) — arka boşluk yok; ${us.style.width >= 58 ? "kanattan" : "yarı-alandan"} kombinasyon ve duran toplarla aç.`);
  else if (them.style.lineHeight >= 60)
    plan.push(`Rakip yüksek hat tutuyor (${them.style.lineHeight}) — arkaya derinlik koşuları ve hızlı dikine paslar net silah.`);
  // Rakip direkt/kontra → geçiş savunması.
  if (them.style.directness >= 60)
    plan.push("Rakip kontra tehdidi yüksek — top kaybında geçiş savunması şart; ön libero geç çıksın, stoperler dar dursun.");
  // Rakip duran top → savunma.
  if (them.style.setPiece >= 58)
    plan.push("Rakip duran topa bağımlı — kornerlerde adam-adama, far-post'u en iyi hava topçuna ver.");
  // Rakip yüksek pres → pres kırma.
  if (them.style.pressing >= 64)
    plan.push("Rakip yüksek pres yapıyor — kaleci-stoper ilk pasta uzun seçeneği açık tut, ön liberoyu pres kırmak için indir.");
  return plan.length ? plan : ["İki stil de dengeli — küçük detaylar (duran top, bireysel eşleşme) belirleyici olacak."];
}

/** Tüm demo kadrosunun DNA'sı (lig stil karşılaştırması için). */
export function allTeamsDna(): TacticalDNA[] {
  return DEMO_TEAM_ROWS.map(tacticalDna);
}

// ── Zaaf Haritası — rakibin DNA'sından TÜRETİLEN taktik zaaflar ───────────────

export type WeakSeverity = "yüksek" | "orta" | "düşük";
export interface Vulnerability {
  title: string;
  severity: WeakSeverity;
  score: number;        // 0-100 sömürülebilirlik
  reason: string;       // hangi DNA ekseninden
  exploit: string;      // nasıl sömürülür
}

const sev = (s: number): WeakSeverity => (s >= 66 ? "yüksek" : s >= 48 ? "orta" : "düşük");

/** Rakibin oyun stilinden hesaplanan zaaflar (elle yazılı değil). usWidth: bizim kanat gücümüz. */
export function weaknessMap(themId: number, usId = 100): Vulnerability[] {
  const themRow = demoTeamById(themId);
  if (!themRow) return [];
  const them = tacticalDna(themRow);
  const s = them.style;
  const us = demoTeamById(usId) ? tacticalDna(demoTeamById(usId)!) : null;
  const v: Vulnerability[] = [];

  // Derin blok → kanat overload + cut-back + ceza yayı + duran top far-post.
  if (s.lineHeight <= 44) {
    const score = 60 + (44 - s.lineHeight);
    v.push({
      title: "Kanat aşırı yüklemesi + cut-back", severity: sev(score), score,
      reason: `Savunma hattı ${s.lineHeight} — derin blok; arka boşluk yok ama yanlar zorlanıyor.`,
      exploit: `${us && us.style.width >= 58 ? "Kanat 1v1 + arka direk cut-back" : "Yarı-alan kombinasyonu"}; bloğu yana çekip penaltı noktasına geri orta.`,
    });
    v.push({
      title: "Ceza yayı / uzaktan şut alanı", severity: sev(score - 16), score: score - 16,
      reason: `Derin blok ceza sahasını doldurur ama ceza yayını boş bırakır.`,
      exploit: "İkinci dalga ve yay üstü vurucuları konumla; temizlenen toplarda ilk vuruş.",
    });
    v.push({
      title: "Far-post duran top zaafı", severity: sev(s.setPiece >= 50 ? 70 : 58), score: s.setPiece >= 50 ? 70 : 58,
      reason: "Yığınak yapan blok yakın direği zonal kapatır, far-post örtüsü zayıflar.",
      exploit: "Inswinger + gecikmeli far-post koşusu; en iyi hava topçunu arka direğe ver.",
    });
  }

  // Yüksek hat → arka boşluk + kontra.
  if (s.lineHeight >= 60) {
    const score = 64 + (s.lineHeight - 60);
    v.push({
      title: "Arka boşluk / derinlik koşusu", severity: sev(score), score,
      reason: `Savunma hattı ${s.lineHeight} — yüksek; stoperlerin arkası açık.`,
      exploit: "Hızlı santrfor + arkaya dikine paslar; ofsayt hattını zorla.",
    });
  }

  // Düşük pres → rahat oyun kurma.
  if (s.pressing <= 46) {
    const score = 54 + (46 - s.pressing);
    v.push({
      title: "Pres yok — rahat oyun kurma", severity: sev(score), score,
      reason: `Pres ${s.pressing} — düşük; sana topla zaman tanıyor.`,
      exploit: "Stoper-ön libero ile sabır; rakibi bloğunda yor, yanları aç.",
    });
  }
  // Yüksek pres → pres arkası boşluk.
  else if (s.pressing >= 66) {
    const score = 58 + (s.pressing - 66);
    v.push({
      title: "Pres arkası boşluk", severity: sev(score), score,
      reason: `Pres ${s.pressing} — yüksek ve riskli; kırılınca arkası açılır.`,
      exploit: "Kaleci-stoper ilk pasta uzun seçenek; presi kırınca hızlı dikine çık.",
    });
  }

  // Düşük topa sahiplik → saha hâkimiyeti.
  if (s.possession <= 46) {
    const score = 50 + (46 - s.possession);
    v.push({
      title: "Saha hâkimiyeti bizde olacak", severity: sev(score), score,
      reason: `Topa sahiplik ${s.possession} — topu sana bırakıyor.`,
      exploit: "Territoryi al, field tilt'i lehe çevir; ama geçiş savunmasını ihmal etme.",
    });
  }

  // Direkt/kontra → geçiş anlarında çift yönlü risk (uyarı + fırsat).
  if (s.directness >= 62) {
    v.push({
      title: "Geçiş anları — kontra riski (DİKKAT)", severity: "orta", score: 55,
      reason: `Direkt oyun ${s.directness} — yüksek; top kaybında hızlı çıkar.`,
      exploit: "Bu bir TEHDİT: top kaybında ön libero geç çıksın, stoperler dar; ama onlar çıkınca arkaları boşalır.",
    });
  }

  return v.sort((a, b) => b.score - a.score).slice(0, 5);
}

// ── Maç Planı — DNA kontrastı + zaaf haritasından TÜRETİLEN oyun planı ────────

export interface PlanScenario { state: "Öndeyiz" | "Berabere" | "Geride"; plan: string }
export interface MatchPlan {
  shape: { formation: string; rationale: string };
  principles: string[];
  pressTriggers: string[];
  scenarios: PlanScenario[];
}

/** Bizim DNA + rakip DNA + zaaflardan tam maç-öncesi plan. */
export function matchPlan(usId = 100, themId = 101): MatchPlan | null {
  const usRow = demoTeamById(usId), themRow = demoTeamById(themId);
  if (!usRow || !themRow) return null;
  const us = tacticalDna(usRow), them = tacticalDna(themRow);
  const weak = weaknessMap(themId, usId);
  const deepBlock = them.style.lineHeight <= 44;
  const highLine = them.style.lineHeight >= 60;
  const counter = them.style.directness >= 62;
  const theirPress = them.style.pressing;

  // Diziliş önerisi — rakip stiline göre bizim şeklimizi ayarla.
  let formation = us.formation;
  let rationale: string;
  if (deepBlock) {
    formation = us.style.width >= 58 ? "4-3-3 (kanat genişliği)" : "4-2-3-1 (10 numara hole'da)";
    rationale = `Rakip derin blokta — arka boşluk yok. Genişlik + yarı-alanda yaratıcı şart; bekler yüksek, kanatlar içe kat etsin, far-post için santrfor sabit.`;
  } else if (highLine) {
    formation = "4-3-3 (hızlı santrfor)";
    rationale = `Rakip yüksek hat tutuyor — arkası açık. Derinlik koşuları için hızlı santrfor + dikine pas çıkaran ön libero.`;
  } else {
    formation = us.formation;
    rationale = `Dengeli rakip — mevcut ${us.formation} şekli uygun; küçük eşleşme avantajlarını zorla.`;
  }

  // Anahtar ilkeler — en yüksek skorlu zaaflar + DNA kontrastından.
  const principles: string[] = [];
  if (us.style.possession - them.style.possession >= 12) principles.push("Topa sahip ol, sabırlı kur — rakibi bloğunda yor.");
  if (weak[0]) principles.push(`Birincil hedef: ${weak[0].title.toLowerCase()} — ${weak[0].exploit}`);
  if (counter) principles.push("Geçiş savunması kutsal — top kaybında ön libero geç çıksın, stoperler dar; kontra tehdidi yüksek.");
  if (them.style.setPiece >= 50) principles.push("Duran toplarda adam-adama; far-post'u en iyi hava topçuna ver.");
  principles.push("Tempo bizim elimizde — acele şut yerine üçüncü adam koşuları ve ikinci top.");

  // Pres tetikleri — rakibin oyun kurma stiline göre.
  const pressTriggers: string[] = [];
  if (them.style.buildUp >= 58) {
    pressTriggers.push("Kaleci → stoper ilk pasında YÜKSEK BAS; santrfor stoperi kapatsın, kanatlar bekleri.");
    pressTriggers.push("Geri pas tetiği: rakip kaleciye dönünce tüm hat 5 metre yukarı.");
  } else {
    pressTriggers.push("Orta blokta bekle (rakip direkt oynuyor) — uzun topa ikinci adamda bas, ikinci topları topla.");
    pressTriggers.push("Yan çizgi tuzağı: top kanada gidince o tarafı kapat, geri dönüşü kes.");
  }
  if (theirPress >= 64) pressTriggers.push("Rakip de yüksek pres yapıyor — ilk pasta uzun seçeneği açık tut, presi atlayınca hızlı çık.");

  // Durum senaryoları — rakip stiline uyarlı.
  const scenarios: PlanScenario[] = [
    {
      state: "Öndeyiz",
      plan: counter
        ? "Topu bırakma ama riski azalt; rakip kontrası tehlikeli, geçiş savunmasını sıkı tut. 75. dk sonrası köşelerde zaman yönet."
        : "Kontrolü koru, bloğu hafif düşür, geçişe çık. İkinci golü ararken dengeyi bozma.",
    },
    {
      state: "Berabere",
      plan: weak[0]
        ? `Zaafı ısrarla zorla: ${weak[0].title.toLowerCase()}. Sabırlı ol; ${deepBlock ? "kanat + duran top" : "dikine pas"} ile aç, acele şut yok.`
        : "Ritmi koru, eşleşme avantajlarını zorla, duran toplarda far-post.",
    },
    {
      state: "Geride",
      plan: counter
        ? "Riski artır ama dengeli: ekstra kanat/ikinci santrfor: ama rakip kontrası için bir stoper + ön libero arkada kalsın."
        : `Yüksek blok + ikinci santrfor; ${deepBlock ? "kanatlardan bol orta ve far-post bombardımanı" : "tüm hat öne, baskıyı artır"}.`,
    },
  ];

  return { shape: { formation, rationale }, principles: principles.slice(0, 5), pressTriggers, scenarios };
}
