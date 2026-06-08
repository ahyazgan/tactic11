"use client";

/**
 * Fiziksel Performans Paneli — saha/tablet için tam-ekran (shell bypass).
 *
 * Tasarım birebir korunur (koyu tema + Beşiktaş kırmızısı + risk halkası);
 * statik veri yerine gerçek API'ye bağlı:
 *   GET  /physical-tests/players          — kadro (özet + risk)
 *   GET  /physical-tests/{id}             — test geçmişi
 *   GET  /physical-tests/{id}/risk        — yük riski (halka + flags + öneriler)
 *   POST /physical-tests/                 — yeni test → 201 → yeniden fetch
 * Risk hesabı backend'de; frontend yalnız gösterir.
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import {
  Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { apiFetch, getAccessToken } from "@/lib/api";
import { useCurrentUser } from "@/lib/auth";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  demoPlayerSummaries, demoHistoryFor, demoRiskFor, demoProtocols,
  type ProtocolInfo,
} from "@/lib/demo-data";

interface PlayerSummary {
  player_id: string;
  player_name: string;
  test_count: number;
  latest_test_date: string | null;
  risk_label: string;
  risk_score: number;
}
interface PhysicalTest {
  id: number;
  player_id: string;
  test_date: string;
  protocol: string;
  value: number;
  unit: string | null;
}
interface RiskReport {
  player_id: string;
  player_name: string;
  risk_score: number;
  risk_label: string;
  flags: { protocol: string; value: number; unit: string; message: string }[];
  summary: string;
  recommendations: string[];
}

const PROTO: { value: string; label: string; name: string; unit: string }[] = [
  { value: "sprint_10m", label: "Sprint 10m (sn)", name: "SPRINT 10M", unit: "sn" },
  { value: "sprint_30m", label: "Sprint 30m (sn)", name: "SPRINT 30M", unit: "sn" },
  { value: "yoyo_irl1", label: "YoYo IRL1 (seviye)", name: "YOYO IRL1", unit: "sv" },
  { value: "cmj", label: "CMJ — Sıçrama (cm)", name: "CMJ", unit: "cm" },
  { value: "isokinetic_quad", label: "İzokinetik Quad (Nm/kg)", name: "İZOKİN. Q", unit: "Nm/kg" },
  { value: "isokinetic_ham", label: "İzokinetik Ham (Nm/kg)", name: "İZOKİN. H", unit: "Nm/kg" },
  { value: "vo2max", label: "VO2max (ml/kg/dk)", name: "VO2MAX", unit: "ml" },
  { value: "gps_total_dist", label: "GPS Toplam Mesafe (m)", name: "GPS MESAFE", unit: "m" },
  { value: "body_fat_pct", label: "Vücut Yağı (%)", name: "VÜCUT YAĞI", unit: "%" },
];
const protoName = (k: string) => PROTO.find((p) => p.value === k)?.name ?? k.toUpperCase();
const protoUnit = (k: string) => PROTO.find((p) => p.value === k)?.unit ?? "";

function riskVar(label: string): string {
  switch (label) {
    case "Düşük": return "var(--low)";
    case "Orta": return "var(--mid)";
    case "Yüksek": return "var(--high)";
    case "Kritik": return "var(--crit)";
    default: return "var(--dim)";
  }
}

type TrendDir = "improving" | "worsening" | "stable" | "insufficient";
const DIRECTION_LABEL: Record<TrendDir, string> = {
  improving: "İyileşiyor ↑",
  worsening: "Kötüleşiyor ↓",
  stable: "Sabit →",
  insufficient: "Yetersiz veri",
};

/** İlk→son değişimden yön çıkar (protokol yönüne duyarlı). */
function seriesDirection(values: number[], higherIsBetter: boolean): TrendDir {
  if (values.length < 2) return "insufficient";
  const first = values[0];
  const last = values[values.length - 1];
  const eps = Math.abs(first) * 0.01 || 0.001;
  const diff = last - first;
  if (Math.abs(diff) <= eps) return "stable";
  const rising = diff > 0;
  return rising === higherIsBetter ? "improving" : "worsening";
}

