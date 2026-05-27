import Link from "next/link";

const ROUTES = [
  { href: "/matches", label: "Maçlar", desc: "Bu haftaki maçlar + tahmin" },
  { href: "/calibration", label: "Kalibrasyon", desc: "Brier + log loss + ECE grafikleri" },
  { href: "/decisions", label: "Kararlar", desc: "Lineup + sub + tactical öneriler" },
  { href: "/chat", label: "Asistan", desc: "Manager co-pilot chat" },
  { href: "/settings", label: "Ayarlar", desc: "Branding + webhook + ML model" },
];

export default function HomePage() {
  return (
    <main className="max-w-5xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-2">manager2</h1>
      <p className="text-muted mb-8">Football Manager için veri-tabanlı co-pilot.</p>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {ROUTES.map((r) => (
          <Link key={r.href} href={r.href} className="card hover:border-accent">
            <h2 className="text-lg font-semibold mb-1">{r.label}</h2>
            <p className="text-sm text-muted">{r.desc}</p>
          </Link>
        ))}
      </div>
      <p className="text-sm text-muted mt-12">
        Giriş yapmadıysan: <Link href="/login" className="text-accent">/login</Link>
      </p>
    </main>
  );
}
