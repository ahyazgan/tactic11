"use client";

/**
 * Maç Modu / Kenar Ekranı — antrenör-analist için maç-içi glanceable yüzey.
 * Tek sütun, dev tip, sadece o an önemli olan (push-mantığı). Üretimde tam-ekran
 * kiosk; burada ConsoleShell içinde, nav'dan keşfedilebilir.
 */

import { ConsoleShell } from "../_console/shell";
import { MatchModeBody } from "../_console/match-mode";

export default function MatchModePage() {
  return (
    <ConsoleShell
      active="/match-mode"
      title="Maç Modu"
      sub="Kenar ekranı · maç-içi"
      desc="Kenarda saniyelerle okunur: en acil hamle, eşik geçen oyuncular, saha & rakip uyarıları ve kapanış duruşu — hepsi tek bakışta."
    >
      <MatchModeBody />
    </ConsoleShell>
  );
}
