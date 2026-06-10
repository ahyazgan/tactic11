/**
 * Hazırlık Kararı — backend `assess_readiness` motorunun TS aynası.
 *
 * Eşikler app/engine/performance_test/compute.py ile BİREBİR. DEMO_MODE'da
 * hesap burada yapılır; backend açıkken POST /physical-tests/readiness aynı
 * kararı döner. Canlı maç "Sıradaki En İyi Hamle" sentezinin test karşılığı:
 * bir oyuncunun türetilmiş test metriklerini tek oynat/oynatma kararına indirger.
 */

import { demoSquad, type SquadPlayer } from "@/lib/demo-data";
import type { SavedRecord } from "@/lib/derived-tests";
import { acwrForPlayer, type LoadSession } from "@/lib/load";
import {
  latestWellnessFor, wellnessReadiness, wellnessZone, type WellnessEntry,
} from "@/lib/wellness";
import { detectRegression, demoRegressionSeriesFor, type RegressionSeries } from "@/lib/regression";

export type Light = "kırmızı" | "sarı" | "yeşil";

export interface ReadinessFlag {
  metric: string;
  engine: string;
  severity: Light;
  value: string;
  threshold: string;
  action: string;
}

export interface ReadinessDecision {
  light: Light;
  verdict: string;
  red_count: number;
  yellow_count: number;
  checked: number;
  flags: ReadinessFlag[];
  summary: string;
}

// ── Eşikler (compute.py ile birebir) ──────────────────────────────────────
const RTP_GREEN = 95.0;
const HQ_IDEAL = 0.6, HQ_RISK = 0.47;
const ASYM_WARN = 10.0, ASYM_HIGH = 15.0;
const RSA_FLAG = 7.0;
const COD_FLAG = 1.0;
const ADDUCTOR_FLAG = 10.0;
const CMJ_FLAG = 10.0;
const ACWR_MIN = 0.8, ACWR_MAX = 1.3, ACWR_HIGH = 1.5;

const VERDICT: Record<Light, string> = {
  "kırmızı": "sahaya çıkmasın",
  "sarı": "izle / yük yönet",
  "yeşil": "tam maça hazır",
};
const LIGHT_RANK: Record<Light, number> = { "kırmızı": 0, "sarı": 1, "yeşil": 2 };

export const LIGHT_VAR: Record<Light, string> = {
  "kırmızı": "var(--crit)", "sarı": "var(--mid)", "yeşil": "var(--low)",
};

const fmt = (n: number) => String(Math.round(n * 1000) / 1000);

export interface ReadinessInput {
  rtp?: { current: number; baseline: number; higherIsBetter: boolean };
  hq?: { hamstring: number; quadriceps: number };
  asymmetry?: { left: number; right: number; label: string };
  rsa?: number[];
  cod?: { codTime: number; linear10m: number };
  adductor?: { current: number; previous: number };
  cmj?: { current: number; baseline: number[] };
  acwr?: number;
  wellness?: { sleep_quality: number; fatigue: number; muscle_soreness: number; stress: number; mood: number };
  regression?: RegressionSeries[];
}

