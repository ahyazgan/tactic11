/**
 * Aksiyon Defteri — analistin maç-içi önerilere verdiği kararı (uygulandı/atlandı)
 * kalıcı kaydeder. Kanıt döngüsünün İNSAN yarısı: sistem öneriyi yaptı, analist
 * onu uyguladı mı? Bu kayıt /calibration'daki Karar Kanıt Defteri'ne düşer.
 *
 * NOT: "uygulandı" reconcile'ın İLK yarısıdır (aksiyon teyidi). İKİNCİ yarı (işe
 * yaradı mı) gerçek sonuç verisi ister — sahte sonuç üretilmez.
 *
 * localStorage tabanlı (DEMO); production'da backend olay kaydı. SSR güvenli.
 */

export type ActionVerb = "applied" | "dismissed";

export interface LoggedAction {
  id: string;        // önerinin benzersiz kimliği (ör. "alert-52", "sub-Orkun Kökçü (10)")
  label: string;     // okunur öneri metni
  minute: number;    // maç dakikası
  verb: ActionVerb;
  at: number;        // teyit zamanı (epoch ms)
}

const KEY = "fi_action_log";

export function loadActions(): LoggedAction[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as LoggedAction[]) : [];
  } catch {
    return [];
  }
}

function save(list: LoggedAction[]): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* kota — yoksay */ }
}

/** Bir öneriye karar ver (aynı id varsa üzerine yazar). */
export function logAction(id: string, label: string, minute: number, verb: ActionVerb): void {
  const list = loadActions().filter((a) => a.id !== id);
  list.unshift({ id, label, minute, verb, at: Date.now() });
  save(list);
}

/** Verilen kararı geri al (kaydı sil). */
export function removeAction(id: string): void {
  save(loadActions().filter((a) => a.id !== id));
}

export function actionFor(id: string): ActionVerb | null {
  return loadActions().find((a) => a.id === id)?.verb ?? null;
}

export function clearActions(): void {
  save([]);
}
