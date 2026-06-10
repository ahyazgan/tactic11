/**
 * Demo veri katmanı — markasız "Beşiktaş" kulübü için gerçekçi sahte veri.
 *
 * Backend/internet GEREKTİRMEZ. `DEMO_MODE` açıkken sayfalar bu veriyi kullanır.
 * Tipler sayfaların beklediği canlı-API şekilleriyle uyumludur (PlayerRow,
 * PlayerSummary, PhysicalTest, RiskReport, PlanVsLive) + demo'ya özel zenginleştirmeler.
 *
 * İçerik tek bir kurgusal maç gününe odaklı: Beşiktaş vs Antalyaspor.
 */

export const DEMO_CLUB = "Beşiktaş";
export const DEMO_OPPONENT = "Antalyaspor";
export const DEMO_ACCENT = "#3d7eff";

// --------------------------------------------------------------------------- //
// KADRO (24 oyuncu)
// --------------------------------------------------------------------------- //

export type RiskLabel = "Düşük" | "Orta" | "Yüksek" | "Kritik";
export type Position = "GK" | "DF" | "MF" | "FW";

export interface SquadPlayer {
  player_id: number;
  player_name: string;
  position: Position;
  pos_detail: string;     // "Stoper", "Sol Bek", "Ön Libero"...
  age: number;
  condition: number;      // 0-100 (kondisyon/hazırlık)
  risk_label: RiskLabel;
  risk_score: number;     // 0-100
  shirt: number;
}

export const demoSquad: SquadPlayer[] = [
  { player_id: 1, player_name: "Ersin Destanoğlu", position: "GK", pos_detail: "Kaleci", age: 29, condition: 92, risk_label: "Düşük", risk_score: 12, shirt: 1 },
  { player_id: 2, player_name: "Amir Murillo", position: "DF", pos_detail: "Sağ Bek", age: 26, condition: 81, risk_label: "Orta", risk_score: 44, shirt: 2 },
  { player_id: 3, player_name: "Tiago Djaló", position: "DF", pos_detail: "Stoper", age: 31, condition: 74, risk_label: "Yüksek", risk_score: 68, shirt: 4 },
  { player_id: 4, player_name: "Emmanuel Agbadou", position: "DF", pos_detail: "Stoper", age: 24, condition: 88, risk_label: "Düşük", risk_score: 19, shirt: 5 },
  { player_id: 5, player_name: "Rıdvan Yılmaz", position: "DF", pos_detail: "Sol Bek", age: 28, condition: 69, risk_label: "Yüksek", risk_score: 71, shirt: 3 },
  { player_id: 6, player_name: "Wilfred Ndidi", position: "MF", pos_detail: "Ön Libero", age: 27, condition: 84, risk_label: "Orta", risk_score: 38, shirt: 6 },
  { player_id: 7, player_name: "Salih Uçan", position: "MF", pos_detail: "Merkez OS", age: 23, condition: 90, risk_label: "Düşük", risk_score: 15, shirt: 8 },
  { player_id: 8, player_name: "Orkun Kökçü", position: "MF", pos_detail: "10 Numara", age: 30, condition: 58, risk_label: "Kritik", risk_score: 86, shirt: 10 },
  { player_id: 9, player_name: "Cengiz Ünder", position: "FW", pos_detail: "Sol Kanat", age: 25, condition: 79, risk_label: "Orta", risk_score: 41, shirt: 11 },
  { player_id: 10, player_name: "Oh Hyeon-Gyu", position: "FW", pos_detail: "Santrfor", age: 27, condition: 86, risk_label: "Düşük", risk_score: 22, shirt: 9 },
  { player_id: 11, player_name: "Milot Rashica", position: "FW", pos_detail: "Sağ Kanat", age: 22, condition: 91, risk_label: "Düşük", risk_score: 17, shirt: 7 },
  { player_id: 12, player_name: "Devis Vásquez", position: "GK", pos_detail: "Kaleci", age: 24, condition: 94, risk_label: "Düşük", risk_score: 8, shirt: 12 },
  { player_id: 13, player_name: "Felix Uduokhai", position: "DF", pos_detail: "Stoper", age: 33, condition: 64, risk_label: "Yüksek", risk_score: 73, shirt: 15 },
  { player_id: 14, player_name: "Taylan Bulut", position: "DF", pos_detail: "Sağ Bek", age: 21, condition: 89, risk_label: "Düşük", risk_score: 20, shirt: 24 },
  { player_id: 15, player_name: "Kristjan Asllani", position: "MF", pos_detail: "Ön Libero", age: 29, condition: 76, risk_label: "Orta", risk_score: 47, shirt: 16 },
  { player_id: 16, player_name: "Gökhan Sazdağı", position: "MF", pos_detail: "Merkez OS", age: 26, condition: 83, risk_label: "Orta", risk_score: 35, shirt: 20 },
  { player_id: 17, player_name: "Jota Silva", position: "MF", pos_detail: "Sol Kanat", age: 20, condition: 93, risk_label: "Düşük", risk_score: 11, shirt: 17 },
  { player_id: 18, player_name: "El Bilal Touré", position: "FW", pos_detail: "Santrfor", age: 31, condition: 67, risk_label: "Yüksek", risk_score: 65, shirt: 19 },
  { player_id: 19, player_name: "Václav Černý", position: "FW", pos_detail: "Sağ Kanat", age: 24, condition: 85, risk_label: "Düşük", risk_score: 24, shirt: 21 },
  { player_id: 20, player_name: "Necip Uysal", position: "DF", pos_detail: "Sol Bek", age: 27, condition: 80, risk_label: "Orta", risk_score: 43, shirt: 23 },
  { player_id: 21, player_name: "Junior Olaitan", position: "MF", pos_detail: "10 Numara", age: 23, condition: 87, risk_label: "Düşük", risk_score: 18, shirt: 14 },
  { player_id: 22, player_name: "Emir Han Topçu", position: "DF", pos_detail: "Stoper", age: 25, condition: 82, risk_label: "Orta", risk_score: 39, shirt: 25 },
  { player_id: 23, player_name: "Kartal Yılmaz", position: "FW", pos_detail: "Sol Kanat", age: 28, condition: 72, risk_label: "Yüksek", risk_score: 61, shirt: 18 },
  { player_id: 24, player_name: "Emre Bilgin", position: "GK", pos_detail: "Kaleci", age: 19, condition: 95, risk_label: "Düşük", risk_score: 6, shirt: 30 },
];

// =========================================================================== //
// OYUNCU ÖZELLİKLERİ — gerçek-kaynak türetme (provenance etiketli, 1-20 FM ölçeği)
//
// Değerler UYDURMA bir rating setinden (FM/FIFA) DEĞİL, gerçek-tip veriden türer:
//  • FİZİKSEL  → kulübün KENDİ ölçümleri (demoHistoryFor: sprint/CMJ/Yo-Yo/VO2)
//               → kadro içi percentile → 1-20.  Kaynak: Performans Lab (perf_lab).
//  • TEKNİK + ZİHİNSEL → sezon maç istatistikleri (demoSeasonStats; şekli
//               API-Football "players" yanıtıyla aynı) → emsal percentile → 1-20.
//               Kaynak: API-Football.
//  • KALECİ    → kaleci istatistikleri (kurtarış/clean sheet/yenilen) mutlak norm.
//
// Backend bağlanınca AYNI fonksiyon gerçek veriyle çalışır: tek değişiklik
// demoSeasonStats yerine canlı /players istatistiğini, demoHistoryFor yerine
// gerçek test kayıtlarını beslemek. Üretim deterministiktir (Math.random YOK).
// =========================================================================== //

