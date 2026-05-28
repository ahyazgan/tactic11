/**
 * TopBar — DESIGN.md §3. h-12, tenant + sezon seçici (sol), kullanıcı (sağ).
 */
"use client";

import * as React from "react";
import { logout, useCurrentUser } from "@/lib/auth";
import { Pill } from "@/components/ui";

const SEASONS = [2024, 2023];

export function TopBar() {
  const { user } = useCurrentUser();
  const [season, setSeason] = React.useState<number>(SEASONS[0]);

  return (
    <header className="fixed top-0 left-0 right-0 h-12 bg-surface border-b border-border z-30 flex items-center px-4 gap-3">
      <div className="font-semibold text-text text-[13px]">manager2</div>
      <div className="text-textdim">·</div>
      {/* Tenant slug — read-only display */}
      <div className="text-[11px] text-textmut">
        {user?.tenant_slug ?? user?.tenant_id ?? "—"}
      </div>
      {/* Sezon seçici */}
      <select
        value={season}
        onChange={(e) => setSeason(Number(e.target.value))}
        className="bg-surface2 border border-border text-text text-[12px] px-2 py-1 rounded h-7"
        aria-label="Sezon"
      >
        {SEASONS.map((s) => (
          <option key={s} value={s}>
            {s}/{s + 1}
          </option>
        ))}
      </select>

      <div className="flex-1" />

      {/* Sağ taraf: kullanıcı + logout */}
      {user && (
        <>
          <Pill variant="neutral">{user.role}</Pill>
          <span className="text-[12px] text-textmut">{user.email}</span>
          <button
            type="button"
            onClick={logout}
            className="text-[11px] uppercase tracking-wide px-2 py-1 rounded border border-borderlt text-textmut hover:text-text hover:border-accent transition-colors"
          >
            Çıkış
          </button>
        </>
      )}
    </header>
  );
}