/** assess_readiness aynası — verilen her metrik flag'lenir, en kötü severity karar. */
export function assessReadiness(input: ReadinessInput): ReadinessDecision {
  const flags: ReadinessFlag[] = [];

  if (input.rtp) {
    const { current, baseline, higherIsBetter } = input.rtp;
    const ratio = higherIsBetter ? current / baseline : baseline / current;
    const pct = Math.round(ratio * 1000) / 10;
    const cleared = pct >= RTP_GREEN;
    flags.push({
      metric: "RTP", engine: "return_to_play_readiness",
      severity: cleared ? "yeşil" : "kırmızı",
      value: `baseline'ın %${fmt(pct)}'i`,
      threshold: `≥%${fmt(RTP_GREEN)} yeşil`,
      action: cleared ? "Hazır"
        : "Rehaba devam — baseline'a ulaşmadan oynatma.",
    });
  }

  if (input.hq) {
    const ratio = Math.round((input.hq.hamstring / input.hq.quadriceps) * 1000) / 1000;
    const band = ratio >= HQ_IDEAL ? "ideal" : ratio >= HQ_RISK ? "sınırda" : "yüksek risk";
    const sev: Light = band === "ideal" ? "yeşil" : band === "sınırda" ? "sarı" : "kırmızı";
    flags.push({
      metric: "H:Q", engine: "hamstring_quad_ratio", severity: sev,
      value: `${fmt(ratio)} (${band})`,
      threshold: `≥${fmt(HQ_IDEAL)} ideal · <${fmt(HQ_RISK)} risk`,
      action: sev === "yeşil" ? "Denge iyi"
        : "Eksantrik hamstring çalışması; <0.47'de yükü sınırla.",
    });
  }

  if (input.asymmetry) {
    const { left, right, label } = input.asymmetry;
    const hi = Math.max(left, right);
    const asym = Math.round((Math.abs(left - right) / hi) * 10000) / 100;
    const side = Math.abs(left - right) < 1e-9 ? "denge" : left > right ? "sol" : "sağ";
    const sev: Light = asym > ASYM_HIGH ? "kırmızı" : asym > ASYM_WARN ? "sarı" : "yeşil";
    flags.push({
      metric: label ? `Asimetri (${label})` : "Asimetri",
      engine: "limb_asymmetry", severity: sev,
      value: `%${fmt(asym)} (güçlü: ${side})`,
      threshold: `>%${fmt(ASYM_WARN)} sarı · >%${fmt(ASYM_HIGH)} kırmızı`,
      action: sev === "yeşil" ? "Denge iyi"
        : "Tek-bacak düzeltici program; tekrar sakatlanma riski.",
    });
  }

  if (input.rsa && input.rsa.length >= 2) {
    const best = Math.min(...input.rsa);
    const total = input.rsa.reduce((a, b) => a + b, 0);
    const fi = Math.round(((total / (best * input.rsa.length)) - 1) * 10000) / 100;
    const flagged = fi > RSA_FLAG;
    flags.push({
      metric: "RSA", engine: "repeated_sprint_fatigue_index",
      severity: flagged ? "sarı" : "yeşil",
      value: `FI %${fmt(fi)}`,
      threshold: `>%${fmt(RSA_FLAG)} yetersiz toparlanma`,
      action: flagged ? "Tekrarlı sprint + toparlanma bloğu." : "Dayanıklılık iyi",
    });
  }

  if (input.cod) {
    const deficit = Math.round((input.cod.codTime - input.cod.linear10m) * 1000) / 1000;
    const poor = deficit > COD_FLAG;
    flags.push({
      metric: "COD", engine: "change_of_direction_deficit",
      severity: poor ? "sarı" : "yeşil",
      value: `${fmt(deficit)}sn açık`,
      threshold: `>${fmt(COD_FLAG)}sn zayıf frenleme`,
      action: poor ? "Frenleme/deselerasyon çalışması." : "Yön değiştirme iyi",
    });
  }

  if (input.adductor) {
    const drop = Math.round(((input.adductor.previous - input.adductor.current) / input.adductor.previous) * 10000) / 100;
    const flagged = drop > ADDUCTOR_FLAG;
    flags.push({
      metric: "Adductor", engine: "adductor_squeeze_drop",
      severity: flagged ? "sarı" : "yeşil",
      value: `%${fmt(drop)} düşüş`,
      threshold: `>%${fmt(ADDUCTOR_FLAG)} kasık/pubis riski`,
      action: flagged ? "Kasık yükünü azalt; pubis riski." : "Kasık kuvveti iyi",
    });
  }

  if (input.cmj && input.cmj.baseline.length) {
    const bmean = input.cmj.baseline.reduce((a, b) => a + b, 0) / input.cmj.baseline.length;
    const drop = Math.round(((bmean - input.cmj.current) / bmean) * 10000) / 100;
    const flagged = drop > CMJ_FLAG;
    flags.push({
      metric: "CMJ", engine: "cmj_neuromuscular_drop",
      severity: flagged ? "sarı" : "yeşil",
      value: `baseline'a göre %${fmt(drop)}`,
      threshold: `>%${fmt(CMJ_FLAG)} nöromusküler yorgunluk`,
      action: flagged ? "Yükü azalt — nöromusküler yorgunluk." : "Toparlanma tam",
    });
  }

  if (input.acwr != null) {
    let sev: Light, act: string;
    if (input.acwr > ACWR_HIGH) { sev = "kırmızı"; act = "Akut yük zirvede — rotasyon / erken çıkış."; }
    else if (input.acwr > ACWR_MAX) { sev = "sarı"; act = "Yük artışı dik — antrenman hacmini düşür."; }
    else if (input.acwr < ACWR_MIN) { sev = "sarı"; act = "Düşük yük — maç temposuna kademeli hazırla."; }
    else { sev = "yeşil"; act = "Yük dengeli"; }
    flags.push({
      metric: "ACWR", engine: "acwr_band", severity: sev,
      value: `${Math.round(input.acwr * 100) / 100}`,
      threshold: `tatlı bölge ${fmt(ACWR_MIN)}–${fmt(ACWR_MAX)} · >${fmt(ACWR_HIGH)} kırmızı`,
      action: act,
    });
  }

  if (input.wellness) {
    const readiness = wellnessReadiness(input.wellness);
    const zone = wellnessZone(readiness);
    const sev: Light = zone === "hazır" ? "yeşil" : zone === "izle" ? "sarı" : "kırmızı";
    flags.push({
      metric: "Wellness", engine: "compute_wellness", severity: sev,
      value: `hazırlık %${Math.round(readiness * 100)} (${zone})`,
      threshold: "≥%70 hazır · %55-70 izle · <%55 dikkat",
      action: sev === "yeşil" ? "Öznel hazırlık iyi" : "Uyku/yorgunluk düşük — yükü gözden geçir.",
    });
  }

  if (input.regression?.length) {
    const dropped = input.regression
      .filter((x) => detectRegression(x.values, x.higherIsBetter))
      .map((x) => x.protocol);
    if (dropped.length) {
      flags.push({
        metric: "Regresyon", engine: "interpret_progression", severity: "sarı",
        value: dropped.join(", "),
        threshold: "ani düşüş (≥1σ kırılma)",
        action: "Ani performans düşüşü — aşırı yük/sakatlık kontrolü.",
      });
    }
  }

  flags.sort((a, b) => LIGHT_RANK[a.severity] - LIGHT_RANK[b.severity]);
  const red = flags.filter((x) => x.severity === "kırmızı").length;
  const yellow = flags.filter((x) => x.severity === "sarı").length;

  let light: Light;
  let summary: string;
  if (!flags.length) {
    light = "sarı";
    summary = "Değerlendirilecek test verisi yok — karar verilemez.";
  } else if (red) {
    light = "kırmızı";
    const top = flags.filter((x) => x.severity === "kırmızı").map((x) => x.metric).join(", ");
    summary = `${red} kırmızı: ${top}`;
  } else if (yellow) {
    light = "sarı";
    const top = flags.filter((x) => x.severity === "sarı").map((x) => x.metric).join(", ");
    summary = `${yellow} sarı: ${top} — yük yönet`;
  } else {
    light = "yeşil";
    summary = `${flags.length} metrik · hepsi yeşil`;
  }

  return {
    light, verdict: VERDICT[light], red_count: red, yellow_count: yellow,
    checked: flags.length, flags, summary,
  };
}

