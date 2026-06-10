"use client";

/**
 * Skaut Raporları — oyuncu bazlı gözlem notları + izleme geçmişi + öneri.
 * ConsoleShell, FM26 açık tema. DEMO_MODE inline mock (hedef oyuncular).
 */

import * as React from "react";
import { useProviderAccess, ProviderConnect, ProviderConnectedBar } from "@/lib/provider-access";
import { ConsoleShell } from "../_console/shell";

type Rec = "İmzala" | "İzlemeye devam" | "Geç";
const REC_META: Record<Rec, { v: string; bg: string }> = {
  "İmzala": { v: "var(--low)", bg: "var(--low-bg)" },
  "İzlemeye devam": { v: "var(--mid)", bg: "var(--mid-bg)" },
  "Geç": { v: "var(--dim)", bg: "var(--surface2)" },
};

interface Report {
  player: string; pos: string; age: number; club: string;
  scout: string; date: string; rating: number; watches: number;
  rec: Rec; summary: string;
}

const REPORTS: Report[] = [
  { player: "Mateo Ferreira", pos: "Sol Kanat", age: 19, club: "CA Rosario", scout: "H. Demir", date: "2026-06-05", rating: 4.5, watches: 6, rec: "İmzala",
    summary: "Sol ayağı çok güçlü, 1v1'de %68 başarı. İçeri kat edip bitiriyor; savunmada efor değişken. Tolga'nın rotasyon/halefi profili." },
  { player: "Luka Novak", pos: "Ön Libero", age: 23, club: "NK Maribor", scout: "A. Yıldız", date: "2026-06-03", rating: 4.0, watches: 4, rec: "İmzala",
    summary: "Pas %91, top kazanımı maç başına 7.2. Tempo kontrolü iyi; uzun pas dağarcığı sınırlı. Serkan'ın yanına ideal denge oyuncusu." },
  { player: "Diego Sánchez", pos: "Santrfor", age: 21, club: "Dep. Cali", scout: "H. Demir", date: "2026-05-29", rating: 3.5, watches: 3, rec: "İzlemeye devam",
    summary: "Ceza sahası içi içgüdüsü yüksek (xG fazlası +0.18). Sırtı dönük oyunda zayıf. Bir sezon daha izlenmeli, fiyat/performans iyi." },
  { player: "Kwame Mensah", pos: "Stoper", age: 20, club: "Asante Kotoko", scout: "M. Kaya", date: "2026-05-24", rating: 4.0, watches: 5, rec: "İmzala",
    summary: "Hava hakimiyeti %79, hız çok iyi (10m 1.71). Sol ayak kullanımı gelişmeli. Eren'in (33) yaş sorununa uzun vadeli çözüm." },
  { player: "Tom Bauer", pos: "Sağ Bek", age: 24, club: "SV Wehen", scout: "A. Yıldız", date: "2026-05-20", rating: 3.0, watches: 2, rec: "Geç",
    summary: "Hücum katkısı sınırlı, orta kalitesi düşük. Savunmada disiplinli ama profilimize (yüksek bek) uymuyor." },
];

const AVG_RATING = Math.round((REPORTS.reduce((a, r) => a + r.rating, 0) / REPORTS.length) * 10) / 10;
const SIGN = REPORTS.filter((r) => r.rec === "İmzala").length;
const WATCHES = REPORTS.reduce((a, r) => a + r.watches, 0);

function Stars({ v }: { v: number }) {
  return (
    <span style={{ display: "inline-flex", gap: 1 }}>
      {[1, 2, 3, 4, 5].map((i) => (
        <i key={i} className={`ti ${i <= v ? "ti-star-filled" : i - 0.5 === v ? "ti-star-half-filled" : "ti-star"}`}
           style={{ fontSize: 13, color: i <= v + 0.5 ? "var(--mid)" : "var(--line2)" }} />
      ))}
    </span>
  );
}

const WATCHLIST = [
  { player: "Mateo Ferreira", match: "CA Rosario — Boca (D)", when: "10 Haz · 02:00" },
  { player: "Diego Sánchez", match: "Dep. Cali — Nacional", when: "12 Haz · 03:30" },
  { player: "Kwame Mensah", match: "Kotoko — Hearts", when: "14 Haz · 17:00" },
];

