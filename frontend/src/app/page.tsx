"use client";

import Link from "next/link";

interface Item {
  href: string;
  label: string;
  desc: string;
}
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

export default function HomePage() {
  return (
    <div className="max-w-6xl">
      <div className="mb-5">
        <h1 className="text-xl font-bold text-text">manager2</h1>
        <p className="text-[12px] text-textmut mt-0.5">
          Veriyle karar destek — kulüp teknik ekibi için co-pilot.
        </p>
      </div>

      <div className="space-y-6">
        {SECTIONS.map((sec) => (
          <section key={sec.title}>
            <h2 className="text-[10px] font-bold uppercase tracking-[1.5px] text-textdim mb-2.5 flex items-center gap-2">
              <span className="w-3 h-px bg-brand" />
              {sec.title}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
              {sec.items.map((it) => (
                <Link
                  key={it.href}
                  href={it.href}
                  className="group block bg-surface border border-border rounded-lg p-3.5 hover:border-accent hover:bg-surface2 transition-colors"
                >
                  <div className="text-[13.5px] font-semibold text-text group-hover:text-accent transition-colors">
                    {it.label}
                  </div>
                  <div className="text-[11.5px] text-textmut mt-1 leading-snug">{it.desc}</div>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