export type AttrSource = "perf_lab" | "api_football";
export interface PlayerAttr { name: string; value: number }     // value: 1..20
export interface AttrGroup { group: string; source: AttrSource; attrs: PlayerAttr[] }

const clamp20 = (v: number) => Math.max(1, Math.min(20, Math.round(v)));
const toAttr = (pct: number) => clamp20(1 + pct * 19);            // 0..1 percentile → 1..20

// --- Sezon maç istatistiği (API-Football "players" yanıtının sadeleştirilmişi) ---
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

// Mevki arketipi — per-90 taban oranlar (gerçekçi futbol dağılımları).
type Arch = {
  goals: number; assists: number; shots: number; sotRate: number; passAcc: number;
  keyP: number; dribAtt: number; dribRate: number; tackles: number; inter: number;
  duels: number; duelRate: number; aerials: number; fouls: number;
};
const ARCH: Record<Position, Arch> = {
  GK: { goals: 0, assists: .02, shots: .02, sotRate: .3, passAcc: 72, keyP: .05, dribAtt: .1, dribRate: .6, tackles: .1, inter: .3, duels: 1.2, duelRate: .55, aerials: .6, fouls: .1 },
  DF: { goals: .06, assists: .07, shots: .45, sotRate: .33, passAcc: 84, keyP: .55, dribAtt: .8, dribRate: .55, tackles: 2.6, inter: 2.3, duels: 11, duelRate: .55, aerials: 3.0, fouls: 1.1 },
  MF: { goals: .14, assists: .22, shots: 1.2, sotRate: .38, passAcc: 86, keyP: 1.8, dribAtt: 1.9, dribRate: .60, tackles: 2.2, inter: 1.6, duels: 10, duelRate: .52, aerials: 1.3, fouls: 1.2 },
  FW: { goals: .48, assists: .20, shots: 2.7, sotRate: .42, passAcc: 76, keyP: 1.4, dribAtt: 3.3, dribRate: .55, tackles: .7, inter: .5, duels: 9, duelRate: .48, aerials: 1.7, fouls: 1.0 },
};

const SEASON_GAMES = 33;

// Bir oyuncunun sezon istatistiği — arketip × dakika × deterministik kalite sapması.
function seasonStatsFor(p: SquadPlayer): PlayerSeasonStats {
  const a = ARCH[p.position];
  // Genel kalite (-0.18..+0.22): kondisyon + oyuncuya özel seed.
  const q = (p.condition - 78) / 100 + Math.sin(p.player_id * 1.9) * 0.12;
  const wob = (i: number) => 1 + Math.sin(p.player_id * 2.3 + i * 1.7) * 0.14;   // ±14%
  const apps = Math.round(Math.max(8, Math.min(SEASON_GAMES, SEASON_GAMES * (0.55 + p.condition / 220) * wob(0))));
  const minutes = Math.round(apps * (62 + p.condition * 0.28) * wob(1));
  const n90 = minutes / 90;
  const r = (per90: number, i: number, mult = 1) => Math.max(0, per90 * n90 * (1 + q * mult) * wob(i));
  const shots = r(a.shots, 2);
  const dribAtt = r(a.dribAtt, 6);
  const duels = r(a.duels, 9);
  const isGk = p.position === "GK";
  return {
    player_id: p.player_id,
    appearances: apps,
    minutes,
    goals: Math.round(r(a.goals, 3, 1.6)),
    assists: Math.round(r(a.assists, 4, 1.3)),
    shots: Math.round(shots),
    shots_on: Math.round(shots * a.sotRate * (1 + q)),
    pass_accuracy: Math.round(Math.max(55, Math.min(94, a.passAcc + q * 30 + Math.sin(p.player_id * 3.1) * 2))),
    key_passes: Math.round(r(a.keyP, 5, 1.2)),
    dribbles_att: Math.round(dribAtt),
    dribbles_succ: Math.round(dribAtt * Math.max(0.35, Math.min(0.85, a.dribRate + q))),
    tackles: Math.round(r(a.tackles, 7)),
    interceptions: Math.round(r(a.inter, 8)),
    duels: Math.round(duels),
    duels_won: Math.round(duels * Math.max(0.4, Math.min(0.68, a.duelRate + q))),
    aerials_won: Math.round(r(a.aerials, 10, 0.8)),
    fouls: Math.round(r(a.fouls, 11, -0.6)),     // kaliteli oyuncu daha az faul
    saves: isGk ? Math.round(r(3.1, 12) ) : 0,
    goals_conceded: isGk ? Math.round(apps * Math.max(0.55, 1.35 - q * 1.4)) : 0,
    clean_sheets: isGk ? Math.round(apps * Math.max(0.12, Math.min(0.5, 0.3 + q * 1.2))) : 0,
  };
}

// Tüm kadronun sezon istatistiği (API-Football şekli). Gerçek modda bunun yerine
// canlı /players verisi gelir; aşağıdaki türetme aynen çalışır.
export const demoSeasonStats: PlayerSeasonStats[] = demoSquad.map(seasonStatsFor);
const STATS_BY_ID = new Map(demoSeasonStats.map((s) => [s.player_id, s]));

// per-90 + oran yardımcıları
const p90 = (v: number, mins: number) => (mins > 0 ? v / (mins / 90) : 0);
const ratio = (num: number, den: number) => (den > 0 ? num / den : 0);

/** value'nun pool içindeki yüzdelik sırası (0..1). higher=true → büyük iyi. */
function pctRank(value: number, pool: number[], higher: boolean): number {
  if (pool.length <= 1) return 0.5;
  const beaten = pool.filter((v) => (higher ? v <= value : v >= value)).length;
  return beaten / pool.length;
}
/** Mutlak norm → 0..1 (kaleci nitelikleri için; küçük havuzda percentile bozulur). */
function normPct(v: number, lo: number, hi: number, higher: boolean): number {
  const t = (v - lo) / (hi - lo);
  return Math.max(0, Math.min(1, higher ? t : 1 - t));
}

// Bir oyuncunun bir protokoldeki SON ölçümü (kulüp test verisi).
function latestTestValue(playerId: number, proto: string): number | null {
  const series = demoHistoryFor(playerId).filter((t) => t.protocol === proto);
  return series.length ? series[series.length - 1].value : null;
}

/**
 * Bir oyuncunun özellik grupları — gerçek-kaynak türetme.
 * Aynı id her zaman aynı sonucu verir (deterministik).
 */
