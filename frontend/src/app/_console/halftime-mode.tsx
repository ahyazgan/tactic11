"use client";

/**
 * DEVRE ARASI MODU — 15 dakikalık altın pencere için karar-öncelikli ekran.
 *
 * Maç Modu'nun kardeşi: analitik duvar DEĞİL (o /matches/[id]/halftime'da).
 * Antrenörün 15 dakikada tek bakışta okuyacağı şey: tek-cümle okuma → 2. yarıya
 * öncelikli hamleler → üç hızlı okuma (ne çalıştı/risk/plan) → duran top düzeltmesi
 * → senaryo planı. Motor: lib/halftime-advice (ilk yarı verisinden CANLI).
 */

import * as React from "react";
import { demoLive, demoScenarios } from "@/lib/demo-data";
import { firstHalfSummary, halftimeMoves, halftimeBrief, type HtMove } from "@/lib/halftime-advice";
import { firstHalfStats, opponentHalftimeRead, secondHalfAdjustments } from "@/lib/halftime-scout";

const MOVE_ICON: Record<HtMove["kind"], string> = { sub: "🔁", attack: "🎯", defense: "🛡️", tempo: "⏱️" };
const URG_COLOR: Record<string, string> = { kritik: "var(--crit)", yüksek: "var(--high)", orta: "var(--mid)" };
const SCEN_COLOR = (s: string) => (s === "Öndeyiz" ? "var(--low)" : s === "Geride" ? "var(--crit)" : "var(--mid)");

