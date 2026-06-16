/**
 * Karar Kanıt Defteri — kadro/sakatlık gibi BACKTEST EDİLEMEYEN motorların
 * zamanla kendi güvenini kazanması için mekanizma.
 *
 * Maç sonucu motoru gerçek geçmiş maçlarla doğrulandı (bkz. /calibration, güven
 * 76). Ama sakatlık/kadro kararlarının "doğru cevabı" ancak GELECEKTE belli olur
 * (oyuncu gerçekten sakatlandı mı, dinlendirme işe yaradı mı). Bu modül her motorun
 * ŞU AN yaptığı FALSİFİYE EDİLEBİLİR iddiaları kaydeder + nasıl reconcile
 * edileceğini yazar. Gerçek sonuç akınca (Sportmonks/gerçek sezon) defter dolar ve
 * her motor kendi "%X tuttu" rakamını kazanır.
 *
 * DÜRÜSTLÜK: demo'da gerçek sonuç akışı yok → resolved=0. SAHTE sonuç ÜRETİLMEZ;
 * "birikiyor, veri bekleniyor" açıkça gösterilir. (Eski demoPredictionLedger'ın
 * hash-uydurma yaklaşımının tersi.)
 */

import { topRiskPlayers } from "@/lib/injury-risk";
import { squadAvailability } from "@/lib/lineup-advice";
import { demoNextMatchSimulation } from "@/lib/match-simulation";
import { VALIDATED_TRUST } from "@/lib/validated-trust";

export type LedgerEngine = "match" | "injury" | "lineup";

export interface OpenClaim {
  subject: string;     // "Orkun Kökçü (10)" / "Beşiktaş vs Antalyaspor"
  claim: string;       // falsifiye edilebilir iddia
  confidence: number;  // 0..1
  horizon: string;     // "14 gün" / "maç günü"
}

export interface EngineLedger {
  engine: LedgerEngine;
  title: string;
  validated: boolean;      // maç=true (backtest), diğerleri=false
  trust: number | null;    // doğrulanmış güven ya da null
  open: OpenClaim[];       // motorun ŞU AN yaptığı gerçek tahminler
  resolved: number;        // sonuçlanmış (demo=0)
  hitRate: number | null;  // yeterli sonuç olana dek null
  resolveRule: string;     // gerçek veri hit/miss'i nasıl işaretler
  needNote: string;        // hangi veri gerekli
}

const sn = (name: string) => name.trim().split(/\s+/).slice(-1)[0];

/** Sakatlık motoru — şu an yüksek/kritik risk işaretlediği oyuncular. */
function injuryLedger(): EngineLedger {
  const open: OpenClaim[] = topRiskPlayers(6)
    .filter((r) => r.risk.level === "high" || r.risk.level === "crit")
    .map((r) => ({
      subject: `${sn(r.player.player_name)} (${r.player.shirt})`,
      claim: `Önümüzdeki 14 günde yüksek sakatlık/yük riski (endeks ${r.risk.score})`,
      confidence: Math.round(r.risk.score) / 100,
      horizon: "14 gün",
    }));
  return {
    engine: "injury", title: "Sakatlık Riski", validated: false, trust: null,
    open, resolved: 0, hitRate: null,
    resolveRule: "14 gün içinde oyuncu gerçekten kas/yük kaynaklı maç kaçırdı mı? Evet → isabet.",
    needNote: "Gerçek sakatlık zaman serisi + yük/giyilebilir veri gerekir.",
  };
}

/** Kadro motoru — şu an dinlendirme/rotasyon önerdiği oyuncular. */
function lineupLedger(): EngineLedger {
  const open: OpenClaim[] = squadAvailability()
    .filter((a) => a.verdict === "dinlendir" || a.verdict === "rotasyon")
    .slice(0, 6)
    .map((a) => ({
      subject: `${sn(a.player.player_name)} (${a.player.shirt})`,
      claim: a.verdict === "dinlendir"
        ? `Bu maçta dinlendirilmeli (risk ${a.risk.score})`
        : `Rotasyona alınmalı / dakika sınırlı (risk ${a.risk.score})`,
      confidence: Math.round(a.risk.score) / 100,
      horizon: "maç günü",
    }));
  return {
    engine: "lineup", title: "Kadro / Rotasyon", validated: false, trust: null,
    open, resolved: 0, hitRate: null,
    resolveRule: "Öneri uygulandığında oyuncu fit kaldı + sonuç beklentiyi tuttu mu? İhlal edilip sakatlanırsa öneri doğrulanır.",
    needNote: "Kim gerçekten oynadı + maç sonucu eşli veri gerekir.",
  };
}

/** Maç sonucu motoru — DOĞRULANMIŞ (backtest, güven 76). Açık tahmin: sıradaki maç. */
function matchLedger(): EngineLedger {
  const sim = demoNextMatchSimulation();
  return {
    engine: "match", title: "Maç Sonucu", validated: true, trust: VALIDATED_TRUST.result,
    open: [{
      subject: `${sim.homeTeam} vs ${sim.awayTeam}`,
      claim: `${sim.homeTeam} galibiyeti %${Math.round(sim.probHomeWin * 100)} · en olası ${sim.mostLikelyScore[0]}-${sim.mostLikelyScore[1]}`,
      confidence: sim.probHomeWin,
      horizon: "maç günü",
    }],
    resolved: 0, hitRate: null,
    resolveRule: "Maç oynanınca skordan otomatik: tahmin edilen sonuç (1/X/2) gerçekleşti mi.",
    needNote: "Bu motor zaten 1826 gerçek maçta doğrulandı (out-of-sample).",
  };
}

/** Tüm motorların kanıt-defteri durumu. */
export function engineLedgers(): EngineLedger[] {
  return [matchLedger(), injuryLedger(), lineupLedger()];
}
