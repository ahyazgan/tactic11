/**
 * Motor Sicili — maç değerlendirmelerini maçlar boyu biriktirir.
 *
 * Tek maç değerlendirmesi (match-review) "bu maçta motor şu kadar tuttu" der.
 * Bu modül her değerlendirmeyi kalıcı deftere ekler ve maçlar boyunca her motorun
 * GERÇEK isabet oranını çıkarır → tek maçtan track record'a. /calibration'daki
 * "pending: veri bekliyor" motorları böyle gerçek rakamını kazanır.
 *
 * DÜRÜSTLÜK: localStorage'da yalnızca GERÇEKTEN değerlendirilen maçlar birikir;
 * sahte geçmiş tohumu YOK. Demo'da 1 maçla başlar, sezonla dolar. (action-log ile
 * aynı ilke.) Production'da backend reconcile job'ı aynı şekli üretir.
 */

export interface EngineGrade { hit: number; graded: number }
export interface MatchGrade {
  matchId: string;          // benzersiz maç kimliği (çift-sayımı önler)
  label: string;            // "Beşiktaş 1-1 Antalyaspor"
  at: number;
  perEngine: Record<string, EngineGrade>;
}

export interface EngineRecord {
  engine: string;
  matches: number;          // bu motoru notlayan maç sayısı
  hit: number;
  graded: number;
  accuracy: number;         // 0..1
}

const KEY = "fi_engine_record";

export function loadGrades(): MatchGrade[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as MatchGrade[]) : [];
  } catch {
    return [];
  }
}

function save(list: MatchGrade[]): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* kota — yoksay */ }
}

/** Bir maç değerlendirmesini sicile ekle (aynı matchId varsa günceller). */
export function commitMatchReview(matchId: string, label: string, byEngine: { engine: string; hit: number; graded: number }[]): void {
  const perEngine: Record<string, EngineGrade> = {};
  for (const e of byEngine) perEngine[e.engine] = { hit: e.hit, graded: e.graded };
  const list = loadGrades().filter((g) => g.matchId !== matchId);
  list.unshift({ matchId, label, at: Date.now(), perEngine });
  save(list);
}

export function isCommitted(matchId: string): boolean {
  return loadGrades().some((g) => g.matchId === matchId);
}
export function removeGrade(matchId: string): void {
  save(loadGrades().filter((g) => g.matchId !== matchId));
}
export function clearGrades(): void { save([]); }

/** Tüm sicilden motor-bazlı toplam isabet oranı. */
export function engineRecords(): { records: EngineRecord[]; matchCount: number } {
  const grades = loadGrades();
  const agg: Record<string, { matches: number; hit: number; graded: number }> = {};
  for (const g of grades) {
    for (const [engine, eg] of Object.entries(g.perEngine)) {
      const a = (agg[engine] ??= { matches: 0, hit: 0, graded: 0 });
      a.matches++; a.hit += eg.hit; a.graded += eg.graded;
    }
  }
  const records = Object.entries(agg)
    .map(([engine, v]) => ({ engine, matches: v.matches, hit: v.hit, graded: v.graded, accuracy: v.graded ? v.hit / v.graded : 0 }))
    .sort((a, b) => b.graded - a.graded);
  return { records, matchCount: grades.length };
}