// ── Demo: kadro test metriklerini risk profilinden deterministik türet ─────
// Yüksek risk → kötü metrik. Çıktı assessReadiness'ten geçer (canlı motorla aynı).

function demoInputFor(p: SquadPlayer): ReadinessInput {
  const r = p.risk_score / 100;             // 0..1
  // H:Q: ratio 0.66 (düşük risk) → 0.36 (yüksek risk)
  const hqRatio = 0.66 - r * 0.3;
  // Asimetri %: 3 → 19
  const asym = 3 + r * 16;
  // ACWR: 0.85 → 1.65
  const acwr = Math.round((0.85 + r * 0.8) * 100) / 100;
  // CMJ MD+1 düşüş %: 0 → 14
  const cmjDrop = r * 14;
  const cmjBaseline = [50, 51, 49];
  const input: ReadinessInput = {
    hq: { hamstring: Math.round(hqRatio * 3.0 * 1000) / 1000, quadriceps: 3.0 },
    asymmetry: { left: 600, right: Math.round(600 * (1 - asym / 100) * 100) / 100, label: "Triple Hop" },
    acwr,
    cmj: { current: Math.round(50 * (1 - cmjDrop / 100) * 10) / 10, baseline: cmjBaseline },
  };
  // Sakatlık dönüşü (Kritik): RTP baseline'ın altında → kırmızı ışık.
  if (p.risk_label === "Kritik") {
    input.rtp = { current: 88, baseline: 100, higherIsBetter: true };
  }
  return input;
}

/** Bir oyuncunun hazırlık kararı (demo: risk profilinden türev). */
export function demoReadinessFor(playerId: number): ReadinessDecision {
  const p = demoSquad.find((s) => s.player_id === playerId);
  if (!p) return assessReadiness({});
  return assessReadiness(demoInputFor(p));
}

// ── Girilen test kayıtlarından (Test Hesaplayıcı) gerçek readiness girdisi ──
// Test Hesaplayıcı'da kaydedilen türetilmiş metrikler `components`'te ham girdiyi
// saklar; bunları assess_readiness girdisine çeviriyoruz. Böylece karar verici
// deterministik demo profili yerine GERÇEK girilen veriyle çalışır.

