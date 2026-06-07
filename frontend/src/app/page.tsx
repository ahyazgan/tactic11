"use client";

/**
 * Launcher — uygulama girişi. ConsoleShell çatısında (eski TopBar+Sidebar
 * kaldırıldı; tüm ekranlar konsol diline geçti). Bölümlere göre kart ızgarası.
 */

import Link from "next/link";
import type { CSSProperties } from "react";
import { ConsoleShell } from "./_console/shell";

interface Item { href: string; label: string; desc: string }
const SECTIONS: { title: string; items: Item[] }[] = [
  {
    title: "Günlük",
    items: [
      { href: "/overview", label: "Genel Bakış", desc: "Günün öncelikleri, kadro sağlığı, sözleşmeler" },
      { href: "/chat", label: "AI Asistan", desc: "Gerçek veriyle co-pilot — sor, öneri al" },
      { href: "/notifications", label: "Bildirimler", desc: "Kritik risk, dönüş, sözleşme uyarıları" },
    ],
  },
  {
    title: "Kadro & Sağlık",
    items: [
      { href: "/squad", label: "Kadro", desc: "Yük & uygunluk panosu (risk sıralı)" },
      { href: "/physical-tests", label: "Performans / Yük Riski", desc: "Test girişi + risk raporu + PDF" },
      { href: "/medical", label: "Tıbbi Merkez", desc: "Sakatlık & dönüş (return-to-play)" },
      { href: "/contracts", label: "Sözleşmeler", desc: "Biten/geçmiş sözleşme uyarıları" },
    ],
  },
  {
    title: "Analiz",
    items: [
      { href: "/xg", label: "xG Performans", desc: "Beklenen gol + over/underperformance" },
      { href: "/manager-performance", label: "TD Performansı", desc: "xPts vs gerçek puan" },
      { href: "/scout", label: "Scout", desc: "Oyuncu benzerliği + izleme listesi" },
      { href: "/opponent", label: "Rakip Raporu", desc: "Eşleşme grid (kanal zaaf × güç)" },
    ],
  },
  {
    title: "Maç",
    items: [
      { href: "/matches", label: "Maçlar", desc: "Fikstür ve maç analizleri" },
      { href: "/match-plan", label: "Maç Planı", desc: "Canlı senaryo + eşleşme reçetesi" },
      { href: "/leagues", label: "Ligler", desc: "Lig tabloları ve takımlar" },
      { href: "/h2h", label: "Head-to-head", desc: "İki takımı yan yana karşılaştır" },
    ],
  },
];

const cardStyle: CSSProperties = {
  display: "block",
  background: "var(--panel)",
  border: "1px solid var(--line)",
  borderRadius: 9,
  padding: "13px 14px",
  textDecoration: "none",
};

export default function HomePage() {
  return (
    <ConsoleShell
      active="/"
      title="manager2"
      sub="Co-pilot"
      desc="Veriyle karar destek — kulüp teknik ekibi için co-pilot. Bir modüle gir."
      right={
        <div className="rc">
          <h3>Hızlı Başlangıç</h3>
          <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.6 }}>
            <b style={{ color: "var(--ink)" }}>Genel Bakış</b> günün özetidir.
            <div style={{ marginTop: 6 }}>Sol menü ya da aşağıdaki kartlarla tüm modüllere geçebilirsin.</div>
          </div>
        </div>
      }
    >
      {SECTIONS.map((sec) => (
        <div key={sec.title} style={{ marginBottom: 18 }}>
          <div className="st" style={{ marginTop: 0, marginBottom: 11 }}><h2>{sec.title}</h2></div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: 10 }}>
            {sec.items.map((it) => (
              <Link key={it.href} href={it.href} style={cardStyle}>
                <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--ink)" }}>{it.label}</div>
                <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4, lineHeight: 1.4 }}>{it.desc}</div>
              </Link>
            ))}
          </div>
        </div>
      ))}
    </ConsoleShell>
  );
}