export function demoAttributesFor(playerId: number): AttrGroup[] {
  const p = demoSquad.find((s) => s.player_id === playerId) ?? demoSquad[0];
  const isGk = p.position === "GK";

  // ── FİZİKSEL: kulüp test ölçümleri → kadro içi percentile (kaynak: perf_lab) ──
  const PHYS = ["sprint_10m", "sprint_30m", "yoyo_irl1", "cmj", "vo2max"] as const;
  const physPool: Record<string, number[]> = { sprint_10m: [], sprint_30m: [], yoyo_irl1: [], cmj: [], vo2max: [] };
  const myTest: Record<string, number | null> = {};
  for (const sp of demoSquad) {
    for (const proto of PHYS) {
      const v = latestTestValue(sp.player_id, proto);
      if (v != null) physPool[proto].push(v);
      if (sp.player_id === p.player_id) myTest[proto] = v;
    }
  }
  const pp = (proto: typeof PHYS[number], higher: boolean) =>
    myTest[proto] == null ? 0.5 : pctRank(myTest[proto]!, physPool[proto], higher);
  const avg = (...xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

  const physAttrs: PlayerAttr[] = [
    { name: "Hız", value: toAttr(pp("sprint_30m", false)) },
    { name: "İvmelenme", value: toAttr(pp("sprint_10m", false)) },
    { name: "Dayanıklılık", value: toAttr(avg(pp("yoyo_irl1", true), pp("vo2max", true))) },
    { name: "Güç", value: toAttr(pp("cmj", true)) },
    { name: "Çeviklik", value: toAttr(avg(pp("sprint_10m", false), pp("cmj", true))) },
    { name: "Zıplama", value: toAttr(pp("cmj", true)) },
    { name: "Denge", value: toAttr(avg(pp("cmj", true), pp("yoyo_irl1", true))) },
  ];
  const physGroup: AttrGroup = { group: "Fiziksel", source: "perf_lab", attrs: physAttrs };

  // ── KALECİ: kaleci istatistikleri → mutlak norm (kaynak: api_football) ──
  if (isGk) {
    const s = STATS_BY_ID.get(p.player_id)!;
    const saves90 = p90(s.saves, s.minutes);
    const conc90 = p90(s.goals_conceded, s.minutes);
    const csRate = ratio(s.clean_sheets, s.appearances);
    const aer90 = p90(s.aerials_won, s.minutes);
    const gkAttrs: PlayerAttr[] = [
      { name: "Refleksler", value: toAttr(normPct(saves90, 1.6, 4.4, true)) },
      { name: "Bir-e-Bir", value: toAttr(normPct(saves90, 1.8, 4.2, true)) },
      { name: "Hava Hakimiyeti", value: toAttr(normPct(aer90, 0.3, 1.6, true)) },
      { name: "Elle Kontrol", value: toAttr(normPct(csRate, 0.12, 0.5, true)) },
      { name: "Ayakla Oyun", value: toAttr(normPct(s.pass_accuracy, 60, 88, true)) },
      { name: "Yumruklama", value: toAttr(normPct(aer90, 0.3, 1.5, true)) },
      { name: "Savunmayı Yönetme", value: toAttr(avg(normPct(conc90, 1.6, 0.55, true), normPct(csRate, 0.12, 0.5, true))) },
    ];
    const gkMental: PlayerAttr[] = [
      { name: "Karar Alma", value: toAttr(normPct(s.pass_accuracy, 62, 86, true)) },
      { name: "Pozisyon Alma", value: toAttr(normPct(csRate, 0.12, 0.5, true)) },
      { name: "Vizyon", value: toAttr(normPct(s.pass_accuracy, 60, 84, true)) },
      { name: "Soğukkanlılık", value: toAttr(normPct(conc90, 1.6, 0.55, true)) },
      { name: "Çalışkanlık", value: toAttr(normPct(saves90, 1.8, 4.2, true)) },
      { name: "Konsantrasyon", value: toAttr(normPct(csRate, 0.12, 0.5, true)) },
      { name: "Liderlik", value: toAttr(normPct(p.age + s.appearances * 0.2, 22, 36, true)) },
    ];
    return [
      { group: "Kaleci", source: "api_football", attrs: gkAttrs },
      { group: "Zihinsel", source: "api_football", attrs: gkMental },
      physGroup,
    ];
  }

  // ── TEKNİK + ZİHİNSEL: sezon istatistiği → emsal percentile (kaynak: api_football) ──
  // Havuz = saha oyuncuları (kaleci hariç) → bir metriğin tüm kadroya göre yüzdelik
  // sırası mevki-uygun yayılım üretir (forvet bitiricilikte üstte, stoper altta).
  const OUT = demoSquad.filter((sp) => sp.position !== "GK");
  const me = STATS_BY_ID.get(p.player_id)!;
  // Bir metrik fonksiyonunun, odak oyuncunun emsal içindeki percentile'ı.
  const pm = (fn: (s: PlayerSeasonStats, pl: SquadPlayer) => number, higher = true) => {
    const pool = OUT.map((sp) => fn(STATS_BY_ID.get(sp.player_id)!, sp));
    return pctRank(fn(me, p), pool, higher);
  };
  // metrik kısayolları
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
  const aer90 = (s: PlayerSeasonStats) => p90(s.aerials_won, s.minutes);
  const fouls90 = (s: PlayerSeasonStats) => p90(s.fouls, s.minutes);
  const exp = (_s: PlayerSeasonStats, pl: SquadPlayer) => pl.age + _s.appearances * 0.2;

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
    { name: "Pozisyon Alma", value: toAttr(avg(pm(int90), pm(aer90))) },
    { name: "Vizyon", value: toAttr(avg(pm(keyp90), pm(assists90))) },
    { name: "Soğukkanlılık", value: toAttr(avg(pm(conv), pm(pass))) },
    { name: "Çalışkanlık", value: toAttr(avg(pm(duels90), pm(tack90))) },
    { name: "Konsantrasyon", value: toAttr(avg(pm(fouls90, false), pm(pass))) },
    { name: "Liderlik", value: toAttr(pm(exp)) },
  ];

  return [
    { group: "Teknik", source: "api_football", attrs: techAttrs },
    { group: "Zihinsel", source: "api_football", attrs: mentalAttrs },
    physGroup,
  ];
}

// --------------------------------------------------------------------------- //
// OVERVIEW — /physical-tests/players şekli (PlayerRow)
// --------------------------------------------------------------------------- //

// NOT: API şekline uyum — player_id string, risk_score 0..1 (sayfalar *100 yapar).
export interface PlayerRow {
  player_id: string;
  player_name: string;
  test_count: number;
  latest_test_date: string | null;
  risk_label: string;
  risk_score: number;
}

export const demoPlayerRows: PlayerRow[] = demoSquad.map((p, i) => ({
  player_id: String(p.player_id),
  player_name: p.player_name,
  test_count: 5,
  latest_test_date: `2026-06-0${(i % 5) + 1}`,
  risk_label: p.risk_label,
  risk_score: p.risk_score / 100,
}));

// KPI şeridi (overview üstü)
export interface OverviewKpi { label: string; value: string; sub: string }
export const demoOverviewKpis: OverviewKpi[] = [
  { label: "Kadro Hazırlığı", value: "%81", sub: "ort. kondisyon" },
  { label: "Sahaya Hazır", value: "20/24", sub: "4 oyuncu riskli" },
  { label: "Kritik Risk", value: "1", sub: "Orkun Kökçü (8)" },
  { label: "Sıradaki Maç", value: "2 gün", sub: "Antalyaspor (D)" },
  { label: "Galibiyet Olasılığı", value: "%48", sub: "model tahmini" },
];

// --------------------------------------------------------------------------- //
// FİZİKSEL TEST — PlayerSummary / PhysicalTest / RiskReport şekilleri
// --------------------------------------------------------------------------- //

export interface PlayerSummary {
  player_id: string;
  player_name: string;
  test_count: number;
  latest_test_date: string | null;
  risk_label: string;
  risk_score: number;
}

export interface PhysicalTest {
  id: number;
  player_id: string;
  test_date: string;
  protocol: string;
  value: number;
  unit: string | null;
}

export interface RiskFlag { protocol: string; value: number; unit: string; message: string }

