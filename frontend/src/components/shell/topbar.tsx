/**
 * TopBar — DESIGN.md §3 + Faz 3:
 * h-12, tenant + sezon, user, logout
 * + kota uyarı pill (analyst/admin)
 * + idle timer 14dk uyarı / 15dk logout
 * + offline banner (TopBar altında)
 */
"use client";

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { logout, useCurrentUser } from "@/lib/auth";
import { useIdleTimer } from "@/lib/idle";
import { useOnlineStatus } from "@/lib/online";
import { useI18n } from "@/lib/i18n";
import { Pill } from "@/components/ui";

function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div
      className="flex items-center rounded border border-border overflow-hidden"
      role="group"
      aria-label={t("common.language")}
    >
      {(["tr", "en"] as const).map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => setLocale(l)}
          aria-pressed={locale === l}
          className={
            "px-1.5 py-0.5 text-[10px] uppercase tracking-wide transition-colors " +
            (locale === l
              ? "bg-accent text-bg font-semibold"
              : "text-textmut hover:text-text")
          }
        >
          {l}
        </button>
      ))}
    </div>
  );
}

const SEASONS = [2024, 2023];

interface UsageSummary {
  anthropic_tokens_today?: number;
  api_football_calls_today?: number;
  anthropic_token_limit?: number;
  api_football_daily_limit?: number;
}

function quotaPct(used?: number, limit?: number): number {
  if (!used || !limit) return 0;
  return Math.round((used / limit) * 100);
}

export function TopBar({ onMenuClick }: { onMenuClick?: () => void } = {}) {
  const { user } = useCurrentUser();
  const { t } = useI18n();
  const [season, setSeason] = React.useState<number>(SEASONS[0]);
  const [idleWarn, setIdleWarn] = React.useState(false);
  const online = useOnlineStatus();

  const shouldFetchUsage =
    user?.role === "admin" || user?.role === "analyst";
  const { data: usage } = useSWR<UsageSummary>(
    shouldFetchUsage ? "/admin/usage" : null,
    apiFetch,
    { refreshInterval: 60_000 },
  );

  useIdleTimer({
    timeout: user ? 15 * 60 * 1000 : Number.POSITIVE_INFINITY,
    warnBefore: 60 * 1000,
    onWarn: React.useCallback(() => setIdleWarn(true), []),
    onIdle: React.useCallback(() => {
      logout();
    }, []),
  });

  React.useEffect(() => {
    if (!idleWarn) return;
    const t = setTimeout(() => setIdleWarn(false), 10_000);
    return () => clearTimeout(t);
  }, [idleWarn]);

  const tokensPct = quotaPct(
    usage?.anthropic_tokens_today,
    usage?.anthropic_token_limit,
  );
  const callsPct = quotaPct(
    usage?.api_football_calls_today,
    usage?.api_football_daily_limit,
  );
  const maxQuotaPct = Math.max(tokensPct, callsPct);

  return (
    <>
      <header className="fixed top-0 left-0 right-0 h-12 bg-surface border-b border-border z-30 flex items-center px-3 sm:px-4 gap-2 sm:gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          className="md:hidden -ml-1 p-1.5 rounded text-textmut hover:text-text hover:bg-surface2 transition-colors"
          aria-label={t("topbar.menu")}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <div className="font-semibold text-text text-[13px]">manager2</div>
        <div className="text-textdim hidden sm:block">·</div>
        <div className="text-[11px] text-textmut hidden sm:block">
          {user?.tenant_slug ?? user?.tenant_id ?? "—"}
        </div>
        <select
          value={season}
          onChange={(e) => setSeason(Number(e.target.value))}
          className="bg-surface2 border border-border text-text text-[12px] px-2 py-1 rounded h-7"
          aria-label={t("topbar.seasonLabel")}
        >
          {SEASONS.map((s) => (
            <option key={s} value={s}>
              {s}/{s + 1}
            </option>
          ))}
        </select>

        <div className="flex-1" />

        <LanguageSwitcher />

        {shouldFetchUsage && maxQuotaPct >= 80 && (
          <Pill variant={maxQuotaPct >= 95 ? "danger" : "warn"}>
            {t("topbar.quota")} %{maxQuotaPct}
          </Pill>
        )}

        {idleWarn && (
          <Pill variant="warn">{t("topbar.idleWarn")}</Pill>
        )}

        {user && (
          <>
            <Pill variant="neutral">{user.role}</Pill>
            <span className="text-[12px] text-textmut hidden sm:inline">{user.email}</span>
            <button
              type="button"
              onClick={logout}
              className="text-[11px] uppercase tracking-wide px-2 py-1 rounded border border-borderlt text-textmut hover:text-text hover:border-accent transition-colors"
            >
              {t("topbar.logout")}
            </button>
          </>
        )}
      </header>

      {!online && (
        <div className="fixed top-12 left-0 right-0 z-30 bg-danger/20 text-danger text-[11px] text-center py-1 border-b border-danger/40">
          {t("topbar.offline")}
        </div>
      )}
    </>
  );
}
