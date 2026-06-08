"use client";

/**
 * Kararlar — açıklanabilir karar ekranı (ürünün satış argümanı).
 *
 * DEMO_MODE: "orkestra şefi" (context_engine) mantığını yansıtan karar kartları.
 * Her kart: dakika + tip + aciliyet + güven + gerekçe + "Neden?" — AYNI ANDA
 * ateşlenen sinyaller (kaynak motor, kaç event'e dayandığı, sinyal gücü).
 * Fark burada: tek bir agent log'u değil, "3 ayrı motor aynı anı işaret ediyor".
 *
 * DEMO_MODE kapalı: eski davranış — GET /admin/agent-outputs düz listesi.
 */

import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoDecisions, demoDecisionSummary, type DecisionCard, type Urgency } from "@/lib/demo-data";
import { ConsoleShell } from "../_console/shell";

const URGENCY_VAR: Record<Urgency, string> = {
  "kritik": "var(--crit)",
  "yüksek": "var(--high)",
  "orta": "var(--mid)",
  "düşük": "var(--dim)",
};

function confColor(c: number): string {
  return c >= 80 ? "var(--low)" : c >= 65 ? "var(--mid)" : "var(--high)";
}

// --------------------------------------------------------------------------- //
// DEMO — karar kartları + "neden?" sinyal zinciri
// --------------------------------------------------------------------------- //

function DecisionCardView({ d }: { d: DecisionCard }) {
  const uv = URGENCY_VAR[d.urgency];
  return (
    <div className="rc" style={{ margin: "0 0 14px", padding: 0, overflow: "hidden", borderLeft: `3px solid ${uv}` }}>
      {/* Üst şerit: dakika + tip + aciliyet */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", borderBottom: "1px solid var(--line)", background: "var(--panel2)" }}>
        <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 15, color: "var(--ink)" }}>{d.minute}&apos;</span>
        <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)" }}>{d.decisionType}</span>
        <span style={{ marginLeft: "auto", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.8, fontWeight: 700, color: uv, border: `1px solid ${uv}`, borderRadius: 999, padding: "2px 9px" }}>
          {d.urgency}
        </span>
      </div>

      <div style={{ padding: "13px 14px" }}>
        {/* Başlık + güven */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 14, marginBottom: 8 }}>
          <h3 style={{ fontSize: 15.5, fontWeight: 800, lineHeight: 1.3, color: "var(--ink)" }}>{d.headline}</h3>
          <div style={{ textAlign: "right", flexShrink: 0, minWidth: 92 }}>
            <div style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 20, color: confColor(d.confidence) }}>%{d.confidence}</div>
            <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--dim)" }}>güven</div>
            <div style={{ height: 5, borderRadius: 3, background: "var(--panel3)", overflow: "hidden", marginTop: 4 }}>
              <i style={{ display: "block", height: "100%", width: `${d.confidence}%`, background: confColor(d.confidence) }} />
            </div>
          </div>
        </div>

        {/* Gerekçe */}
        <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.55, marginBottom: 14 }}>{d.rationale}</div>

        {/* Neden? — aynı anda ateşlenen sinyaller */}
        <div style={{ borderTop: "1px dashed var(--line2)", paddingTop: 11 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 9 }}>
            <span style={{ fontSize: 10.5, fontWeight: 800, textTransform: "uppercase", letterSpacing: 1, color: "var(--ink)" }}>Neden?</span>
            <span style={{ fontSize: 11, color: "var(--dim)" }}>{d.signals.length} sinyal aynı anı işaret ediyor</span>
          </div>
          {d.signals.map((s, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "152px 1fr auto", gap: 10, alignItems: "center", padding: "6px 0", borderTop: i ? "1px solid rgba(128,128,128,0.12)" : undefined }}>
              <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--ink)", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.engine}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12, color: "var(--ink)", marginBottom: 3 }}>{s.label}</div>
                <div style={{ height: 5, borderRadius: 3, background: "var(--panel3)", overflow: "hidden" }}>
                  <i style={{ display: "block", height: "100%", width: `${Math.round(s.magnitude * 100)}%`, background: uv }} />
                </div>
              </div>
              <span style={{ fontFamily: "JetBrains Mono", fontSize: 10.5, color: "var(--dim)", whiteSpace: "nowrap" }}>n={s.sampleSize}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DemoDecisions() {
  const cards = [...demoDecisions].sort((a, b) => a.minute - b.minute);
  const sum = demoDecisionSummary();

  const right = (
    <>
      <div className="rc">
        <h3>Karar Özeti <span className="tiny">{sum.total} karar</span></h3>
        <div className="stat"><span>Ortalama güven</span><span className="sv" style={{ color: confColor(sum.avgConfidence) }}>%{sum.avgConfidence}</span></div>
        <div className="stat"><span>En kritik</span><span className="sv" style={{ color: URGENCY_VAR[sum.mostCritical.urgency] }}>{sum.mostCritical.minute}&apos;</span></div>
      </div>
      <div className="rc">
        <h3>Tipe Göre Dağılım</h3>
        {sum.byType.map((t) => (
          <div className="stat" key={t.type}><span>{t.type}</span><span className="sv">{t.count}</span></div>
        ))}
      </div>
      <div className="rc" style={{ borderLeft: `2px solid ${URGENCY_VAR[sum.mostCritical.urgency]}` }}>
        <h3>En Kritik Karar</h3>
        <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--ink)", marginBottom: 4 }}>{sum.mostCritical.minute}&apos; — {sum.mostCritical.headline}</div>
        <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>{sum.mostCritical.signals.length} motor aynı anı işaret etti · güven %{sum.mostCritical.confidence}</div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/decisions"
      title="Kararlar"
      sub="Açıklanabilir karar motoru — neden bu öneri?"
      desc="Orkestra şefi (context_engine) birden çok sinyali aynı anda okur ve tek bir önceliklendirilmiş karar üretir. Her kartın altında AYNI ANDA ateşlenen sinyaller var."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Maç Boyunca Kararlar</h2>
        <span className="ep">FK Demo vs Rakip SK</span>
      </div>
      {cards.map((d) => <DecisionCardView key={d.minute} d={d} />)}
    </ConsoleShell>
  );
}