export interface RiskReport {
  player_id: string;
  player_name: string;
  risk_score: number;            // 0..1 (sayfa *100 yapar)
  risk_label: string;
  flags: RiskFlag[];
  summary: string;
  recommendations: string[];
}

export const demoPlayerSummaries: PlayerSummary[] = demoPlayerRows;

// Sayfanın PROTO katalog anahtarlarını kullan (protoName/protoUnit çözer).
const PROTOCOLS: { protocol: string; unit: string; base: number; spread: number; better: "low" | "high" }[] = [
  { protocol: "sprint_10m", unit: "sn", base: 1.75, spread: 0.12, better: "low" },
  { protocol: "sprint_30m", unit: "sn", base: 4.10, spread: 0.22, better: "low" },
  { protocol: "yoyo_irl1", unit: "sv", base: 19.0, spread: 2.4, better: "high" },
  { protocol: "cmj", unit: "cm", base: 52.0, spread: 6.0, better: "high" },
  { protocol: "vo2max", unit: "ml", base: 57.0, spread: 4.0, better: "high" },
];

const TEST_DATES = ["2026-05-09", "2026-05-16", "2026-05-23", "2026-05-30", "2026-06-05"];

/** Bir oyuncunun son 5 ölçümü (5 protokol × 5 tarih = 25 kayıt). Risk yüksekse trend kötüleşir. */
export function demoHistoryFor(playerId: number): PhysicalTest[] {
  const player = demoSquad.find((p) => p.player_id === playerId);
  const decline = player ? (player.risk_score - 40) / 100 : 0; // riskli → kötüye gidiş
  const rows: PhysicalTest[] = [];
  let id = playerId * 100;
  PROTOCOLS.forEach((pr, pi) => {
    TEST_DATES.forEach((date, di) => {
      // Deterministik dalgalanma (Math.random YOK — demo tekrarlanabilir olsun)
      const wave = Math.sin((playerId + pi * 3 + di) * 1.7) * 0.4 + 0.5; // 0.1..0.9
      const drift = (di / 4) * decline * (pr.better === "low" ? 1 : -1);
      const raw = pr.base + (wave - 0.5) * pr.spread + drift * pr.spread;
      rows.push({
        id: id++,
        player_id: String(playerId),
        test_date: date,
        protocol: pr.protocol,
        value: Math.round(raw * 100) / 100,
        unit: pr.unit,
      });
    });
  });
  return rows;
}

export function demoRiskFor(playerId: number): RiskReport {
  const p = demoSquad.find((s) => s.player_id === playerId)!;
  const flagsByLabel: Record<RiskLabel, RiskFlag[]> = {
    "Kritik": [
      { protocol: "sprint_30m", value: 4.38, unit: "sn", message: "ACWR 1.6 — akut yük zirvede" },
      { protocol: "sprint_10m", value: 1.92, unit: "sn", message: "Sprint hızı 3 hafta üst üste düştü" },
      { protocol: "cmj", value: 47.0, unit: "cm", message: "Dikey sıçrama -%9 (yorgunluk)" },
    ],
    "Yüksek": [
      { protocol: "sprint_30m", value: 4.29, unit: "sn", message: "ACWR 1.4 — yük artışı dik" },
      { protocol: "cmj", value: 49.0, unit: "cm", message: "Dikey sıçrama -%6 (yorgunluk)" },
    ],
    "Orta": [
      { protocol: "yoyo_irl1", value: 18.2, unit: "sv", message: "Yo-Yo mekik hafif geriledi (ACWR 1.2)" },
    ],
    "Düşük": [],
  };
  const summaryByLabel: Record<RiskLabel, string> = {
    "Kritik": `${p.player_name} için sakatlık riski KRİTİK. Akut/kronik yük oranı eşik üstünde ve performans metrikleri belirgin düşüyor. Bu maç için rotasyon veya erken oyundan alma önerilir.`,
    "Yüksek": `${p.player_name} yüksek risk bandında. Yük yönetimi ve maç-içi dakika sınırı düşünülmeli.`,
    "Orta": `${p.player_name} izlenmesi gereken orta risk seviyesinde. Antrenman yoğunluğu kademeli ayarlanmalı.`,
    "Düşük": `${p.player_name} düşük risk; tam maç yüküne hazır.`,
  };
  const recsByLabel: Record<RiskLabel, string[]> = {
    "Kritik": ["Bu hafta yüksek şiddetli koşuyu %40 azalt", "Maçta 60. dakika sonrası değişiklik planla", "Fizyoterapi + uyku/HRV takibi"],
    "Yüksek": ["Antrenmanda sprint hacmini sınırla", "Maç-içi yük izle, gerekirse erken değiştir"],
    "Orta": ["Yükü kademeli artır", "Bir sonraki test penceresinde yeniden değerlendir"],
    "Düşük": ["Mevcut programa devam", "Rutin haftalık takip yeterli"],
  };
  return {
    player_id: String(p.player_id),
    player_name: p.player_name,
    risk_score: p.risk_score / 100,
    risk_label: p.risk_label,
    flags: flagsByLabel[p.risk_label],
    summary: summaryByLabel[p.risk_label],
    recommendations: recsByLabel[p.risk_label],
  };
}

// Protokol rehberi — canlıda GET /physical-tests/protocols döndürür; demo'da statik.
export interface ProtocolInfo {
  key: string;
  name: string;
  unit: string;
  higher_is_better: boolean;
  description: string;
  norm_elite: number;
  norm_good: number;
  norm_average: number;
  ref_low?: number;
  ref_high?: number;
}

export const demoProtocols: ProtocolInfo[] = [
  { key: "sprint_10m", name: "10m Sprint (ivmelenme)", unit: "sn", higher_is_better: false,
    description: "Foto-hücre kapıları; durağan başlangıç, 10m. İlk adım gücü/ivmelenme. 2 deneme, en iyisi.",
    norm_elite: 1.70, norm_good: 1.80, norm_average: 1.90 },
  { key: "sprint_30m", name: "30m Sprint", unit: "sn", higher_is_better: false,
    description: "Foto-hücre kapıları; durağan başlangıç, 30m. 2 deneme, en iyisi. 10m split de kaydedilebilir.",
    norm_elite: 4.00, norm_good: 4.20, norm_average: 4.40 },
  { key: "yoyo_irl1", name: "Yo-Yo Intermittent Recovery L1", unit: "seviye", higher_is_better: true,
    description: "20m mekik + 10s aktif dinlenme, artan hız; bip'e uyamayınca biter. Ulaşılan kademe.",
    norm_elite: 20.0, norm_good: 18.0, norm_average: 16.0 },
  { key: "cmj", name: "Countermovement Jump (dikey sıçrama)", unit: "cm", higher_is_better: true,
    description: "Eller belde, hızlı çömel-zıpla; force plate ya da jump mat ile yükseklik. 3 deneme, en iyisi.",
    norm_elite: 40.0, norm_good: 35.0, norm_average: 30.0 },
  { key: "isokinetic_quad", name: "İzokinetik Quadriceps (60°/s)", unit: "Nm/kg", higher_is_better: true,
    description: "İzokinetik dinamometre, 60°/sn; kuadriseps tepe torku / vücut ağırlığı. H/Q oranı için.",
    norm_elite: 3.20, norm_good: 2.85, norm_average: 2.50 },
  { key: "isokinetic_ham", name: "İzokinetik Hamstring (60°/s)", unit: "Nm/kg", higher_is_better: true,
    description: "İzokinetik dinamometre, 60°/sn; hamstring tepe torku / vücut ağırlığı. Sakatlık riskinin anahtarı.",
    norm_elite: 2.00, norm_good: 1.75, norm_average: 1.50 },
  { key: "vo2max", name: "VO2max (maksimal oksijen)", unit: "ml/kg/min", higher_is_better: true,
    description: "Doğrudan (metabolik araba) ya da Beep/Cooper'dan kestirim. Aerobik kapasite.",
    norm_elite: 62.0, norm_good: 57.0, norm_average: 52.0 },
  { key: "gps_total_dist", name: "GPS Toplam Mesafe (maç)", unit: "m", higher_is_better: true,
    description: "GPS/LPS biriminden bir maç/antrenmandaki toplam kat edilen mesafe. İş hacmi göstergesi.",
    norm_elite: 11500, norm_good: 10250, norm_average: 9000 },
  { key: "body_fat_pct", name: "Vücut Yağ Oranı", unit: "%", higher_is_better: false,
    description: "Skinfold (kaliper) ya da biyoimpedans; vücut yağ yüzdesi. Düşük iyi (atletik kompozisyon).",
    norm_elite: 8.0, norm_good: 11.0, norm_average: 14.0 },
];

