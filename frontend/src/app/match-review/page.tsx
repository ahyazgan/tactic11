"use client";

/**
 * Maç Değerlendirmesi — kanıt döngüsünü kapatan retrospektif. Sistemin uyarıları
 * gerçek olaylarla reconcile edilir + analistin kararları (action-log) bindirilir.
 */

import { ConsoleShell } from "../_console/shell";
import { MatchReviewBody } from "../_console/match-review";

export default function MatchReviewPage() {
  return (
    <ConsoleShell
      active="/match-review"
      title="Maç Değerlendirmesi"
      sub="Uyarı → sonuç · retrospektif"
      desc="Sistemin maç boyunca yaptığı uyarıların kaçı gerçekten oldu? Her uyarı gerçek olayla reconcile edilir; analistin kararları üstüne bindirilir. Kanıt döngüsünün son halkası."
    >
      <MatchReviewBody />
    </ConsoleShell>
  );
}
