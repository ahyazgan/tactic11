/**
 * Tracking geometrisi — oyuncu pozisyonlarından saha overlay metrikleri.
 *
 * Girdi: bir "tracking frame" (0-100 normalize koordinat; kaynak StatsBomb 360
 * freeze-frame ya da ileride video takibi). Çıktı: pas seçenekleri, en yakın
 * baskı, yerel alan kontrolü, topa sahip olma payı, faz etiketi.
 *
 * Hepsi saf fonksiyon; DOM/API bilmez. Sayılar TAHMİNDİR — pas modeli
 * geometrik bir kestirimdir (mesafe + hat kapalı mı + alıcı üstündeki baskı),
 * garanti değil. UI bunu "~" ile gösterir.
 */

export interface TrackingPlayer {
  player_external_id: number;
  x: number;
  y: number;
  team_external_id: number | null;
  is_actor: boolean;
  is_keeper: boolean;
  identity_estimated: boolean;
  velocity_mps?: number | null;
  name?: string | null;
  jersey_number?: number | null;
  track_player_external_id?: number | null;
}

export interface TrackingFrame {
  minute: number;
  period: number;
  ball: { x: number; y: number; velocity_mps?: number | null } | null;
  ball_estimated?: boolean;
  players: TrackingPlayer[];
  source?: string | null;
  event_uuid?: string | null;
  event_type?: string | null;
  possession_team_external_id?: number | null;
  visible_area?: number[][] | null;
}

/** Saha ölçüsü (m) — 0-100 normalize koordinatı metreye çevirmek için. */
export const PITCH_M = { x: 105, y: 68 } as const;

type Pt = { x: number; y: number };

export function distM(a: Pt, b: Pt): number {
  const dx = ((a.x - b.x) / 100) * PITCH_M.x;
  const dy = ((a.y - b.y) / 100) * PITCH_M.y;
  return Math.hypot(dx, dy);
}

function toM(p: Pt): Pt {
  return { x: (p.x / 100) * PITCH_M.x, y: (p.y / 100) * PITCH_M.y };
}

/** `o`, a→b hattının koridoru (±corridorM) içinde ve arada mı? */
function blocksLane(a: Pt, b: Pt, o: Pt, corridorM: number): boolean {
  const A = toM(a), B = toM(b), O = toM(o);
  const vx = B.x - A.x, vy = B.y - A.y;
  const len2 = vx * vx + vy * vy;
  if (len2 < 1e-6) return false;
  const t = ((O.x - A.x) * vx + (O.y - A.y) * vy) / len2;
  if (t <= 0.05 || t >= 0.95) return false;
  const px = A.x + t * vx, py = A.y + t * vy;
  return Math.hypot(O.x - px, O.y - py) < corridorM;
}

const sigmoid = (z: number) => 1 / (1 + Math.exp(-z));

export function actorOf(frame: TrackingFrame): TrackingPlayer | null {
  return frame.players.find((p) => p.is_actor) ?? null;
}

export function teammatesOf(frame: TrackingFrame, actor: TrackingPlayer): TrackingPlayer[] {
  return frame.players.filter(
    (p) => p !== actor && p.team_external_id !== null && p.team_external_id === actor.team_external_id,
  );
}

export function opponentsOf(frame: TrackingFrame, actor: TrackingPlayer): TrackingPlayer[] {
  return frame.players.filter(
    (p) => p.team_external_id !== null && p.team_external_id !== actor.team_external_id,
  );
}

export interface PassOption {
  player: TrackingPlayer;
  distM: number;
  screened: boolean;
  nearestDefM: number | null;
  /** 0-1, kısa pas tamamlanma kestirimi */
  prob: number;
}

const LANE_CORRIDOR_M = 1.5;

/** Aktörün pas seçenekleri — olasılığa göre sıralı, en iyi `maxN`. */
export function passOptions(frame: TrackingFrame, maxN = 3): PassOption[] {
  const actor = actorOf(frame);
  if (!actor) return [];
  const mates = teammatesOf(frame, actor);
  const opps = opponentsOf(frame, actor);
  const out: PassOption[] = mates.map((m) => {
    const d = distM(actor, m);
    const screened = opps.some((o) => blocksLane(actor, m, o, LANE_CORRIDOR_M));
    const nearestDef = opps.length
      ? Math.min(...opps.map((o) => distM(m, o)))
      : null;
    const pressure = nearestDef === null ? 0 : Math.max(0, Math.min(1, 1 - nearestDef / 6));
    const prob = sigmoid(2.6 - 0.05 * d - 1.5 * (screened ? 1 : 0) - 0.8 * pressure);
    return { player: m, distM: d, screened, nearestDefM: nearestDef, prob };
  });
  out.sort((a, b) => b.prob - a.prob);
  return out.slice(0, maxN);
}

