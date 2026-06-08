/**
 * Demo veri katmanı — markasız "FK Demo" kulübü için gerçekçi sahte veri.
 *
 * Backend/internet GEREKTİRMEZ. `DEMO_MODE` açıkken sayfalar bu veriyi kullanır.
 * Tipler sayfaların beklediği canlı-API şekilleriyle uyumludur (PlayerRow,
 * PlayerSummary, PhysicalTest, RiskReport, PlanVsLive) + demo'ya özel zenginleştirmeler.
 *
 * İçerik tek bir kurgusal maç gününe odaklı: FK Demo vs Rakip SK.
 */

export const DEMO_CLUB = "FK Demo";
export const DEMO_OPPONENT = "Rakip SK";
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
  { player_id: 1, player_name: "Emre Çetin", position: "GK", pos_detail: "Kaleci", age: 29, condition: 92, risk_label: "Düşük", risk_score: 12, shirt: 1 },
  { player_id: 2, player_name: "Burak Yıldız", position: "DF", pos_detail: "Sağ Bek", age: 26, condition: 81, risk_label: "Orta", risk_score: 44, shirt: 2 },
  { player_id: 3, player_name: "Kerem Aslan", position: "DF", pos_detail: "Stoper", age: 31, condition: 74, risk_label: "Yüksek", risk_score: 68, shirt: 4 },
  { player_id: 4, player_name: "Mert Demir", position: "DF", pos_detail: "Stoper", age: 24, condition: 88, risk_label: "Düşük", risk_score: 19, shirt: 5 },
  { player_id: 5, player_name: "Onur Kaya", position: "DF", pos_detail: "Sol Bek", age: 28, condition: 69, risk_label: "Yüksek", risk_score: 71, shirt: 3 },
  { player_id: 6, player_name: "Serkan Polat", position: "MF", pos_detail: "Ön Libero", age: 27, condition: 84, risk_label: "Orta", risk_score: 38, shirt: 6 },
  { player_id: 7, player_name: "Yusuf Şahin", position: "MF", pos_detail: "Merkez OS", age: 23, condition: 90, risk_label: "Düşük", risk_score: 15, shirt: 8 },
  { player_id: 8, player_name: "Caner Öztürk", position: "MF", pos_detail: "10 Numara", age: 30, condition: 58, risk_label: "Kritik", risk_score: 86, shirt: 10 },
  { player_id: 9, player_name: "Hakan Arslan", position: "FW", pos_detail: "Sol Kanat", age: 25, condition: 79, risk_label: "Orta", risk_score: 41, shirt: 11 },
  { player_id: 10, player_name: "Doğan Yılmaz", position: "FW", pos_detail: "Santrfor", age: 27, condition: 86, risk_label: "Düşük", risk_score: 22, shirt: 9 },
  { player_id: 11, player_name: "Tolga Erdem", position: "FW", pos_detail: "Sağ Kanat", age: 22, condition: 91, risk_label: "Düşük", risk_score: 17, shirt: 7 },
  { player_id: 12, player_name: "Barış Koç", position: "GK", pos_detail: "Kaleci", age: 24, condition: 94, risk_label: "Düşük", risk_score: 8, shirt: 12 },
  { player_id: 13, player_name: "Eren Acar", position: "DF", pos_detail: "Stoper", age: 33, condition: 64, risk_label: "Yüksek", risk_score: 73, shirt: 15 },
  { player_id: 14, player_name: "Sinan Güneş", position: "DF", pos_detail: "Sağ Bek", age: 21, condition: 89, risk_label: "Düşük", risk_score: 20, shirt: 24 },
  { player_id: 15, player_name: "Volkan Taş", position: "MF", pos_detail: "Ön Libero", age: 29, condition: 76, risk_label: "Orta", risk_score: 47, shirt: 16 },
  { player_id: 16, player_name: "Cem Aydın", position: "MF", pos_detail: "Merkez OS", age: 26, condition: 83, risk_label: "Orta", risk_score: 35, shirt: 20 },
  { player_id: 17, player_name: "Arda Çelik", position: "MF", pos_detail: "Sol Kanat", age: 20, condition: 93, risk_label: "Düşük", risk_score: 11, shirt: 17 },
  { player_id: 18, player_name: "Uğur Bal", position: "FW", pos_detail: "Santrfor", age: 31, condition: 67, risk_label: "Yüksek", risk_score: 65, shirt: 19 },
  { player_id: 19, player_name: "Murat Şen", position: "FW", pos_detail: "Sağ Kanat", age: 24, condition: 85, risk_label: "Düşük", risk_score: 24, shirt: 21 },
  { player_id: 20, player_name: "Okan Yavuz", position: "DF", pos_detail: "Sol Bek", age: 27, condition: 80, risk_label: "Orta", risk_score: 43, shirt: 23 },
  { player_id: 21, player_name: "Berkay Doğan", position: "MF", pos_detail: "10 Numara", age: 23, condition: 87, risk_label: "Düşük", risk_score: 18, shirt: 14 },
  { player_id: 22, player_name: "Furkan Er", position: "DF", pos_detail: "Stoper", age: 25, condition: 82, risk_label: "Orta", risk_score: 39, shirt: 25 },
  { player_id: 23, player_name: "Selim Korkmaz", position: "FW", pos_detail: "Sol Kanat", age: 28, condition: 72, risk_label: "Yüksek", risk_score: 61, shirt: 18 },
  { player_id: 24, player_name: "İlkay Bozkurt", position: "GK", pos_detail: "Kaleci", age: 19, condition: 95, risk_label: "Düşük", risk_score: 6, shirt: 30 },
];

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
  { label: "Kritik Risk", value: "1", sub: "Caner Öztürk (8)" },
  { label: "Sıradaki Maç", value: "2 gün", sub: "Rakip SK (D)" },
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
};

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
  summary: "Rakip SK sağ bek arkasını boş bırakıyor; sol kanattan derinlik + 10 numara ile yarı-alan baskısı planlandı. Geçiş anlarında ön libero koruması kritik.",
  updated_at: "2026-06-08T18:42:00Z",
  plan_age_seconds: 540,
  status: "Hazır",
  active_scenario: "level",   // sayfa anahtarı: leading|level|trailing
  matchup_recommendation: "Tolga Erdem (7) vs rakip sol bek: hız avantajı %72 — bu eşleşmeyi sömür",
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
  { ours: "Tolga Erdem (7) — Sağ Kanat", theirs: "Sol Bek", advantage: 72, note: "1v1 hız ve dripling üstünlüğü" },
  { ours: "Doğan Yılmaz (9) — Santrfor", theirs: "Stoper ikilisi", advantage: 58, note: "Hava topu ve derinlik tehdidi" },
  { ours: "Yusuf Şahin (8) — Merkez", theirs: "6 Numara", advantage: 63, note: "Pres kırma ve ileri pas kalitesi" },
  { ours: "Onur Kaya (3) — Sol Bek", theirs: "Sağ Kanat", advantage: 41, note: "Savunmada zorlanabilir — destek gerekli" },
];

