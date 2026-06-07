"use client";

/**
 * Performans Testi — tablet veri-giriş ekranı. ConsoleShell çatısında.
 * Protokol seç → değer gir → kalıcı kayıt + batarya değerlendirme + PDF.
 * Backend:
 *   GET  /admin/performance/protocols
 *   POST /physical-tests/
 *   POST /admin/performance/battery
 *   POST /reports/performance/pdf
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch, getAccessToken } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

interface Protocol {
  key: string;
  name: string;
  unit: string;
  higher_is_better: boolean;
  description: string;
}
interface TestScore {
  protocol_key: string;
  protocol_name: string;
  raw_value: number;
  unit: string;
  rating: string;
  squad_percentile: number | null;
  note: string;
}
interface BatteryReport {
  player_external_id: number;
  scores: TestScore[];
  weak_areas: string[];
  strong_areas: string[];
}
interface Row {
  id: number;
  protocol_key: string;
  raw_value: string;
}

const RATING_VAR: Record<string, string> = {
  elit: "var(--low)",
  iyi: "var(--low)",
  ortalama: "var(--mid)",
  zayıf: "var(--crit)",
};

const fieldStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "14px",
  padding: "0 10px",
  height: "42px",
  borderRadius: "7px",
  fontFamily: "inherit",
};
const labelStyle: React.CSSProperties = { display: "block", fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--muted)", marginBottom: 4 };

let _rowSeq = 1;

export default function PerformanceConsolePage() {
  const { data: lib } = useSWR<{ protocols: Protocol[] }>("/admin/performance/protocols", apiFetch, { shouldRetryOnError: false });
  const protocols = lib?.protocols ?? [];

  const [playerName, setPlayerName] = React.useState("");
  const [playerId, setPlayerId] = React.useState("");
  const [testDate, setTestDate] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [rows, setRows] = React.useState<Row[]>([{ id: _rowSeq++, protocol_key: "", raw_value: "" }]);
  const [report, setReport] = React.useState<BatteryReport | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [savedCount, setSavedCount] = React.useState<number | null>(null);

  function updateRow(id: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setRows((rs) => [...rs, { id: _rowSeq++, protocol_key: "", raw_value: "" }]);
  }
  function removeRow(id: number) {
    setRows((rs) => (rs.length > 1 ? rs.filter((r) => r.id !== id) : rs));
  }

  function validResults(): [string, number][] {
    return rows
      .filter((r) => r.protocol_key && r.raw_value.trim() !== "")
      .map((r) => [r.protocol_key, Number(r.raw_value)] as [string, number])
      .filter(([, v]) => !Number.isNaN(v));
  }

  async function persistResults(): Promise<number> {
    let ok = 0;
    for (const [protocol, value] of validResults()) {
      try {
        await apiFetch("/physical-tests/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            player_id: playerId || "0",
            player_name: playerName || `Oyuncu #${playerId || 0}`,
            test_date: testDate,
            protocol,
            value,
          }),
        });
        ok++;
      } catch {
        /* best-effort */
      }
    }
    return ok;
  }

  async function evaluate() {
    setError(null);
    setBusy(true);
    setSavedCount(null);
    try {
      const saved = await persistResults();
      setSavedCount(saved);
      const res = await apiFetch<BatteryReport>("/admin/performance/battery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_id: Number(playerId) || 0, results: validResults() }),
      });
      setReport(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Değerlendirme başarısız");
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf() {
    setError(null);
    setBusy(true);
    try {
      const token = getAccessToken();
      const res = await fetch("/api/reports/performance/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({
          player_name: playerName || `Oyuncu #${playerId || 0}`,
          player_id: Number(playerId) || 0,
          results: validResults(),
          test_date: testDate,
        }),
      });
      if (!res.ok) {
        if (res.status === 503) throw new Error("PDF üretici sunucuda devre dışı (reportlab yok)");
        throw new Error(`PDF üretilemedi (HTTP ${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `performans_oyuncu_${playerId || 0}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "PDF indirme başarısız");
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = validResults().length > 0 && !busy;
  const activeProtocol = (key: string) => protocols.find((p) => p.key === key);

  const right = (
    <div className="rc">
      <h3>Yeni Panel</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5, marginBottom: 12 }}>
        Kalıcı kayıt + yük riski + trend + risk halkası artık <b style={{ color: "var(--ink)" }}>Performans (Yük Riski)</b> panelinde.
      </div>
      <Link href="/physical-tests" style={{ display: "inline-block", fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.5, padding: "8px 14px", borderRadius: 7, background: "var(--besiktas)", color: "#fff", fontWeight: 600, textDecoration: "none" }}>
        Yeni panele git →
      </Link>
      {report && (report.strong_areas.length > 0 || report.weak_areas.length > 0) && (
        <div style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          {report.strong_areas.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--low)", marginBottom: 3 }}>Güçlü yönler</div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>{report.strong_areas.join(", ")}</div>
            </div>
          )}
          {report.weak_areas.length > 0 && (
            <div>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--crit)", marginBottom: 3 }}>Gelişim alanları</div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>{report.weak_areas.join(", ")}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <ConsoleShell
      active="/performance"
      title="Performans Testi"
      sub="Veri girişi & batarya"
      desc="Saha/laboratuvar veri girişi. Sağlık/performans verisi KVKK'da özel niteliklidir; erişim ve dışa aktarım denetim kaydına yazılır."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}><h2>Oyuncu</h2></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          <label><span style={labelStyle}>Ad</span><input value={playerName} onChange={(e) => setPlayerName(e.target.value)} placeholder="Oyuncu adı" style={fieldStyle} /></label>
          <label><span style={labelStyle}>Oyuncu ID</span><input value={playerId} onChange={(e) => setPlayerId(e.target.value.replace(/[^0-9]/g, ""))} inputMode="numeric" placeholder="örn. 42" style={fieldStyle} /></label>
          <label><span style={labelStyle}>Test tarihi</span><input type="date" value={testDate} onChange={(e) => setTestDate(e.target.value)} style={fieldStyle} /></label>
        </div>
      </div>

      <div className="st"><h2>Test Sonuçları</h2><button type="button" onClick={addRow} style={{ fontSize: 11, textTransform: "uppercase", padding: "4px 10px", borderRadius: 6, border: "1px solid var(--line)", color: "var(--ink)", background: "var(--panel3)", cursor: "pointer" }}>+ Test ekle</button></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        {rows.map((row) => {
          const proto = activeProtocol(row.protocol_key);
          return (
            <div key={row.id} style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
                <label style={{ flex: 1 }}>
                  <span style={labelStyle}>Protokol</span>
                  <select value={row.protocol_key} onChange={(e) => updateRow(row.id, { protocol_key: e.target.value })} style={fieldStyle}>
                    <option value="">Test seç…</option>
                    {protocols.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
                  </select>
                </label>
                <label style={{ width: 120 }}>
                  <span style={labelStyle}>Değer {proto ? `(${proto.unit})` : ""}</span>
                  <input value={row.raw_value} onChange={(e) => updateRow(row.id, { raw_value: e.target.value.replace(/[^0-9.]/g, "") })} inputMode="decimal" placeholder="0" style={{ ...fieldStyle, textAlign: "right" }} />
                </label>
                <button type="button" onClick={() => removeRow(row.id)} disabled={rows.length <= 1} aria-label="Satırı sil" style={{ height: 42, width: 42, flexShrink: 0, borderRadius: 7, border: "1px solid var(--line)", color: "var(--dim)", background: "transparent", cursor: rows.length <= 1 ? "default" : "pointer", opacity: rows.length <= 1 ? 0.3 : 1 }}>×</button>
              </div>
              {proto && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4, lineHeight: 1.4 }}>{proto.description}</div>}
            </div>
          );
        })}

        {error && <div style={{ marginTop: 10, fontSize: 12, color: "var(--crit)" }}>{error}</div>}
        {savedCount !== null && savedCount > 0 && <div style={{ marginTop: 10, fontSize: 12, color: "var(--low)" }}>{savedCount} sonuç kaydedildi — geçmiş, trend ve risk panellerine işlendi.</div>}

        <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 8 }}>
          <button type="button" onClick={evaluate} disabled={!canSubmit} style={{ padding: "0 16px", height: 42, borderRadius: 7, background: "var(--besiktas)", color: "#fff", fontWeight: 600, fontSize: 13, border: 0, cursor: canSubmit ? "pointer" : "default", opacity: canSubmit ? 1 : 0.4, fontFamily: "inherit" }}>{busy ? "İşleniyor…" : "Kaydet & Değerlendir"}</button>
          <button type="button" onClick={downloadPdf} disabled={!canSubmit} style={{ padding: "0 16px", height: 42, borderRadius: 7, background: "transparent", color: "var(--ink)", fontSize: 13, border: "1px solid var(--line)", cursor: canSubmit ? "pointer" : "default", opacity: canSubmit ? 1 : 0.4, fontFamily: "inherit" }}>PDF Rapor indir</button>
        </div>
      </div>

      {report && (
        <>
          <div className="st"><h2>Değerlendirme</h2><span className="ep">POST /admin/performance/battery</span></div>
          <div className="tbl">
            <table>
              <thead><tr><th>Protokol</th><th className="r">Değer</th><th className="c">Kadro %</th><th className="c">Değerlendirme</th></tr></thead>
              <tbody>
                {report.scores.map((s) => {
                  const v = RATING_VAR[s.rating] ?? "var(--muted)";
                  return (
                    <tr key={s.protocol_key}>
                      <td><span className="nm">{s.protocol_name}</span></td>
                      <td className="r" style={{ color: "var(--muted)" }}>{s.raw_value} {s.unit}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{s.squad_percentile != null ? `%${s.squad_percentile}` : "—"}</td>
                      <td className="c"><span style={{ fontSize: 10, textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: `1px solid ${v}`, color: v }}>{s.rating}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
