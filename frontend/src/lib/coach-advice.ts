/**
 * Teknik Direktör Brifingi — koç-seviyesi STRATEJİK sentez (matchday değil).
 *
 * "Bu takımı devraldın, neye öncelik ver?" sorusunu cevaplar: kadro denetimi
 * (mevki derinliği + kalite), yaş profili (yaşlanan çekirdek + yetenekler), kadroya
 * uygun taktik kimlik, ve öncelik-sıralı koç kararları (geliştir/yönet/güçlendir/
 * halefiyet). Mevcut motorları (attributes/development/risk/tactical-dna) koç
 * seviyesinde birleştirir. Saf/deterministik.
 */

import { demoSquad, demoAttributesFor } from "./demo-data";
import { demoTeamById } from "./demo-teams";
import { tacticalDna } from "./tactical-dna";
import { computeDevelopmentFor } from "./player-development";

type Line = "GK" | "DF" | "MF" | "FW";
const LINE_LABEL: Record<Line, string> = { GK: "Kaleci", DF: "Defans", MF: "Orta saha", FW: "Hücum" };
const LINE_NEED: Record<Line, number> = { GK: 2, DF: 7, MF: 6, FW: 4 };   // tipik derinlik ihtiyacı

const _q = new Map<number, number>();
function quality(id: number): number {
  const hit = _q.get(id); if (hit !== undefined) return hit;
  const all = demoAttributesFor(id).flatMap((g) => g.attrs);
  const q = all.length ? all.reduce((s, a) => s + a.value, 0) / all.length : 10;
  _q.set(id, q); return q;
}
const r1 = (n: number) => Math.round(n * 10) / 10;

export type Depth = "güçlü" | "yeterli" | "ince" | "zayıf";
export interface PositionLine { line: Line; label: string; count: number; avgQuality: number; depth: Depth; note: string }
export interface AgeProfile {
  avg: number; young: number; prime: number; aging: number;
  agingKey: { name: string; age: number; pos: string }[];
  talents: { name: string; age: number; pos: string; potential: number }[];
}
export interface IdentitySuggestion { formation: string; identity: string; traits: string[]; rationale: string }
export type DecisionKind = "kimlik" | "geliştir" | "yönet" | "güçlendir" | "halefiyet";
export interface CoachDecision { rank: number; kind: DecisionKind; title: string; detail: string }
export interface CoachBriefing {
  summary: string; audit: PositionLine[]; age: AgeProfile; identity: IdentitySuggestion; decisions: CoachDecision[];
}

/** Mevki-hattı denetimi: derinlik + kalite. */
export function squadAudit(): PositionLine[] {
  const lines: Line[] = ["GK", "DF", "MF", "FW"];
  return lines.map((line) => {
    const ps = demoSquad.filter((p) => p.position === line);
    const count = ps.length;
    const avgQ = ps.length ? r1(ps.reduce((s, p) => s + quality(p.player_id), 0) / ps.length) : 0;
    const need = LINE_NEED[line];
    const depth: Depth = count >= need + 1 ? "güçlü" : count === need ? "yeterli" : count === need - 1 ? "ince" : "zayıf";
    const note = `${count} oyuncu (ihtiyaç ~${need}) · ortalama kalite ${avgQ}/20`;
    return { line, label: LINE_LABEL[line], count, avgQuality: avgQ, depth, note };
  });
}

function ageProfile(): AgeProfile {
  const ages = demoSquad.map((p) => p.age);
  const avg = r1(ages.reduce((a, b) => a + b, 0) / ages.length);
  const young = demoSquad.filter((p) => p.age <= 23).length;
  const aging = demoSquad.filter((p) => p.age >= 30).length;
  const prime = demoSquad.length - young - aging;
  const agingKey = demoSquad.filter((p) => p.age >= 30).sort((a, b) => quality(b.player_id) - quality(a.player_id)).slice(0, 3)
    .map((p) => ({ name: p.player_name, age: p.age, pos: p.pos_detail }));
  const talents = demoSquad.filter((p) => p.age <= 23)
    .map((p) => ({ p, dev: computeDevelopmentFor(p.player_id) }))
    .sort((a, b) => (b.dev?.potential ?? 0) - (a.dev?.potential ?? 0)).slice(0, 3)
    .map(({ p, dev }) => ({ name: p.player_name, age: p.age, pos: p.pos_detail, potential: dev?.potential ?? 0 }));
  return { avg, young, prime, aging, agingKey, talents };
}