/** Aktöre en yakın rakip mesafesi (m); aktör/rakip yoksa null. */
export function closestPressureM(frame: TrackingFrame): number | null {
  const actor = actorOf(frame);
  if (!actor) return null;
  const opps = opponentsOf(frame, actor);
  if (!opps.length) return null;
  return Math.min(...opps.map((o) => distM(actor, o)));
}

/** Kaç pas hattı kapalı (top-3 içinde). */
export function screenedLaneCount(options: PassOption[]): number {
  return options.filter((o) => o.screened).length;
}

export interface SpaceControl {
  /** takımın kontrol ettiği hücre yüzdesi (0-100) */
  pct: number;
  cells: number;
  /** yalnız görünen oyuncular sayıldı (kamera dışı yok) */
  visibleOnly: true;
}

/**
 * Yerel alan kontrolü — "en yakın oyuncu" bölgelendirmesi (kaba Voronoi).
 * Görünür oyuncuların sarmalı içindeki hücreler sayılır; kamera dışı alan
 * belirsiz olduğu için tüm saha yerine görünen sarmal kullanılır.
 */
export function spaceControl(frame: TrackingFrame, teamId: number, cols = 21, rows = 14): SpaceControl | null {
  const ps = frame.players.filter((p) => p.team_external_id !== null);
  if (ps.length < 4) return null;
  const minX = Math.min(...ps.map((p) => p.x)), maxX = Math.max(...ps.map((p) => p.x));
  const minY = Math.min(...ps.map((p) => p.y)), maxY = Math.max(...ps.map((p) => p.y));
  let ours = 0, total = 0;
  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      const cx = (i + 0.5) / cols * 100, cy = (j + 0.5) / rows * 100;
      if (cx < minX || cx > maxX || cy < minY || cy > maxY) continue;
      let best = Infinity, bestTeam: number | null = null;
      for (const p of ps) {
        const d = distM({ x: cx, y: cy }, p);
        if (d < best) { best = d; bestTeam = p.team_external_id; }
      }
      total++;
      if (bestTeam === teamId) ours++;
    }
  }
  if (!total) return null;
  return { pct: Math.round((ours / total) * 100), cells: total, visibleOnly: true };
}

export interface PossessionShare {
  ours: number;
  theirs: number;
  frames: number;
}

/** Pencere içindeki event karelerinde topa sahip takım payı (%). */
export function possessionShare(frames: TrackingFrame[], teamId: number): PossessionShare | null {
  const withPoss = frames.filter((f) => f.possession_team_external_id != null);
  if (!withPoss.length) return null;
  const ours = withPoss.filter((f) => f.possession_team_external_id === teamId).length;
  const pct = Math.round((ours / withPoss.length) * 100);
  return { ours: pct, theirs: 100 - pct, frames: withPoss.length };
}

const EVENT_TR: Record<string, string> = {
  "Pass": "Pas",
  "Carry": "Top taşıma",
  "Ball Receipt*": "Top alma",
  "Pressure": "Baskı",
  "Ball Recovery": "Top kazanma",
  "Duel": "İkili mücadele",
  "Clearance": "Uzaklaştırma",
  "Foul Committed": "Faul",
  "Foul Won": "Faul kazanıldı",
  "Shot": "Şut",
  "Goal Keeper": "Kaleci",
  "Dribble": "Çalım",
  "Interception": "Kesme",
  "Block": "Blok",
  "Miscontrol": "Kontrol hatası",
  "Dispossessed": "Top kaybı",
  "Shield": "Perdeleme",
  "Dribbled Past": "Çalım yenildi",
  "video_sample": "Video karesi",
};

export const SOURCE_TR: Record<string, string> = {
  statsbomb_360: "StatsBomb 360",
  video_tracking: "Video takibi",
};

export function sourceTR(s: string | null | undefined): string {
  return s ? (SOURCE_TR[s] ?? s) : "tracking";
}

export function eventTypeTR(t: string | null | undefined): string {
  if (!t) return "—";
  return EVENT_TR[t] ?? t;
}

/** "Biz · Pas" / "Rakip · Baskı" gibi faz etiketi. */
export function phaseLabel(frame: TrackingFrame, teamId: number): string {
  const side = frame.possession_team_external_id == null
    ? ""
    : frame.possession_team_external_id === teamId ? "Biz · " : "Rakip · ";
  return side + eventTypeTR(frame.event_type);
}

export function visibleTracks(frame: TrackingFrame): number {
  return frame.players.length;
}

/** m/s → "~12 km/h"; hız yoksa null. */
export function fmtKmh(mps: number | null | undefined): string | null {
  if (mps == null) return null;
  return `~${Math.round(mps * 3.6)} km/h`;
}

/** Karedeki en hızlı oyuncu (hız verisi olan kaynaklarda). */
export function fastestPlayer(frame: TrackingFrame): TrackingPlayer | null {
  let best: TrackingPlayer | null = null;
  for (const p of frame.players) {
    if (p.velocity_mps != null && (best === null || p.velocity_mps > (best.velocity_mps ?? 0))) best = p;
  }
  return best;
}