const numOf = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

const numArrOf = (v: unknown): number[] | null =>
  Array.isArray(v) && v.every((x) => typeof x === "number") ? (v as number[]) : null;

/** Bir oyuncunun kayıtlarından ReadinessInput kur (protokol başına en son). null = eşlenebilir kayıt yok. */
export function inputFromRecords(records: SavedRecord[]): ReadinessInput | null {
  if (!records.length) return null;
  const latest = [...records].sort((a, b) => b.id - a.id);
  const pick = (proto: string) => latest.find((r) => r.protocol === proto);
  const input: ReadinessInput = {};
  let any = false;

  // H:Q: ya tek kayıtta (derive: components.quadriceps), ya da ayrı
  // isokinetic_ham + isokinetic_quad kayıtlarından (CSV toplu import).
  const hq = pick("isokinetic_ham");
  if (hq) {
    const quadRec = pick("isokinetic_quad");
    const quad = numOf(hq.components.quadriceps) ?? (quadRec ? quadRec.value : null);
    if (quad != null && quad > 0) { input.hq = { hamstring: hq.value, quadriceps: quad }; any = true; }
  }

  const asym = pick("triple_hop");
  const left = asym && numOf(asym.components.left);
  const right = asym && numOf(asym.components.right);
  if (asym && left != null && right != null) { input.asymmetry = { left, right, label: "Triple Hop" }; any = true; }

  const rsa = pick("rsa");
  const times = rsa && numArrOf(rsa.components.sprint_times);
  if (rsa && times && times.length >= 2) { input.rsa = times; any = true; }

  const cod = pick("t505");
  const lin = cod && numOf(cod.components.linear_10m);
  if (cod && lin != null && lin > 0 && cod.value > 0) { input.cod = { codTime: cod.value, linear10m: lin }; any = true; }

  const add = pick("adductor_squeeze");
  const prev = add && numOf(add.components.previous);
  if (add && prev != null && prev > 0) { input.adductor = { current: add.value, previous: prev }; any = true; }

  const cmj = pick("cmj");
  const base = cmj && numArrOf(cmj.components.baseline_values);
  if (cmj && base && base.length) { input.cmj = { current: cmj.value, baseline: base }; any = true; }

  return any ? input : null;
}

/** Oyuncunun girilen kayıtlarından hazırlık kararı. null = girilen veri yok (demo'ya düş). */
export function enteredReadinessFor(playerId: number, records: SavedRecord[]): ReadinessDecision | null {
  const mine = records.filter((r) => String(r.player_id) === String(playerId));
  const input = inputFromRecords(mine);
  return input ? assessReadiness(input) : null;
}

export interface SquadReadinessRow {
  player: SquadPlayer;
  decision: ReadinessDecision;
  source: "entered" | "demo";   // karar gerçek girilen veriden mi, demo profilinden mi
}

/** Tüm kadro: girilen test + yük (ACWR) varsa onlardan, yoksa demo profili. Kırmızı önce. */
export function squadReadiness(
  records: SavedRecord[] = [], loads: LoadSession[] = [], wellness: WellnessEntry[] = [],
): SquadReadinessRow[] {
  return demoSquad
    .map((player): SquadReadinessRow => {
      const recInput = inputFromRecords(
        records.filter((r) => String(r.player_id) === String(player.player_id)));
      const acwr = acwrForPlayer(player.player_id, loads);
      const we = latestWellnessFor(player.player_id, wellness);
      const hasEntered = !!(recInput || acwr != null || we);
      const input: ReadinessInput = hasEntered ? { ...(recInput ?? {}) } : demoInputFor(player);
      if (acwr != null) input.acwr = acwr;
      if (we) {
        input.wellness = {
          sleep_quality: we.sleep_quality, fatigue: we.fatigue,
          muscle_soreness: we.muscle_soreness, stress: we.stress, mood: we.mood,
        };
      }
      // Regresyon serisi (demo: risk-tabanlı; gerçek modda backend test geçmişinden).
      input.regression = demoRegressionSeriesFor(player.player_id);
      return { player, decision: assessReadiness(input), source: hasEntered ? "entered" : "demo" };
    })
    .sort((a, b) =>
      LIGHT_RANK[a.decision.light] - LIGHT_RANK[b.decision.light]
      || b.player.risk_score - a.player.risk_score,
    );
}

/** Geriye dönük uyum: girilen kayıt yokken tüm kadro demo profilinden. */
export function demoSquadReadiness(): SquadReadinessRow[] {
  return squadReadiness([]);
}
