"use client";

/**
 * Kadro Reçetesi görselleştirmesi — lib/lineup-advice çıktısını render eder:
 * 4-3-3 formasyon sahası (oyuncular uygunluk-renkli), önerilen 11 + yedekler,
 * dinlendirilen kilit oyuncular ve tam uygunluk tablosu (verdi + yük azaltma).
 */

import * as React from "react";
import {
  VERDICT_LABEL, VERDICT_VAR, type Availability, type LineupAdvice, type SlotPick,
} from "@/lib/lineup-advice";

/** Sahadaki tek oyuncu pulu — forma no + uygunluk-renkli halka + isim. */
function PitchDot({ p }: { p: SlotPick }) {
  const a = p.pick;
  const color = a ? VERDICT_VAR[a.verdict] : "var(--dim)";
  const shirt = a ? a.player.shirt : "—";
  const name = a ? a.player.player_name.split(" ").slice(-1)[0] : p.label;
  return (
    <div style={{ position: "absolute", left: `${p.x}%`, top: `${p.y}%`, transform: "translate(-50%,-50%)", textAlign: "center", width: 64 }}>
      <div style={{
        width: 30, height: 30, borderRadius: "50%", margin: "0 auto",
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "var(--panel)", border: `2px solid ${color}`, boxShadow: `0 0 8px ${color}66`,
        fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 12, color: "var(--ink)",
        position: "relative",
      }}>
        {shirt}
        {p.forced && <span style={{ position: "absolute", top: -6, right: -6, fontSize: 10 }} title="zorunlu seçim">⚠</span>}
      </div>
      <div style={{ fontSize: 9.5, color: "var(--ink)", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textShadow: "0 1px 2px rgba(0,0,0,.6)" }}>{name}</div>
      {a && a.minutesCap && <div style={{ fontSize: 8.5, color: VERDICT_VAR[a.verdict] }}>{a.minutesCap}dk</div>}
    </div>
  );
}

/** 4-3-3 formasyon sahası — saf div, tema-yeşili çim. */
export function FormationPitch({ advice }: { advice: LineupAdvice }) {
  return (
    <div style={{
      position: "relative", width: "100%", aspectRatio: "3 / 4", maxWidth: 380, margin: "0 auto",
      background: "linear-gradient(180deg, color-mix(in srgb, var(--low) 16%, var(--panel)) 0%, var(--panel) 60%)",
      border: "1px solid var(--line)", borderRadius: 12, overflow: "hidden",
    }}>
      {/* saha çizgileri */}
      <div style={{ position: "absolute", left: "8%", right: "8%", top: "50%", borderTop: "1px solid var(--line)" }} />
      <div style={{ position: "absolute", left: "50%", top: "50%", width: 64, height: 64, marginLeft: -32, marginTop: -32, border: "1px solid var(--line)", borderRadius: "50%" }} />
      <div style={{ position: "absolute", left: "28%", right: "28%", bottom: 0, height: "14%", borderTop: "1px solid var(--line)", borderLeft: "1px solid var(--line)", borderRight: "1px solid var(--line)" }} />
      <div style={{ position: "absolute", left: "28%", right: "28%", top: 0, height: "14%", borderBottom: "1px solid var(--line)", borderLeft: "1px solid var(--line)", borderRight: "1px solid var(--line)" }} />
      {advice.picks.map((p, i) => <PitchDot key={i} p={p} />)}
    </div>
  );
}

/** Uygunluk verdi rozeti. */
export function VerdictChip({ a, compact = false }: { a: Availability; compact?: boolean }) {
  const color = VERDICT_VAR[a.verdict];
  return (
    <span className="risk" style={{ color, fontSize: compact ? 10 : 11 }}>
      <span className="rd" style={{ background: color }} />
      {VERDICT_LABEL[a.verdict]}{a.minutesCap ? ` ${a.minutesCap}dk` : ""}
    </span>
  );
}

/** Önerilen 11 + saha + dinlendirilenler + yedekler. */
export function LineupAdviceBody({ advice }: { advice: LineupAdvice }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 18 }}>
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 14, color: "var(--ink)" }}>{advice.formation}</span>
          <span style={{ fontSize: 11, color: "var(--muted)" }}>öneri güveni</span>
          <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: advice.confidence >= 80 ? "var(--low)" : "var(--mid)" }}>%{advice.confidence}</span>
        </div>
        <FormationPitch advice={advice} />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.5 }}>{advice.headline}</div>

        {advice.restedKey.length > 0 && (
          <div>
            <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>Dinlendirilen / sınırlı kilit oyuncular</div>
            {advice.restedKey.map((a) => (
              <div key={a.player.player_id} className="alrt" style={{ alignItems: "flex-start" }}>
                <span className="ai" style={{ background: VERDICT_VAR[a.verdict], marginTop: 4 }} />
                <div className="am">
                  <b>{a.player.player_name}</b> ({a.player.shirt}) · <VerdictChip a={a} compact />
                  <span className="tm">{a.reasons[0]}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {advice.benched.length > 0 && (
          <div>
            <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>Önerilen yedekler</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {advice.benched.map((a) => (
                <span key={a.player.player_id} className="risk" style={{ fontSize: 10.5, color: "var(--muted)" }}>
                  <span className="rd" style={{ background: VERDICT_VAR[a.verdict] }} />
                  {a.player.player_name.split(" ").slice(-1)[0]} ({a.player.shirt})
                </span>
              ))}
            </div>
          </div>
        )}

        {advice.gaps.length > 0 && (
          <div style={{ fontSize: 11, color: "var(--high)", lineHeight: 1.5 }}>
            ⚠ {advice.gaps.join(" · ")}
          </div>
        )}
      </div>
    </div>
  );
}

/** Tam uygunluk tablosu — verdi + dakika sınırı + yük azaltma + gerekçe. */
export function AvailabilityTable({ rows }: { rows: Availability[] }) {
  const rank: Record<Availability["verdict"], number> = { "dinlendir": 0, "dakika_sınırı": 1, "rotasyon": 2, "başla": 3 };
  const sorted = [...rows].sort((a, b) => rank[a.verdict] - rank[b.verdict] || b.risk.score - a.risk.score);
  return (
    <div className="tbl">
      <table>
        <thead><tr>
          <th>Oyuncu</th><th className="c">Mevki</th><th className="c">Risk</th><th className="c">Verdi</th><th className="c">Yük Azalt</th><th>Gerekçe</th>
        </tr></thead>
        <tbody>
          {sorted.map((a) => (
            <tr key={a.player.player_id}>
              <td><span className="nm">{a.player.player_name}</span> <span className="nat">#{a.player.shirt}</span></td>
              <td className="c" style={{ fontSize: 11.5, color: "var(--muted)" }}>{a.player.pos_detail}</td>
              <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: VERDICT_VAR[a.verdict] }}>{a.risk.score}</td>
              <td className="c"><VerdictChip a={a} compact /></td>
              <td className="c" style={{ fontFamily: "JetBrains Mono", color: a.deloadPct > 0 ? "var(--high)" : "var(--dim)" }}>{a.deloadPct > 0 ? `−%${a.deloadPct}` : "—"}</td>
              <td style={{ fontSize: 11.5, color: "var(--muted)" }}>{a.reasons[0]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