// --------------------------------------------------------------------------- //
// SIRADAKİ MAÇ + MAÇ PLANI
// --------------------------------------------------------------------------- //

export interface NextMatch {
  home: string;
  away: string;
  date: string;
  kickoff: string;
  competition: string;
  win: number;   // 0..1
  draw: number;
  loss: number;
  venue?: string;
  aiPreview?: string;   // PreMatchReportAgent tek-cümle önizleme
}

export const demoNextMatch: NextMatch = {
  home: DEMO_CLUB,
  away: DEMO_OPPONENT,
  date: "2026-06-08",
  kickoff: "20:00",
  competition: "Süper Lig — 34. Hafta",
  win: 0.48,
  draw: 0.27,
  loss: 0.25,
  venue: "İç saha",
  aiPreview: "Rakip sağ bek arkası zayıf; yüksek pres + sağ kanat 1v1 ile xG üstünlüğü bekleniyor.",
};

// Genel Bakış — Form & rating trendi (form/rating motorlarının demo karşılığı)
export interface FormResult { opp: string; ha: "H" | "A"; gf: number; ga: number; r: "W" | "D" | "L" }
export const demoRecentForm: FormResult[] = [
  { opp: "Trabzonspor",     ha: "H", gf: 3, ga: 1, r: "W" },
  { opp: "Kasımpaşa",       ha: "A", gf: 1, ga: 1, r: "D" },
  { opp: "Eyüpspor",        ha: "H", gf: 2, ga: 0, r: "W" },
  { opp: "Çaykur Rizespor", ha: "A", gf: 0, ga: 2, r: "L" },
  { opp: "Gaziantep FK",    ha: "H", gf: 2, ga: 1, r: "W" },
];
// Model rating trendi (son 8 hafta) — sparkline için
export const demoRatingTrend: number[] = [71, 70, 73, 72, 74, 73, 76, 78];

// Genel Bakış — AI brifing akışı (AgentOutput tablosunun demo karşılığı)
export interface Briefing { type: string; title: string; when: string; summary: string }
export const demoBriefings: Briefing[] = [
  { type: "Maç Öncesi", title: `${DEMO_OPPONENT} maçı önizleme`, when: "2s önce",  summary: "Rakip sağ koridoru zayıf; yüksek pres + kanat 1v1 ile xG üstünlüğü beklenir." },
  { type: "Haftalık",   title: "Haftalık digest hazır",          when: "dün",      summary: "Son 3 maçta +1.8 xG farkı; kadro yükü kontrol altında, 2 oyuncu re-test." },
  { type: "Scout",      title: "İzleme listesi güncellendi",      when: "2g önce",  summary: "Sol bek hedefi son 5 maçta progresif pas %18 arttı — öncelik yükseldi." },
];

export interface PlanVsLive {
  summary: string;
  updated_at: string;
  plan_age_seconds: number;
  status: string;
  active_scenario: string;
  matchup_recommendation: string;
  set_piece_hint: string;
  notes: string[];
}

export const demoPlan: PlanVsLive = {
  summary: "Antalyaspor sağ bek arkasını boş bırakıyor; sol kanattan derinlik + 10 numara ile yarı-alan baskısı planlandı. Geçiş anlarında ön libero koruması kritik.",
  updated_at: "2026-06-08T18:42:00Z",
  plan_age_seconds: 540,
  status: "Hazır",
  active_scenario: "level",   // sayfa anahtarı: leading|level|trailing
  matchup_recommendation: "Milot Rashica (7) vs rakip sol bek: hız avantajı %72 — bu eşleşmeyi sömür",
  set_piece_hint: "Köşelerde ikinci direk: rakip zonal savunmada far-post zayıf",
  notes: [
    "Rakip pres tetiği: kaleci-stoper ilk pasında yüksek bas",
    "İlk 15 dk yüksek tempo bekleniyor; ön libero geç çıksın",
    "Sakatlık sonrası dönen rakip 6 numara 60. dk sonrası yoruluyor",
  ],
};

export interface OpponentWeakness { title: string; detail: string; severity: "yüksek" | "orta" | "düşük" }
export const demoWeaknesses: OpponentWeakness[] = [
  { title: "Sağ bek arkası boşluğu", detail: "Sağ bek hücumda yüksek konumlanıyor; arkasındaki koridor maç başına ort. 6 kez açılıyor.", severity: "yüksek" },
  { title: "Zonal duran top zaafı", detail: "Köşe vuruşlarında ikinci direk (far-post) örtülemiyor — son 8 maçta 4 gol yedi.", severity: "yüksek" },
  { title: "Geç dakika tempo düşüşü", detail: "75. dk sonrası PPDA %30 artıyor (pres çözülüyor); taze kanat oyuncusu cezalandırabilir.", severity: "orta" },
];

export interface Matchup { ours: string; theirs: string; advantage: number; note: string }
export const demoMatchups: Matchup[] = [
  { ours: "Milot Rashica (7) — Sağ Kanat", theirs: "Sol Bek", advantage: 72, note: "1v1 hız ve dripling üstünlüğü" },
  { ours: "Oh Hyeon-Gyu (9) — Santrfor", theirs: "Stoper ikilisi", advantage: 58, note: "Hava topu ve derinlik tehdidi" },
  { ours: "Salih Uçan (8) — Merkez", theirs: "6 Numara", advantage: 63, note: "Pres kırma ve ileri pas kalitesi" },
  { ours: "Rıdvan Yılmaz (3) — Sol Bek", theirs: "Sağ Kanat", advantage: 41, note: "Savunmada zorlanabilir — destek gerekli" },
];

export interface Scenario { state: "Öndeyiz" | "Berabere" | "Geride"; plan: string; subs: string }
export const demoScenarios: Scenario[] = [
  { state: "Öndeyiz", plan: "Blok düşür, geçişe çık. Kanat oyuncuları savunmaya yardım etsin.", subs: "Taze stoper + savunma 6 numarası" },
  { state: "Berabere", plan: "Ritmi koru, sağ kanat 1v1'i sömür. Duran toplarda far-post.", subs: "Junior Olaitan (14) ile yaratıcılık" },
  { state: "Geride", plan: "İkinci santrfor + yüksek blok. Kanatlardan bol orta.", subs: "El Bilal Touré (19) — hava topu hedefi" },
];

