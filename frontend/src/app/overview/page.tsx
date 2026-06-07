"use client";

/**
 * Genel Bakış — Teknik Ekip Konsolu (FM 3-kolon, tam-ekran).
 * Üst header + sol nav + KPI şeridi + yük-riski tablosu + sağ kolon
 * (sıradaki maç / uyarılar / görevler). Gerçek veri: /physical-tests/players.
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface PlayerRow {
  player_id: string;
  player_name: string;
  test_count: number;
  latest_test_date: string | null;
  risk_label: string;
  risk_score: number;
}

const RISK_VAR: Record<string, string> = {
  Kritik: "var(--crit)",
  Yüksek: "var(--high)",
  Orta: "var(--mid)",
  Düşük: "var(--low)",
};

const TABS = [
  { label: "Genel Bakış", href: "/overview", active: true },
  { label: "Kadro", href: "/squad" },
  { label: "Performans", href: "/physical-tests" },
  { label: "Maç", href: "/matches" },
  { label: "Scout", href: "/scout" },
  { label: "Analiz", href: "/xg" },
];
const NAV = [
  { grp: "Kulüp", items: [
    { ic: "▦", label: "Genel Bakış", href: "/overview", active: true },
    { ic: "👥", label: "Kadro", href: "/squad" },
    { ic: "📋", label: "Performans", href: "/physical-tests" },
    { ic: "🏥", label: "Tıbbi Merkez", href: "/medical" },
  ] },
  { grp: "Analiz", items: [
    { ic: "📈", label: "xG Performans", href: "/xg" },
    { ic: "🎯", label: "TD Performansı", href: "/manager-performance" },
    { ic: "🔍", label: "Rakip & Scout", href: "/scout" },
    { ic: "🤖", label: "AI Asistan", href: "/chat" },
  ] },
  { grp: "Sistem", items: [
    { ic: "💳", label: "Sözleşmeler", href: "/contracts" },
    { ic: "🔔", label: "Bildirimler", href: "/notifications" },
    { ic: "🔒", label: "Erişim Denetimi", href: "/compliance" },
  ] },
];

function condColor(v: number): string {
  return v >= 85 ? "var(--low)" : v >= 72 ? "var(--mid)" : "var(--high)";
}

export default function OverviewConsolePage() {
  const { data } = useSWR<PlayerRow[]>("/physical-tests/players", apiFetch, {
    shouldRetryOnError: false,
  });
  const players = data ?? [];
  const total = players.length;
  const totalTests = players.reduce((a, p) => a + p.test_count, 0);
  const risky = players.filter((p) => p.risk_label === "Yüksek" || p.risk_label === "Kritik").length;
  const ready = players.filter((p) => p.risk_label === "Düşük").length;
  const avgCond = total
    ? Math.round(players.reduce((a, p) => a + (100 - p.risk_score * 100), 0) / total)
    : 0;
  const alerts = players
    .filter((p) => p.risk_label === "Kritik" || p.risk_label === "Yüksek")
    .slice(0, 4);

  const today = new Date().toLocaleDateString("tr-TR", { day: "2-digit", month: "short", year: "numeric" });

  return (
    <div className="ovroot">
      {/* Header */}
      <div className="header">
        <div className="logo"><div className="m">m2</div><b>manager2</b></div>
        <div className="htabs">
          {TABS.map((t) => (
            <Link key={t.href} href={t.href} className={`htab${t.active ? " active" : ""}`}>
              {t.label}
            </Link>
          ))}
        </div>
        <div className="hright">
          <div className="datebox"><span>Teknik Ekip Konsolu</span><b>{today}</b></div>
          <div className="clubchip">
            <div className="badge">B</div>
            <div><div className="cn">Kulüp</div><div className="cr">teknik ekip</div></div>
          </div>
        </div>
      </div>

      <div className="cbody">
        {/* Left nav */}
        <nav className="nav">
          {NAV.map((g) => (
            <React.Fragment key={g.grp}>
              <div className="navgrp">{g.grp}</div>
              {g.items.map((it) => (
                <Link key={it.href} href={it.href} className={`ni${it.active ? " active" : ""}`}>
                  <span className="ic">{it.ic}</span> {it.label}
                  {it.label === "Performans" && risky > 0 && (
                    <span className="badge2">{risky}</span>
                  )}
                </Link>
              ))}
            </React.Fragment>
          ))}
        </nav>

        {/* Center */}
        <main className="center">
          <div className="pgttl"><h1>Genel Bakış</h1><span className="sub">Teknik ekip kontrol paneli</span></div>
          <div className="pgdesc">Kadro durumu ve yük-riski öncelikleri aşağıda. Sayılar canlı veriden.</div>

          <div className="kpis">
            <div className="kpi"><div className="kl">Kadro</div><div className="kn">{total}</div><div className="kd"><span className="u">{ready} hazır</span> · {risky} riskli</div></div>
            <div className="kpi"><div className="kl">Toplam Test</div><div className="kn">{totalTests}</div><div className="kd">{total} oyuncu</div></div>
            <div className="kpi"><div className="kl">Ort. Kondisyon</div><div className="kn">{avgCond}<span className="pct">%</span></div><div className="kd">risk skorundan</div></div>
            <div className="kpi"><div className="kl">Kritik/Yüksek</div><div className="kn" style={{ color: risky ? "var(--high)" : "var(--low)" }}>{risky}</div><div className="kd">acil takip</div></div>
            <div className="kpi"><div className="kl">Hazır</div><div className="kn" style={{ color: "var(--low)" }}>{ready}</div><div className="kd">düşük risk</div></div>
          </div>

          <div className="st"><h2>Yük Riski — Kadro Durumu</h2><span className="ep">GET /physical-tests/players</span></div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th className="c">#</th><th>Oyuncu</th><th className="c">Test</th>
                <th className="c">Kondisyon</th><th className="c">Son Test</th><th className="c">Risk</th><th className="r">Skor</th>
              </tr></thead>
              <tbody>
                {players.length === 0 && (
                  <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                    Veri yok (backend bağlı değilse boş gelir).
                  </td></tr>
                )}
                {players.map((p, i) => {
                  const cond = Math.round(100 - p.risk_score * 100);
                  const rv = RISK_VAR[p.risk_label] ?? "var(--dim)";
                  return (
                    <tr key={p.player_id}>
                      <td className="pnum c">{i + 1}</td>
                      <td><span className="nm">{p.player_name}</span> <span className="nat">#{p.player_id}</span></td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{p.test_count}</td>
                      <td className="c"><span className="cond"><i style={{ width: `${cond}%`, background: condColor(cond) }} /></span></td>
                      <td className="c" style={{ color: "var(--dim)", fontFamily: "JetBrains Mono", fontSize: "11px" }}>{p.latest_test_date ?? "—"}</td>
                      <td className="c"><span className="risk" style={{ color: rv }}><span className="rd" style={{ background: rv, boxShadow: `0 0 7px ${rv}` }} />{p.risk_label}</span></td>
                      <td className="r" style={{ color: rv }}>{Math.round(p.risk_score * 100)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </main>

        {/* Right */}
        <aside className="right">
          <div className="rc">
            <h3>Sıradaki Maç <span className="tiny">— · —</span></h3>
            <div className="nm-vs"><span className="t">BJK</span><span className="x">vs</span><span className="t away">—</span></div>
            <div className="nm-when">Maç verisi için Maçlar sekmesi</div>
            <div className="probbar">
              <i style={{ width: "34%", background: "var(--low)" }} />
              <i style={{ width: "33%", background: "var(--dim)" }} />
              <i style={{ width: "33%", background: "var(--high)" }} />
            </div>
            <div className="probleg">
              <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>—</div><div className="pl">Galibiyet</div></div>
              <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>—</div><div className="pl">Berabere</div></div>
              <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>—</div><div className="pl">Mağlubiyet</div></div>
            </div>
          </div>

          <div className="rc">
            <h3>Uyarılar <span className="tiny">{alerts.length} aktif</span></h3>
            {alerts.length === 0 && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Kritik/yüksek riskli oyuncu yok.</div>}
            {alerts.map((a) => {
              const rv = RISK_VAR[a.risk_label] ?? "var(--dim)";
              return (
                <div className="alrt" key={a.player_id}>
                  <span className="ai" style={{ background: rv }} />
                  <div className="am"><b>{a.player_name}</b> {a.risk_label.toLowerCase()} yük riski.
                    <span className="tm">risk {Math.round(a.risk_score * 100)}/100</span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="rc">
            <h3>Görevler <span className="tiny">{risky ? `0/${risky + 1}` : "0/0"}</span></h3>
            {risky > 0 ? (
              <>
                <div className="task"><span className="cb" /><span className="tt">{risky} riskli oyuncu için kadro kararı</span></div>
                <div className="task"><span className="cb" /><span className="tt">Re-test planı (yüksek risk)</span></div>
              </>
            ) : (
              <div style={{ fontSize: "12px", color: "var(--dim)" }}>Bekleyen görev yok.</div>
            )}
          </div>
        </aside>
      </div>

      <style dangerouslySetInnerHTML={{ __html: CSS }} />
    </div>
  );
}

const CSS = `
.ovroot{
  --bg:#0c0e14;--header:#10131c;--panel:#141823;--panel2:#1a1f2e;--panel3:#212838;
  --line:#262d3d;--line2:#323b4f;--ink:#e8ebf2;--muted:#8b94a8;--dim:#5a6276;
  --besiktas:#e30613;--low:#22c55e;--mid:#eab308;--high:#f97316;--crit:#ef4444;
  --grad:linear-gradient(180deg,#1a1f2e,#141823);
  position:fixed;inset:0;background:var(--bg);color:var(--ink);
  font-family:'Inter',sans-serif;font-size:13px;overflow:hidden;
}
.ovroot .header{height:46px;background:var(--header);border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 16px;gap:20px}
.ovroot .logo{display:flex;align-items:center;gap:10px;padding-right:18px;border-right:1px solid var(--line)}
.ovroot .logo .m{width:28px;height:28px;border-radius:7px;background:linear-gradient(135deg,#fff,#aeb4c2);display:flex;align-items:center;justify-content:center;font-weight:900;color:#0c0e14;font-size:14px}
.ovroot .logo b{font-size:15px;font-weight:800}
.ovroot .htabs{display:flex;gap:2px;height:100%}
.ovroot .htab{display:flex;align-items:center;padding:0 16px;font-size:12.5px;font-weight:600;color:var(--muted);text-decoration:none;border-bottom:2px solid transparent}
.ovroot .htab:hover{color:var(--ink);background:var(--panel)}
.ovroot .htab.active{color:var(--ink);border-bottom-color:var(--besiktas)}
.ovroot .hright{margin-left:auto;display:flex;align-items:center;gap:16px}
.ovroot .datebox{text-align:right;font-size:11px;color:var(--dim);line-height:1.3}
.ovroot .datebox b{display:block;color:var(--ink);font-size:12.5px;font-weight:700;font-family:'JetBrains Mono'}
.ovroot .clubchip{display:flex;align-items:center;gap:9px;background:var(--panel);border:1px solid var(--line);padding:5px 12px;border-radius:7px}
.ovroot .clubchip .badge{width:22px;height:22px;border-radius:5px;background:var(--besiktas);display:flex;align-items:center;justify-content:center;font-weight:900;font-size:11px;color:#fff}
.ovroot .clubchip .cn{font-size:12px;font-weight:700;line-height:1.2}
.ovroot .clubchip .cr{font-size:10px;color:var(--dim)}
.ovroot .cbody{display:grid;grid-template-columns:208px 1fr 300px;height:calc(100vh - 46px)}
.ovroot .nav{background:var(--header);border-right:1px solid var(--line);overflow-y:auto;padding:10px 0}
.ovroot .navgrp{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:var(--dim);padding:14px 16px 6px}
.ovroot .ni{display:flex;align-items:center;gap:11px;padding:8px 16px;color:var(--muted);font-size:13px;font-weight:500;text-decoration:none;border-left:2px solid transparent}
.ovroot .ni:hover{background:var(--panel);color:var(--ink)}
.ovroot .ni.active{background:var(--panel);color:var(--ink);border-left-color:var(--besiktas);font-weight:600}
.ovroot .ni .ic{width:16px;text-align:center;font-size:13px}
.ovroot .ni .badge2{margin-left:auto;background:var(--crit);color:#fff;font-size:10px;font-weight:700;padding:1px 6px;border-radius:9px;font-family:'JetBrains Mono'}
.ovroot .center{overflow-y:auto;padding:16px 18px}
.ovroot .pgttl{display:flex;align-items:baseline;gap:12px;margin-bottom:4px}
.ovroot .pgttl h1{font-size:20px;font-weight:800}
.ovroot .pgttl .sub{font-size:12px;color:var(--dim)}
.ovroot .pgdesc{font-size:12px;color:var(--muted);margin-bottom:16px}
.ovroot .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:18px}
.ovroot .kpi{background:var(--grad);border:1px solid var(--line);border-radius:9px;padding:13px 14px}
.ovroot .kpi .kl{font-size:10.5px;text-transform:uppercase;letter-spacing:0.8px;color:var(--muted);font-weight:600;margin-bottom:8px}
.ovroot .kpi .kn{font-size:26px;font-weight:800;font-family:'JetBrains Mono';line-height:1}
.ovroot .kpi .kn .pct{font-size:14px;color:var(--dim)}
.ovroot .kpi .kd{font-size:10.5px;color:var(--dim);margin-top:6px}
.ovroot .kpi .kd .u{color:var(--low)}
.ovroot .st{display:flex;align-items:center;justify-content:space-between;margin:18px 0 11px}
.ovroot .st h2{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--ink);display:flex;align-items:center;gap:9px}
.ovroot .st h2::before{content:'';width:3px;height:13px;background:var(--besiktas);border-radius:2px}
.ovroot .st .ep{font-family:'JetBrains Mono';font-size:10.5px;color:var(--dim);background:var(--panel);border:1px solid var(--line);padding:3px 9px;border-radius:5px}
.ovroot .tbl{background:var(--panel);border:1px solid var(--line);border-radius:9px;overflow:hidden}
.ovroot table{width:100%;border-collapse:collapse;font-size:12.5px}
.ovroot thead th{background:var(--panel2);text-align:left;padding:8px 11px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;color:var(--muted);border-bottom:1px solid var(--line)}
.ovroot thead th.c{text-align:center}.ovroot thead th.r{text-align:right}
.ovroot tbody td{padding:8px 11px;border-bottom:1px solid rgba(38,45,61,0.5)}
.ovroot tbody tr:last-child td{border:0}
.ovroot tbody tr:hover{background:var(--panel2)}
.ovroot td.c{text-align:center}.ovroot td.r{text-align:right;font-family:'JetBrains Mono';font-weight:600}
.ovroot .pnum{font-family:'JetBrains Mono';color:var(--dim);font-weight:700}
.ovroot .nm{font-weight:600}
.ovroot .nat{color:var(--dim);font-size:11px;font-family:'JetBrains Mono'}
.ovroot .risk{display:inline-flex;align-items:center;gap:6px;font-weight:700;font-family:'JetBrains Mono';font-size:12px}
.ovroot .risk .rd{width:8px;height:8px;border-radius:50%}
.ovroot .cond{display:inline-block;width:60px;height:7px;border-radius:4px;background:var(--panel3);overflow:hidden;vertical-align:middle}
.ovroot .cond i{display:block;height:100%}
.ovroot .right{background:var(--header);border-left:1px solid var(--line);overflow-y:auto;padding:14px}
.ovroot .rc{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:14px;margin-bottom:12px}
.ovroot .rc h3{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:12px;display:flex;align-items:center;justify-content:space-between}
.ovroot .rc h3 .tiny{font-size:10px;color:var(--dim);font-weight:500;font-family:'JetBrains Mono'}
.ovroot .nm-vs{display:flex;align-items:center;justify-content:center;gap:14px;margin:6px 0 4px}
.ovroot .nm-vs .t{font-size:16px;font-weight:800}
.ovroot .nm-vs .t.away{color:var(--muted)}
.ovroot .nm-vs .x{font-family:'JetBrains Mono';color:var(--dim);font-size:12px}
.ovroot .nm-when{text-align:center;font-size:11px;color:var(--dim);margin-bottom:14px}
.ovroot .probbar{height:8px;border-radius:4px;background:var(--panel3);display:flex;overflow:hidden;margin-bottom:10px}
.ovroot .probbar i{display:block;height:100%}
.ovroot .probleg{display:flex;justify-content:space-between}
.ovroot .probleg .pi{text-align:center;flex:1}
.ovroot .probleg .pv{font-family:'JetBrains Mono';font-weight:700;font-size:15px}
.ovroot .probleg .pl{font-size:9.5px;text-transform:uppercase;letter-spacing:0.5px;color:var(--dim);margin-top:2px}
.ovroot .alrt{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid rgba(38,45,61,0.5);font-size:12px}
.ovroot .alrt:last-child{border:0;padding-bottom:0}
.ovroot .alrt .ai{width:7px;height:7px;border-radius:50%;margin-top:5px;flex-shrink:0}
.ovroot .alrt .am{line-height:1.4}
.ovroot .alrt .am .tm{display:block;font-size:10px;color:var(--dim);margin-top:2px;font-family:'JetBrains Mono'}
.ovroot .task{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid rgba(38,45,61,0.5);font-size:12.5px}
.ovroot .task:last-child{border:0}
.ovroot .task .cb{width:15px;height:15px;border-radius:4px;border:1.5px solid var(--line2);flex-shrink:0}
.ovroot .task .tt{flex:1}
.ovroot .tbl{overflow-x:auto}
.ovroot .htabs{overflow-x:auto;-webkit-overflow-scrolling:touch}
.ovroot .htabs::-webkit-scrollbar{display:none}
/* Tablet (yatay): kolonları daralt, KPI 3'lü */
@media (max-width:1200px){
  .ovroot .cbody{grid-template-columns:172px 1fr 248px}
  .ovroot .kpis{grid-template-columns:repeat(3,1fr)}
}
/* Telefon (yatay) / dar: tek kolon — sol nav gizli, sağ widget'lar altta */
@media (max-width:900px){
  .ovroot .cbody{display:block;overflow-y:auto;height:calc(100vh - 46px)}
  .ovroot .nav{display:none}
  .ovroot .center{height:auto;overflow:visible;padding:14px}
  .ovroot .right{border-left:0;border-top:1px solid var(--line);overflow:visible}
  .ovroot .kpis{grid-template-columns:repeat(2,1fr)}
  .ovroot .kpi .kn{font-size:22px}
  .ovroot .pgttl h1{font-size:18px}
  .ovroot .htab{padding:0 12px;font-size:12px}
  .ovroot .datebox{display:none}
}
@media (max-width:560px){
  .ovroot .kpis{grid-template-columns:repeat(2,1fr)}
  .ovroot .logo b{display:none}
}
`;
