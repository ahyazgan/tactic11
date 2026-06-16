"use client";

/**
 * Tıbbi Merkez — sakatlık / rehabilitasyon / dönüş-riski konsolu. ConsoleShell çatısında.
 *
 * DEMO_MODE açıkken: canlı API'ye hiç dokunulmaz; Beşiktaş evreninden zengin,
 * inandırıcı Türkçe tıbbi içerik render edilir (boş-state / "ID gir" / spinner yok).
 * DEMO_MODE kapalıyken eski canlı-API davranışı (SWR + form) geri gelir.
 *
 * Backend (DEMO kapalıyken):
 *   GET   /rehab/active
 *   GET   /players/{id}/rehab/active
 *   POST  /players/{id}/rehab
 *   PATCH /players/{id}/rehab/{rid}
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { topRiskPlayers, LEVEL_VAR, LEVEL_LABEL } from "@/lib/injury-risk";
import { ConsoleShell } from "../_console/shell";
import { RiskDonut, LegendRow } from "../_console/viz";

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

// --------------------------------------------------------------------------- //
// DEMO VERİSİ (bu dosyaya özel inline const) — Beşiktaş evreni ile tutarlı.
// "Bugün" 2026-06-08 (maç günü). Tarihler buna göre kurgulandı.
// --------------------------------------------------------------------------- //

interface DemoInjury {
  player: string;
  shirt: number;
  pos: string;
  injury: string;
  region: "Adale" | "Eklem" | "Kemik" | "Bağ" | "Diğer";
  start: string;          // sakatlanma tarihi
  expected: string | null; // tahmini dönüş
  status: "active" | "recovering" | "cleared";
  progress: number;       // rehab ilerleme 0..100
  load: number;           // dönüşe hazırlık / yük toleransı 0..100
  notes: string;
}

const DEMO_INJURIES: DemoInjury[] = [
  { player: "Orkun Kökçü", shirt: 10, pos: "10 Numara", injury: "Hamstring zorlanması (Grade 1)", region: "Adale", start: "2026-06-06", expected: "2026-06-20", status: "active", progress: 18, load: 24, notes: "Maç-içi arka adale sinyali. MR temiz, düşük dereceli. Tam istirahat 4 gün." },
  { player: "Rıdvan Yılmaz", shirt: 3, pos: "Sol Bek", injury: "Aşil tendinopatisi", region: "Eklem", start: "2026-05-28", expected: "2026-06-15", status: "active", progress: 35, load: 41, notes: "Yük yönetimi protokolü. Eksantrik güç çalışması başladı." },
  { player: "Tiago Djaló", shirt: 4, pos: "Stoper", injury: "Adduktor zorlanması (Grade 2)", region: "Adale", start: "2026-05-22", expected: "2026-06-12", status: "recovering", progress: 64, load: 58, notes: "Saha-içi koşu fazına geçti. Yön değiştirme testleri %80 simetri." },
  { player: "Felix Uduokhai", shirt: 15, pos: "Stoper", injury: "Diz kapsül zorlanması", region: "Eklem", start: "2026-05-18", expected: "2026-06-14", status: "recovering", progress: 58, load: 52, notes: "Şişlik geriledi. İzokinetik kuvvet farkı %12 (hedef <%10)." },
  { player: "Kartal Yılmaz", shirt: 18, pos: "Sol Kanat", injury: "Bilek burkulması (Grade 1)", region: "Bağ", start: "2026-05-30", expected: "2026-06-10", status: "recovering", progress: 78, load: 71, notes: "Ağrısız tam yük. Proprioseptif denge + sprint hazır." },
  { player: "El Bilal Touré", shirt: 19, pos: "Santrfor", injury: "Kasık ödemi (overload)", region: "Adale", start: "2026-05-25", expected: "2026-06-11", status: "recovering", progress: 70, load: 66, notes: "ACWR yüksekti, yük düşürüldü. Bu hafta takımla kısmi antrenman." },
  { player: "Kristjan Asllani", shirt: 16, pos: "Ön Libero", injury: "Baldır zorlanması (Grade 1)", region: "Adale", start: "2026-05-12", expected: "2026-06-02", status: "cleared", progress: 100, load: 92, notes: "Return-to-play tamamlandı. Son maçta 72 dk oynadı, sorun yok." },
  { player: "Taylan Bulut", shirt: 24, pos: "Sağ Bek", injury: "Ayak bileği kontüzyonu", region: "Diğer", start: "2026-05-08", expected: "2026-05-26", status: "cleared", progress: 100, load: 96, notes: "Tam temizlendi. Kadroya geri döndü, full yük." },
];

const DEMO_REGION_DIST = [
  { label: "Adale", v: "var(--crit)" },
  { label: "Eklem", v: "var(--high)" },
  { label: "Bağ", v: "var(--mid)" },
  { label: "Diğer", v: "var(--low)" },
];

// Return-to-play takvimi (önümüzdeki günler) — sadece aktif/iyileşen kayıtlar.
interface RtpRow { player: string; shirt: number; phase: string; eta: string; days: number; conf: number; v: string }
const DEMO_RTP: RtpRow[] = [
  { player: "Kartal Yılmaz", shirt: 18, phase: "Kadro değerlendirme", eta: "2026-06-10", days: 2, conf: 88, v: "var(--low)" },
  { player: "El Bilal Touré", shirt: 19, phase: "Takımla kısmi antrenman", eta: "2026-06-11", days: 3, conf: 74, v: "var(--mid)" },
  { player: "Tiago Djaló", shirt: 4, phase: "Saha-içi koşu fazı", eta: "2026-06-12", days: 4, conf: 69, v: "var(--mid)" },
  { player: "Felix Uduokhai", shirt: 15, phase: "Kuvvet simetri çalışması", eta: "2026-06-14", days: 6, conf: 61, v: "var(--high)" },
  { player: "Rıdvan Yılmaz", shirt: 3, phase: "Yük yönetimi (tendinopati)", eta: "2026-06-15", days: 7, conf: 52, v: "var(--high)" },
  { player: "Orkun Kökçü", shirt: 10, phase: "Akut faz — istirahat", eta: "2026-06-20", days: 12, conf: 44, v: "var(--crit)" },
];

// Yük / re-injury risk uyarıları (sağ kolon) — birleşik risk endeksinden HESAPLANIR
// (lib/injury-risk). En riskli oyuncular + her birinin öncelikli aksiyonu; oyuncu
// profili sayfasıyla TEK kaynaktan tutarlı (elle yazılmış sabit liste değil).
interface LoadAlert { player: string; note: string; v: string; tag: string }
const DEMO_LOAD_ALERTS: LoadAlert[] = topRiskPlayers(4).map(({ player, risk }) => ({
  player: `${player.player_name} (${player.shirt})`,
  note: risk.recommendation,
  v: LEVEL_VAR[risk.level],
  tag: LEVEL_LABEL[risk.level].toLowerCase(),
}));

function progColor(v: number): string {
  return v >= 80 ? "var(--low)" : v >= 50 ? "var(--mid)" : "var(--high)";
}

export default function MedicalConsolePage() {
  // ───────────────────────────── DEMO MODU ─────────────────────────────
  // Canlı API'ye hiç dokunma; Beşiktaş evreninden zengin tıbbi merkez render et.
  if (DEMO_MODE) return <MedicalDemo />;
  return <MedicalLive />;
}

/* ─────────────────────────── DEMO RENDER ─────────────────────────── */
function MedicalDemo() {
  type Filter = "all" | "active" | "recovering" | "cleared";
  const [filter, setFilter] = React.useState<Filter>("all");

  const activeN = DEMO_INJURIES.filter((r) => r.status === "active").length;
  const recoveringN = DEMO_INJURIES.filter((r) => r.status === "recovering").length;
  const clearedN = DEMO_INJURIES.filter((r) => r.status === "cleared").length;
  const openN = activeN + recoveringN;

  // Bölge dağılımı (donut) — açık (cleared olmayan) kayıtlardan.
  const open = DEMO_INJURIES.filter((r) => r.status !== "cleared");
  const regionCount = (label: string) => open.filter((r) => r.region === label).length;
  const dist = DEMO_REGION_DIST.map((d) => ({ ...d, n: regionCount(d.label) }));

  const shown = DEMO_INJURIES.filter((r) => filter === "all" || r.status === filter);

  const right = (
    <>
      <div className="rc">
        <h3>Sakatlık Bölgesi <span className="tiny">{open.length} açık</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut segments={dist.map((d) => ({ value: d.n, color: d.v }))} centerLabel={open.length} centerSub="açık" />
          <div style={{ flex: 1, minWidth: 0 }}>
            {dist.map((d) => (
              <LegendRow key={d.label} color={d.v} label={d.label} value={d.n} />
            ))}
          </div>
        </div>
      </div>

      <div className="rc">
        <h3>Sıradaki Dönüş <span className="tiny">return-to-play</span></h3>
        <div className="nm-vs"><span className="t">Kartal Yılmaz</span></div>
        <div className="nm-when">Kadro değerlendirme · 2 gün · Antalyaspor maçı</div>
        <div className="probbar">
          <i style={{ width: "88%", background: "var(--low)" }} />
          <i style={{ width: "12%", background: "var(--surface2)" }} />
        </div>
        <div className="probleg">
          <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>%88</div><div className="pl">Hazırlık</div></div>
          <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>78</div><div className="pl">Rehab İlerleme</div></div>
          <div className="pi"><div className="pv" style={{ color: "var(--ink)" }}>13g</div><div className="pl">Süre</div></div>
        </div>
      </div>

      <div className="rc">
        <h3>Re-injury / Yük Uyarıları <span className="tiny">{DEMO_LOAD_ALERTS.length} aktif</span></h3>
        {DEMO_LOAD_ALERTS.map((a) => (
          <div className="alrt" key={a.player}>
            <span className="ai" style={{ background: a.v }} />
            <div className="am"><b>{a.player}</b> · {a.tag}
              <span className="tm">{a.note}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="rc">
        <h3>Görevler <span className="tiny">0/3</span></h3>
        <div className="task"><span className="cb" /><span className="tt">Orkun Kökçü dönüş protokolü onayı</span></div>
        <div className="task"><span className="cb" /><span className="tt">Kartal Yılmaz kadro değerlendirme (RTP)</span></div>
        <div className="task"><span className="cb" /><span className="tt">Felix Uduokhai izokinetik re-test planı</span></div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/medical"
      title="Tıbbi Merkez"
      sub="Sakatlık & dönüş takibi"
      desc="Return-to-play takibi, rehabilitasyon ilerlemesi ve tekrar-sakatlık riski. Sağlık verisi KVKK'da özel niteliklidir; erişim denetim kaydına yazılır."
      navBadge={activeN}
      right={right}
    >
      <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        <div className="kpi"><div className="kl">Aktif Sakatlık</div><div className="kn" style={{ color: activeN ? "var(--crit)" : "var(--low)" }}>{activeN}</div><div className="kd">akut tedavide</div></div>
        <div className="kpi"><div className="kl">İyileşiyor</div><div className="kn" style={{ color: "var(--mid)" }}>{recoveringN}</div><div className="kd">rehab fazında</div></div>
        <div className="kpi"><div className="kl">Bu Hafta Dönen</div><div className="kn" style={{ color: "var(--low)" }}>{clearedN}</div><div className="kd">kadroya geri</div></div>
        <div className="kpi"><div className="kl">Açık Vaka</div><div className="kn">{openN}</div><div className="kd">takipte</div></div>
      </div>

      <div className="st">
        <h2>Sakatlık & Rehabilitasyon</h2>
        <div className="seg">
          <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>Tümü</button>
          <button className={filter === "active" ? "on" : ""} onClick={() => setFilter("active")}>Sakat</button>
          <button className={filter === "recovering" ? "on" : ""} onClick={() => setFilter("recovering")}>İyileşiyor</button>
          <button className={filter === "cleared" ? "on" : ""} onClick={() => setFilter("cleared")}>Hazır</button>
        </div>
      </div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th>Oyuncu</th><th>Sakatlık</th><th className="c">Başlangıç → Dönüş</th>
            <th className="c">Kalan</th><th className="c">Rehab İlerleme</th><th className="c">Durum</th>
          </tr></thead>
          <tbody>
            {shown.map((r, i) => {
              const left = daysUntil(r.expected);
              const v = STATUS_VAR[r.status];
              return (
                <tr key={`${r.player}-${i}`}>
                  <td>
                    <span className="nm">{r.player}</span> <span className="nat">#{r.shirt}</span>
                    <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 2 }}>{r.pos}</div>
                  </td>
                  <td>
                    <span style={{ fontSize: 12.5 }}>{r.injury}</span>
                    <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 2 }}>{r.region}</div>
                  </td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11 }}>{r.start} → {r.expected ?? "—"}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: r.status === "cleared" ? "var(--dim)" : left !== null && left <= 3 ? "var(--high)" : "var(--muted)" }}>
                    {r.status === "cleared" ? "döndü" : left !== null ? `${left}g` : "—"}
                  </td>
                  <td className="c">
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="mbar" style={{ flex: 1, margin: 0 }}><i style={{ width: `${r.progress}%`, background: progColor(r.progress) }} /></span>
                      <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--muted)", minWidth: 30, textAlign: "right" }}>{r.progress}%</span>
                    </div>
                  </td>
                  <td className="c"><span className="risk" style={{ color: v }}><span className="rd" style={{ background: v, boxShadow: `0 0 7px ${v}` }} />{STATUS_LABEL[r.status]}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="st"><h2>Return-to-Play Takvimi</h2><span className="ep">model güveni · tahmini dönüş</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th>Oyuncu</th><th>Mevcut Faz</th><th className="c">Tahmini Dönüş</th>
            <th className="c">Kalan</th><th className="r">Model Güveni</th>
          </tr></thead>
          <tbody>
            {DEMO_RTP.map((r) => (
              <tr key={r.player}>
                <td><span className="nm">{r.player}</span> <span className="nat">#{r.shirt}</span></td>
                <td style={{ color: "var(--muted)", fontSize: 12 }}>{r.phase}</td>
                <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11 }}>{r.eta}</td>
                <td className="c" style={{ fontFamily: "JetBrains Mono", color: r.days <= 3 ? "var(--low)" : r.days <= 7 ? "var(--mid)" : "var(--high)" }}>{r.days}g</td>
                <td className="r" style={{ color: r.v }}>{r.conf}<span style={{ fontSize: 10, color: "var(--dim)", fontWeight: 400 }}>/100</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="st"><h2>Klinik Notlar</h2><span className="ep">tıbbi ekip</span></div>
      <div className="tbl">
        <table>
          <thead><tr><th>Oyuncu</th><th>Not</th></tr></thead>
          <tbody>
            {DEMO_INJURIES.filter((r) => r.status !== "cleared").map((r, i) => (
              <tr key={`note-${i}`}>
                <td style={{ whiteSpace: "nowrap" }}><span className="nm">{r.player}</span> <span className="nat">#{r.shirt}</span></td>
                <td style={{ color: "var(--muted)", fontSize: 12 }}>{r.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}

/* ─────────────────────── CANLI RENDER (DEMO kapalı) ─────────────────────── */
function MedicalLive() {
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