// --------------------------------------------------------------------------- //
// CANLI MAÇ — xG serisi, momentum, olaylar, sub önerileri
// --------------------------------------------------------------------------- //

export interface XgPoint { minute: number; home: number; away: number; momentum: number } // momentum: -100..100 (+ bize)
export interface LiveEvent {
  minute: number;
  type: "gol" | "sari_kart" | "kirmizi_kart" | "sakatlik" | "degisiklik" | "buyuk_firsat";
  team: "home" | "away";
  text: string;
}
export interface LiveSubSuggestion {
  player_out: string;
  player_in: string;
  urgency: "orta" | "yüksek" | "kritik";
  rationale: string;
}
// Faz B — sahadaki kadro farkındalığı: as-of sahadaki oyuncular, oyuncu-başı
// gerçek dakika ve dakikaya normalize VAEP/90. Çıkan oyuncu öneri havuzundan düşer.
export interface LivePlayerImpact {
  shirt: number;
  name: string;
  pos: string;              // kısa pozisyon kodu: GK/RB/CB/LB/DM/CM/AM/LW/ST/RW
  onPitch: boolean;
  minutes: number;          // bu dakikaya kadar oynadığı GERÇEK dakika
  vaep: number;             // kümülatif VAEP katkısı
  vaepPer90: number;        // dakikaya normalize: vaep / minutes * 90
  subbedInMinute?: number;  // sonradan girdiyse
  subbedOutMinute?: number; // çıktıysa (öneri havuzundan düşer)
}
// Gizli karar motorları — backend WS snapshot'ı bunları zaten üretiyor;
// demo'da aynı şekillerle besleyip canlı konsola taşıyoruz (plan: "gizli
// motorları ekrana taşı"). Alan adları WS snapshot ile uyumlu tutuldu.
export interface LiveTacticalTrigger { type: string; urgency: string; recommendation: string }
export interface LiveMatchup { struggling_defender?: number | null; hot_opponent?: number | null; alerts: string[] }
export interface LiveSpatial { gap_between_lines?: number; superiority_flank?: string; shape_state?: string; alerts: string[] }
export interface LiveClosingRecipe { score_state: string; posture: string; closing_recipe: string; alerts: string[] }
export interface LiveSubTimingAdvice { player_id: number; verdict: string; impact: number }
export interface LiveSubTiming { package: string[]; rationale: string; advices: LiveSubTimingAdvice[] }
export interface LiveAlert { type: string; severity: string; message: string; player_id?: number | null }
export interface LiveAlertsFeed { total: number; critical: number; warning: number; info: number; alerts: LiveAlert[] }
export interface LiveDataQuality { score: number; status: string; density_per_min?: number; largest_gap_min?: number; freshness_min?: number; flags?: string[] }
export interface LiveRiskFlag { player_external_id: number; risk_type: string; severity: string; message: string }
export interface LiveRiskMonitor { score_state: string; time_management: string; card_flags: LiveRiskFlag[]; injury_flags: LiveRiskFlag[]; total_flags: number }

export interface DemoLive {
  home: string;
  away: string;
  minute: number;
  score: [number, number];
  homeXg: number;
  awayXg: number;
  momentumHolder: string;
  formation: string;
  series: XgPoint[];
  events: LiveEvent[];
  subs: LiveSubSuggestion[];
  lineup: LivePlayerImpact[];
  // Gizli motorlar (ekrana taşınan):
  tacticalTriggers: LiveTacticalTrigger[];
  matchup: LiveMatchup;
  spatial: LiveSpatial;
  closing: LiveClosingRecipe;
  subTiming: LiveSubTiming;
  alerts: LiveAlertsFeed;
  dataQuality: LiveDataQuality;
  riskMonitor: LiveRiskMonitor;
}

// 0..67 dakika, 5'er dakikalık kümülatif xG + momentum serisi
const LIVE_SERIES: XgPoint[] = [
  { minute: 0, home: 0.0, away: 0.0, momentum: 5 },
  { minute: 5, home: 0.08, away: 0.04, momentum: 22 },
  { minute: 10, home: 0.21, away: 0.06, momentum: 40 },
  { minute: 15, home: 0.34, away: 0.10, momentum: 35 },
  { minute: 20, home: 0.41, away: 0.27, momentum: 5 },
  { minute: 25, home: 0.45, away: 0.52, momentum: -28 },
  { minute: 30, home: 0.52, away: 0.71, momentum: -40 },
  { minute: 35, home: 0.66, away: 0.74, momentum: -15 },
  { minute: 40, home: 0.79, away: 0.78, momentum: 8 },
  { minute: 45, home: 0.91, away: 0.83, momentum: 18 },
  { minute: 50, home: 1.02, away: 0.86, momentum: 24 },
  { minute: 55, home: 1.05, away: 1.03, momentum: -20 },
  { minute: 60, home: 1.11, away: 1.24, momentum: -38 },
  { minute: 65, home: 1.18, away: 1.33, momentum: -30 },
  { minute: 67, home: 1.22, away: 1.35, momentum: -34 },
];

