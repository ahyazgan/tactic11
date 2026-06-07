"use client";

/**
 * Takımlar — lig bazlı takım listesine giriş. ConsoleShell çatısında.
 */

import Link from "next/link";
import { ConsoleShell } from "../_console/shell";

export default function TeamsConsolePage() {
  return (
    <ConsoleShell
      active="/teams"
      title="Takımlar"
      sub="Lig bazlı liste"
      desc="Takım listesi lig bazında tutulur. Önce bir lig seç, ardından takımları gör."
      right={
        <div className="rc">
          <h3>İpucu</h3>
          <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
            Ligler ekranından bir lige tıklayınca o ligin takımları açılır.
          </div>
        </div>
      }
    >
      <div className="rc" style={{ margin: 0 }}>
        <div style={{ fontSize: 13, color: "var(--ink)", marginBottom: 12 }}>Takımları görmek için önce bir lig seç:</div>
        <Link href="/leagues" style={{ display: "inline-block", fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.5, padding: "7px 14px", borderRadius: 7, border: "1px solid var(--line)", color: "var(--ink)", background: "var(--panel3)", textDecoration: "none" }}>
          Liglere git →
        </Link>
      </div>
    </ConsoleShell>
  );
}
