/**
 * Hazırlık Kararı — backend `assess_readiness` motorunun TS aynası.
 *
 * Eşikler app/engine/performance_test/compute.py ile BİREBİR. DEMO_MODE'da
 * hesap burada yapılır; backend açıkken POST /physical-tests/readiness aynı
 * kararı döner. Canlı maç "Sıradaki En İyi Hamle" sentezinin test karşılığı:
 * bir oyuncunun türetilmiş test metriklerini tek oynat/oynatma kararına indirger.
 */

import { demoSquad, type SquadPlayer } from "@/lib/demo-data";

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
      threshold: `≥%${fmt(RTP_GREEN)} yeşil ışık`,
      action: cleared ? "sahaya hazır"
        : "sahaya çıkmasın — rehabilitasyona devam, baseline'a ulaşsın",
    });
  }

  if (input.hq) {
    const ratio = Math.round((input.hq.hamstring / input.hq.quadriceps) * 1000) / 1000;
    const band = ratio >= HQ_IDEAL ? "ideal" : ratio >= HQ_RISK ? "sınırda" : "yüksek_risk";
    const sev: Light = band === "ideal" ? "yeşil" : band === "sınırda" ? "sarı" : "kırmızı";
    flags.push({
      metric: "H:Q", engine: "hamstring_quad_ratio", severity: sev,
      value: `${fmt(ratio)} (${band})`,
      threshold: `≥${fmt(HQ_IDEAL)} ideal · <${fmt(HQ_RISK)} risk`,
      action: sev === "yeşil" ? "denge iyi"
        : "eksantrik hamstring güçlendirme; <0.47 ise maç yükünü sınırla",
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
      action: sev === "yeşil" ? "denge iyi"
        : "tek-bacak düzeltici program; yeniden-sakatlanma riski",
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
      action: flagged ? "tekrarlı sprint + toparlanma bloğu" : "anaerobik dayanıklılık iyi",
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
      action: poor ? "frenleme/deceleration mekaniği çalışması" : "yön değiştirme iyi",
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
      action: flagged ? "kasık yükünü azalt, MD+1 takip; kasık/pubis riski" : "kasık kuvveti iyi",
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
      action: flagged ? "yükü azalt; nöromusküler yorgunluk" : "toparlanma tam",
    });
  }

  if (input.acwr != null) {
    let sev: Light, act: string;
    if (input.acwr > ACWR_HIGH) { sev = "kırmızı"; act = "akut yük zirvede — rotasyon / erken çıkış planla"; }
    else if (input.acwr > ACWR_MAX) { sev = "sarı"; act = "yük artışı dik — antrenman hacmini düşür"; }
    else if (input.acwr < ACWR_MIN) { sev = "sarı"; act = "düşük yük — maç temposuna kademeli hazırla"; }
    else { sev = "yeşil"; act = "yük dengeli"; }
    flags.push({
      metric: "ACWR", engine: "acwr_band", severity: sev,
      value: `${Math.round(input.acwr * 100) / 100}`,
      threshold: `tatlı bölge ${fmt(ACWR_MIN)}–${fmt(ACWR_MAX)} · >${fmt(ACWR_HIGH)} kırmızı`,
      action: act,
    });
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
    summary = `${red} kırmızı bayrak (${top}) — sahaya çıkmasın.`;
  } else if (yellow) {
    light = "sarı";
    const top = flags.filter((x) => x.severity === "sarı").map((x) => x.metric).join(", ");
    summary = `${yellow} sarı bayrak (${top}) — oynayabilir, yük yönetilmeli.`;
  } else {
    light = "yeşil";
    summary = `${flags.length} metrik kontrol edildi, hepsi yeşil — tam maça hazır.`;
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

export interface SquadReadinessRow {
  player: SquadPlayer;
  decision: ReadinessDecision;
}

/** Tüm kadro: kırmızı önce, sonra sarı/yeşil; eşitlikte risk skoru. */
export function demoSquadReadiness(): SquadReadinessRow[] {
  return demoSquad
    .map((player) => ({ player, decision: assessReadiness(demoInputFor(player)) }))
    .sort((a, b) =>
      LIGHT_RANK[a.decision.light] - LIGHT_RANK[b.decision.light]
      || b.player.risk_score - a.player.risk_score,
    );
}
