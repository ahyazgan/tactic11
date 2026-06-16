"use client";

/**
 * Sportmonks Bağlantı Planı — matchday motorunu gerçek veriye bağlama haritası.
 */

import { ConsoleShell } from "../_console/shell";
import { SportmonksPlanBody } from "../_console/sportmonks-plan";

export default function SportmonksPlanPage() {
  return (
    <ConsoleShell
      active="/sportmonks-plan"
      title="Sportmonks Bağlantı Planı"
      sub="Matchday → gerçek veri"
      desc="Matchday motorunun her parçası hangi Sportmonks kaynağına bağlanır, hangisi add-on ister, hangisi premium feed gerektirir — durum haritası + 3 fazlı geçiş. Mimari hazır; motor ve UI değişmeden gerçeğe geçer."
    >
      <SportmonksPlanBody />
    </ConsoleShell>
  );
}