function identity(): IdentitySuggestion {
  const dna = tacticalDna(demoTeamById(100)!);
  const audit = squadAudit();
  const strongest = [...audit].sort((a, b) => b.avgQuality - a.avgQuality)[0];
  return {
    formation: dna.formation, identity: dna.identity, traits: dna.traits,
    rationale: `Kadronun en güçlü hattı ${strongest.label.toLowerCase()} (kalite ${strongest.avgQuality}); ${dna.identity.toLowerCase()} kimliği bu profile oturuyor. ${dna.formation} şekli mevcut derinlikle sürdürülebilir.`,
  };
}

export function coachBriefing(): CoachBriefing {
  const audit = squadAudit();
  const age = ageProfile();
  const id = identity();

  // En zayıf hat (kalite × derinlik).
  const weak = [...audit].sort((a, b) => (a.avgQuality - (a.depth === "zayıf" ? 3 : a.depth === "ince" ? 1.5 : 0)) - (b.avgQuality - (b.depth === "zayıf" ? 3 : b.depth === "ince" ? 1.5 : 0)))[0];
  // En riskli oyuncu (kadro risk_score).
  const risky = [...demoSquad].sort((a, b) => b.risk_score - a.risk_score)[0];
  // En yaşlı kilit oyuncu (halefiyet).
  const oldKey = age.agingKey[0];
  const talent = age.talents[0];

  const decisions: CoachDecision[] = [
    { rank: 1, kind: "kimlik", title: `Taktik kimlik: ${id.formation} · ${id.identity}`, detail: id.rationale },
    { rank: 2, kind: "güçlendir", title: `${weak.label} en zayıf halka`, detail: `${weak.note}. ${weak.depth === "zayıf" || weak.depth === "ince" ? "Derinlik takviyesi" : "Kalite takviyesi"} ilk transfer önceliği — bu hat çözülmeden kimlik tam oturmaz.` },
    { rank: 3, kind: "yönet", title: `${risky.player_name} (${risky.shirt}) yük yönetimi`, detail: `Risk endeksi ${risky.risk_score} (${risky.risk_label.toLowerCase()}). Rotasyon + yük azaltımıyla sezona sağlam taşı; sakatlanırsa ${weak.label.toLowerCase()} dışında en kırılgan nokta burası.` },
    ...(talent ? [{ rank: 4, kind: "geliştir" as DecisionKind, title: `${talent.name} (${talent.age}) — geliştir`, detail: `Potansiyel tavanı ${talent.potential}/20 (${talent.pos}). Dakika + bireysel plan ile çekirdeğe taşı; uzun vadeli en yüksek getirili yatırım.` }] : []),
    ...(oldKey ? [{ rank: 5, kind: "halefiyet" as DecisionKind, title: `${oldKey.name} (${oldKey.age}) için halef planla`, detail: `${oldKey.pos} hattında yaşlanan çekirdek. 1-2 sezonluk geçiş planı: genç bir alternatifi şimdiden yanında yetiştir.` }] : []),
  ];

  const summary = `Kadro yaş ortalaması ${age.avg} (${age.aging} oyuncu 30+, ${age.young} genç). En güçlü hat ${[...audit].sort((a, b) => b.avgQuality - a.avgQuality)[0].label.toLowerCase()}, en zayıf ${weak.label.toLowerCase()}. Önerilen kimlik ${id.formation} · ${id.identity.toLowerCase()}. İlk 3 öncelik: kimliği oturt, ${weak.label.toLowerCase()} takviyesi, ${risky.player_name.split(" ").slice(-1)[0]} yük yönetimi.`;

  return { summary, audit, age, identity: id, decisions };
}
