/**
 * Antrenman Odağı — "bu hafta neyi çalış" (koç kimliği + zaaflardan). Karar→aksiyon
 * köprüsü. Motor: lib/training-focus. Transfer/fikstür değil — sahada çalıştırmak.
 */

import { weeklyTraining, type TrainCat, type Intensity } from "@/lib/training-focus";
import { ConsoleShell } from "../_console/shell";

const CAT_ICON: Record<TrainCat, string> = { Taktik: "🧠", Savunma: "🛡️", Hücum: "🎯", Fiziksel: "🏃", "Duran Top": "⚙", Geçiş: "⚡" };
const CAT_COLOR: Record<TrainCat, string> = { Taktik: "var(--accent)", Savunma: "var(--high)", Hücum: "var(--low)", Fiziksel: "var(--mid)", "Duran Top": "var(--crit)", Geçiş: "var(--accent)" };
const INT_COLOR: Record<Intensity, string> = { yüksek: "var(--crit)", orta: "var(--mid)", düşük: "var(--low)" };

export default function TrainingFocusPage() {
  const w = weeklyTraining();

  return (
    <ConsoleShell
      active="/training-focus"
      title="Antrenman Odağı"
      sub="Bu hafta neyi çalış"
      desc="Koç kimliği + bilinen taktik zaaflar + kadro kondisyonundan önceliklendirilmiş antrenman temaları. Karar→aksiyon köprüsü: brifingdeki tespitleri sahaya taşır."
    >
      {/* Özet */}
      <div className="rc" style={{ margin: "0 0 16px", borderLeft: "3px solid var(--accent)" }}>
        <div style={{ fontSize: 13.5, color: "var(--ink)", lineHeight: 1.65 }}>{w.summary}</div>
      </div>

      {/* Temalar */}
      <div className="st" style={{ marginTop: 0 }}><h2>Öncelikli Temalar</h2><span className="ep">neyi · neden · kim · yoğunluk</span></div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
        {w.themes.map((t) => (
          <div key={t.priority} style={{ borderRadius: 10, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: `4px solid ${CAT_COLOR[t.category]}`, padding: "13px 15px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 5, flexWrap: "wrap" }}>
              <span style={{ fontSize: 18 }}>{CAT_ICON[t.category]}</span>
              <span style={{ fontSize: 15, fontWeight: 800 }}>{t.title}</span>
              <span style={{ fontSize: 9, fontWeight: 700, color: "#fff", background: CAT_COLOR[t.category], borderRadius: 4, padding: "2px 7px" }}>{t.category}</span>
              <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 5, fontSize: 10.5, fontWeight: 700, color: INT_COLOR[t.intensity] }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: INT_COLOR[t.intensity] }} />{t.intensity} yoğunluk
              </span>
            </div>
            <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.55 }}>{t.why}</div>
            <div style={{ fontSize: 12, color: "var(--low)", fontWeight: 700, marginTop: 5 }}>↳ Odak: {t.focus}</div>
          </div>
        ))}
      </div>

      {/* Yorgun oyuncular — ayrı yük */}
      {w.fatigued.length > 0 && (
        <>
          <div className="st"><h2>Bireysel Yük — Yorgun Oyuncular</h2><span className="ep">kondisyon &lt;75 · gruptan ayrı program</span></div>
          <div className="rc" style={{ margin: 0 }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {w.fatigued.map((f) => {
                const c = f.condition < 65 ? "var(--crit)" : f.condition < 72 ? "var(--high)" : "var(--mid)";
                return (
                  <div key={f.shirt} style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: `3px solid ${c}`, borderRadius: 8, padding: "8px 12px" }}>
                    <span style={{ fontFamily: "JetBrains Mono", color: "var(--dim)", fontSize: 11 }}>#{f.shirt}</span>
                    <span style={{ fontSize: 12.5, fontWeight: 700 }}>{f.name}</span>
                    <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, color: c, fontSize: 12 }}>{f.condition}</span>
                  </div>
                );
              })}
            </div>
            <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 10, lineHeight: 1.5 }}>Bu oyuncular yüksek-yoğunluk temalarında hacim azaltır (yarı süre / düşük-temas); toparlanma + aktivasyon ön planda. Risk yüksekse maç-öncesi tam yüke alınmaz.</div>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
