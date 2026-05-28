"use client";

import Link from "next/link";
import { Panel } from "@/components/ui";

export default function TeamsIndexPage() {
  return (
    <div className="max-w-3xl">
      <h1 className="text-lg font-semibold text-text mb-3">Takımlar</h1>
      <Panel>
        <p className="text-[13px] text-text mb-3">
          Takım listesi lig bazında. Önce bir lig seç:
        </p>
        <Link
          href="/leagues"
          className="inline-block text-[11px] uppercase tracking-wide px-3 py-1 rounded border border-borderlt text-accent hover:bg-surface2"
        >
          Liglere git →
        </Link>
      </Panel>
    </div>
  );
}
