"use client";

/**
 * Maç Günü — maçın dört aşaması tek ekranda: Hazırlık → Canlı → Devre Arası → Maç Sonu.
 * Eski dört ayrı sayfanın (prematch-mode / match-mode / halftime-mode / match-review)
 * gövdelerini aynen kullanır; yalnız aralarındaki geçiş tek bir aşama şeridine indi.
 * Aşama `?asama=` ile seçilir; yoksa maçın o anki durumuna göre açılır.
 *
 * Canlı aşaması: demo modunda kayıtlı zaman-serisiyle kenar ekranı; canlı modda
 * gerçek motor paneli. Koç işareti (Uyguladım / Uygulamadım) yalnız canlı modda
 * karar defterine yazılır — motor oradan öğrenir.
 */

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { matchState, type MatchState } from "@/lib/command-brief";
import { DEMO_MODE } from "@/lib/demo-mode";
import { ConsoleShell } from "../_console/shell";
import { PrematchModeBody } from "../_console/prematch-mode";
import { MatchModeBody } from "../_console/match-mode";
import { HalftimeModeBody } from "../_console/halftime-mode";
import { MatchReviewBody } from "../_console/match-review";
import { LiveDecisionPanel } from "../_console/live-decision";

type PhaseId = "hazirlik" | "canli" | "devre" | "sonu";

interface Phase { id: PhaseId; label: string; icon: string; desc: string }

const PHASES: Phase[] = [
  { id: "hazirlik", label: "Hazırlık",    icon: "ti-clipboard-check", desc: "Maç sabahı tek bakışta: tahmin, oyun planı, rakip zaafları, önerilen 11 ve senaryolar." },
  { id: "canli",    label: "Canlı",       icon: "ti-ball-football",   desc: "Kenarda saniyelerle okunur: en acil hamle, eşik geçen oyuncular, saha ve rakip uyarıları." },
  { id: "devre",    label: "Devre Arası", icon: "ti-clock-pause",     desc: "15 dakikalık pencere: tek cümle okuma, ikinci yarı hamleleri, duran top düzeltmesi." },
  { id: "sonu",     label: "Maç Sonu",    icon: "ti-checkup-list",    desc: "Maç boyunca verilen uyarıların kaçı gerçekleşti; kararların üstüne bindirilmiş hali." },
];

const NOW_PHASE: Record<MatchState, PhaseId> = { pre: "hazirlik", live: "canli", post: "sonu" };

function isPhase(v: string | null): v is PhaseId {
  return PHASES.some((p) => p.id === v);
}

function MatchDay() {
  const requested = useSearchParams().get("asama");
  const now = NOW_PHASE[matchState()];
  const phase = PHASES.find((p) => p.id === (isPhase(requested) ? requested : now)) ?? PHASES[0];

  const nav = (
      <nav className="phases" aria-label="Maç aşamaları">
        {PHASES.map((p, i) => (
          <Link
            key={p.id}
            href={`/match-day?asama=${p.id}`}
            scroll={false}
            className={`phase${p.id === phase.id ? " on" : ""}`}
            aria-current={p.id === phase.id ? "step" : undefined}
          >
            <span className="ph-n">{i + 1}</span>
            <i className={`ti ${p.icon}`} aria-hidden="true" />
            <span className="ph-l">{p.label}</span>
            {p.id === now && <span className="ph-now">Şimdi</span>}
          </Link>
        ))}
      </nav>
  );

  if (phase.id === "canli" && !DEMO_MODE) {
    return (
      <LiveDecisionPanel
        frame={({ sub, right, children }) => (
          <ConsoleShell active="/match-day" title="Maç Günü" sub={sub ? `Canlı · ${sub}` : "Canlı"} desc={phase.desc} right={right}>
            {nav}
            {children}
          </ConsoleShell>
        )}
      />
    );
  }

  return (
    <ConsoleShell active="/match-day" title="Maç Günü" sub={phase.label} desc={phase.desc}>
      {nav}

      {phase.id === "hazirlik" && <PrematchModeBody />}
      {phase.id === "canli" && (
        <>
          <MatchModeBody />
          <Link href="/matches/demo/live" className="phase-more">
            <i className="ti ti-layout-dashboard" aria-hidden="true" />
            Ayrıntılı canlı konsolu aç
          </Link>
        </>
      )}
      {phase.id === "devre" && <HalftimeModeBody />}
      {phase.id === "sonu" && <MatchReviewBody />}
    </ConsoleShell>
  );
}

export default function MatchDayPage() {
  // useSearchParams statik derlemede Suspense sınırı ister.
  return (
    <Suspense fallback={null}>
      <MatchDay />
    </Suspense>
  );
}
