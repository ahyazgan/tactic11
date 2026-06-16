"use client";

/**
 * Maç Öncesi Modu — maç günü hazırlık brifingi (karar-öncelikli). In-match
 * mode'ların pre-match kardeşi; matchday akışını başlatır → Maç Modu.
 */

import { ConsoleShell } from "../_console/shell";
import { PrematchModeBody } from "../_console/prematch-mode";

export default function PrematchModePage() {
  return (
    <ConsoleShell
      active="/prematch-mode"
      title="Maç Öncesi Modu"
      sub="Maç günü · hazırlık brifingi"
      desc="Maç sabahı tek bakışta: doğrulanmış tahmin, oyun planı, rakip zaafları, anahtar eşleşmeler, önerilen 11, ilkeler/pres ve senaryolar."
    >
      <PrematchModeBody />
    </ConsoleShell>
  );
}
