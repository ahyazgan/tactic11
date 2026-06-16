/**
 * Oyuncu özellik türetimi — SAF fonksiyonlar (demo + canlı ortak çekirdek).
 *
 * FM tarzı 1-20 nitelikler uydurma bir rating setinden değil, gözlenen
 * veriden türer:
 *  • Teknik + Zihinsel (saha) ve Kaleci grupları → sezon maç istatistiği
 *    (PlayerSeasonStats; şekli backend GET /players/{id}/season-stats ve
 *    API-Football "players" yanıtıyla uyumlu) → emsal havuzunda yüzdelik sıra.
 *  • Fiziksel grup → kulüp test ölçümlerinin kadro içi yüzdelikleri
 *    (physicalGroupFromPercentiles çağıranın verdiği yüzdeliklerle kurulur).
 *
 * Demo (demo-data.ts) bu çekirdeği sentetik-deterministik veriyle, canlı mod
 * (players/[id]) gerçek backend yanıtıyla besler — türetme MANTIĞI tektir.
 */

export type AttrSource = "perf_lab" | "api_football";
export interface PlayerAttr { name: string; value: number }     // value: 1..20
export interface AttrGroup { group: string; source: AttrSource; attrs: PlayerAttr[] }

// Sezon istatistiği — backend season-stats endpoint'i bu alanları döner.
export interface PlayerSeasonStats {
  player_id: number;
  appearances: number;
  minutes: number;
  goals: number; assists: number;
  shots: number; shots_on: number;
  pass_accuracy: number;       // %
  key_passes: number;
  dribbles_att: number; dribbles_succ: number;
  tackles: number; interceptions: number;
  duels: number; duels_won: number;
  aerials_won: number;
  fouls: number;
  // kaleci
  saves: number; goals_conceded: number; clean_sheets: number;
}

