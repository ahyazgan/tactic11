/**
 * Sidebar — DESIGN.md §3 + Faz 3:
 * w-56, dikey nav, aktif border-l-2 accent, admin role guard.
 * Footer: last-sync timestamp + build SHA.
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import { cn } from "@/lib/cn";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

interface NavItem {
  href: string;
  labelKey: string;
  roles?: ("admin" | "analyst" | "coach" | "viewer")[];
}

const NAV_ITEMS: NavItem[] = [
  { href: "/leagues", labelKey: "nav.leagues" },
  { href: "/teams", labelKey: "nav.teams" },
  { href: "/h2h", labelKey: "nav.h2h" },
  { href: "/matches", labelKey: "nav.matches" },
  { href: "/training", labelKey: "nav.training", roles: ["admin", "coach", "analyst"] },
  { href: "/decisions", labelKey: "nav.decisions", roles: ["admin", "coach", "analyst"] },
  { href: "/calibration", labelKey: "nav.calibration" },
  { href: "/chat", labelKey: "nav.chat" },
  { href: "/admin", labelKey: "nav.admin", roles: ["admin"] },
];

interface JobRow {
  job_name: string;
  status: string;
  ended_at: string | null;
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  if (diff < 60_000) return "az önce";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} dk önce`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} sa önce`;
  return `${Math.floor(diff / 86_400_000)} g önce`;
}

export function Sidebar({
  mobileOpen = false,
  onClose,
}: { mobileOpen?: boolean; onClose?: () => void } = {}) {
  const pathname = usePathname();
  const { user } = useCurrentUser();
  const { t } = useI18n();
  const role = user?.role ?? "viewer";

  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.roles || item.roles.includes(role),
  );

  const shouldFetchJobs =
    user?.role === "admin" || user?.role === "analyst";
  const { data: jobs } = useSWR<JobRow[]>(
    shouldFetchJobs ? "/admin/jobs" : null,
    apiFetch,
    { refreshInterval: 5 * 60_000 },
  );
  const lastSync = jobs?.find(
    (j) => j.job_name.startsWith("sync") && j.status === "success" && j.ended_at,
  );

  return (
    <>
      {/* Mobil overlay — drawer açıkken arka planı karart + tıklayınca kapat */}
      {mobileOpen && (
        <div
          className="fixed inset-0 top-12 z-20 bg-black/50 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        className={cn(
          "fixed left-0 top-12 bottom-0 w-56 bg-surface border-r border-border flex flex-col z-30",
          "transition-transform duration-200 md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        <nav className="flex-1 overflow-y-auto py-2">
          {visibleItems.map((item) => {
            const isActive =
              pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                className={cn(
                  "block px-4 py-2 text-[13px] border-l-2 transition-colors",
                  isActive
                    ? "bg-surface2 text-text border-accent font-medium"
                    : "border-transparent text-textmut hover:text-text hover:bg-surface2",
                )}
              >
                {t(item.labelKey)}
              </Link>
            );
          })}
        </nav>
        <SidebarFooter lastSyncIso={lastSync?.ended_at ?? null} />
      </aside>
    </>
  );
}

function SidebarFooter({ lastSyncIso }: { lastSyncIso: string | null }) {
  const { t, locale } = useI18n();
  const buildSha = process.env.NEXT_PUBLIC_BUILD_SHA ?? "dev";
  const buildLabel = buildSha.slice(0, 7);
  return (
    <footer className="px-4 py-2 border-t border-border text-[10px] text-textdim space-y-0.5">
      {lastSyncIso && (
        <Link
          href="/admin"
          className="block hover:text-text transition-colors"
          title={new Date(lastSyncIso).toLocaleString(locale === "en" ? "en-GB" : "tr-TR")}
        >
          {t("sidebar.lastSync")}: {relativeTime(lastSyncIso)}
        </Link>
      )}
      <div>DESIGN.md • v1</div>
      <div className="font-mono">build {buildLabel}</div>
    </footer>
  );
}
