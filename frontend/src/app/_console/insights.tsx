"use client";

/**
 * Haftalık İçgörü akışı görselleştirmesi — lib/weekly-insights çıktısını render eder.
 * `InsightFeed` tam kartlar (haftalık rapor), `InsightFeedCompact` özet satırlar
 * (overview retention yüzeyi). Her içgörü tıklanınca kaynak sayfaya gider.
 */

import * as React from "react";
import Link from "next/link";
import { SEV_VAR, type Insight, type WeeklyInsights } from "@/lib/weekly-insights";

/** Tam içgörü kartı — kategori + başlık + gövde + metrik, kaynağa link. */
function InsightCard({ ins }: { ins: Insight }) {
  const color = SEV_VAR[ins.severity];
  return (
    <Link href={ins.href} className="rowlink" style={{ textDecoration: "none", display: "block" }}>
      <div style={{ display: "flex", gap: 11, padding: "11px 13px", borderRadius: 9, background: "var(--panel3)", borderLeft: `3px solid ${color}` }}>
        <i className={`ti ${ins.icon}`} style={{ fontSize: 17, color, marginTop: 1, flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.5, color, fontWeight: 700 }}>{ins.category}</span>
            <b style={{ fontSize: 12.5, color: "var(--ink)" }}>{ins.title}</b>
            {ins.metric && <span style={{ marginLeft: "auto", fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 13, color }}>{ins.metric}</span>}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5, marginTop: 3 }}>{ins.body}</div>
        </div>
      </div>
    </Link>
  );
}

/** Tam içgörü akışı (haftalık rapor / detay). */
export function InsightFeed({ data }: { data: WeeklyInsights }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {data.insights.map((ins) => <InsightCard key={ins.id} ins={ins} />)}
    </div>
  );
}

/** Kompakt satır akışı — overview gibi dar kolonlar için (retention yüzeyi). */
export function InsightFeedCompact({ data, limit }: { data: WeeklyInsights; limit?: number }) {
  const rows = limit ? data.insights.slice(0, limit) : data.insights;
  return (
    <>
      {rows.map((ins) => {
        const color = SEV_VAR[ins.severity];
        return (
          <Link key={ins.id} href={ins.href} className="alrt rowlink" style={{ textDecoration: "none", alignItems: "flex-start" }}>
            <span className="ai" style={{ background: color, marginTop: 4 }} />
            <div className="am">
              <b style={{ color: "var(--ink)" }}>{ins.title}</b>
              {ins.metric && <span style={{ color, fontFamily: "JetBrains Mono", marginLeft: 6 }}>{ins.metric}</span>}
              <span className="tm">{ins.body}</span>
            </div>
          </Link>
        );
      })}
    </>
  );
}
