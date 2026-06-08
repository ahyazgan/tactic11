/**
 * Türetilmiş test hesaplamaları — Test Hesaplayıcı (/physical-tests/derive)
 * sayfasının ürettiği kayıtların ortak tip + sözlük + okuma yardımcısı.
 *
 * DEMO_MODE'da kayıtlar tarayıcıda localStorage'da (LS_KEY) tutulur; hem
 * hesaplayıcı sayfası hem Fiziksel Durum panosu buradan okur.
 */

export const LS_KEY = "fi_demo_physical_tests";

export interface SavePayload {
  protocol: string;
  value: number;
  components: Record<string, unknown>;
  label: string; // kayıt panelinde gösterilecek kısa özet
}

export interface SavedRecord extends SavePayload {
  id: number;
  player_id: string;
  player_name: string;
  test_date: string;
}

export const PROTO_NAME: Record<string, string> = {
  cmj: "CMJ Sıçrama", sj: "Squat Jump", drop_jump_rsi: "Drop Jump RSI",
  sprint_5m: "5m Sprint", sprint_10m: "10m Sprint", sprint_30m: "30m Sprint",
  t505: "505 Çeviklik", yoyo_irl1: "Yo-Yo IR1", isokinetic_ham: "İzokinetik Hamstring",
  adductor_squeeze: "Adductor Squeeze", ift_30_15: "30-15 IFT (VIFT)", illinois: "Illinois",
  rsa: "RSA (tekrarlı sprint)", triple_hop: "Triple Hop", arrowhead: "Arrowhead",
  vo2max: "VO2max", ttest_agility: "T-Test Çeviklik",
};

export const PROTO_UNIT: Record<string, string> = {
  cmj: "cm", drop_jump_rsi: "RSI", t505: "sn", isokinetic_ham: "Nm/kg",
  adductor_squeeze: "N", ift_30_15: "km/sa", rsa: "sn", triple_hop: "cm", vo2max: "ml/kg/dk",
};

/** localStorage'tan kayıtları oku (yalnız tarayıcıda; SSR'de boş döner). */
export function loadDerivedRecords(): SavedRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    return raw ? (JSON.parse(raw) as SavedRecord[]) : [];
  } catch {
    return [];
  }
}