// --------------------------------------------------------------------------- //
// CANLI (DEMO kapalı) — eski agent-outputs listesi
// --------------------------------------------------------------------------- //

interface AgentOutput {
  id: number;
  agent_name: string;
  agent_version: string;
  subject_type: string;
  subject_id: number;
  summary: string;
  updated_at: string;
}

function LiveAgentOutputs() {
  const { data, error, isLoading } = useSWR<AgentOutput[]>(
    "/admin/agent-outputs?limit=20", apiFetch, { shouldRetryOnError: false },
  );
  const rows = data ?? [];
  const byAgent = new Map<string, number>();
  rows.forEach((o) => byAgent.set(o.agent_name, (byAgent.get(o.agent_name) ?? 0) + 1));

  const right = (
    <div className="rc">
      <h3>Agent Dağılımı <span className="tiny">{rows.length} çıktı</span></h3>
      {byAgent.size === 0 && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Henüz çıktı yok.</div>}
      {[...byAgent.entries()].map(([name, n]) => (
        <div className="stat" key={name}>
          <span style={{ fontFamily: "JetBrains Mono", fontSize: 11.5 }}>{name}</span>
          <span className="sv">{n}</span>
        </div>
      ))}
    </div>
  );

  return (
    <ConsoleShell active="/decisions" title="Kararlar" sub="Agent çıktıları"
      desc="Son agent çıktıları — lineup, sub advice, tactical adjustment, injury load." right={right}>
      {isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {error && <div className="pgdesc">Yüklenemedi ya da yetki yok.</div>}
      <div className="st" style={{ marginTop: 0 }}><h2>Son Çıktılar</h2><span className="ep">GET /admin/agent-outputs</span></div>
      <div className="tbl">
        <table>
          <thead><tr><th>Zaman</th><th>Agent</th><th>Özne</th><th className="c">Sürüm</th><th>Özet</th></tr></thead>
          <tbody>
            {rows.length === 0 && !isLoading && (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                Henüz agent çıktısı yok (daily brief tetiklendi mi?).
              </td></tr>
            )}
            {rows.map((o) => (
              <tr key={o.id}>
                <td style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11, whiteSpace: "nowrap" }}>{o.updated_at.slice(0, 16).replace("T", " ")}</td>
                <td><span className="nm" style={{ fontFamily: "JetBrains Mono", fontSize: 11.5, color: "var(--ink)" }}>{o.agent_name}</span></td>
                <td style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11.5 }}>{o.subject_type}:{o.subject_id}</td>
                <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)", fontSize: 11 }}>v{o.agent_version}</td>
                <td style={{ color: "var(--muted)", fontSize: 12 }}>{o.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}

export default function DecisionsPage() {
  return DEMO_MODE ? <DemoDecisions /> : <LiveAgentOutputs />;
}