function dirColor(dir: TrendDir): string {
  if (dir === "improving") return "var(--low)";
  if (dir === "worsening") return "var(--crit)";
  return "var(--muted)";
}

export default function PhysicalPanelPage() {
  const { user } = useCurrentUser();
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [toast, setToast] = React.useState(false);

  // Form
  const [playerId, setPlayerId] = React.useState("");
  const [playerName, setPlayerName] = React.useState("");
  const [proto, setProto] = React.useState("sprint_10m");
  const [val, setVal] = React.useState("");
  const [by, setBy] = React.useState("");
  const [date, setDate] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [showGuide, setShowGuide] = React.useState(false);

  const playersSwr = useSWR<PlayerSummary[]>(
    DEMO_MODE ? null : "/physical-tests/players", apiFetch);
  const players = DEMO_MODE
    ? { data: demoPlayerSummaries as PlayerSummary[], isLoading: false, mutate: async () => {} }
    : playersSwr;
  const list = players.data ?? [];

  // İlk yükte ilk oyuncuyu seç
  React.useEffect(() => {
    if (activeId === null && list.length > 0) setActiveId(list[0].player_id);
  }, [list, activeId]);

  const active = list.find((p) => p.player_id === activeId) ?? null;

  // Seçili oyuncu değişince formu ön-doldur
  React.useEffect(() => {
    if (active) {
      setPlayerId(active.player_id);
      setPlayerName(active.player_name);
    }
  }, [active]);

  const historySwr = useSWR<PhysicalTest[]>(
    DEMO_MODE || !activeId ? null : `/physical-tests/${activeId}`, apiFetch,
  );
  const history = DEMO_MODE
    ? { data: activeId ? (demoHistoryFor(Number(activeId)) as PhysicalTest[]) : [], isLoading: false, mutate: async () => {} }
    : historySwr;
  const riskSwr = useSWR<RiskReport>(
    DEMO_MODE || !activeId ? null : `/physical-tests/${activeId}/risk`, apiFetch,
    { shouldRetryOnError: false },
  );
  const risk = DEMO_MODE
    ? { data: activeId ? (demoRiskFor(Number(activeId)) as RiskReport) : undefined, isLoading: false, mutate: async () => {} }
    : riskSwr;

  // Protokol rehberi — canlıda GET /protocols (auth'suz), demo'da statik.
  const protocolsSwr = useSWR<ProtocolInfo[]>(
    DEMO_MODE ? null : "/physical-tests/protocols", apiFetch);
  const protocols: ProtocolInfo[] = DEMO_MODE ? demoProtocols : (protocolsSwr.data ?? []);
  const protoInfo = protocols.find((p) => p.key === proto) ?? null;

  // Trend sparkline — yüklü geçmişten seçili protokolün serisi (tarih artan).
  const protoSeries = React.useMemo(() => {
    const rows = (history.data ?? [])
      .filter((t) => t.protocol === proto)
      .slice()
      .sort((a, b) => a.test_date.localeCompare(b.test_date));
    return rows.map((t) => ({ date: t.test_date, val: t.value }));
  }, [history.data, proto]);
  const protoDir = seriesDirection(
    protoSeries.map((p) => p.val), protoInfo?.higher_is_better ?? true,
  );

  async function addTest() {
    const v = parseFloat(val);
    if (!playerId.trim() || !playerName.trim() || Number.isNaN(v)) {
      setErr("Oyuncu ID, ad ve geçerli bir değer gerekli.");
      return;
    }
    setErr(null);
    setBusy(true);
    try {
      await apiFetch("/physical-tests/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          player_id: playerId.trim(), player_name: playerName.trim(),
          test_date: date, protocol: proto, value: v,
          recorded_by: by.trim() || null,
        }),
      });
      setVal("");
      setActiveId(playerId.trim());
      await Promise.all([players.mutate(), history.mutate(), risk.mutate()]);
      setToast(true);
      window.setTimeout(() => setToast(false), 2200);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Kayıt başarısız");
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf() {
    if (!activeId) return;
    const token = getAccessToken();
    const res = await fetch(`/api/physical-tests/${activeId}/pdf`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      setErr("PDF üretilemedi.");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }

  const score = risk.data ? Math.round(risk.data.risk_score * 100) : 0;
  const ringColor = risk.data ? riskVar(risk.data.risk_label) : "var(--dim)";

  return (
    <div className="pp-root">
      <div className="topbar">
        <div className="brand">
          <Link href="/" className="pp-back" title="Uygulamaya dön">←</Link>
          <div className="mark">m2</div>
          <h1>manager2 <span>/ Performans Modülü</span></h1>
          <nav style={{ display: "flex", gap: 2, marginLeft: 18 }}>
            <span
              style={{
                padding: "5px 12px", fontSize: 12.5, fontWeight: 600,
                color: "#e8ebf2", borderBottom: "2px solid var(--besiktas, #e30613)",
              }}
            >
              Panel
            </span>
            <Link
              href="/performance"
              style={{
                padding: "5px 12px", fontSize: 12.5, fontWeight: 600,
                color: "#8b94a8", borderBottom: "2px solid transparent",
                textDecoration: "none",
              }}
              title="Protokol kütüphanesi + batarya değerlendirme"
            >
              Veri Girişi &amp; Batarya
            </Link>
          </nav>
        </div>
        <Link href="/test-session" style={{
          display: "flex", alignItems: "center", gap: 6,
          background: "var(--besiktas)", color: "#fff",
          padding: "8px 16px", borderRadius: 9, fontSize: 13,
          fontWeight: 800, textDecoration: "none", fontFamily: "'Archivo'",
          letterSpacing: "0.2px", marginLeft: "auto",
        }}>
          ▶ Saha Testi Başlat
        </Link>
        <div className="club-pill">
          <span className="dot" />
          <b>{user?.tenant_slug?.toUpperCase() ?? user?.tenant_id ?? "KULÜP"}</b>
          <span className="role">· {user?.email ?? ""}</span>
        </div>
      </div>

      <div className="wrap">
        <aside className="roster">
          <div className="lbl">Kadro · {list.length} oyuncu</div>
          <div id="roster">
            {players.isLoading && <div className="empty">Yükleniyor…</div>}
            {!players.isLoading && list.length === 0 && (
              <div className="empty">Henüz test kaydı yok. Sağdaki formla ilk testi gir.</div>
            )}
            {list.map((p) => (
              <div
                key={p.player_id}
                className={`player ${p.player_id === activeId ? "active" : ""}`}
                onClick={() => setActiveId(p.player_id)}
              >
                <div className="topline">
                  <span className="num">{p.test_count}</span>
                  <span
                    className="pdot"
                    style={{ background: riskVar(p.risk_label), boxShadow: `0 0 8px ${riskVar(p.risk_label)}` }}
                  />
                </div>
                <div className="pinfo">
                  <div className="pname">{p.player_name}</div>
                  <div className="ppos">{p.test_count} test · {p.risk_label}</div>
                </div>
              </div>
            ))}
          </div>
        </aside>

        <main className="main">
          <div className="phead">
            <div>
              <div className="crumb">Oyuncu Profili</div>
              <h2 id="pname">{active ? active.player_name : "—"}</h2>
              <div className="meta">
                {active
                  ? <>#{active.player_id} · <b>{active.test_count}</b> test kaydı{active.latest_test_date ? ` · son ${active.latest_test_date}` : ""}</>
                  : "Soldan oyuncu seç veya yeni test gir."}
              </div>
            </div>
            {active && (
              <button type="button" className="pdfbtn" onClick={downloadPdf}>
                ⬇ PDF indir
              </button>
            )}
          </div>

          <div className="grid">
            {/* Risk */}
            <section className="card riskcard">
              <div className="ctitle">Yükleme Riski Analizi</div>
              <div className="gauge">
                <div
                  className="ring"
                  style={{ "--p": score, "--ringc": ringColor } as unknown as React.CSSProperties}
                >
                  <div className="val">
                    <div className="num">{score}</div>
                    <div className="of">/ 100</div>
                  </div>
                </div>
                <div className="risklabel">
                  <span
                    className="tag"
                    style={{
                      background: ringColor,
                      color: risk.data?.risk_label === "Orta" ? "#1a1500" : "#0a0a0c",
                    }}
                  >
                    {risk.data?.risk_label ?? (active ? "Veri Yok" : "—")}
                  </span>
                  <div className="summary">
                    {risk.data?.summary
                      ?? (active ? "Bu oyuncu için risk verisi yok." : "Oyuncu seçin.")}
                  </div>
                </div>
              </div>

              <div className="flags">
                {risk.data && risk.data.flags.length > 0
                  ? risk.data.flags.map((f, i) => (
                    <div className="flag" key={i}>
                      <span className="ficon" style={{ background: ringColor }} />
                      <span className="fname">{protoName(f.protocol)}</span>
                      <span className="fmsg">{f.message}</span>
                      <span className="fval" style={{ color: ringColor }}>
                        {f.value} {f.unit || protoUnit(f.protocol)}
                      </span>
                    </div>
                  ))
                  : (
                    <div className="flag">
                      <span className="ficon" style={{ background: "var(--low)" }} />
                      <span className="fmsg">
                        {risk.data ? "Tüm parametreler referans aralığında." : "—"}
                      </span>
                    </div>
                  )}
              </div>

              <div style={{ marginTop: 18, paddingTop: 16, borderTop: "1px solid var(--line)" }}>
                <div className="ctitle" style={{ marginBottom: 12 }}>Öneriler</div>
                <ul className="recs">
                  {(risk.data?.recommendations ?? []).map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </div>
            </section>

            {/* Giriş + geçmiş */}
            <section className="card">
              <div className="ctitle">Saha Testi Veri Girişi</div>
              <div className="row">
                <div className="field">
                  <label>Oyuncu ID</label>
                  <input value={playerId} onChange={(e) => setPlayerId(e.target.value)} placeholder="API-Football id" />
                </div>
                <div className="field">
                  <label>Oyuncu Adı</label>
                  <input value={playerName} onChange={(e) => setPlayerName(e.target.value)} placeholder="Ad Soyad" />
                </div>
              </div>
              <div className="row">
                <div className="field">
                  <label>Test Protokolü</label>
                  <select value={proto} onChange={(e) => setProto(e.target.value)}>
                    {PROTO.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                  </select>
                </div>
                <div className="field" style={{ maxWidth: 110 }}>
                  <label>Değer</label>
                  <input type="number" step="0.01" value={val} onChange={(e) => setVal(e.target.value)} placeholder="0.00" />
                </div>
              </div>

              {/* Protokol rehberi — "nasıl uygulanır" + norm eşikleri */}
              <button
                type="button"
                onClick={() => setShowGuide((v) => !v)}
                style={{
                  background: "none", border: 0, color: "var(--muted)",
                  fontSize: 12, cursor: "pointer", padding: "0 0 10px",
                  textDecoration: "underline", fontFamily: "inherit",
                }}
              >
                {showGuide ? "Rehberi gizle" : "Protokol nasıl uygulanır?"}
              </button>
              {showGuide && protoInfo && (
                <div style={{
                  background: "var(--panel2)", border: "1px solid var(--line)",
                  borderRadius: 10, padding: "13px 15px", marginBottom: 13,
                }}>
                  <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 5 }}>{protoInfo.name}</div>
                  <div style={{ color: "var(--muted)", fontSize: 13, lineHeight: 1.5, marginBottom: 11 }}>
                    {protoInfo.description}
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {([
                      ["Elit", protoInfo.norm_elite, "var(--low)"],
                      ["İyi", protoInfo.norm_good, "var(--mid)"],
                      ["Ortalama", protoInfo.norm_average, "var(--dim)"],
                    ] as [string, number, string][]).map(([label, v, col]) => (
                      <span key={label} style={{
                        fontFamily: "'JetBrains Mono'", fontSize: 12,
                        background: "var(--panel)", border: "1px solid var(--line)",
                        borderRadius: 7, padding: "5px 10px",
                      }}>
                        <b style={{ color: col }}>{label}</b>{" "}
                        {v} {protoInfo.unit}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div className="row">
                <div className="field">
                  <label>Kaydeden</label>
                  <input value={by} onChange={(e) => setBy(e.target.value)} placeholder="Kondisyoner" />
                </div>
                <div className="field" style={{ maxWidth: 140 }}>
                  <label>Tarih</label>
                  <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
                </div>
              </div>
              {err && <div style={{ color: "var(--crit)", fontSize: 13, marginBottom: 8 }}>{err}</div>}
              <button className="addbtn" onClick={addTest} disabled={busy}>
                {busy ? "Kaydediliyor…" : "+ Testi Kaydet → analiz et"}
              </button>

              <div className="tests">
                <div className="ctitle" style={{ marginBottom: 10 }}>Test Geçmişi</div>

                {/* Seçili protokolün trend sparkline'ı (yön renkli) */}
                {protoSeries.length >= 2 && (
                  <div style={{ marginBottom: 14 }}>
                    <div style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      marginBottom: 4,
                    }}>
                      <span style={{ fontSize: 12, color: "var(--muted)", fontFamily: "'Archivo Narrow'", textTransform: "uppercase", letterSpacing: 1 }}>
                        {protoName(proto)} trendi
                      </span>
                      <span style={{ fontSize: 12, fontWeight: 700, color: dirColor(protoDir) }}>
                        {DIRECTION_LABEL[protoDir]}
                      </span>
                    </div>
                    <div style={{ height: 72 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={protoSeries} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
                          <XAxis dataKey="date" hide />
                          <YAxis domain={["auto", "auto"]} hide />
                          <Tooltip
                            contentStyle={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }}
                            labelStyle={{ color: "var(--muted)" }}
                            formatter={(v: number) => [`${v} ${protoUnit(proto)}`, protoName(proto)]}
                          />
                          <Line type="monotone" dataKey="val" stroke={dirColor(protoDir)} strokeWidth={2.5} dot={{ r: 2.5, fill: dirColor(protoDir) }} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                <div id="history">
                  {(history.data ?? []).map((t) => (
                    <div className="testrow" key={t.id}>
                      <span className="tn">{protoName(t.protocol)}</span>
                      <span className="tv">{t.value} {t.unit || protoUnit(t.protocol)}</span>
                      <span className="td">{t.test_date}</span>
                    </div>
                  ))}
                  {activeId && (history.data?.length ?? 0) === 0 && !history.isLoading && (
                    <div className="empty">Kayıt yok.</div>
                  )}
                </div>
              </div>
            </section>
          </div>
        </main>
      </div>

      <div className={`toast ${toast ? "show" : ""}`}>
        ✓ Kayıt eklendi <span className="code">201 Created</span>
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        @import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800;900&family=Archivo+Narrow:wght@500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');
        @property --p { syntax:'<number>'; inherits:false; initial-value:0 }
        @keyframes pp-slidein { from{opacity:0;transform:translateY(-6px)} to{opacity:1;transform:none} }

        .pp-root{
          --bg:#0a0a0c; --panel:#131318; --panel2:#1a1a21; --line:#26262f;
          --ink:#f4f4f6; --muted:#8a8a96; --dim:#5a5a66; --accent:#ffffff;
          --low:#3ddc84; --mid:#ffd23f; --high:#ff8c42; --crit:#ff4d4d; --besiktas:#e30613;
          background:var(--bg); color:var(--ink); font-family:'Archivo',sans-serif;
          min-height:100vh; margin:0;
          background-image:
            radial-gradient(circle at 15% 10%, rgba(255,255,255,0.03), transparent 40%),
            radial-gradient(circle at 85% 90%, rgba(227,6,19,0.05), transparent 45%);
        }
        .pp-root *{margin:0;padding:0;box-sizing:border-box}
        .pp-root .empty{color:var(--dim);font-size:13px;padding:8px 24px}

        .pp-root .topbar{
          display:flex;align-items:center;justify-content:space-between;
          padding:18px 34px;border-bottom:1px solid var(--line);
          background:rgba(10,10,12,0.8);backdrop-filter:blur(12px);
          position:sticky;top:0;z-index:20;
        }
        .pp-root .brand{display:flex;align-items:center;gap:14px}
        .pp-root .pp-back{
          display:flex;align-items:center;justify-content:center;
          width:30px;height:30px;border-radius:8px;border:1px solid var(--line);
          color:var(--muted);text-decoration:none;font-size:16px;font-weight:700;
          background:var(--panel2);transition:all .15s
        }
        .pp-root .pp-back:hover{color:var(--ink);border-color:var(--muted)}
        .pp-root .brand .mark{
          width:38px;height:38px;border-radius:9px;
          background:linear-gradient(135deg,#fff,#bdbdc7);
          display:flex;align-items:center;justify-content:center;
          font-weight:900;color:#0a0a0c;font-size:19px;letter-spacing:-1px;
        }
        .pp-root .brand h1{font-size:17px;font-weight:800;letter-spacing:-0.4px}
        .pp-root .brand h1 span{color:var(--dim);font-weight:500}
        .pp-root .club-pill{
          display:flex;align-items:center;gap:9px;background:var(--panel);
          border:1px solid var(--line);padding:7px 14px;border-radius:999px;font-size:13px;
        }
        .pp-root .club-pill .dot{width:9px;height:9px;border-radius:50%;background:var(--besiktas);box-shadow:0 0 10px var(--besiktas)}
        .pp-root .club-pill b{font-weight:700;letter-spacing:0.3px}
        .pp-root .club-pill .role{color:var(--dim);font-size:12px}

        .pp-root .wrap{display:grid;grid-template-columns:300px 1fr;gap:0;min-height:calc(100vh - 75px)}

        .pp-root .roster{border-right:1px solid var(--line);padding:24px 0;background:var(--panel)}
        .pp-root .roster .lbl{
          font-family:'Archivo Narrow';text-transform:uppercase;letter-spacing:2px;
          font-size:11px;color:var(--dim);padding:0 24px;margin-bottom:14px;font-weight:600
        }
        .pp-root .player{
          display:flex;align-items:center;gap:13px;padding:13px 24px;cursor:pointer;
          border-left:3px solid transparent;transition:all .15s
        }
        .pp-root .player:hover{background:var(--panel2)}
        .pp-root .player.active{background:var(--panel2);border-left-color:var(--besiktas)}
        .pp-root .player .num{font-family:'JetBrains Mono';font-size:13px;color:var(--dim);width:24px;font-weight:700}
        .pp-root .player .topline{display:contents}
        .pp-root .player .pinfo{flex:1}
        .pp-root .player .pname{font-size:14px;font-weight:600;letter-spacing:-0.2px}
        .pp-root .player .ppos{font-size:11px;color:var(--muted);font-family:'Archivo Narrow';text-transform:uppercase;letter-spacing:1px}
        .pp-root .player .pdot{width:8px;height:8px;border-radius:50%}

        .pp-root .main{padding:30px 36px;overflow-y:auto}
        .pp-root .crumb{font-family:'Archivo Narrow';text-transform:uppercase;letter-spacing:2px;font-size:11px;color:var(--dim);margin-bottom:6px}
        .pp-root .phead{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:26px}
        .pp-root .phead h2{font-size:34px;font-weight:900;letter-spacing:-1px}
        .pp-root .phead .meta{color:var(--muted);font-size:13px;margin-top:4px}
        .pp-root .phead .meta b{color:var(--ink)}

        .pp-root .grid{display:grid;grid-template-columns:1.15fr 1fr;gap:22px}

        .pp-root .card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:24px}
        .pp-root .card .ctitle{
          font-family:'Archivo Narrow';text-transform:uppercase;letter-spacing:2px;
          font-size:12px;color:var(--muted);margin-bottom:18px;font-weight:600;
          display:flex;align-items:center;gap:8px
        }
        .pp-root .card .ctitle::before{content:'';width:14px;height:2px;background:var(--besiktas)}

        .pp-root .riskcard{position:relative;overflow:hidden}
        .pp-root .gauge{display:flex;align-items:center;gap:26px;margin-bottom:8px}
        .pp-root .ring{
          --p:0;width:128px;height:128px;border-radius:50%;flex-shrink:0;position:relative;
          background:conic-gradient(var(--ringc) calc(var(--p)*1%), var(--panel2) 0);
          display:flex;align-items:center;justify-content:center;transition:--p 1.1s ease;
        }
        .pp-root .ring::before{content:'';position:absolute;inset:11px;border-radius:50%;background:var(--panel)}
        .pp-root .ring .val{position:relative;text-align:center}
        .pp-root .ring .val .num{font-size:32px;font-weight:900;font-family:'JetBrains Mono';line-height:1}
        .pp-root .ring .val .of{font-size:11px;color:var(--dim);font-family:'JetBrains Mono'}
        .pp-root .risklabel{flex:1}
        .pp-root .risklabel .tag{
          display:inline-block;padding:6px 15px;border-radius:8px;font-size:13px;font-weight:800;
          letter-spacing:1px;text-transform:uppercase;font-family:'Archivo Narrow';margin-bottom:10px
        }
        .pp-root .risklabel .summary{font-size:14.5px;line-height:1.55;color:var(--ink)}

        .pp-root .flags{margin-top:20px;padding-top:18px;border-top:1px solid var(--line)}
        .pp-root .flag{
          display:flex;align-items:center;gap:12px;padding:10px 0;font-size:13px;
          border-bottom:1px solid rgba(38,38,47,0.5)
        }
        .pp-root .flag:last-child{border:0}
        .pp-root .flag .ficon{width:7px;height:7px;border-radius:50%;flex-shrink:0}
        .pp-root .flag .fname{font-family:'JetBrains Mono';font-size:12px;color:var(--muted);width:120px;flex-shrink:0}
        .pp-root .flag .fmsg{flex:1;color:var(--ink)}
        .pp-root .flag .fval{font-family:'JetBrains Mono';font-weight:700;font-size:13px}

        .pp-root .recs li{
          list-style:none;padding:11px 0 11px 26px;position:relative;font-size:13.5px;
          line-height:1.5;border-bottom:1px solid rgba(38,38,47,0.5)
        }
        .pp-root .recs li:last-child{border:0}
        .pp-root .recs li::before{content:'→';position:absolute;left:0;color:var(--besiktas);font-weight:800}

        .pp-root .row{display:flex;gap:12px;margin-bottom:13px}
        .pp-root .field{flex:1}
        .pp-root .field label{
          display:block;font-family:'Archivo Narrow';text-transform:uppercase;
          letter-spacing:1.5px;font-size:10.5px;color:var(--dim);margin-bottom:6px;font-weight:600
        }
        .pp-root .field select,.pp-root .field input{
          width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--ink);
          padding:11px 13px;border-radius:9px;font-size:14px;font-family:'Archivo';outline:none;transition:border .15s
        }
        .pp-root .field select:focus,.pp-root .field input:focus{border-color:var(--muted)}
        .pp-root .field input::placeholder{color:var(--dim)}
        .pp-root .addbtn{
          width:100%;margin-top:6px;background:var(--ink);color:#0a0a0c;border:0;
          padding:13px;border-radius:10px;font-size:14px;font-weight:800;font-family:'Archivo';
          cursor:pointer;letter-spacing:0.3px;transition:transform .1s,box-shadow .2s
        }
        .pp-root .addbtn:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(255,255,255,0.12)}
        .pp-root .addbtn:active{transform:translateY(0)}
        .pp-root .addbtn:disabled{opacity:.5;cursor:default;transform:none;box-shadow:none}

        .pp-root .tests{margin-top:20px;padding-top:18px;border-top:1px solid var(--line)}
        .pp-root .testrow{
          display:grid;grid-template-columns:1fr auto auto;gap:12px;align-items:center;
          padding:9px 0;font-size:13px;border-bottom:1px solid rgba(38,38,47,0.5);
          animation:pp-slidein .35s ease
        }
        .pp-root .testrow .tn{font-family:'Archivo Narrow';text-transform:uppercase;letter-spacing:1px;color:var(--muted);font-weight:600;font-size:12px}
        .pp-root .testrow .tv{font-family:'JetBrains Mono';font-weight:700;text-align:right}
        .pp-root .testrow .td{font-family:'JetBrains Mono';color:var(--dim);font-size:11px;text-align:right}

        .pp-root .toast{
          position:fixed;bottom:28px;right:28px;background:var(--low);color:#04140a;
          padding:14px 22px;border-radius:11px;font-weight:800;font-size:14px;
          transform:translateY(120px);transition:transform .35s cubic-bezier(.2,.9,.3,1.2);
          box-shadow:0 12px 40px rgba(0,0,0,.5);z-index:50;display:flex;align-items:center;gap:10px
        }
        .pp-root .toast.show{transform:translateY(0)}
        .pp-root .toast .code{font-family:'JetBrains Mono';background:rgba(0,0,0,.15);padding:2px 8px;border-radius:6px;font-size:12px}

        .pp-root .endpoint{
          font-family:'JetBrains Mono';font-size:11px;color:var(--dim);
          background:var(--panel2);padding:4px 10px;border-radius:6px;border:1px solid var(--line)
        }
        .pp-root .pdfbtn{
          background:var(--besiktas);color:#fff;border:0;padding:9px 16px;border-radius:9px;
          font-weight:800;font-size:13px;font-family:'Archivo';cursor:pointer;
          letter-spacing:0.2px;transition:filter .15s
        }
        .pp-root .pdfbtn:hover{filter:brightness(1.1)}

        @media (max-width:820px){
          .pp-root .topbar{padding:14px 18px;flex-wrap:wrap;gap:10px}
          .pp-root .brand h1{font-size:15px}
          .pp-root .club-pill{font-size:12px;padding:6px 12px}
          .pp-root .club-pill .role{display:none}
          .pp-root .wrap{display:block}
          .pp-root .roster{border-right:0;border-bottom:1px solid var(--line);padding:16px 0 6px}
          .pp-root .roster .lbl{padding:0 18px;margin-bottom:10px}
          .pp-root #roster{display:flex;gap:10px;overflow-x:auto;padding:0 18px 12px;-webkit-overflow-scrolling:touch;scrollbar-width:none}
          .pp-root #roster::-webkit-scrollbar{display:none}
          .pp-root .player{
            flex-direction:column;align-items:flex-start;gap:8px;min-width:140px;padding:14px;
            border-left:0;border:1px solid var(--line);border-radius:12px;border-top:3px solid transparent
          }
          .pp-root .player.active{border-top-color:var(--besiktas)}
          .pp-root .player .topline{display:flex;align-items:center;justify-content:space-between;width:100%}
          .pp-root .player .num{width:auto;font-size:15px}
          .pp-root .main{padding:20px 18px 40px}
          .pp-root .phead{flex-direction:column;align-items:flex-start;gap:12px}
          .pp-root .phead h2{font-size:27px}
          .pp-root .phead .endpoint{font-size:10px;align-self:flex-start}
          .pp-root .grid{grid-template-columns:1fr;gap:16px}
          .pp-root .card{padding:18px;border-radius:14px}
          .pp-root .gauge{flex-direction:column;text-align:center;gap:18px}
          .pp-root .ring{width:120px;height:120px}
          .pp-root .risklabel{width:100%}
          .pp-root .flag{flex-wrap:wrap;gap:6px 10px}
          .pp-root .flag .fname{width:auto}
          .pp-root .flag .fmsg{flex-basis:100%;order:3;color:var(--muted);font-size:12px}
          .pp-root .row{flex-direction:column;gap:13px}
          .pp-root .field select,.pp-root .field input{padding:13px;font-size:16px}
          .pp-root .addbtn{padding:15px;font-size:15px}
          .pp-root .toast{left:18px;right:18px;bottom:18px;justify-content:center}
        }
      ` }} />
    </div>
  );
}