export interface Scenario { state: "Öndeyiz" | "Berabere" | "Geride"; plan: string; subs: string }
export const demoScenarios: Scenario[] = [
  { state: "Öndeyiz", plan: "Blok düşür, geçişe çık. Kanat oyuncuları savunmaya yardım etsin.", subs: "Taze stoper + savunma 6 numarası" },
  { state: "Berabere", plan: "Ritmi koru, sağ kanat 1v1'i sömür. Duran toplarda far-post.", subs: "Berkay Doğan (14) ile yaratıcılık" },
  { state: "Geride", plan: "İkinci santrfor + yüksek blok. Kanatlardan bol orta.", subs: "Uğur Bal (19) — hava topu hedefi" },
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
    { minute: 12, type: "buyuk_firsat", team: "home", text: "Tolga Erdem sağdan içeri kat etti, vuruş direkten döndü (xG 0.31)." },
    { minute: 23, type: "gol", team: "home", text: "GOL! Doğan Yılmaz ceza sahasında topla buluştu ve ağları havalandırdı. 1-0." },
    { minute: 31, type: "sari_kart", team: "home", text: "Kerem Aslan geç müdahaleden sarı kart gördü." },
    { minute: 38, type: "buyuk_firsat", team: "away", text: "Rakip SK kontra atağında kaleci Emre Çetin kurtardı." },
    { minute: 45, type: "gol", team: "away", text: "GOL! Rakip SK köşe vuruşunda far-post'ta boş kaldı, kafa golü. 1-1." },
    { minute: 46, type: "degisiklik", team: "home", text: "Değişiklik: Hakan Arslan (11) çıktı, Arda Çelik (17) girdi — sol kanada tazelik." },
    { minute: 52, type: "sakatlik", team: "home", text: "Caner Öztürk arka adalesini tuttu; sağlık ekibi sahada." },
    { minute: 58, type: "sari_kart", team: "away", text: "Rakip 6 numara taktik faulden sarı gördü." },
    { minute: 64, type: "buyuk_firsat", team: "away", text: "Rakip SK üst üste 2 korner kullandı; momentum onlarda." },
  ],
  subs: [
    {
      player_out: "Caner Öztürk (10)",
      player_in: "Berkay Doğan (14)",
      urgency: "kritik",
      rationale: "8 numara sakatlık sinyali + kondisyon kritik eşikte (58). Momentum 3 dakikadır rakipte. Şimdi taze yaratıcılık şart.",
    },
    {
      player_out: "Onur Kaya (3)",
      player_in: "Okan Yavuz (23)",
      urgency: "yüksek",
      rationale: "Sol bek yorgunluk bandında; rakip sağ kanat bu koridordan sürekli giriyor. Savunma istikrarı için değişiklik.",
    },
  ],
  // 67. dakikaya kadarki saha durumu. minutes = gerçek oynanan dakika;
  // vaepPer90 = vaep / minutes * 90 → kısa süre oynayan etkili oyuncu (Arda) öne çıkar.
  lineup: [
    { shirt: 1,  name: "Emre Çetin",   pos: "GK", onPitch: true,  minutes: 67, vaep: 0.02, vaepPer90: 0.03 },
    { shirt: 2,  name: "Burak Yıldız", pos: "RB", onPitch: true,  minutes: 67, vaep: 0.07, vaepPer90: 0.09 },
    { shirt: 4,  name: "Kerem Aslan",  pos: "CB", onPitch: true,  minutes: 67, vaep: 0.05, vaepPer90: 0.07 },
    { shirt: 5,  name: "Mert Demir",   pos: "CB", onPitch: true,  minutes: 67, vaep: 0.06, vaepPer90: 0.08 },
    { shirt: 3,  name: "Onur Kaya",    pos: "LB", onPitch: true,  minutes: 67, vaep: 0.04, vaepPer90: 0.05 },
    { shirt: 6,  name: "Serkan Polat", pos: "DM", onPitch: true,  minutes: 67, vaep: 0.09, vaepPer90: 0.12 },
    { shirt: 8,  name: "Yusuf Şahin",  pos: "CM", onPitch: true,  minutes: 67, vaep: 0.17, vaepPer90: 0.23 },
    { shirt: 10, name: "Caner Öztürk", pos: "AM", onPitch: true,  minutes: 67, vaep: 0.21, vaepPer90: 0.28 },
    { shirt: 17, name: "Arda Çelik",   pos: "LW", onPitch: true,  minutes: 21, vaep: 0.18, vaepPer90: 0.77, subbedInMinute: 46 },
    { shirt: 9,  name: "Doğan Yılmaz", pos: "ST", onPitch: true,  minutes: 67, vaep: 0.34, vaepPer90: 0.46 },
    { shirt: 7,  name: "Tolga Erdem",  pos: "RW", onPitch: true,  minutes: 67, vaep: 0.29, vaepPer90: 0.39 },
    { shirt: 11, name: "Hakan Arslan", pos: "LW", onPitch: false, minutes: 46, vaep: 0.05, vaepPer90: 0.10, subbedOutMinute: 46 },
  ],
};

