"use client";

/**
 * Tıbbi Merkez — sakatlık/rehabilitasyon takibi (return_to_play). ConsoleShell çatısında.
 * Takım geneli aktif sakatlıklar + oyuncu sorgu + yeni rehab kaydı (sağ kolon).
 * Backend:
 *   GET   /rehab/active
 *   GET   /players/{id}/rehab/active
 *   POST  /players/{id}/rehab
 *   PATCH /players/{id}/rehab/{rid}
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

interface Rehab {
  id: number;
  player_external_id: number;
  injury_type: string;
  injury_start: string;
  expected_return: string | null;
  actual_return: string | null;
  status: string;
  notes: string | null;
}

const STATUS_VAR: Record<string, string> = {
  active: "var(--crit)",
  recovering: "var(--mid)",
  cleared: "var(--low)",
};
const STATUS_LABEL: Record<string, string> = {
  active: "Sakat",
  recovering: "İyileşiyor",
  cleared: "Hazır",
};

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return Math.ceil(ms / 86_400_000);
}

const fieldStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 9px",
  borderRadius: "6px",
  fontFamily: "inherit",
};
const labelStyle: React.CSSProperties = { display: "block", fontSize: "10.5px", color: "var(--muted)", margin: "8px 0 3px", textTransform: "uppercase", letterSpacing: "0.5px" };

export default function MedicalConsolePage() {
  const [query, setQuery] = React.useState("");
  const [search, setSearch] = React.useState("");

  // Yeni kayıt formu
  const [injuryType, setInjuryType] = React.useState("");
  const [status, setStatus] = React.useState("active");
  const [start, setStart] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [expected, setExpected] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const rehab = useSWR<Rehab[]>(query ? `/players/${query}/rehab/active` : null, apiFetch, { shouldRetryOnError: false });
  const rows = rehab.data ?? [];
  const team = useSWR<Rehab[]>("/rehab/active", apiFetch, { shouldRetryOnError: false });
  const teamRows = team.data ?? [];

  const NEXT: Record<string, string> = { active: "recovering", recovering: "cleared" };

  async function setStatusFor(r: Rehab, next: string) {
    try {
      await apiFetch(`/players/${r.player_external_id}/rehab/${r.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: next }),
      });
      team.mutate();
      rehab.mutate();
    } catch {
      /* sessizce yut */
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!query) { setErr("Önce bir oyuncu getir."); return; }
    if (!injuryType.trim()) { setErr("Sakatlık tipi gerekli."); return; }
    setErr(null);
    setBusy(true);
    try {
      await apiFetch(`/players/${query}/rehab`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          injury_type: injuryType.trim(),
          injury_start: start,
          expected_return: expected || null,
          status,
          notes: notes.trim() || null,
        }),
      });
      setInjuryType(""); setNotes(""); setExpected("");
      rehab.mutate();
      team.mutate();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Kayıt başarısız");
    } finally {
      setBusy(false);
    }
  }

  const activeN = teamRows.filter((r) => r.status === "active").length;
  const recoveringN = teamRows.filter((r) => r.status === "recovering").length;
  const clearedN = teamRows.filter((r) => r.status === "cleared").length;

  const right = (
    <div className="rc">
      <h3>Yeni Rehab Kaydı {query ? <span className="tiny">#{query}</span> : <span className="tiny">oyuncu seç</span>}</h3>
      <form onSubmit={submit}>
        <label style={labelStyle}>Sakatlık tipi</label>
        <input value={injuryType} onChange={(e) => setInjuryType(e.target.value)} placeholder="örn. hamstring grade 2" style={fieldStyle} />
        <label style={labelStyle}>Durum</label>
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={fieldStyle}>
          <option value="active">Sakat</option>
          <option value="recovering">İyileşiyor</option>
          <option value="cleared">Hazır</option>
        </select>
        <label style={labelStyle}>Başlangıç</label>
        <input type="date" value={start} onChange={(e) => setStart(e.target.value)} style={fieldStyle} />
        <label style={labelStyle}>Tahmini dönüş</label>
        <input type="date" value={expected} onChange={(e) => setExpected(e.target.value)} style={fieldStyle} />
        <label style={labelStyle}>Not</label>
        <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="opsiyonel" style={fieldStyle} />
        {err && <div style={{ fontSize: "11.5px", color: "var(--crit)", marginTop: 8 }}>{err}</div>}
        <button type="submit" disabled={busy} style={{ width: "100%", marginTop: 12, padding: "9px", borderRadius: 7, background: "var(--besiktas)", color: "#fff", fontWeight: 600, fontSize: 12.5, border: 0, cursor: busy ? "default" : "pointer", opacity: busy ? 0.5 : 1, fontFamily: "inherit" }}>
          {busy ? "Kaydediliyor…" : "Kaydet"}
        </button>
      </form>
    </div>
  );

  return (
    <ConsoleShell
      active="/medical"
      title="Tıbbi Merkez"
      sub="Sakatlık & dönüş takibi"
      desc="Return-to-play takibi. Sağlık verisi KVKK'da özel niteliklidir; erişim denetim kaydına yazılır."
      navBadge={activeN}
      right={right}
    >
      <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        <div className="kpi"><div className="kl">Aktif Sakatlık</div><div className="kn" style={{ color: activeN ? "var(--crit)" : "var(--low)" }}>{activeN}</div><div className="kd">tedavide</div></div>
        <div className="kpi"><div className="kl">İyileşiyor</div><div className="kn" style={{ color: "var(--mid)" }}>{recoveringN}</div><div className="kd">dönüşe yakın</div></div>
        <div className="kpi"><div className="kl">Hazır</div><div className="kn" style={{ color: "var(--low)" }}>{clearedN}</div><div className="kd">temizlendi</div></div>
        <div className="kpi"><div className="kl">Toplam Kayıt</div><div className="kn">{teamRows.length}</div><div className="kd">aktif rehab</div></div>
      </div>

      <div className="st"><h2>Aktif Sakatlıklar</h2><span className="ep">GET /rehab/active</span></div>
      {team.isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {team.error && <div className="pgdesc">Liste alınamadı ya da yetki yok.</div>}
      <div className="tbl">
        <table>
          <thead><tr>
            <th>Oyuncu</th><th>Sakatlık</th><th className="c">Başlangıç → Dönüş</th>
            <th className="c">Kalan</th><th className="c">Durum</th><th className="r">Aksiyon</th>
          </tr></thead>
          <tbody>
            {teamRows.length === 0 && (
              <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                {team.data ? "Aktif sakatlık yok — kadro tam." : "Veri yok (backend bağlı değilse boş gelir)."}
              </td></tr>
            )}
            {teamRows.map((r) => {
              const left = daysUntil(r.expected_return);
              const next = NEXT[r.status];
              const v = STATUS_VAR[r.status] ?? "var(--muted)";
              return (
                <tr key={r.id}>
                  <td><span className="nm" style={{ fontFamily: "JetBrains Mono" }}>#{r.player_external_id}</span></td>
                  <td>{r.injury_type}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11 }}>{r.injury_start} → {r.expected_return ?? "—"}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: left !== null && left <= 0 ? "var(--high)" : "var(--muted)" }}>{left !== null ? `${left}g` : "—"}</td>
                  <td className="c"><span className="risk" style={{ color: v }}><span className="rd" style={{ background: v, boxShadow: `0 0 7px ${v}` }} />{STATUS_LABEL[r.status] ?? r.status}</span></td>
                  <td className="r">
                    {next ? (
                      <button type="button" onClick={() => setStatusFor(r, next)} style={{ fontSize: "10px", textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: "1px solid var(--line)", color: "var(--ink)", background: "var(--panel3)", cursor: "pointer" }}>
                        {next === "recovering" ? "İyileşmeye al" : "✓ Hazır"}
                      </button>
                    ) : <span style={{ color: "var(--dim)", fontSize: 11 }}>—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="st">
        <h2>Oyuncu Sorgu</h2>
        <form onSubmit={(e) => { e.preventDefault(); setQuery(search.trim()); }} style={{ display: "flex", gap: 6 }}>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Oyuncu ID" inputMode="numeric" style={{ ...fieldStyle, width: 120 }} />
          <button type="submit" style={{ ...fieldStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Getir</button>
        </form>
      </div>
      {!query && <div className="pgdesc">Bir oyuncunun rehab geçmişi için ID gir; sağdaki formla yeni kayıt ekleyebilirsin.</div>}
      {query && rehab.isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {query && !rehab.isLoading && rows.length === 0 && <div className="pgdesc">#{query} için aktif rehab kaydı yok.</div>}
      {rows.length > 0 && (
        <div className="tbl">
          <table>
            <thead><tr><th>Sakatlık</th><th className="c">Başlangıç → Dönüş</th><th className="c">Kalan</th><th className="c">Durum</th><th>Not</th></tr></thead>
            <tbody>
              {rows.map((r) => {
                const left = daysUntil(r.expected_return);
                const v = STATUS_VAR[r.status] ?? "var(--muted)";
                return (
                  <tr key={r.id}>
                    <td><span className="nm">{r.injury_type}</span></td>
                    <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11 }}>{r.injury_start} → {r.expected_return ?? "—"}</td>
                    <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{left !== null && r.status !== "cleared" ? `${left}g` : "—"}</td>
                    <td className="c"><span className="risk" style={{ color: v }}><span className="rd" style={{ background: v, boxShadow: `0 0 7px ${v}` }} />{STATUS_LABEL[r.status] ?? r.status}</span></td>
                    <td style={{ color: "var(--muted)", fontSize: 11.5 }}>{r.notes ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </ConsoleShell>
  );
}
