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
  label: string;
  roles?: ("admin" | "analyst" | "coach" | "viewer")[];
}

const NAV_ITEMS: NavItem[] = [
  { href: "/overview", label: "Genel Bakış", roles: ["admin", "coach", "analyst"] },
  { href: "/leagues", label: "Ligler" },
  { href: "/teams", label: "Takımlar" },
  { href: "/h2h", label: "H2H" },
  { href: "/matches", label: "Maçlar" },
  { href: "/match-plan", label: "Maç Planı", roles: ["admin", "coach", "analyst"] },
  { href: "/training", label: "Antrenman", roles: ["admin", "coach", "analyst"] },
  { href: "/performance", label: "Performans Testi", roles: ["admin", "coach", "analyst"] },
  { href: "/physical-tests", label: "Yük Riski", roles: ["admin", "coach", "analyst"] },
  { href: "/medical", label: "Tıbbi Merkez", roles: ["admin", "coach", "analyst"] },
  { href: "/decisions", label: "Kararlar", roles: ["admin", "coach", "analyst"] },
  { href: "/xg", label: "xG Analiz", roles: ["admin", "coach", "analyst"] },
  { href: "/calibration", label: "Kalibrasyon" },
  { href: "/chat", label: "Asistan" },
  { href: "/notifications", label: "Bildirimler", roles: ["admin"] },
  { href: "/contracts", label: "Sözleşmeler", roles: ["admin", "analyst"] },
  { href: "/admin", label: "Admin", roles: ["admin"] },
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

export function Sidebar() {
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
    <aside className="fixed left-0 top-12 bottom-0 w-56 bg-surface border-r border-border flex flex-col">
      <nav className="flex-1 overflow-y-auto py-2">
        {visibleItems.map((item) => {
          const isActive =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "block px-4 py-2 text-[13px] border-l-2 transition-colors",
                isActive
                  ? "bg-surface2 text-text border-accent font-medium"
                  : "border-transparent text-textmut hover:text-text hover:bg-surface2",
              )}
            >
              {t(item.label)}
            </Link>
          );
        })}
      </nav>
      <SidebarFooter lastSyncIso={lastSync?.ended_at ?? null} />
    </aside>
  );
}

function SidebarFooter({ lastSyncIso }: { lastSyncIso: string | null }) {
  const buildSha = process.env.NEXT_PUBLIC_BUILD_SHA ?? "dev";
  const buildLabel = buildSha.slice(0, 7);
  return (
    <footer className="px-4 py-2 border-t border-border text-[10px] text-textdim space-y-0.5">
      {lastSyncIso && (
        <Link
          href="/admin"
          className="block hover:text-text transition-colors"
          title={new Date(lastSyncIso).toLocaleString("tr-TR")}
        >
          Son sync: {relativeTime(lastSyncIso)}
        </Link>
      )}
      <div>DESIGN.md • v1</div>
      <div className="font-mono">build {buildLabel}</div>
    </footer>
  );
}
