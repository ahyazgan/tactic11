"use client";

/**
 * Haftalık Rapor — otomatik PDF digest önizleme, direktöre hazır. ConsoleShell,
 * FM26 açık tema. DEMO_MODE inline mock. Backend bağlanınca app/api/reports.py
 * (reportlab PDF) + scheduler'a bağlanacak.
 */

import * as React from "react";
import { ConsoleShell } from "../_console/shell";

interface Section { icon: string; title: string; lines: string[]; tone?: string }

const SECTIONS: Section[] = [
  { icon: "ti-ball-football", title: "Maç Özeti", tone: "var(--accent)", lines: [
    "FK Demo 1–1 Rakip SK (Süper Lig 34. Hafta) — beraberlik.",
    "xG 1.22–1.35: ikinci yarı momentum rakibe geçti (son 8 dk -34).",
    "Doğan Yılmaz golü (23'), 45'+ yenilen duran top golü dengeledi.",
  ]},
  { icon: "ti-heart-rate-monitor", title: "Sağlık & Yük", tone: "var(--crit)", lines: [
    "1 kritik risk: Caner Öztürk (10) — arka adale, MG-1 testine bağlı.",
    "Ortalama ACWR 1.18; 3 oyuncu 1.3 üstü (yük yönetimi).",
    "Sahaya hazır 20/24 — geçen haftaya göre +2.",
  ]},
  { icon: "ti-run", title: "Antrenman", tone: "var(--low)", lines: [
    "6 saha seansı + 1 izin; haftalık katılım %92.",
    "MG-2 taktik provası: sağ kanat 1v1 + far-post duran top.",
    "Zirve yük MG-4 (%88), maça doğru kademeli düşüş (tapering).",
  ]},
  { icon: "ti-chart-line", title: "Performans Öne Çıkanlar", tone: "var(--mid)", lines: [
    "Tolga Erdem VAEP/90 0.39 — kanat üretiminde lider.",
    "Arda Çelik (impact-sub) 21 dk'da VAEP/90 0.77.",
    "Takım pres yoğunluğu (PPDA) sezon ortalamasının %8 üstünde.",
  ]},
];

const RECIPIENTS = ["Spor Direktörü", "Başkan Yardımcısı", "Teknik Ekip (3)"];
const HISTORY = [
  { week: "31. Hafta — 25 May", status: "Gönderildi" },
  { week: "32. Hafta — 01 Haz", status: "Gönderildi" },
  { week: "33. Hafta — 08 Haz", status: "Hazır" },
];

export default function WeeklyReportPage() {
  const right = (
    <>
      <div className="rc">
        <h3>Rapor Ayarları</h3>
        <div className="stat"><span>Gönderim</span><span className="sv" style={{ color: "var(--low)" }}>Her Pzt 09:00</span></div>
        <div className="stat"><span>Biçim</span><span className="sv">PDF · 1 sayfa</span></div>
        <div style={{ marginTop: 10, fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--dim)", marginBottom: 6 }}>Alıcılar</div>
        {RECIPIENTS.map((r) => (
          <div key={r} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, padding: "4px 0" }}>
            <i className="ti ti-mail" style={{ color: "var(--accent)" }} /> {r}
          </div>
        ))}
      </div>
      <div className="rc">
        <h3>Geçmiş Raporlar</h3>
        {HISTORY.map((h) => {
          const sent = h.status === "Gönderildi";
          return (
            <div className="stat" key={h.week}>
              <span>{h.week}</span>
              <span className="sv" style={{ color: sent ? "var(--low)" : "var(--mid)" }}>
                <i className={`ti ${sent ? "ti-check" : "ti-clock"}`} style={{ marginRight: 4 }} />{h.status}
              </span>
            </div>
          );
        })}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/weekly-report"
      title="Haftalık Rapor"
      sub="Otomatik digest · direktöre hazır"
      desc="Maç, sağlık, antrenman ve performans özetini tek sayfalık PDF olarak üretir; haftalık otomatik gönderilir."
      right={right}
    >
      <div className="kpis">
        <div className="kpi"><div className="kl">Hafta</div><div className="kn" style={{ fontSize: 20 }}>34.</div><div className="kd">02–08 Haziran</div></div>
        <div className="kpi"><div className="kl">Maç Sonucu</div><div className="kn" style={{ fontSize: 20 }}>1–1</div><div className="kd">Rakip SK (E)</div></div>
        <div className="kpi"><div className="kl">Sahaya Hazır</div><div className="kn" style={{ color: "var(--low)" }}>20<span className="pct">/24</span></div><div className="kd">+2 hafta</div></div>
        <div className="kpi"><div className="kl">Kritik Uyarı</div><div className="kn" style={{ color: "var(--crit)" }}>1</div><div className="kd">Caner Öztürk</div></div>
        <div className="kpi"><div className="kl">Rapor</div><div className="kn" style={{ fontSize: 20, color: "var(--mid)" }}>Hazır</div><div className="kd">gönderilmedi</div></div>
      </div>

      <div className="st" style={{ marginTop: 0 }}>
        <h2>Rapor Önizleme</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" style={{ padding: "8px 14px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontWeight: 600, fontSize: 12.5, cursor: "pointer", fontFamily: "inherit" }}>
            <i className="ti ti-file-type-pdf" style={{ marginRight: 6 }} />PDF indir
          </button>
          <button type="button" style={{ padding: "8px 14px", borderRadius: 9, border: 0, background: "var(--besiktas)", color: "#fff", fontWeight: 700, fontSize: 12.5, cursor: "pointer", fontFamily: "inherit" }}>
            <i className="ti ti-send" style={{ marginRight: 6 }} />Direktöre gönder
          </button>
        </div>
      </div>

      {/* A4 benzeri rapor kağıdı */}
      <div className="rc" style={{ margin: 0, padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--surface2)" }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>FK Demo — Haftalık Teknik Rapor</div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>34. Hafta · 02–08 Haziran 2026 · hazırlayan: Teknik Ekip</div>
          </div>
          <div style={{ width: 38, height: 38, borderRadius: 9, background: "var(--accent)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800 }}>FK</div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
          {SECTIONS.map((s, i) => (
            <div key={s.title} style={{ padding: "16px 22px", borderBottom: i < SECTIONS.length - (SECTIONS.length % 2 === 0 ? 2 : 1) ? "1px solid var(--line)" : 0, borderRight: i % 2 === 0 ? "1px solid var(--line)" : 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <i className={`ti ${s.icon}`} style={{ fontSize: 16, color: s.tone }} />
                <b style={{ fontSize: 13 }}>{s.title}</b>
              </div>
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {s.lines.map((l, j) => (
                  <li key={j} style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5, paddingLeft: 14, position: "relative", marginBottom: 5 }}>
                    <span style={{ position: "absolute", left: 0, color: s.tone }}>•</span>{l}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div style={{ padding: "12px 22px", borderTop: "1px solid var(--line)", fontSize: 11, color: "var(--dim)", display: "flex", justifyContent: "space-between" }}>
          <span>manager2 · otomatik üretildi</span>
          <span>Sonraki gönderim: Pazartesi 09:00</span>
        </div>
      </div>
    </ConsoleShell>
  );
}