export const demoLive: DemoLive = {
  home: DEMO_CLUB,
  away: DEMO_OPPONENT,
  minute: 67,
  score: [1, 1],
  homeXg: 1.22,
  awayXg: 1.35,
  momentumHolder: DEMO_OPPONENT,
  formation: "4-3-3",
  series: LIVE_SERIES,
  events: [
    { minute: 12, type: "buyuk_firsat", team: "home", text: "Milot Rashica sağdan içeri kat etti, vuruş direkten döndü (xG 0.31)." },
    { minute: 23, type: "gol", team: "home", text: "GOL! Oh Hyeon-Gyu ceza sahasında topla buluştu ve ağları havalandırdı. 1-0." },
    { minute: 31, type: "sari_kart", team: "home", text: "Tiago Djaló geç müdahaleden sarı kart gördü." },
    { minute: 38, type: "buyuk_firsat", team: "away", text: "Antalyaspor kontra atağında kaleci Ersin Destanoğlu kurtardı." },
    { minute: 45, type: "gol", team: "away", text: "GOL! Antalyaspor köşe vuruşunda far-post'ta boş kaldı, kafa golü. 1-1." },
    { minute: 46, type: "degisiklik", team: "home", text: "Değişiklik: Cengiz Ünder (11) çıktı, Jota Silva (17) girdi — sol kanada tazelik." },
    { minute: 52, type: "sakatlik", team: "home", text: "Orkun Kökçü arka adalesini tuttu; sağlık ekibi sahada." },
    { minute: 58, type: "sari_kart", team: "away", text: "Rakip 6 numara taktik faulden sarı gördü." },
    { minute: 64, type: "buyuk_firsat", team: "away", text: "Antalyaspor üst üste 2 korner kullandı; momentum onlarda." },
  ],
  subs: [
    {
      player_out: "Orkun Kökçü (10)",
      player_in: "Junior Olaitan (14)",
      urgency: "kritik",
      rationale: "8 numara sakatlık sinyali + kondisyon kritik eşikte (58). Momentum 3 dakikadır rakipte. Şimdi taze yaratıcılık şart.",
    },
    {
      player_out: "Rıdvan Yılmaz (3)",
      player_in: "Necip Uysal (23)",
      urgency: "yüksek",
      rationale: "Sol bek yorgunluk bandında; rakip sağ kanat bu koridordan sürekli giriyor. Savunma istikrarı için değişiklik.",
    },
  ],
  // 67. dakikaya kadarki saha durumu. minutes = gerçek oynanan dakika;
  // vaepPer90 = vaep / minutes * 90 → kısa süre oynayan etkili oyuncu (Jota) öne çıkar.
  lineup: [
    { shirt: 1,  name: "Ersin Destanoğlu",   pos: "GK", onPitch: true,  minutes: 67, vaep: 0.02, vaepPer90: 0.03 },
    { shirt: 2,  name: "Amir Murillo", pos: "RB", onPitch: true,  minutes: 67, vaep: 0.07, vaepPer90: 0.09 },
    { shirt: 4,  name: "Tiago Djaló",  pos: "CB", onPitch: true,  minutes: 67, vaep: 0.05, vaepPer90: 0.07 },
    { shirt: 5,  name: "Emmanuel Agbadou",   pos: "CB", onPitch: true,  minutes: 67, vaep: 0.06, vaepPer90: 0.08 },
    { shirt: 3,  name: "Rıdvan Yılmaz",    pos: "LB", onPitch: true,  minutes: 67, vaep: 0.04, vaepPer90: 0.05 },
    { shirt: 6,  name: "Wilfred Ndidi", pos: "DM", onPitch: true,  minutes: 67, vaep: 0.09, vaepPer90: 0.12 },
    { shirt: 8,  name: "Salih Uçan",  pos: "CM", onPitch: true,  minutes: 67, vaep: 0.17, vaepPer90: 0.23 },
    { shirt: 10, name: "Orkun Kökçü", pos: "AM", onPitch: true,  minutes: 67, vaep: 0.21, vaepPer90: 0.28 },
    { shirt: 17, name: "Jota Silva",   pos: "LW", onPitch: true,  minutes: 21, vaep: 0.18, vaepPer90: 0.77, subbedInMinute: 46 },
    { shirt: 9,  name: "Oh Hyeon-Gyu", pos: "ST", onPitch: true,  minutes: 67, vaep: 0.34, vaepPer90: 0.46 },
    { shirt: 7,  name: "Milot Rashica",  pos: "RW", onPitch: true,  minutes: 67, vaep: 0.29, vaepPer90: 0.39 },
    { shirt: 11, name: "Cengiz Ünder", pos: "LW", onPitch: false, minutes: 46, vaep: 0.05, vaepPer90: 0.10, subbedOutMinute: 46 },
  ],
  // ── Gizli karar motorları (67'/1-1/momentum rakipte/Caner sakatlık sinyali) ──
  tacticalTriggers: [
    { type: "press_height", urgency: "medium", recommendation:
      "Momentum 8 dakikadır rakipte — pres hattını düşür, orta blokta dengeyi yeniden kur." },
    { type: "channel_shift", urgency: "medium", recommendation:
      "Rakip sol koridorumuzdan (Rıdvan Yılmaz, 3) sürekli giriyor — hücum yükünü sağ kanada (Tolga, 7) kaydır." },
  ],
  matchup: {
    struggling_defender: 3,
    hot_opponent: 23,
    alerts: [
      "DÜELLO: Rıdvan Yılmaz (3) son 10 dakikada 4 düellodan 3'ünü kaybetti — yardımcı gönder ya da eşleşmeyi değiştir.",
      "SICAK EL: Rakip #23 her topa giriyor (%42 dokunuş payı) — özel markaj düşün.",
    ],
  },
  spatial: {
    gap_between_lines: 18.4,
    superiority_flank: "sağ (biz)",
    shape_state: "orta blok dağınık",
    alerts: [
      "Hatlar arası boşluk açıldı (~18m) — rakip 10 numarası bu alana sızıyor.",
      "Sağ kanatta sayısal üstünlük (Tolga + Burak) — geçiş anında bu tarafı kullan.",
    ],
  },
  closing: {
    score_state: "berabere",
    posture: "dengeli — kazanmaya yönelik",
    closing_recipe:
      "Berabere @ 67' — kontrolü kaybetme; ikinci topları topla, kanat değişimiyle yeni alan ara. Riski 75. dakikadan sonra artır.",
    alerts: [],
  },
  subTiming: {
    package: ["Orkun Kökçü (10)", "Rıdvan Yılmaz (3)"],
    rationale:
      "Çifte değişiklik penceresi 68–72 dk: yaratıcılık (Caner) + savunma istikrarı (Onur) birlikte tazelensin; tek pencerede iki sorunu çöz.",
    advices: [
      { player_id: 10, verdict: "şimdi (68–70')", impact: 0.28 },
      { player_id: 3, verdict: "yakında (72–75')", impact: 0.19 },
    ],
  },
  alerts: {
    total: 3, critical: 1, warning: 2, info: 0,
    alerts: [
      { type: "fatigue", severity: "critical", player_id: 10,
        message: "Orkun Kökçü (10) yorgunluk kritik (0.62) + sakatlık sinyali — değiştir." },
      { type: "momentum_break", severity: "warning",
        message: "Momentum 2 snapshot'tır rakibe doğru — kontrolü geri al." },
      { type: "matchup", severity: "warning", player_id: 3,
        message: "Sol koridor zayıf (Rıdvan Yılmaz, 3 düello kaybı)." },
    ],
  },
  dataQuality: {
    score: 0.86, status: "ok", density_per_min: 7.2, largest_gap_min: 1.4,
    freshness_min: 0.3, flags: [],
  },
  riskMonitor: {
    score_state: "level",
    time_management: "Normal tempo — 70. dakikadan sonra zaman yönetimi devreye girecek.",
    card_flags: [
      { player_external_id: 4, risk_type: "card", severity: "medium",
        message: "Tiago Djaló (4) sarı kartlı — agresif girişlere dikkat, ikinci sarı riski." },
    ],
    injury_flags: [
      { player_external_id: 10, risk_type: "injury", severity: "medium",
        message: "Orkun Kökçü (10) yorgunluk 0.62 — sakatlık riski, değişiklik düşün." },
    ],
    total_flags: 2,
  },
};

// --------------------------------------------------------------------------- //
// AI ASİSTAN — hazır soru-cevap çiftleri
// --------------------------------------------------------------------------- //

export interface ChatQA { question: string; answer: string; tools: string[] }
export const demoChatQA: ChatQA[] = [
  {
    question: "Bu hafta sakatlık riski en yüksek oyuncular kim?",
    answer:
      "En yüksek risk Orkun Kökçü (10) — KRİTİK. Akut/kronik yük oranı 1.6 (eşik 1.5 üstü) ve son 3 ölçümde sprint hızı düştü; kondisyonu 58. Bu maç için 60. dakika sonrası değişiklik öneriyorum.\n\nİkinci grup Yüksek risk: Rıdvan Yılmaz (3), Tiago Djaló (4) ve Felix Uduokhai (15). Üçü de ACWR 1.4 bandında ve dikey sıçramada yorgunluk işareti var.\n\nDüşük risk tarafında kadronun %58'i tam maç yüküne hazır; rotasyon için Jota Silva (17) ve Taylan Bulut (24) ideal.",
    tools: ["load_risk_monitor", "physical_test_trend", "squad_availability"],
  },
  {
    question: "Antalyaspor'a karşı hangi taktiği önerirsin?",
    answer:
      "Antalyaspor sağ bekini hücumda yüksek tutuyor; arkasındaki koridor maç başına ortalama 6 kez açılıyor. Milot Rashica'i (7) o tarafa koyup hız avantajını (%72) sömürmenizi öneriyorum.\n\nDuran toplarda büyük fırsat var: rakip zonal savunmada ikinci direği (far-post) örtemiyor — son 8 maçta 4 gol yedi. Köşelerde far-post varyasyonu hazırlayın.\n\nDikkat: ilk 15 dakika yüksek pres bekleniyor. Ön libero geç çıksın, kaleci-stoper ilk pasında uzun seçeneği açık tutun.",
    tools: ["opponent_report", "matchup_engine", "set_piece_analyzer"],
  },
  {
    question: "67. dakikada momentum neden rakibe geçti?",
    answer:
      "Üç sinyal aynı anda işaret ediyor: (1) Momentum izleyici son 8 dakikada xG akışını -34'e çekti — rakip üst üste 2 korner kullandı. (2) Orkun Kökçü'ün 52. dakikadaki sakatlık sinyali sonrası orta sahada pres yoğunluğunuz %22 düştü. (3) Sol bek Rıdvan Yılmaz yorgunluk bandında ve rakip sağ kanat o koridordan sürekli giriyor.\n\nNet öneri: Orkun Kökçü → Junior Olaitan değişikliği (kritik aciliyet) + sol beke taze oyuncu. Bu iki hamle momentum'u dengeler; model güveni %83.",
    tools: ["momentum_tracker", "context_engine", "sub_timing"],
  },
];