export function HalftimeModeBody() {
  const L = demoLive;
  const fh = firstHalfSummary();
  const moves = halftimeMoves();
  const brief = halftimeBrief();
  const top = moves[0];
  const rest = moves.slice(1);
  const xgEdge = fh.homeXg - fh.awayXg;
  const stats = firstHalfStats();
  const oppRead = opponentHalftimeRead(101);
  const adjusts = secondHalfAdjustments(101);

  return (
    <div style={{ maxWidth: 580, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Başlık — skor + tek cümle okuma */}
      <div className="rc" style={{ margin: 0, textAlign: "center" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
          <span style={{ fontSize: 16, fontWeight: 800 }}>{L.home}</span>
          <span style={{ fontSize: 28, fontWeight: 900, fontFamily: "JetBrains Mono" }}>{fh.score[0]}–{fh.score[1]}</span>
          <span style={{ fontSize: 16, fontWeight: 800 }}>{L.away}</span>
          <span style={{ fontSize: 12, fontWeight: 800, color: "#fff", background: "var(--accent)", borderRadius: 5, padding: "3px 9px", fontFamily: "JetBrains Mono" }}>DEVRE ARASI</span>
        </div>
        <div style={{ display: "flex", justifyContent: "center", gap: 16, marginTop: 8, fontFamily: "JetBrains Mono", fontSize: 12.5, color: "var(--muted)" }}>
          <span>xG <b style={{ color: "var(--ink)" }}>{fh.homeXg.toFixed(2)}–{fh.awayXg.toFixed(2)}</b> ({xgEdge >= 0 ? "+" : ""}{xgEdge.toFixed(2)})</span>
          <span>şut {fh.shotsHome}–{fh.shotsAway}</span>
          <span style={{ color: fh.momentum >= 0 ? "var(--low)" : "var(--high)" }}>momentum {fh.momentum >= 0 ? "+" : ""}{fh.momentum}</span>
        </div>
        <div style={{ fontSize: 14.5, color: "var(--ink)", lineHeight: 1.55, marginTop: 12, fontWeight: 600 }}>{brief.summary}</div>
      </div>

      {/* 1. yarı sayı şeridi */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(90px, 1fr))", gap: 8 }}>
        {[
          { l: "Topla oynama", v: `%${stats.possession}`, c: "var(--low)" },
          { l: "Saha tilt", v: `%${stats.fieldTilt}`, c: "var(--low)" },
          { l: "PPDA", v: stats.ppda.toFixed(1), c: "var(--ink)" },
          { l: "xG", v: `${stats.xg[0].toFixed(2)}–${stats.xg[1].toFixed(2)}`, c: "var(--ink)" },
          { l: "Şut", v: `${stats.shots[0]}–${stats.shots[1]}`, c: "var(--ink)" },
        ].map((s) => (
          <div key={s.l} className="kpi" style={{ padding: "9px 10px" }}>
            <div className="kl">{s.l}</div>
            <div className="kn" style={{ fontSize: 17, color: s.c }}>{s.v}</div>
          </div>
        ))}
      </div>

      {/* En öncelikli hamle — dev kart */}
      {top && (
        <div style={{ borderRadius: 12, border: `2px solid ${URG_COLOR[top.urgency] ?? "var(--accent)"}`, background: `color-mix(in srgb, ${URG_COLOR[top.urgency] ?? "var(--accent)"} 8%, var(--panel))`, padding: "16px 18px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 18 }}>{MOVE_ICON[top.kind]}</span>
            <span style={{ fontSize: 12, fontWeight: 900, letterSpacing: 1, color: URG_COLOR[top.urgency] ?? "var(--accent)" }}>2. YARIYA — İLK İŞ</span>
            <span style={{ marginLeft: "auto", fontSize: 10.5, fontWeight: 800, textTransform: "uppercase", color: URG_COLOR[top.urgency] }}>{top.urgency}</span>
          </div>
          <div style={{ fontSize: 19, fontWeight: 900, lineHeight: 1.2, marginBottom: 5 }}>{top.title}</div>
          <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.5 }}>{top.detail}</div>
        </div>
      )}

      {/* Diğer öncelikli hamleler */}
      {rest.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>Diğer öncelikli hamleler</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {rest.map((m) => {
              const c = URG_COLOR[m.urgency] ?? "var(--muted)";
              return (
                <div key={m.id} style={{ display: "flex", gap: 11, alignItems: "flex-start", borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: `4px solid ${c}`, padding: "11px 13px" }}>
                  <span style={{ fontSize: 17, flexShrink: 0 }}>{MOVE_ICON[m.kind]}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 800 }}>{m.title}</div>
                    <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.45, marginTop: 2 }}>{m.detail}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Üç hızlı okuma */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(165px, 1fr))", gap: 10 }}>
        {[
          { label: "Ne çalıştı", body: brief.whatWorked, c: "var(--low)" },
          { label: "Risk", body: brief.risk, c: "var(--crit)" },
          { label: "Plan", body: brief.plan, c: "var(--accent)" },
        ].map((b) => (
          <div key={b.label} style={{ borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", borderTop: `3px solid ${b.c}`, padding: "11px 13px" }}>
            <div style={{ fontSize: 10.5, fontWeight: 800, textTransform: "uppercase", letterSpacing: 0.5, color: b.c, marginBottom: 5 }}>{b.label}</div>
            <div style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.5 }}>{b.body}</div>
          </div>
        ))}
      </div>

      {/* ── RAKİBİ OKU ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
        <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
        <span style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: 0.8, color: "var(--high)" }}>RAKİBİ OKU</span>
        <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
      </div>

      {/* Rakip 1. yarı okuması + 2. yarı beklentisi */}
      <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--high)" }}>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 6 }}>Rakip 1. yarıda ne yaptı</div>
        <ul style={{ margin: "0 0 10px", paddingLeft: 16, fontSize: 12.5, color: "var(--ink)", lineHeight: 1.55 }}>
          {oppRead.whatWorked.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
        <div style={{ fontSize: 12.5, lineHeight: 1.55 }}>
          <div><span style={{ color: "var(--high)", fontWeight: 700 }}>2. yarı beklentisi:</span> {oppRead.theyllLikely}</div>
          <div style={{ marginTop: 5 }}><span style={{ color: "var(--low)", fontWeight: 700 }}>↳ Önlemimiz:</span> {oppRead.ourCounter}</div>
        </div>
      </div>

      {/* 2. yarı taktik ayarlar — değişiklik dışı */}
      <div>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>2. yarı taktik ayarlar <span style={{ textTransform: "none", color: "var(--muted)" }}>· değişiklik dışı</span></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {adjusts.map((a, i) => (
            <div key={i} style={{ display: "flex", gap: 11, alignItems: "flex-start", borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: "4px solid var(--accent)", padding: "11px 13px" }}>
              <span style={{ fontSize: 13, fontWeight: 800, color: "var(--accent)", flexShrink: 0 }}>⚙</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 800 }}>{a.move}</div>
                <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.45, marginTop: 2 }}>{a.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Duran top düzeltmesi — beraberlik golü buradan geldi */}
      {fh.concededSetPiece && (
        <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--crit)" }}>
          <div style={{ fontSize: 11, color: "var(--crit)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 4, fontWeight: 800 }}>Duran top düzeltmesi</div>
          <div style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.55 }}>
            Beraberlik golü 45&apos; köşe vuruşunda <b>far-post</b>&apos;tan geldi — ikinci direği örtemiyoruz.
            2. yarı zonal dizilimi <b>adam-adama</b> kaydır; en iyi hava topçuyu (Agbadou) far-post&apos;a koy.
          </div>
        </div>
      )}

      {/* Senaryo planı */}
      <div>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>2. yarı senaryo planı</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(165px, 1fr))", gap: 10 }}>
          {demoScenarios.map((s) => {
            const c = SCEN_COLOR(s.state);
            return (
              <div key={s.state} style={{ borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", borderTop: `3px solid ${c}`, padding: "11px 13px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: c }} />
                  <b style={{ fontSize: 12.5 }}>{s.state}</b>
                </div>
                <div style={{ fontSize: 11.5, color: "var(--ink)", lineHeight: 1.45 }}>{s.plan}</div>
              </div>
            );
          })}
        </div>
      </div>

      <a href="/match-mode" style={{ textDecoration: "none", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 10, border: "1.5px solid var(--accent)", background: "color-mix(in srgb, var(--accent) 8%, var(--panel))", padding: "11px 14px" }}>
        <span style={{ fontSize: 16 }}>▶</span>
        <span style={{ fontSize: 13, fontWeight: 800, color: "var(--ink)" }}>2. yarı başlıyor — Maç Modu&apos;na dön</span>
      </a>
      <div style={{ fontSize: 11, color: "var(--dim)", textAlign: "center", lineHeight: 1.5 }}>
        Devre arası modu · 15 dakikalık karar penceresi. Tam analitik döküm{" "}
        <a href="/matches/demo/halftime" style={{ color: "var(--accent)" }}>Devre Arası Brief</a>&apos;te.
      </div>
    </div>
  );
}
