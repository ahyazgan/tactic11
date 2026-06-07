"use client";

/**
 * Kararlar — son agent çıktıları (lineup, sub advice, tactical, injury load).
 * ConsoleShell çatısında. Veri: GET /admin/agent-outputs?limit=20.
 */

import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

interface AgentOutput {
  id: number;
  agent_name: string;
  agent_version: string;
  subject_type: string;
  subject_id: number;
  summary: string;
  updated_at: string;
}

export default function DecisionsConsolePage() {
  const { data, error, isLoading } = useSWR<AgentOutput[]>(
    "/admin/agent-outputs?limit=20",
    apiFetch,
    { shouldRetryOnError: false },
  );
  const rows = data ?? [];

  // Agent bazlı sayım (sağ kolon).
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
    <ConsoleShell
      active="/decisions"
      title="Kararlar"
      sub="Agent çıktıları"
      desc="Son agent çıktıları — lineup, sub advice, tactical adjustment, injury load."
      right={right}
    >
      {isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {error && <div className="pgdesc">Yüklenemedi ya da yetki yok.</div>}
      <div className="st" style={{ marginTop: 0 }}><h2>Son Çıktılar</h2><span className="ep">GET /admin/agent-outputs</span></div>
      <div className="tbl">
        <table>
          <thead><tr><th>Zaman</th><th>Agent</th><th>Özne</th><th className="c">Sürüm</th><th>Özet</th></tr></thead>
          <tbody>
            {rows.length === 0 && (
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
