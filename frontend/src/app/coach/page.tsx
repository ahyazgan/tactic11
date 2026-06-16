/**
 * Teknik Direktör Brifingi — koç-seviyesi stratejik sentez (matchday değil).
 * "Bu takımı devraldın, neye öncelik ver?" Kadro denetimi + yaş profili + taktik
 * kimlik + öncelikli kararlar. Motor: lib/coach-advice.
 */

import { coachBriefing, type Depth, type DecisionKind } from "@/lib/coach-advice";
import { ConsoleShell } from "../_console/shell";

const DEPTH_COLOR: Record<Depth, string> = { güçlü: "var(--low)", yeterli: "var(--accent)", ince: "var(--mid)", zayıf: "var(--crit)" };
const KIND_ICON: Record<DecisionKind, string> = { kimlik: "🧭", güçlendir: "🛠", yönet: "⚖", geliştir: "📈", halefiyet: "🔄" };
const KIND_COLOR: Record<DecisionKind, string> = { kimlik: "var(--accent)", güçlendir: "var(--mid)", yönet: "var(--high)", geliştir: "var(--low)", halefiyet: "var(--dim)" };
const KIND_LABEL: Record<DecisionKind, string> = { kimlik: "KİMLİK", güçlendir: "GÜÇLENDİR", yönet: "YÖNET", geliştir: "GELİŞTİR", halefiyet: "HALEFİYET" };

export default function CoachPage() {
  const b = coachBriefing();

  return (
    <ConsoleShell
      active="/coach"
      title="Teknik Direktör Brifingi"
      sub="Takımı devral · stratejik öncelikler"
      desc="Matchday değil — koç-seviyesi sentez: kadro denetimi, yaş profili, kadroya uygun taktik kimlik ve öncelik-sıralı kararlar. 'Bu takımı devraldın, neye odaklan?'"
    >
      {/* Yönetici özeti */}
      <div className="rc" style={{ margin: "0 0 16px", borderLeft: "3px solid var(--accent)" }}>
        <div style={{ fontSize: 13.5, color: "var(--ink)", lineHeight: 1.65 }}>{b.summary}</div>
      </div>

      {/* Öncelikli kararlar — manşet */}
      <div className="st" style={{ marginTop: 0 }}><h2>Öncelikli Kararlar</h2><span className="ep">devralırken ilk odak · önem sırası</span></div>
      <div className="rc" style={{ margin: "0 0 16px", padding: 0, overflow: "hidden" }}>
        {b.decisions.map((d, i) => (
          <div key={d.rank} style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: "13px 15px", borderTop: i ? "1px solid var(--line)" : undefined, borderLeft: `4px solid ${KIND_COLOR[d.kind]}` }}>
            <span style={{ fontSize: 19, flexShrink: 0 }}>{KIND_ICON[d.kind]}</span>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                <span style={{ fontSize: 9, fontWeight: 800, color: "#fff", background: KIND_COLOR[d.kind], borderRadius: 4, padding: "1px 6px" }}>{KIND_LABEL[d.kind]}</span>
                <span style={{ fontSize: 14, fontWeight: 800 }}>{d.title}</span>
              </div>
              <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5 }}>{d.detail}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Kadro denetimi */}
      <div className="st"><h2>Kadro Denetimi</h2><span className="ep">mevki derinliği + kalite</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {b.audit.map((l) => (
            <div key={l.line} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ width: 88, fontWeight: 700, fontSize: 13, flexShrink: 0 }}>{l.label}</span>
              <span className="mbar" style={{ flex: 1, margin: 0 }}><i style={{ width: `${(l.avgQuality / 20) * 100}%`, background: DEPTH_COLOR[l.depth] }} /></span>
              <span style={{ fontFamily: "JetBrains Mono", fontSize: 12, fontWeight: 700, width: 44, textAlign: "right" }}>{l.avgQuality}</span>
              <span style={{ fontSize: 9.5, fontWeight: 800, color: "#fff", background: DEPTH_COLOR[l.depth], borderRadius: 4, padding: "2px 7px", width: 56, textAlign: "center", flexShrink: 0 }}>{l.depth}</span>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 8 }}>Bar = ortalama kalite (1-20). Etiket = derinlik (ihtiyaca göre). Kırmızı/sarı = takviye önceliği.</div>
      </div>

      {/* Yaş profili */}
      <div className="st"><h2>Yaş Profili</h2><span className="ep">çekirdek + yetenekler · halefiyet planı</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }}>
        <div className="kpis" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", marginBottom: 14 }}>
          <div className="kpi"><div className="kl">Yaş ort.</div><div className="kn" style={{ fontSize: 22 }}>{b.age.avg}</div></div>
          <div className="kpi"><div className="kl">Genç (≤23)</div><div className="kn" style={{ fontSize: 22, color: "var(--low)" }}>{b.age.young}</div></div>
          <div className="kpi"><div className="kl">Zirve (24-29)</div><div className="kn" style={{ fontSize: 22 }}>{b.age.prime}</div></div>
          <div className="kpi"><div className="kl">Yaşlanan (30+)</div><div className="kn" style={{ fontSize: 22, color: "var(--mid)" }}>{b.age.aging}</div></div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14 }}>
          <div>
            <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Geleceğin yetenekleri</div>
            {b.age.talents.map((t) => (
              <div key={t.name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, padding: "5px 0", borderTop: "1px solid var(--line)" }}>
                <span style={{ flex: 1 }}><b>{t.name}</b> <span style={{ color: "var(--dim)" }}>{t.age} · {t.pos}</span></span>
                <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: "var(--low)" }}>tavan {t.potential}</span>
              </div>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Yaşlanan çekirdek (halefiyet)</div>
            {b.age.agingKey.map((p) => (
              <div key={p.name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, padding: "5px 0", borderTop: "1px solid var(--line)" }}>
                <span style={{ flex: 1 }}><b>{p.name}</b> <span style={{ color: "var(--dim)" }}>{p.pos}</span></span>
                <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: "var(--mid)" }}>{p.age}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Taktik kimlik */}
      <div className="st"><h2>Önerilen Taktik Kimlik</h2><span className="ep">kadroya uygun</span></div>
      <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--accent)" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: 22, fontWeight: 900 }}>{b.identity.formation}</span>
          <span style={{ fontSize: 14, fontWeight: 700, color: "var(--accent)" }}>{b.identity.identity}</span>
          <span style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
            {b.identity.traits.map((t) => <span key={t} style={{ fontSize: 10, fontWeight: 700, color: "var(--muted)", background: "var(--panel3)", borderRadius: 4, padding: "2px 7px" }}>{t}</span>)}
          </span>
        </div>
        <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.6 }}>{b.identity.rationale}</div>
      </div>
    </ConsoleShell>
  );
}
