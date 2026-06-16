"use client";

/**
 * Bugünün Kararları kuyruğu — lib/command-brief commandDecisions çıktısını
 * KARAR-odaklı render eder: her satırın önerilen aksiyonu + Onayla/Ertele.
 * Komuta merkezini gösterge panosundan kumandaya çevirir (local state).
 */

import * as React from "react";
import Link from "next/link";
import type { CommandDecision } from "@/lib/command-brief";

const SEV_VAR: Record<CommandDecision["severity"], string> = {
  kritik: "var(--crit)", yüksek: "var(--high)", orta: "var(--mid)",
};

export function DecisionsQueue({ decisions }: { decisions: CommandDecision[] }) {
  const [accepted, setAccepted] = React.useState<Set<string>>(new Set());
  const [dismissed, setDismissed] = React.useState<Set<string>>(new Set());

  const open = decisions.filter((d) => !dismissed.has(d.id));
  const pendingCount = open.filter((d) => !accepted.has(d.id)).length;

  return (
    <div className="rc" style={{ margin: "0 0 14px" }}>
      <h3>
        Bugünün Kararları{" "}
        <span className="tiny">{pendingCount > 0 ? `${pendingCount} bekleyen` : "hepsi ele alındı ✓"}</span>
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {open.length === 0 && <div style={{ fontSize: 12, color: "var(--dim)" }}>Karar ertelendi — kuyruk boş.</div>}
        {open.map((d) => {
          const done = accepted.has(d.id);
          const c = SEV_VAR[d.severity];
          return (
            <div
              key={d.id}
              style={{
                display: "flex", gap: 11, alignItems: "flex-start", padding: "10px 12px",
                borderRadius: 9, background: "var(--panel3)", borderLeft: `3px solid ${done ? "var(--low)" : c}`,
                opacity: done ? 0.6 : 1,
              }}
            >
              <span style={{ width: 8, height: 8, borderRadius: 999, background: done ? "var(--low)" : c, marginTop: 4, flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.5, color: c, fontWeight: 700 }}>{d.category}</span>
                  <Link href={d.href} style={{ textDecoration: "none" }}><b style={{ fontSize: 12.5, color: "var(--ink)" }}>{d.title}</b></Link>
                </div>
                <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5, marginTop: 3 }}>
                  <span style={{ color: "var(--dim)" }}>Aksiyon: </span>{d.action}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                {done ? (
                  <span style={{ fontSize: 10.5, color: "var(--low)", fontWeight: 700, whiteSpace: "nowrap" }}>✓ uygulandı</span>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => setAccepted((s) => new Set(s).add(d.id))}
                      style={{ fontSize: 10.5, fontWeight: 700, padding: "4px 10px", borderRadius: 6, border: 0, background: "var(--accent)", color: "#fff", cursor: "pointer", whiteSpace: "nowrap", fontFamily: "inherit" }}
                    >
                      Onayla
                    </button>
                    <button
                      type="button"
                      onClick={() => setDismissed((s) => new Set(s).add(d.id))}
                      style={{ fontSize: 10.5, padding: "4px 10px", borderRadius: 6, border: "1px solid var(--line)", background: "transparent", color: "var(--muted)", cursor: "pointer", whiteSpace: "nowrap", fontFamily: "inherit" }}
                    >
                      Ertele
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
