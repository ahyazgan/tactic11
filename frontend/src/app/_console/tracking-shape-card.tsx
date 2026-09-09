"use client";

/**
 * Takım şekli & pres — engine.tracking köprüsü (GET /tracking/matches/{id}/shape).
 * Pencere (son ~1 dk) içindeki pozisyon karelerinden: yerleşim tahmini, genişlik /
 * derinlik / kompaktlık, hat konumları ve rakip topa sahipken pres endeksi.
 */

import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface ShapeValue {
  frames_used: number; players_mean: number; width_m: number; depth_m: number; compactness_m: number;
  centroid_x: number; centroid_y: number; rear_line_x: number; front_line_x: number;
  formation: string | null; formation_support: number;
}
interface PressureValue { frames_used: number; nearest_mean_m: number; within_5m_mean: number; press_index: number }
interface TeamBlock { team_external_id: number; shape: ShapeValue; pressure: PressureValue; formula: { shape?: string; pressure?: string } }
interface ShapeResponse { frames: number; window: number; teams: { home: TeamBlock; away: TeamBlock } }

const US = "var(--accent)";
const THEM = "var(--high)";

function Row({ label, a, b, unit }: { label: string; a: string | number | null; b: string | number | null; unit?: string }) {
  const f = (v: string | number | null) => (v == null || v === "" ? "—" : `${v}${unit ?? ""}`);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 90px 90px", gap: 8, padding: "5px 0", borderBottom: "1px solid var(--line)", fontSize: 11.5 }}>
      <span style={{ color: "var(--muted)" }}>{label}</span>
      <span style={{ fontFamily: "JetBrains Mono, monospace", color: "var(--ink)", textAlign: "right" }}>{f(a)}</span>
      <span style={{ fontFamily: "JetBrains Mono, monospace", color: "var(--ink)", textAlign: "right" }}>{f(b)}</span>
    </div>
  );
}

// Yerleşim ancak kadro büyük ölçüde görünür VE hat yapısı kareler arasında
// tutarlıyken anlamlı; aksi halde "4-6" gibi yanıltıcı çıktı üretir.
const FORMATION_MIN_SUPPORT = 0.35;
const FORMATION_MIN_PLAYERS = 10;

function formationText(s: ShapeValue): string | null {
  if (!s.formation || s.formation_support < FORMATION_MIN_SUPPORT || s.players_mean < FORMATION_MIN_PLAYERS) {
    return null;
  }
  return `${s.formation} · ${Math.round(s.formation_support * 100)}%`;
}

function PressBar({ v, color }: { v: number; color: string }) {
  return (
    <div style={{ height: 6, background: "var(--panel2)", borderRadius: 3, overflow: "hidden" }}>
      <div style={{ width: `${Math.round(v * 100)}%`, height: "100%", background: color }} />
    </div>
  );
}

export function TrackingShapeCard({ matchId, minute, ourSide, windowMin = 1 }: {
  matchId: number | null; minute: number; ourSide: "home" | "away"; windowMin?: number;
}) {
  const key = matchId != null ? `/tracking/matches/${matchId}/shape?minute=${minute.toFixed(2)}&window=${windowMin}` : null;
  const { data, error } = useSWR<ShapeResponse>(key, apiFetch, { revalidateOnFocus: false, shouldRetryOnError: false, keepPreviousData: true });
  if (!matchId) return null;
  const us = data ? data.teams[ourSide] : null;
  const them = data ? data.teams[ourSide === "home" ? "away" : "home"] : null;
  const ready = us && us.shape.frames_used > 0;
  return (
    <div className="rc" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Takım şekli & pres <span style={{ fontWeight: 400, color: "var(--muted)", fontSize: 11 }}>· engine.tracking</span></h3>
        <span style={{ fontSize: 10, color: "var(--muted)" }}>son {windowMin} dk · {data?.frames ?? 0} kare · görünür oyuncular</span>
      </div>
      {error && <div style={{ fontSize: 11, color: "var(--crit)", marginTop: 6 }}>Yüklenemedi: {String(error).slice(0, 120)}</div>}
      {!error && !ready && <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>Bu pencerede yeterli oyuncu yok (takım başına ≥3).</div>}
      {ready && us && them && (
        <div className="tracking-shape-grid" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 16, marginTop: 8 }}>
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 90px 90px", gap: 8, fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>
              <span>Şekil</span><span style={{ color: US, textAlign: "right" }}>Biz</span><span style={{ color: THEM, textAlign: "right" }}>Rakip</span>
            </div>
            <Row label="Yerleşim (tahmin)" a={formationText(us.shape) ?? "belirsiz"} b={formationText(them.shape) ?? "belirsiz"} />
            <Row label="Genişlik" a={us.shape.width_m} b={them.shape.width_m} unit=" m" />
            <Row label="Derinlik" a={us.shape.depth_m} b={them.shape.depth_m} unit=" m" />
            <Row label="Kompaktlık (merkeze ort.)" a={us.shape.compactness_m} b={them.shape.compactness_m} unit=" m" />
            <Row label="Geri hat / ileri hat (x%)" a={`${us.shape.rear_line_x}–${us.shape.front_line_x}`} b={`${them.shape.rear_line_x}–${them.shape.front_line_x}`} />
            <Row label="Görünür oyuncu (ort.)" a={us.shape.players_mean} b={them.shape.players_mean} />
          </div>
          <div>
            <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>Pres (rakip topa sahipken)</div>
            {[{ t: us, c: US, n: "Biz" }, { t: them, c: THEM, n: "Rakip" }].map(({ t, c, n }) => (
              <div key={n} style={{ marginTop: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5 }}>
                  <span style={{ color: c, fontWeight: 700 }}>{n}</span>
                  <span style={{ fontFamily: "JetBrains Mono, monospace", color: "var(--ink)" }}>
                    {t.pressure.frames_used ? `endeks ${t.pressure.press_index.toFixed(2)}` : "ölçülemedi"}
                  </span>
                </div>
                <PressBar v={t.pressure.frames_used ? t.pressure.press_index : 0} color={c} />
                <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 3 }}>
                  {t.pressure.frames_used
                    ? `topa en yakın ~${t.pressure.nearest_mean_m} m · 5 m içinde ${t.pressure.within_5m_mean} oyuncu · ${t.pressure.frames_used} kare`
                    : "rakip possession + görünür top olan kare yok"}
                </div>
              </div>
            ))}
            <div style={{ fontSize: 10, color: "var(--dim)", marginTop: 10, lineHeight: 1.5 }}>
              Hatlar x ekseninde 6 m boşluklardan bölünür; izole kenar tek kişi kaleci sayılır.
              Kamera dışı oyuncular sayılmaz — StatsBomb 360&apos;ta kısmi kadro normaldir.
              Yerleşim yalnız kadro görünür (≥{FORMATION_MIN_PLAYERS}) ve kareler tutarlıysa
              (≥%{Math.round(FORMATION_MIN_SUPPORT * 100)}) yazılır; oyun akışında &quot;belirsiz&quot; normaldir.
            </div>
          </div>
        </div>
      )}
      <style>{`@media (max-width: 760px) { .tracking-shape-grid { grid-template-columns: 1fr !important; } }`}</style>
    </div>
  );
}