export default function ScoutReportsPage() {
  const access = useProviderAccess("scout");

  if (!access.connected) {
    return (
      <ConsoleShell
        active="/scout-reports"
        title="Skaut Raporları"
        sub="Bağlantı gerekli"
        desc="Skaut gözlem notları ve izleme verileri için bir 3. parti scout sağlayıcıya bağlan."
        right={<div className="rc"><h3>Neden bağlantı?</h3><div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55 }}>Rapor, izleme listesi ve skaut ağı bir scout veri sağlayıcısından gelir. Sağlayıcını seçip ID + şifreni girince bölüm açılır.</div></div>}
      >
        <ProviderConnect kind="scout" onConnect={access.connect} />
      </ConsoleShell>
    );
  }

  const right = (
    <>
      <div className="rc">
        <h3>İzleme Listesi <span className="tiny">yaklaşan maçlar</span></h3>
        {WATCHLIST.map((w, i) => (
          <div className="alrt" key={i}>
            <span className="ai" style={{ background: "var(--accent)" }} />
            <div className="am"><b>{w.player}</b>
              <span className="tm">{w.match} · {w.when}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="rc">
        <h3>Skaut Ağı</h3>
        <div className="stat"><span>H. Demir</span><span className="sv">2 rapor</span></div>
        <div className="stat"><span>A. Yıldız</span><span className="sv">2 rapor</span></div>
        <div className="stat"><span>M. Kaya</span><span className="sv">1 rapor</span></div>
        <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 10 }}>Bölgeler: Güney Amerika, Orta Avrupa, Batı Afrika.</div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/scout-reports"
      title="Skaut Raporları"
      sub="Gözlem · öneri"
      desc="Hedef oyuncular için skaut gözlem notları, izleme geçmişi ve transfer önerisi."
      source={["statsbomb", "claude"]}
      right={right}
    >
      <ProviderConnectedBar providerLabel={access.providerLabel} user={access.user} onDisconnect={access.disconnect} />
      <div className="kpis">
        <div className="kpi"><div className="kl">Toplam Rapor</div><div className="kn">{REPORTS.length}</div><div className="kd">aktif dosya</div></div>
        <div className="kpi"><div className="kl">İzlenen Oyuncu</div><div className="kn">{REPORTS.length}</div><div className="kd">{WATCHES} maç izlendi</div></div>
        <div className="kpi"><div className="kl">İmzala Önerisi</div><div className="kn" style={{ color: "var(--low)" }}>{SIGN}</div><div className="kd">öncelikli hedef</div></div>
        <div className="kpi"><div className="kl">Ort. Rating</div><div className="kn" style={{ color: "var(--mid)" }}>{AVG_RATING.toFixed(1)}</div><div className="kd">5 üzerinden</div></div>
        <div className="kpi"><div className="kl">Bu Ay</div><div className="kn">{REPORTS.length}</div><div className="kd">yeni rapor</div></div>
      </div>

      <div className="st" style={{ marginTop: 0 }}><h2>Raporlar</h2><span className="ep">en yeni önce</span></div>
      <div style={{ display: "grid", gap: 10 }}>
        {REPORTS.map((r, i) => {
          const m = REC_META[r.rec];
          return (
            <div className="rc" key={i} style={{ margin: 0, borderLeft: `3px solid ${m.v}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
                <div>
                  <b style={{ fontSize: 14 }}>{r.player}</b>
                  <span style={{ color: "var(--muted)", fontSize: 12.5 }}> · {r.pos} · {r.age} yaş · {r.club}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <Stars v={r.rating} />
                  <span className="risk" style={{ background: m.bg, color: m.v }}>
                    <span className="rd" style={{ background: m.v }} />{r.rec}
                  </span>
                </div>
              </div>
              <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.55, marginBottom: 8 }}>{r.summary}</div>
              <div style={{ fontSize: 11, color: "var(--dim)", borderTop: "1px solid var(--line)", paddingTop: 7, display: "flex", gap: 14, flexWrap: "wrap" }}>
                <span><i className="ti ti-user-search" style={{ marginRight: 4 }} />{r.scout}</span>
                <span><i className="ti ti-calendar" style={{ marginRight: 4 }} />{r.date}</span>
                <span><i className="ti ti-eye" style={{ marginRight: 4 }} />{r.watches} maç izlendi</span>
              </div>
            </div>
          );
        })}
      </div>
    </ConsoleShell>
  );
}
