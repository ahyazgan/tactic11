"use client";

/**
 * Boşluk Haritası — "nerede üstünlük var, nereye oyna" (engine.space_map)
 *
 * `tracking-shape-card` takımın şeklini (genişlik/kompaktlık) özetler; bu kart
 * o şekli SAHANIN ÜSTÜNE yerleştirir: 3 koridor × 3 üçte bir ızgarasında her
 * hücrede kaç oyuncumuz, kaç rakip var ve fark ne.
 *
 * Izgara her zaman **bizim hücum yönümüze** göre çizilir: sağ kenar bizim
 * hücum ettiğimiz kale. Backend koordinatları buna göre döndürdüğü için
 * (ikinci yarıda da) kart aynı kalır — koç hep aynı yönde okur.
 *
 * Bulgu üretilemediğinde kart SEBEBİ yazar (kamera sahanın azını görüyor,
 * hücum yönü çıkarılamadı, oyuncu az). Boş kart göstermek koçu "veri yok mu,
 * sinyal mi yok" ikilemine sokuyordu.
 */

import type { CSSProperties } from "react";

export interface ZoneCell {
  lane: string; third: string; ours: number; theirs: number; delta: number;
}
export interface LineGap {
  def_line_m: number | null; mid_line_m: number | null;
  gap_m: number | null; our_players_between: number;
}
export interface SpaceFinding {
  key: string; headline: string; urgency: number; magnitude: number;
  detail?: Record<string, unknown>;
}
export interface SpaceMapOut {
  minute: number; frames_used: number; players_seen: number;
  attack_direction: number; direction_method: string;
  zones: ZoneCell[]; line_gap: LineGap; best_overload: ZoneCell | null;
  findings: SpaceFinding[]; pitch_coverage: number; note: string | null;
}

const LANES = ["sol", "merkez", "sağ"] as const;
const THIRDS = ["savunma", "orta", "hücum"] as const;

const LABEL: CSSProperties = {
  fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6,
  color: "var(--muted)", fontWeight: 700,
};

/** Farkı renge çevir: bizde fazlaysa yeşil, rakipte fazlaysa kırmızı. */
function cellStyle(delta: number): CSSProperties {
  const mag = Math.min(1, Math.abs(delta) / 3);
  if (Math.abs(delta) < 0.5) {
    return { background: "var(--panel2)", color: "var(--dim)" };
  }
  // rgba ile tek renk üstüne yoğunluk — tema değişkenlerini bozmadan
  const rgb = delta > 0 ? "42, 157, 92" : "203, 68, 68";
  return {
    background: `rgba(${rgb}, ${0.15 + mag * 0.5})`,
    color: "var(--ink)",
  };
}

export function SpaceMapCard({ data }: { data: SpaceMapOut | null | undefined }) {
  if (!data) return null;
  const hasZones = Array.isArray(data.zones) && data.zones.length > 0;
  const byKey = new Map(hasZones ? data.zones.map((z) => [`${z.lane}|${z.third}`, z]) : []);

  return (
    <div className="rc" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>
          Boşluk haritası{" "}
          <span style={{ fontWeight: 400, color: "var(--muted)", fontSize: 11 }}>· nereye oyna</span>
        </h3>
        <span style={{ fontSize: 10, color: "var(--muted)" }}>
          {data.frames_used} kare · {data.players_seen} oyuncu görünür
          {data.pitch_coverage ? ` · saha %${Math.round(data.pitch_coverage * 100)}` : ""}
        </span>
      </div>

      {!hasZones && (
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>
          {data.note ?? "Bölge analizi üretilemedi."}
        </div>
      )}

      {hasZones && (
        <>
          {/* Saha ızgarası — sağ kenar bizim hücum ettiğimiz kale */}
          <div style={{ marginTop: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", ...LABEL, marginBottom: 4 }}>
              <span>kendi kalemiz</span>
              <span>hücum yönü →</span>
            </div>
            <div style={{
              display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 3,
              border: "1px solid var(--line)", borderRadius: 5, padding: 3,
            }}>
              {LANES.map((lane) => (
                THIRDS.map((third) => {
                  const z = byKey.get(`${lane}|${third}`);
                  const delta = z?.delta ?? 0;
                  return (
                    <div key={`${lane}-${third}`}
                      title={`${lane} · ${third} üçte biri — biz ${z?.ours ?? 0}, rakip ${z?.theirs ?? 0}`}
                      style={{
                        ...cellStyle(delta), borderRadius: 3, padding: "8px 4px",
                        textAlign: "center", minWidth: 0,
                      }}>
                      <div style={{ fontSize: 15, fontWeight: 700, fontFamily: "JetBrains Mono, monospace" }}>
                        {delta > 0 ? "+" : ""}{delta.toFixed(1)}
                      </div>
                      <div style={{ fontSize: 9.5, opacity: 0.75 }}>
                        {(z?.ours ?? 0).toFixed(1)}v{(z?.theirs ?? 0).toFixed(1)}
                      </div>
                      <div style={{ fontSize: 8.5, opacity: 0.6, textTransform: "uppercase", letterSpacing: 0.4 }}>
                        {lane}
                      </div>
                    </div>
                  );
                })
              ))}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--dim)", marginTop: 3 }}>
              <span>savunma üçte biri</span><span>orta</span><span>hücum üçte biri</span>
            </div>
          </div>

          {/* Hatlar arası boşluk */}
          {data.line_gap?.gap_m != null && (
            <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--line)" }}>
              <div style={{ ...LABEL, marginBottom: 4 }}>Rakip hatları arası</div>
              <div style={{ display: "flex", gap: 18, flexWrap: "wrap", alignItems: "baseline" }}>
                <span style={{ fontSize: 20, fontWeight: 700, fontFamily: "JetBrains Mono, monospace", color: "var(--ink)" }}>
                  {data.line_gap.gap_m.toFixed(0)} m
                </span>
                <span style={{ fontSize: 11, color: "var(--muted)" }}>
                  cepte {data.line_gap.our_players_between.toFixed(1)} oyuncumuz
                </span>
                <span style={{ fontSize: 10, color: "var(--dim)" }}>
                  geri hat {data.line_gap.def_line_m?.toFixed(0)} m · orta hat {data.line_gap.mid_line_m?.toFixed(0)} m
                </span>
              </div>
            </div>
          )}

          {/* Bulgular */}
          {data.findings.length > 0 ? (
            <div style={{ marginTop: 12, display: "grid", gap: 6 }}>
              {data.findings.map((f) => (
                <div key={f.key} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                  <span style={{
                    width: 6, height: 6, borderRadius: 3, flexShrink: 0,
                    background: f.urgency >= 0.6 ? "var(--crit)" : "var(--mid)",
                    transform: "translateY(-1px)",
                  }} />
                  <span style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.45 }}>{f.headline}</span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 10 }}>
              {data.note ?? "Belirgin bölgesel üstünlük yok."}
            </div>
          )}

          <div style={{ fontSize: 9.5, color: "var(--dim)", marginTop: 10, lineHeight: 1.5 }}>
            Hücreler kare başına ortalama oyuncu farkıdır (biz − rakip); kameranın görmediği
            oyuncu sayılmaz. Hücum yönü{" "}
            {data.direction_method === "keeper" ? "kaleci konumundan" : "en derin oyuncudan"} çıkarıldı.
          </div>
        </>
      )}
    </div>
  );
}