// --------------------------------------------------------------------------- //
// AI ASİSTAN — hazır soru-cevap çiftleri
// --------------------------------------------------------------------------- //

export interface ChatQA { question: string; answer: string; tools: string[] }
export const demoChatQA: ChatQA[] = [
  {
    question: "Bu hafta sakatlık riski en yüksek oyuncular kim?",
    answer:
      "En yüksek risk Caner Öztürk (10) — KRİTİK. Akut/kronik yük oranı 1.6 (eşik 1.5 üstü) ve son 3 ölçümde sprint hızı düştü; kondisyonu 58. Bu maç için 60. dakika sonrası değişiklik öneriyorum.\n\nİkinci grup Yüksek risk: Onur Kaya (3), Kerem Aslan (4) ve Eren Acar (15). Üçü de ACWR 1.4 bandında ve dikey sıçramada yorgunluk işareti var.\n\nDüşük risk tarafında kadronun %58'i tam maç yüküne hazır; rotasyon için Arda Çelik (17) ve Sinan Güneş (24) ideal.",
    tools: ["load_risk_monitor", "physical_test_trend", "squad_availability"],
  },
  {
    question: "Rakip SK'ya karşı hangi taktiği önerirsin?",
    answer:
      "Rakip SK sağ bekini hücumda yüksek tutuyor; arkasındaki koridor maç başına ortalama 6 kez açılıyor. Tolga Erdem'i (7) o tarafa koyup hız avantajını (%72) sömürmenizi öneriyorum.\n\nDuran toplarda büyük fırsat var: rakip zonal savunmada ikinci direği (far-post) örtemiyor — son 8 maçta 4 gol yedi. Köşelerde far-post varyasyonu hazırlayın.\n\nDikkat: ilk 15 dakika yüksek pres bekleniyor. Ön libero geç çıksın, kaleci-stoper ilk pasında uzun seçeneği açık tutun.",
    tools: ["opponent_report", "matchup_engine", "set_piece_analyzer"],
  },
  {
    question: "67. dakikada momentum neden rakibe geçti?",
    answer:
      "Üç sinyal aynı anda işaret ediyor: (1) Momentum izleyici son 8 dakikada xG akışını -34'e çekti — rakip üst üste 2 korner kullandı. (2) Caner Öztürk'ün 52. dakikadaki sakatlık sinyali sonrası orta sahada pres yoğunluğunuz %22 düştü. (3) Sol bek Onur Kaya yorgunluk bandında ve rakip sağ kanat o koridordan sürekli giriyor.\n\nNet öneri: Caner Öztürk → Berkay Doğan değişikliği (kritik aciliyet) + sol beke taze oyuncu. Bu iki hamle momentum'u dengeler; model güveni %83.",
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
    headline: "Sağ kanat 1v1'i sömür — Tolga Erdem'e topu getir",
    decisionType: "Taktik",
    confidence: 76,
    urgency: "orta",
    rationale: "Rakip sağ bek yüksek konumlanıyor; sağ kanattaki hız üstünlüğü açık fırsat. Hücum yönünü o tarafa kaydır.",
    signals: [
      { engine: "matchup_engine", label: "Tolga Erdem vs sol bek hız avantajı %72", sampleSize: 14, magnitude: 0.72 },
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
    headline: "Caner Öztürk'ü yakın izle — sakatlık + yük riski",
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
    headline: "Şimdi oyuncu değişikliği yap — Caner Öztürk çıksın",
    decisionType: "Oyuncu Değişikliği",
    confidence: 83,
    urgency: "kritik",
    rationale: "Üç motor aynı anı işaret ediyor: momentum 3 dakikadır düşüyor, 8 numara sakatlık + kondisyon kritik eşikte, skor 1-1. Taze yaratıcılık (Berkay Doğan) momentum'u dengeler.",
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
