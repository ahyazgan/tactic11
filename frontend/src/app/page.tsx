"use client";

import Link from "next/link";
import { Panel } from "@/components/ui";
import { useCurrentUser } from "@/lib/auth";

const QUICK_LINKS: { href: string; label: string; desc: string }[] = [
  { href: "/leagues", label: "Ligler",
    desc: "Lig listesi ve takım tabloları" },
  { href: "/h2h", label: "Head-to-head",
    desc: "İki takımı yan yana karşılaştır" },
  { href: "/matches/16029/halftime?my_team_id=217", label: "Devre Arası",
    desc: "1. yarı sayılar + AI brief" },
  { href: "/matches/16029/live?my_team_id=217&interval_seconds=5&max_minute=90",
    label: "Canlı Maç (Replay)",
    desc: "WebSocket push + sub önerisi" },
  { href: "/teams/217/tactical", label: "Takım Taktiksel",
    desc: "30 engine batch çıktısı" },
  { href: "/teams/217/trend", label: "Sezon Trendi",
    desc: "PPDA/tilt/xT slope + biggest shift" },
];

export default function HomePage() {
  const { user, isLoading } = useCurrentUser();

  return (
    <div className="max-w-6xl">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <h1 className="text-lg font-semibold text-text">Gösterge tablosu</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Veriyle karar destek — kulüp analiz şefi için co-pilot.
          </p>
        </div>
        {!isLoading && !user && (
          <Link
            href="/login"
            className="text-[11px] uppercase tracking-wide px-2 py-1 rounded border border-borderlt text-accent hover:bg-surface2"
          >
            Giriş yap
          </Link>
        )}
      </div>

      <h2 className="text-sm font-semibold text-text mb-2 mt-4">
        Hızlı erişim
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {QUICK_LINKS.map((r) => (
          <Link
            key={r.href}
            href={r.href}
            className="block bg-surface border border-border rounded-md p-3 hover:border-accent transition-colors"
          >
            <div className="text-sm font-semibold text-text">{r.label}</div>
            <div className="text-[12px] text-textmut mt-1">{r.desc}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