const clamp20 = (v: number) => Math.max(1, Math.min(20, Math.round(v)));
const toAttr = (pct: number) => clamp20(1 + pct * 19);            // 0..1 → 1..20
const avg = (...xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

export const p90 = (v: number, mins: number) => (mins > 0 ? v / (mins / 90) : 0);
const ratio = (num: number, den: number) => (den > 0 ? num / den : 0);

/** value'nun pool içindeki yüzdelik sırası (0..1). higher=true → büyük iyi. */
export function pctRank(value: number, pool: number[], higher: boolean): number {
  if (pool.length <= 1) return 0.5;
  const beaten = pool.filter((v) => (higher ? v <= value : v >= value)).length;
  return beaten / pool.length;
}

/** Mutlak norm → 0..1 (küçük havuzda percentile bozulur; kaleci için). */
function normPct(v: number, lo: number, hi: number, higher: boolean): number {
  const t = (v - lo) / (hi - lo);
  return Math.max(0, Math.min(1, higher ? t : 1 - t));
}

// ── metrik kısayolları ──
const goals90 = (s: PlayerSeasonStats) => p90(s.goals, s.minutes);
const assists90 = (s: PlayerSeasonStats) => p90(s.assists, s.minutes);
const shots90 = (s: PlayerSeasonStats) => p90(s.shots, s.minutes);
const conv = (s: PlayerSeasonStats) => ratio(s.goals, s.shots);
const keyp90 = (s: PlayerSeasonStats) => p90(s.key_passes, s.minutes);
const drib90 = (s: PlayerSeasonStats) => p90(s.dribbles_succ, s.minutes);
const dribRate = (s: PlayerSeasonStats) => ratio(s.dribbles_succ, s.dribbles_att);
const pass = (s: PlayerSeasonStats) => s.pass_accuracy;
const tack90 = (s: PlayerSeasonStats) => p90(s.tackles, s.minutes);
const int90 = (s: PlayerSeasonStats) => p90(s.interceptions, s.minutes);
const duels90 = (s: PlayerSeasonStats) => p90(s.duels, s.minutes);
const aerOrDuelWon90 = (s: PlayerSeasonStats) =>
  p90(s.aerials_won > 0 ? s.aerials_won : s.duels_won, s.minutes);
const fouls90 = (s: PlayerSeasonStats) => p90(s.fouls, s.minutes);
// Tecrübe vekili: oynanan dakika (havuz genelinde karşılaştırılabilir tek ölçü).
const expScore = (s: PlayerSeasonStats) => s.minutes + s.appearances * 30;

export interface StatAttrOptions {
  isGk: boolean;
  /** Liderlik için yaş bonusu (canlıda /players/{id}/info'dan; yoksa atlanır). */
  age?: number | null;
}

/**
 * Sezon istatistiğinden Teknik + Zihinsel (saha) ya da Kaleci + Zihinsel
 * grupları. pool = emsal havuz (saha oyuncuları; me dahil olabilir).
 */
export function statAttrGroups(
  me: PlayerSeasonStats,
  pool: PlayerSeasonStats[],
  opts: StatAttrOptions,
): AttrGroup[] {
  const { isGk, age } = opts;

  if (isGk) {
    const saves90 = p90(me.saves, me.minutes);
    const conc90 = p90(me.goals_conceded, me.minutes);
    const csRate = ratio(me.clean_sheets, me.appearances);
    const aer90v = aerOrDuelWon90(me);
    const lead = normPct((age ?? 26) + me.appearances * 0.2, 22, 36, true);
    const gkAttrs: PlayerAttr[] = [
      { name: "Refleksler", value: toAttr(normPct(saves90, 1.6, 4.4, true)) },
      { name: "Bir-e-Bir", value: toAttr(normPct(saves90, 1.8, 4.2, true)) },
      { name: "Hava Hakimiyeti", value: toAttr(normPct(aer90v, 0.3, 1.6, true)) },
      { name: "Elle Kontrol", value: toAttr(normPct(csRate, 0.12, 0.5, true)) },
      { name: "Ayakla Oyun", value: toAttr(normPct(me.pass_accuracy, 60, 88, true)) },
      { name: "Yumruklama", value: toAttr(normPct(aer90v, 0.3, 1.5, true)) },
      { name: "Savunmayı Yönetme", value: toAttr(avg(normPct(conc90, 1.6, 0.55, true), normPct(csRate, 0.12, 0.5, true))) },
    ];
    const gkMental: PlayerAttr[] = [
      { name: "Karar Alma", value: toAttr(normPct(me.pass_accuracy, 62, 86, true)) },
      { name: "Pozisyon Alma", value: toAttr(normPct(csRate, 0.12, 0.5, true)) },
      { name: "Vizyon", value: toAttr(normPct(me.pass_accuracy, 60, 84, true)) },
      { name: "Soğukkanlılık", value: toAttr(normPct(conc90, 1.6, 0.55, true)) },
      { name: "Çalışkanlık", value: toAttr(normPct(saves90, 1.8, 4.2, true)) },
      { name: "Konsantrasyon", value: toAttr(normPct(csRate, 0.12, 0.5, true)) },
      { name: "Liderlik", value: toAttr(lead) },
    ];
    return [
      { group: "Kaleci", source: "api_football", attrs: gkAttrs },
      { group: "Zihinsel", source: "api_football", attrs: gkMental },
    ];
  }

  // Saha oyuncusu: her metrik için emsal havuzda yüzdelik sıra.
  const pm = (fn: (s: PlayerSeasonStats) => number, higher = true) =>
    pctRank(fn(me), pool.map(fn), higher);
  // Liderlik: dakika-tabanlı tecrübe yüzdeliği + (varsa) 30+ yaş bonusu.
  const leadPct = Math.min(1, pm(expScore) + (age != null && age >= 30 ? 0.1 : 0));

  const techAttrs: PlayerAttr[] = [
    { name: "Bitiricilik", value: toAttr(avg(pm(conv), pm(goals90))) },
    { name: "İlk Dokunuş", value: toAttr(avg(pm(pass), pm(dribRate))) },
    { name: "Pas", value: toAttr(avg(pm(pass), pm(keyp90))) },
    { name: "Dripling", value: toAttr(avg(pm(dribRate), pm(drib90))) },
    { name: "Orta", value: toAttr(avg(pm(keyp90), pm(assists90))) },
    { name: "Uzun Şut", value: toAttr(avg(pm(shots90), pm(goals90))) },
    { name: "Top Kapma", value: toAttr(avg(pm(tack90), pm(int90))) },
  ];
  const mentalAttrs: PlayerAttr[] = [
    { name: "Karar Alma", value: toAttr(avg(pm(pass), pm(fouls90, false))) },
    { name: "Pozisyon Alma", value: toAttr(avg(pm(int90), pm(aerOrDuelWon90))) },
    { name: "Vizyon", value: toAttr(avg(pm(keyp90), pm(assists90))) },
    { name: "Soğukkanlılık", value: toAttr(avg(pm(conv), pm(pass))) },
    { name: "Çalışkanlık", value: toAttr(avg(pm(duels90), pm(tack90))) },
    { name: "Konsantrasyon", value: toAttr(avg(pm(fouls90, false), pm(pass))) },
    { name: "Liderlik", value: toAttr(leadPct) },
  ];
  return [
    { group: "Teknik", source: "api_football", attrs: techAttrs },
    { group: "Zihinsel", source: "api_football", attrs: mentalAttrs },
  ];
}

/**
 * Fiziksel grup — test protokolü yüzdeliklerinden (0..1) kurulur.
 * pp(proto, higher): oyuncunun o protokoldeki kadro-içi yüzdelik sırası.
 * Veri yoksa çağıran bu grubu hiç üretmesin (canlıda dürüst davranış).
 */
export function physicalGroupFromPercentiles(
  pp: (proto: "sprint_10m" | "sprint_30m" | "yoyo_irl1" | "cmj" | "vo2max", higher: boolean) => number,
): AttrGroup {
  const attrs: PlayerAttr[] = [
    { name: "Hız", value: toAttr(pp("sprint_30m", false)) },
    { name: "İvmelenme", value: toAttr(pp("sprint_10m", false)) },
    { name: "Dayanıklılık", value: toAttr(avg(pp("yoyo_irl1", true), pp("vo2max", true))) },
    { name: "Güç", value: toAttr(pp("cmj", true)) },
    { name: "Çeviklik", value: toAttr(avg(pp("sprint_10m", false), pp("cmj", true))) },
    { name: "Zıplama", value: toAttr(pp("cmj", true)) },
    { name: "Denge", value: toAttr(avg(pp("cmj", true), pp("yoyo_irl1", true))) },
  ];
  return { group: "Fiziksel", source: "perf_lab", attrs };
}