// --------------------------------------------------------------------------- //
// KARARLAR — açıklanabilir karar kartları ("neden" sinyal zinciri)
// --------------------------------------------------------------------------- //

export type Urgency = "düşük" | "orta" | "yüksek" | "kritik";

export interface DecisionSignal {
  engine: string;      // kaynak motor
  label: string;       // okunur sinyal açıklaması
  sampleSize: number;  // kaç event/şut/düello destekliyor
  magnitude: number;   // 0..1 sinyal gücü
}

export interface DecisionCard {
  minute: number;
  headline: string;
  decisionType: "Oyuncu Değişikliği" | "Taktik" | "Risk" | "Duran Top";
  confidence: number;  // 0..100
  urgency: Urgency;
  rationale: string;
  signals: DecisionSignal[];
}

export const demoDecisions: DecisionCard[] = [
  {
    minute: 23,
    headline: "Sağ kanat 1v1'i sömür — Milot Rashica'e topu getir",
    decisionType: "Taktik",
    confidence: 76,
    urgency: "orta",
    rationale: "Rakip sağ bek yüksek konumlanıyor; sağ kanattaki hız üstünlüğü açık fırsat. Hücum yönünü o tarafa kaydır.",
    signals: [
      { engine: "matchup_engine", label: "Milot Rashica vs sol bek hız avantajı %72", sampleSize: 14, magnitude: 0.72 },
      { engine: "field_tilt", label: "Sağ koridordan girişler artıyor", sampleSize: 9, magnitude: 0.55 },
      { engine: "opponent_shape", label: "Rakip sağ bek arkası 6 kez açıldı", sampleSize: 6, magnitude: 0.48 },
    ],
  },
  {
    minute: 41,
    headline: "Duran topta far-post varyasyonu hazır olsun",
    decisionType: "Duran Top",
    confidence: 71,
    urgency: "orta",
    rationale: "Rakip zonal savunmada ikinci direği örtemiyor; köşe kazanımlarında far-post koşusu yüksek beklenen gol üretir.",
    signals: [
      { engine: "set_piece_analyzer", label: "Far-post zonal boşluk (son 8 maçta 4 gol)", sampleSize: 8, magnitude: 0.64 },
      { engine: "xg_model", label: "Far-post kafa xG'si 0.19 (lig ort. üstü)", sampleSize: 22, magnitude: 0.58 },
    ],
  },
  {
    minute: 52,
    headline: "Orkun Kökçü'ü yakın izle — sakatlık + yük riski",
    decisionType: "Risk",
    confidence: 80,
    urgency: "yüksek",
    rationale: "Arka adale sinyali + akut/kronik yük oranı eşik üstünde. Maç-içi yükü sınırla, değişiklik için hazırlan.",
    signals: [
      { engine: "live_risk_monitor", label: "Sakatlık sinyali: arka adale, 52. dk", sampleSize: 3, magnitude: 0.74 },
      { engine: "load_monitor", label: "ACWR 1.6 — akut yük zirvede", sampleSize: 12, magnitude: 0.69 },
      { engine: "physical_test_trend", label: "Sprint hızı 3 ölçüm üst üste düştü", sampleSize: 15, magnitude: 0.61 },
    ],
  },
  {
    minute: 67,
    headline: "Şimdi oyuncu değişikliği yap — Orkun Kökçü çıksın",
    decisionType: "Oyuncu Değişikliği",
    confidence: 83,
    urgency: "kritik",
    rationale: "Üç motor aynı anı işaret ediyor: momentum 3 dakikadır düşüyor, 8 numara sakatlık + kondisyon kritik eşikte, skor 1-1. Taze yaratıcılık (Junior Olaitan) momentum'u dengeler.",
    signals: [
      { engine: "momentum_tracker", label: "Momentum 8 dakikadır rakipte (-34)", sampleSize: 18, magnitude: 0.78 },
      { engine: "sub_timing", label: "8 numara kondisyon kritik eşikte (58)", sampleSize: 11, magnitude: 0.81 },
      { engine: "live_risk_monitor", label: "Sakatlık riski + yük zirvede", sampleSize: 9, magnitude: 0.7 },
    ],
  },
  {
    minute: 79,
    headline: "Skoru koru — blok düşür, geçişe çık",
    decisionType: "Taktik",
    confidence: 68,
    urgency: "orta",
    rationale: "Son 10 dakikada öne geçilirse: orta blok + kanatlardan geçiş. Rakip geç dakika tempo düşüşünü kontra ile cezalandır.",
    signals: [
      { engine: "score_time_matrix", label: "78+ dk önde: düşük blok reçetesi", sampleSize: 7, magnitude: 0.6 },
      { engine: "opponent_fatigue", label: "Rakip 75. dk sonrası PPDA +%30", sampleSize: 13, magnitude: 0.57 },
    ],
  },
];

// Karar özeti (sağ kolon)
export interface DecisionSummary {
  total: number;
  byType: { type: string; count: number }[];
  avgConfidence: number;
  mostCritical: DecisionCard;
}
export function demoDecisionSummary(): DecisionSummary {
  const byTypeMap: Record<string, number> = {};
  demoDecisions.forEach((d) => { byTypeMap[d.decisionType] = (byTypeMap[d.decisionType] ?? 0) + 1; });
  const avg = Math.round(demoDecisions.reduce((s, d) => s + d.confidence, 0) / demoDecisions.length);
  const order: Record<Urgency, number> = { "kritik": 4, "yüksek": 3, "orta": 2, "düşük": 1 };
  const mostCritical = [...demoDecisions].sort((a, b) => order[b.urgency] - order[a.urgency] || b.confidence - a.confidence)[0];
  return {
    total: demoDecisions.length,
    byType: Object.entries(byTypeMap).map(([type, count]) => ({ type, count })),
    avgConfidence: avg,
    mostCritical,
  };
}

// Risk dağılımı (overview donut için)
export function demoRiskDistribution() {
  const counts: Record<RiskLabel, number> = { "Düşük": 0, "Orta": 0, "Yüksek": 0, "Kritik": 0 };
  demoSquad.forEach((p) => { counts[p.risk_label] += 1; });
  return counts;
}
