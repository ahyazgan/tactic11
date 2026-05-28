/**
 * Sidebar — DESIGN.md §3. w-56, dikey nav, aktif item border-l-2 accent.
 * Admin nav sadece role==='admin'.
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/cn";
import { useCurrentUser } from "@/lib/auth";

interface NavItem {
  href: string;
  label: string;
  /** Hangi rollere görünür (boşsa hepsi). */
  roles?: ("admin" | "analyst" | "coach" | "viewer")[];
}

const NAV_ITEMS: NavItem[] = [
  { href: "/leagues", label: "Ligler" },
  { href: "/teams", label: "Takımlar" },
  { href: "/h2h", label: "H2H" },
  { href: "/matches", label: "Maçlar" },
  { href: "/decisions", label: "Kararlar", roles: ["admin", "coach", "analyst"] },
  { href: "/calibration", label: "Kalibrasyon" },
  { href: "/chat", label: "Asistan" },
  { href: "/admin", label: "Admin", roles: ["admin"] },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user } = useCurrentUser();
  const role = user?.role ?? "viewer";

  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.roles || item.roles.includes(role),
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
              {item.label}
            </Link>
          );
        })}
      </nav>
      <SidebarFooter />
    </aside>
  );
}

function SidebarFooter() {
  const buildSha = process.env.NEXT_PUBLIC_BUILD_SHA ?? "dev";
  const buildLabel = buildSha.slice(0, 7);
  return (
    <footer className="px-4 py-2 border-t border-border text-[10px] text-textdim">
      <div>DESIGN.md • v1</div>
      <div className="mt-0.5 font-mono">build {buildLabel}</div>
    </footer>
  );
}
