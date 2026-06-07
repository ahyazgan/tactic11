"use client";

/**
 * ConsoleShell — Teknik Ekip Konsolu çatısı (FM 3-kolon, tam-ekran).
 * Tüm konsol ekranları (Genel Bakış, Kadro, Performans, Analiz, Scout)
 * bu shell'i kullanır → tutarlı header + sol nav + sağ kolon + tema.
 * Sayfalar yalnızca orta içeriği (children) ve sağ kolonu (right) verir.
 */

import * as React from "react";
import Link from "next/link";

const TABS = [
  { label: "Genel Bakış", href: "/overview" },
  { label: "Kadro", href: "/squad" },
  { label: "Performans", href: "/physical-tests" },
  { label: "Maç", href: "/matches" },
  { label: "Scout", href: "/scout" },
  { label: "Analiz", href: "/xg" },
];

const NAV = [
  { grp: "Kulüp", items: [
    { ic: "▦", label: "Genel Bakış", href: "/overview" },
    { ic: "👥", label: "Kadro", href: "/squad" },
    { ic: "📋", label: "Performans", href: "/physical-tests" },
    { ic: "🏥", label: "Tıbbi Merkez", href: "/medical" },
    { ic: "🏃", label: "Antrenman", href: "/training" },
    { ic: "📝", label: "Maç Planı", href: "/match-plan" },
  ] },
  { grp: "Analiz", items: [
    { ic: "📈", label: "xG Performans", href: "/xg" },
    { ic: "🎯", label: "TD Performansı", href: "/manager-performance" },
    { ic: "🔍", label: "Rakip & Scout", href: "/scout" },
    { ic: "🤖", label: "AI Asistan", href: "/chat" },
  ] },
  { grp: "Maç & Veri", items: [
    { ic: "🆚", label: "Rakip Raporu", href: "/opponent" },
    { ic: "⚔️", label: "Kafa Kafaya", href: "/h2h" },
    { ic: "🏆", label: "Ligler", href: "/leagues" },
    { ic: "👔", label: "Takımlar", href: "/teams" },
    { ic: "🧠", label: "Kararlar", href: "/decisions" },
  ] },
  { grp: "Sistem", items: [
    { ic: "💳", label: "Sözleşmeler", href: "/contracts" },
    { ic: "🔔", label: "Bildirimler", href: "/notifications" },
    { ic: "🔒", label: "Erişim Denetimi", href: "/compliance" },
  ] },
];

export interface ConsoleShellProps {
  /** Aktif ekranın href'i (tab + nav vurgusu). Örn: "/squad" */
  active: string;
  title: string;
  sub?: string;
  desc?: string;
  /** "Performans" nav öğesindeki riskli-sayı rozeti. */
  navBadge?: number;
  /** Sağ kolon içeriği. */
  right?: React.ReactNode;
  /** Orta içerik (başlık/desc altı). */
  children: React.ReactNode;
}

export function ConsoleShell({ active, title, sub, desc, navBadge, right, children }: ConsoleShellProps) {
  const today = new Date().toLocaleDateString("tr-TR", { day: "2-digit", month: "short", year: "numeric" });

  return (
    <div className="ovroot">
      {/* Header */}
      <div className="header">
        <div className="logo"><div className="m">m2</div><b>manager2</b></div>
        <div className="htabs">
          {TABS.map((t) => (
            <Link key={t.href} href={t.href} className={`htab${t.href === active ? " active" : ""}`}>
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
                <Link key={it.href} href={it.href} className={`ni${it.href === active ? " active" : ""}`}>
                  <span className="ic">{it.ic}</span> {it.label}
                  {it.label === "Performans" && navBadge != null && navBadge > 0 && (
                    <span className="badge2">{navBadge}</span>
                  )}
                </Link>
              ))}
            </React.Fragment>
          ))}
        </nav>

        {/* Center */}
        <main className="center">
          <div className="pgttl"><h1>{title}</h1>{sub && <span className="sub">{sub}</span>}</div>
          {desc && <div className="pgdesc">{desc}</div>}
          {children}
        </main>

        {/* Right */}
        <aside className="right">{right}</aside>
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
/* Segment kontrol (filtreler) */
.ovroot .seg{display:inline-flex;background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:2px;gap:2px}
.ovroot .seg button{background:transparent;border:0;color:var(--muted);font-size:11.5px;font-weight:600;padding:5px 11px;border-radius:5px;cursor:pointer;font-family:inherit}
.ovroot .seg button.on{background:var(--panel3);color:var(--ink)}
/* Pozisyon rozeti */
.ovroot .pos{display:inline-flex;align-items:center;justify-content:center;min-width:30px;padding:2px 6px;border-radius:5px;font-size:10.5px;font-weight:700;font-family:'JetBrains Mono';background:var(--panel3);color:var(--muted)}
/* Genel istatistik satırı (sağ kolon) */
.ovroot .stat{display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px solid rgba(38,45,61,0.5);font-size:12.5px}
.ovroot .stat:last-child{border:0}
.ovroot .stat .sv{font-family:'JetBrains Mono';font-weight:700}
/* Mini bar (sağ kolon dağılımları) */
.ovroot .mbar{height:7px;border-radius:4px;background:var(--panel3);overflow:hidden;margin:4px 0 10px}
.ovroot .mbar i{display:block;height:100%}
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
