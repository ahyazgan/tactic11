"use client";

/**
 * Devre Arası Modu — 15 dakikalık altın pencere için karar-öncelikli ekran.
 * Maç Modu'nun kardeşi. Analitik döküm /matches/[id]/halftime'da.
 */

import { ConsoleShell } from "../_console/shell";
import { HalftimeModeBody } from "../_console/halftime-mode";

export default function HalftimeModePage() {
  return (
    <ConsoleShell
      active="/halftime-mode"
      title="Devre Arası Modu"
      sub="15 dk · karar penceresi"
      desc="Soyunma odasında tek bakışta: tek-cümle okuma, 2. yarıya öncelikli hamleler, ne çalıştı/risk/plan, duran top düzeltmesi ve senaryo planı."
    >
      <HalftimeModeBody />
    </ConsoleShell>
  );
}
