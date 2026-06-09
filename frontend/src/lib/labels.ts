/**
 * Jargon → sade Türkçe etiket sözlüğü.
 *
 * Backend job adları ve karar/sinyal motor anahtarları (snake_case) kullanıcıya
 * kod gibi görünüyordu (statsbomb_ingest, matchup_engine, hamstring_quad_ratio…).
 * Bu yardımcılar bunları anlaşılır Türkçe'ye çevirir. Anahtar sözlükte yoksa
 * otomatik "prettify" (alt çizgi → boşluk, baş harf büyük) ile geri döner —
 * yani additive, hiçbir yeri bozmaz.
 */

// Arka plan görevleri (Admin Paneli · Son Job Geçmişi).
const JOB_LABELS: Record<string, string> = {
  statsbomb_ingest: "StatsBomb veri çekme",
  xg_model_recompute: "xG modeli yeniden hesabı",
  load_risk_recalc: "Yük & risk yeniden hesabı",
  opponent_report_build: "Rakip raporu üretimi",
  api_football_sync: "API-Football senkronizasyonu",
  decision_engine_warm: "Karar motoru ısıtma",
  physical_test_etl: "Fiziksel test veri aktarımı",
  calibration_nightly: "Gecelik kalibrasyon",
  h2h_aggregate: "Averaj & H2H toplama",
  notification_dispatch: "Bildirim gönderimi",
  sync_squad: "Kadro senkronizasyonu",
  sync_fixtures: "Fikstür senkronizasyonu",
};

// Karar / sinyal / analiz motorları (Kararlar, Canlı Maç, Taktik, Trend, Chat…).
const ENGINE_LABELS: Record<string, string> = {
  // Fiziksel / sağlık
  acwr_band: "Akut:kronik yük oranı",
  adductor_squeeze_drop: "Kasık kuvveti düşüşü",
  change_of_direction_deficit: "Yön değiştirme açığı",
  cmj_neuromuscular_drop: "Dikey sıçrama (yorgunluk)",
  compute_wellness: "Öznel hazırlık (anket)",
  hamstring_quad_ratio: "Arka/ön bacak kuvvet dengesi",
  interpret_progression: "Performans düşüş takibi",
  limb_asymmetry: "İki bacak arası denge",
  repeated_sprint_fatigue_index: "Tekrarlı sprint dayanıklılığı",
  return_to_play_readiness: "Sahaya dönüş hazırlığı",
  live_risk_monitor: "Canlı risk izleme",
  load_monitor: "Yük izleme",
  load_risk_monitor: "Yük & risk izleme",
  physical_test_trend: "Fiziksel test trendi",
  squad_availability: "Kadro uygunluğu",
  // Taktik / oyun
  build_up: "Oyun kurma",
  compactness: "Hat kompaktlığı",
  counter_press: "Karşı pres (geri kazanım)",
  defensive_duels: "Savunma ikili mücadeleleri",
  defensive_line: "Savunma hattı yüksekliği",
  direct_play: "Direkt oyun",
  field_tilt: "Saha hâkimiyeti",
  final_third: "Son bölge etkinliği",
  matchup_engine: "Eşleşme analizi",
  momentum_tracker: "Momentum takibi",
  opponent_fatigue: "Rakip yorgunluğu",
  opponent_shape: "Rakip dizilişi",
  press_resistance: "Pres direnci",
  pressing_engine: "Pres analizi",
  score_time_matrix: "Skor-zaman matrisi",
  set_piece_analyzer: "Duran top analizi",
  sub_timing: "Değişiklik zamanlaması",
  tempo_engine: "Tempo analizi",
  transition: "Geçiş oyunu",
  xg_model: "xG (beklenen gol) modeli",
  context_engine: "Orkestra şefi (karar birleştirici)",
  // Sinyal/karar tipleri
  channel_shift: "Koridor değişimi",
  press_height: "Pres yüksekliği",
  momentum_break: "Momentum kırılması",
  // Metrik anahtarları (taktik/trend)
  possession_share: "Topla oynama payı",
  team_xt: "Takım xT (tehdit üretimi)",
  dominance_score: "Hâkimiyet skoru",
  gps_total_dist: "Toplam mesafe (GPS)",
  body_fat_pct: "Vücut yağ oranı",
  isokinetic_ham: "İzokinetik hamstring",
  isokinetic_quad: "İzokinetik quadriceps",
  sleep_quality: "Uyku kalitesi",
  muscle_soreness: "Kas ağrısı",
  fatigue: "Yorgunluk",
  stress: "Stres",
};

/** snake_case/teknik anahtarı sade Türkçe'ye çevir; yoksa boşluklu/baş-harf-büyük döndür. */
function prettify(key: string): string {
  const s = key.replace(/_/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function jobLabel(key: string): string {
  return JOB_LABELS[key] ?? prettify(key);
}

export function engineLabel(key: string): string {
  return ENGINE_LABELS[key] ?? prettify(key);
}
