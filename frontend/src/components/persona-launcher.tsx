/**
 * Persona Launcher — giriş ekranı.
 *
 * İki faz:
 *  1) Persona seçimi: "Hangisisin / neyle ilgileniyorsun?" 4 büyük kart.
 *  2) Görev panosu: seçilen personanın 4-5 görev kartı. Tıkla → işe git.
 *
 * Seçim localStorage'da tutulur; sonraki girişlerde doğrudan görev panosu
 * açılır ("Rolü değiştir" ile sıfırlanır). Tüm 61 sayfa hâlâ erişilebilir —
 * bu sadece sade bir varsayılan başlangıç.
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, ChevronLeft } from "lucide-react";
import {
  PERSONAS,
  findPersona,
  getStoredPersona,
  storePersona,
  clearStoredPersona,
  type Persona,
} from "@/lib/personas";

export function PersonaLauncher() {
  const [selected, setSelected] = React.useState<Persona | null>(null);
  const [ready, setReady] = React.useState(false);

  // İlk render'da kayıtlı persona varsa doğrudan görev panosuna geç.
  React.useEffect(() => {
    const stored = findPersona(getStoredPersona());
    if (stored) setSelected(stored);
    setReady(true);
  }, []);

  function choose(p: Persona) {
    storePersona(p.id);
    setSelected(p);
  }

  function reset() {
    clearStoredPersona();
    setSelected(null);
  }

  // Hydration sırasında boş tut — flicker olmasın.
  if (!ready) return <div className="min-h-screen bg-bg" />;

  if (selected) return <TaskBoard persona={selected} onChangeRole={reset} />;
  return <PersonaPicker onChoose={choose} />;
}

function PersonaPicker({ onChoose }: { onChoose: (p: Persona) => void }) {
  return (
    <div className="min-h-screen bg-bg text-text flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-3xl">
        <header className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Hoş geldin</h1>
          <p className="mt-2 text-textmut">
            Teknik ekipte hangi roldesin? Seç — sadece senin işine yarayan
            ekranları göstereceğiz.
          </p>
        </header>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {PERSONAS.map((p) => {
            const Icon = p.icon;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onChoose(p)}
                className="group text-left rounded-xl border border-border bg-surface p-5
                           hover:border-accent hover:shadow-lg transition
                           focus:outline-none focus:ring-2 focus:ring-accent"
              >
                <div className="flex items-start gap-4">
                  <span className="shrink-0 rounded-lg bg-accent/10 p-3 text-accent">
                    <Icon size={24} />
                  </span>
                  <div className="min-w-0">
                    <div className="font-semibold">{p.title}</div>
                    <div className="mt-1 text-sm text-textmut">{p.tagline}</div>
                    <div className="mt-3 inline-flex items-center gap-1 text-sm text-accent
                                    opacity-0 group-hover:opacity-100 transition">
                      Başla <ArrowRight size={15} />
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        <p className="mt-8 text-center text-xs text-textdim">
          Tüm modüllere yine kenar menüden ulaşabilirsin. Bu ekran sadece hızlı
          bir başlangıç.
        </p>
      </div>
    </div>
  );
}

function TaskBoard({
  persona,
  onChangeRole,
}: {
  persona: Persona;
  onChangeRole: () => void;
}) {
  const Icon = persona.icon;
  return (
    <div className="min-h-screen bg-bg text-text px-4 py-10">
      <div className="mx-auto w-full max-w-4xl">
        <header className="mb-8 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="rounded-lg bg-accent/10 p-3 text-accent">
              <Icon size={26} />
            </span>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">{persona.title}</h1>
              <p className="text-sm text-textmut">{persona.tagline}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onChangeRole}
            className="shrink-0 inline-flex items-center gap-1 rounded-lg border border-border
                       bg-surface px-3 py-1.5 text-sm text-textmut hover:text-text
                       hover:border-accent transition"
          >
            <ChevronLeft size={15} /> Rolü değiştir
          </button>
        </header>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {persona.tasks.map((task) => {
            const TIcon = task.icon;
            const isPrimary = task.href === persona.primary;
            return (
              <Link
                key={task.href}
                href={task.href}
                className={`group rounded-xl border bg-surface p-5 transition
                            hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-accent
                            ${isPrimary ? "border-accent ring-1 ring-accent/30" : "border-border hover:border-accent"}`}
              >
                <div className="flex items-center gap-3">
                  <span className="rounded-lg bg-accent/10 p-2.5 text-accent">
                    <TIcon size={20} />
                  </span>
                  <div className="font-semibold">{task.label}</div>
                </div>
                <p className="mt-3 text-sm text-textmut">{task.description}</p>
                <div className="mt-3 inline-flex items-center gap-1 text-sm text-accent
                                opacity-0 group-hover:opacity-100 transition">
                  Aç <ArrowRight size={15} />
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
