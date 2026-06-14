"use client";

/**
 * ConsoleShell — FM26 Açık Tema
 * Tile & Card sistemi, üstte navbar, sol ince sidebar, beyaz yüzeyler.
 * Inter font, 8-12px border-radius, pill badge'ler, temiz boşluk.
 *
 * DEMO_MODE: navbar + sidebar maçın ritmine göre sadeleşir (Maç Öncesi / Maç Günü
 * / Asistan), kulüp "Beşiktaş" olur. DEMO kapalı: tam navigasyon geri gelir.
 *
 * NOT: Sayfalar eski değişken adlarını (--panel/--line/--header/--grad ...) hâlâ
 * kullanıyor; aşağıdaki .ovroot bloğunda yeni FM26 paletine alias'lanır.
 */

import * as React from "react";
import Link from "next/link";

import { DEMO_MODE } from "@/lib/demo-mode";
import { DataSourceStrip, type SourceId } from "@/lib/data-source";
import { Crest } from "@/lib/teams";
import { demoLive } from "@/lib/demo-data";

// Demo: canlı maç ekranına markasız sabit hedef (id "demo" → sayfa mock gösterir).
const DEMO_LIVE_HREF = "/matches/demo/live";

const FULL_BTABS = [
  { ic: "ti-home",             label: "Portal",  href: "/overview" },
  { ic: "ti-users",            label: "Kadro",   href: "/squad" },
  { ic: "ti-activity",         label: "Perf",    href: "/physical-tests" },
  { ic: "ti-ball-football",    label: "Maç",     href: "/matches" },
  { ic: "ti-search",           label: "Scout",   href: "/scout" },
];

const BTABS = FULL_BTABS;

// Yapı, kullanıcının "Yardımcı Antrenör" menü mockup'ından (IA) alındı; görsel
// dil mevcut FM26 açık temasıdır. Rozetler: live (CANLI), new (YENİ), ai (AI),
// count (sayı). "Fiziksel Durum" sayısı dinamik (navBadge prop'u) ile dolar.
type BadgeKind = "live" | "new" | "ai" | "count";
interface NavItem { label: string; href: string; icon: string; badge?: string | number; badgeKind?: BadgeKind }
interface NavGroup { grp: string; items: NavItem[] }

const FULL_NAV: NavGroup[] = [
  { grp: "Genel", items: [
    { label: "Komuta Merkezi", href: "/command",       icon: "ti-brain", badge: "AI", badgeKind: "ai" },
    { label: "Kontrol Paneli", href: "/overview",      icon: "ti-layout-dashboard" },
    { label: "Canlı Maç",      href: DEMO_LIVE_HREF,    icon: "ti-ball-football", badge: "CANLI", badgeKind: "live" },
  ]},
  { grp: "Takım", items: [
    { label: "Kadro",            href: "/squad",          icon: "ti-users" },
    { label: "Fiziksel Durum",   href: "/physical-tests", icon: "ti-activity" },
    { label: "Test Hesaplayıcı", href: "/physical-tests/derive", icon: "ti-calculator" },
    { label: "Sakatlık & Sağlık",href: "/medical",        icon: "ti-heart-rate-monitor" },
    { label: "Yük Takibi",       href: "/workload",       icon: "ti-chart-area-line" },
  ]},
  { grp: "Maç & Taktik", items: [
    { label: "Fikstür",          href: "/matches",        icon: "ti-calendar-event" },
    { label: "Maç Öncesi Plan",  href: "/match-plan",     icon: "ti-clipboard-list" },
    { label: "Rakip Analizi",    href: "/opponent",       icon: "ti-file-analytics" },
    { label: "Taktik Tahtası",   href: "/tactics-board",  icon: "ti-soccer-field", badge: "YENİ", badgeKind: "new" },
  ]},
  { grp: "Antrenman", items: [
    { label: "Antrenman Planı",  href: "/training",       icon: "ti-run" },
    { label: "Yoklama",          href: "/attendance",     icon: "ti-checklist" },
  ]},
  { grp: "Keşif & Transfer", items: [
    { label: "Oyuncu Keşif",     href: "/scout",          icon: "ti-binoculars" },
    { label: "Skaut Raporları",  href: "/scout-reports",  icon: "ti-file-text" },
    { label: "Transfer",         href: "/transfer",       icon: "ti-arrows-exchange" },
  ]},
  { grp: "Raporlar & AI", items: [
    { label: "Performans Analizi", href: "/xg",           icon: "ti-chart-line" },
    { label: "Haftalık Rapor",     href: "/weekly-report",icon: "ti-report-analytics" },
    { label: "AI Asistan",         href: "/chat",         icon: "ti-robot", badge: "AI", badgeKind: "ai" },
  ]},
  // "Diğer" — mockup IA'sında olmayan ama mevcut (eski) sayfalar; URL'leri korunur.
  { grp: "Diğer", items: [
    { label: "Kararlar",            href: "/decisions",           icon: "ti-brain" },
    { label: "Maç-içi Karar",       href: "/decisions/live",      icon: "ti-bolt" },
    { label: "Karar Takip",         href: "/decisions/track",     icon: "ti-chart-histogram" },
    { label: "Kafa Kafaya",         href: "/h2h",                 icon: "ti-swords" },
    { label: "Ligler",              href: "/leagues",             icon: "ti-trophy" },
    { label: "Takımlar",            href: "/teams",               icon: "ti-shield" },
    { label: "Sözleşmeler",         href: "/contracts",           icon: "ti-file-text" },
    { label: "TD Performansı",      href: "/manager-performance", icon: "ti-target" },
    { label: "Veri Girişi & Batarya",href: "/performance",        icon: "ti-clipboard-data" },
  ]},
  { grp: "Sistem", items: [
    { label: "Bildirimler",    href: "/notifications", icon: "ti-bell", badge: 5, badgeKind: "count" },
    { label: "Erişim Denetimi",href: "/compliance",    icon: "ti-lock" },
    { label: "Kalibrasyon",    href: "/calibration",   icon: "ti-adjustments" },
    { label: "Ayarlar",        href: "/admin",         icon: "ti-settings" },
  ]},
];

const NAV = FULL_NAV;

export interface ConsoleShellProps {
  active: string;
  title: string;
  sub?: string;
  desc?: string;
  navBadge?: number;
  /** Bu sayfanın verisini hangi kaynak(lar)dan aldığını başlık altında işaretler. */
  source?: SourceId | SourceId[];
  right?: React.ReactNode;
  children: React.ReactNode;
}

export function ConsoleShell({
  active, title, sub, desc, navBadge, source, right, children,
}: ConsoleShellProps) {
  // Tablet/mobil: sidebar çekmece (drawer) olarak açılır.
  const [menuOpen, setMenuOpen] = React.useState(false);

  return (
    <div className={`ovroot${DEMO_MODE ? " demo" : ""}${menuOpen ? " nav-open" : ""}`}>

      {/* ── FM26 Navbar ── */}
      <header className="navbar">
        <button
          type="button"
          className="menu-btn"
          aria-label={menuOpen ? "Menüyü kapat" : "Menüyü aç"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
        >
          <i className={`ti ${menuOpen ? "ti-x" : "ti-menu-2"}`} aria-hidden="true" />
        </button>
        <div className="logo">
          {/* tactic11 yatay logo — "Taktik Oku" (logo-onizleme #5). Inline SVG:
              sayfa fontunu ve tema renklerini (--ink/--accent) otomatik alır. */}
          <svg
            viewBox="0 0 178 48"
            role="img"
            aria-label="tactic11"
            style={{ height: 32, width: "auto", display: "block" }}
          >
            <text
              x="4" y="29"
              fontFamily="Inter,'Segoe UI',sans-serif"
              fontSize="27" fontWeight="800" letterSpacing="-1.2"
            >
              <tspan fill="var(--ink)">tactic</tspan>
              <tspan fill="var(--accent)">11</tspan>
            </text>
            <circle cx="8" cy="40" r="3" fill="var(--accent)" />
            <path
              d="M8 40 C 40 33, 100 47, 148 38"
              stroke="var(--accent)" strokeWidth="2.4"
              strokeDasharray="6 4.5" strokeLinecap="round" fill="none"
            />
            <polygon points="158,35.5 146,33.5 148.5,42.5" fill="var(--accent)" />
          </svg>
        </div>

        <div className="nav-right">
          {DEMO_MODE && (
            <Link href={DEMO_LIVE_HREF} className="live-strip" title={`Canlı maç — konsola git`}>
              <span className="ls-dot" aria-hidden="true" />
              <span className="ls-tag">CANLI</span>
              <Crest team={demoLive.home} size={18} />
              <span className="ls-score">{demoLive.score[0]}–{demoLive.score[1]}</span>
              <Crest team={demoLive.away} size={18} />
              <span className="ls-min">{demoLive.minute}&apos;</span>
            </Link>
          )}
        </div>
      </header>

      {/* Çekmece açıkken arka plan karartması (tıklayınca kapanır) */}
      {menuOpen && <div className="nav-backdrop" onClick={() => setMenuOpen(false)} aria-hidden="true" />}

      {/* ── Gövde ── */}
      <div className="cbody">

        {/* Sol Sidebar */}
        <div className="sidebar-wrap" onClick={(e) => {
          // Çekmece modunda bir linke dokununca menüyü kapat.
          if ((e.target as HTMLElement).closest("a")) setMenuOpen(false);
        }}>
          <SidebarNav active={active} navBadge={navBadge} />
        </div>

        {/* Orta */}
        <main className="center">
          <div className="pghdr">
            <div className="pgttl">
              <h1>{title}</h1>
              {sub && <span className="pg-badge">{sub}</span>}
            </div>
            {desc && <p className="pgdesc">{desc}</p>}
            {source && <DataSourceStrip sources={source} />}
          </div>
          {children}
        </main>

        {/* Sağ */}
        <aside className="right">{right}</aside>
      </div>

      {/* Mobil alt bar */}
      <nav className="btabs" aria-label="Mobil navigasyon">
        {BTABS.map((t) => (
          <Link key={t.href} href={t.href} className={`btab${t.href === active ? " active" : ""}`}>
            <i className={`ti ${t.ic} bi`} aria-hidden="true" />
            {t.label}
          </Link>
        ))}
      </nav>

      <style dangerouslySetInnerHTML={{ __html: CSS }} />
    </div>
  );
}

/* ─────────────────────────────────────────────
   Sol sidebar — açılır/kapanır gruplar
   Kapalı gruplar localStorage'da tutulur; aktif öğe içeren grup daima açık.
───────────────────────────────────────────── */
const SIDEBAR_COLLAPSE_KEY = "manager2_console_sidebar_collapsed";

function SidebarNav({ active, navBadge }: { active: string; navBadge?: number }) {
  const [collapsed, setCollapsed] = React.useState<Set<string>>(new Set());

  React.useEffect(() => {
    try {
      const saved = window.localStorage.getItem(SIDEBAR_COLLAPSE_KEY);
      if (saved) setCollapsed(new Set(JSON.parse(saved) as string[]));
    } catch {
      /* yok say */
    }
  }, []);

  const toggle = React.useCallback((grp: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(grp)) next.delete(grp);
      else next.add(grp);
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSE_KEY, JSON.stringify([...next]));
      } catch {
        /* yok say */
      }
      return next;
    });
  }, []);

  return (
    <nav className="sidebar" aria-label="Yan navigasyon">
      {NAV.map((g) => {
        const hasActive = g.items.some((it) => it.href === active);
        // Aktif sayfa içeren grup, kullanıcı kapatmış olsa da açık kalır.
        const open = !collapsed.has(g.grp) || hasActive;
        return (
          <React.Fragment key={g.grp}>
            <button
              type="button"
              className="sgrp"
              aria-expanded={open}
              onClick={() => toggle(g.grp)}
            >
              <span>{g.grp}</span>
              <i className={`ti ti-chevron-down sgrp-chev${open ? "" : " closed"}`} aria-hidden="true" />
            </button>
            {open &&
              g.items.map((it) => (
                <Link
                  key={it.href}
                  href={it.href}
                  className={`sni${it.href === active ? " active" : ""}`}
                >
                  <i className={`ti ${it.icon}`} aria-hidden="true" />
                  <span className="sni-label">{it.label}</span>
                  {it.badge != null && (
                    <span className={`nbadge ${it.badgeKind ?? "count"}`}>{it.badge}</span>
                  )}
                  {it.label === "Fiziksel Durum" && navBadge != null && navBadge > 0 && (
                    <span className="nbadge count">{navBadge}</span>
                  )}
                </Link>
              ))}
          </React.Fragment>
        );
      })}
    </nav>
  );
}

/* ─────────────────────────────────────────────
   FM26 AÇIK TEMA — CSS
───────────────────────────────────────────── */
const CSS = `
.ovroot{
  /* ADAÇAYI & KOYU YEŞİL TEMA (önizleme #14) — açık yeşilimsi zemin,
     beyaz kartlar, koyu yeşil vurgu. */
  --white:#ffffff;
  --bg:#eaf0ea;
  --surface:#f7faf7;
  --surface2:#e1eae1;
  --border:#d5e0d5;
  --border2:#bccdbc;
  --ink:#1b261e;
  --muted:#53635a;
  --dim:#86978c;
  --accent:#1e6b41;
  --accent-lt:#d8ecdd;
  --accent-dk:#1a5d39;
  --low:#1e6b41;--low-bg:#d8ecdd;
  --mid:#ad7a14;--mid-bg:#f3e9cc;
  --high:#c2410c;--high-bg:#f8e0cf;
  --crit:#bb2d26;--crit-bg:#f7dedb;
  --besiktas:#e30613;
  /* Geriye-uyum alias'ları — sayfalar bu eski adları kullanıyor. */
  --panel:#ffffff;--panel2:#e1eae1;--panel3:#d3e0d3;
  --line:#d5e0d5;--line2:#bccdbc;
  --header:#ffffff;--grad:linear-gradient(180deg,#ffffff,#eaf0ea);
  position:fixed;inset:0;
  background:var(--bg);color:var(--ink);
  font-family:'Inter','Segoe UI',system-ui,sans-serif;
  font-size:13px;overflow:hidden;
}
/* ── NAVBAR ── */
.ovroot .navbar{
  height:50px;
  background:var(--white);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;
  padding:0 16px;gap:0;flex-shrink:0;
  position:relative;z-index:10;
}
/* Hamburger — yalnız tablet/mobilde görünür */
.ovroot .menu-btn{
  display:none;align-items:center;justify-content:center;
  width:40px;height:40px;margin-right:6px;flex-shrink:0;
  background:transparent;border:1px solid transparent;border-radius:10px;
  color:var(--ink);font-size:21px;cursor:pointer;
  transition:background .12s,border-color .12s;
}
.ovroot .menu-btn:hover{background:var(--surface2);border-color:var(--border)}
.ovroot .menu-btn:active{transform:scale(.94)}

/* Çekmece karartması */
.ovroot .nav-backdrop{
  display:none;position:fixed;inset:50px 0 0 0;z-index:60;
  background:rgba(0,0,0,.45);
  animation:fadeIn .2s ease both;
}

.ovroot .sidebar-wrap{display:contents}

.ovroot .logo{display:flex;align-items:center;margin-right:24px;flex-shrink:0}

/* Nav tabs */
.ovroot .nav-tabs{display:flex;gap:2px;height:100%;align-items:center;overflow-x:auto}
.ovroot .nav-tabs::-webkit-scrollbar{display:none}
.ovroot .ntab{
  display:flex;align-items:center;gap:6px;white-space:nowrap;
  padding:7px 13px;border-radius:9px;
  font-size:13px;font-weight:500;color:var(--muted);
  text-decoration:none;
  transition:background .1s,color .1s;
}
.ovroot .ntab i{font-size:16px;line-height:1}
.ovroot .ntab:hover{background:var(--surface2);color:var(--ink)}
.ovroot .ntab.active{background:var(--accent-lt);color:var(--accent);font-weight:600}

/* Sağ araçlar */
.ovroot .nav-right{margin-left:auto;display:flex;align-items:center;gap:10px}

/* Canlı maç şeridi (FM26 stili, sağ üst) */
.ovroot .live-strip{
  display:flex;align-items:center;gap:7px;
  background:var(--crit-bg);border:1px solid #fca5a5;
  border-radius:20px;padding:4px 12px 4px 10px;
  text-decoration:none;cursor:pointer;
  transition:border-color .12s,box-shadow .12s;
}
.ovroot .live-strip:hover{border-color:var(--crit);box-shadow:0 2px 8px rgba(220,38,38,.18)}
.ovroot .live-strip:focus-visible{outline:2px solid var(--crit);outline-offset:2px}
.ovroot .ls-dot{
  width:7px;height:7px;border-radius:50%;background:var(--crit);flex-shrink:0;
  box-shadow:0 0 0 0 rgba(220,38,38,.5);animation:ls-pulse 1.6s ease-out infinite;
}
@keyframes ls-pulse{
  0%{box-shadow:0 0 0 0 rgba(220,38,38,.5)}
  70%{box-shadow:0 0 0 6px rgba(220,38,38,0)}
  100%{box-shadow:0 0 0 0 rgba(220,38,38,0)}
}
.ovroot .ls-tag{
  font-size:9.5px;font-weight:800;letter-spacing:.5px;color:var(--crit);
  text-transform:uppercase;
}
.ovroot .ls-score{font-size:13px;font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums}
.ovroot .ls-min{font-size:11px;font-weight:700;color:var(--crit);font-variant-numeric:tabular-nums;margin-left:1px}
/* Dar ekranda küçült: sadece nokta + skor + dk kalsın */
@media (max-width:760px){
  .ovroot .live-strip .ls-tag{display:none}
}
.ovroot .datebox{font-size:12px;color:var(--dim);font-variant-numeric:tabular-nums}

/* ── GÖVDE ── */
.ovroot .cbody{
  display:grid;
  grid-template-columns:200px 1fr 296px;
  height:calc(100vh - 50px);
}

/* ── SIDEBAR ── */
.ovroot .sidebar{
  background:var(--white);
  border-right:1px solid var(--border);
  overflow-y:auto;padding:10px 8px;
}
.ovroot .sidebar::-webkit-scrollbar{width:4px}
.ovroot .sidebar::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}

.ovroot .sgrp{
  display:flex;align-items:center;justify-content:space-between;
  width:100%;
  font-size:10.5px;font-weight:600;
  text-transform:uppercase;letter-spacing:1px;
  color:var(--dim);
  padding:14px 10px 5px;
  background:transparent;border:0;
  font-family:inherit;cursor:pointer;
  transition:color .08s;
}
.ovroot .sgrp:hover{color:var(--muted)}
.ovroot .sgrp:first-child{padding-top:5px}
.ovroot .sgrp-chev{
  font-size:14px;line-height:1;
  transition:transform .15s ease;
}
.ovroot .sgrp-chev.closed{transform:rotate(-90deg)}

.ovroot .sni{
  display:flex;align-items:center;gap:9px;
  padding:7px 10px;border-radius:8px;
  font-size:12.5px;font-weight:500;color:var(--muted);
  text-decoration:none;
  transition:background .08s,color .08s;
}
.ovroot .sni i{font-size:16px;flex-shrink:0;line-height:1}
.ovroot .sni:hover{background:var(--surface2);color:var(--ink)}
.ovroot .sni.active{background:var(--accent-lt);color:var(--accent);font-weight:600}
.ovroot .sni-label{flex:1}
.ovroot .sbadge{
  background:var(--crit);color:#fff;
  font-size:10.5px;font-weight:700;
  padding:2px 6px;border-radius:10px;
  min-width:20px;text-align:center;
}
/* Nav rozetleri (mockup IA): live / new / ai / count */
.ovroot .nbadge{
  margin-left:auto;flex-shrink:0;
  font-size:9.5px;font-weight:700;letter-spacing:.4px;
  padding:2px 7px;border-radius:20px;line-height:1.5;
}
.ovroot .nbadge.live{background:var(--low-bg);color:var(--low);text-transform:uppercase}
.ovroot .nbadge.new{background:var(--accent-lt);color:var(--accent);text-transform:uppercase}
.ovroot .nbadge.ai{background:#e6efff;color:#2563eb;letter-spacing:.6px}
.ovroot .nbadge.count{
  background:var(--mid-bg);color:var(--mid);
  min-width:18px;text-align:center;padding:2px 6px;border-radius:10px;
}

/* ── ORTA ── */
.ovroot .center{overflow-y:auto;padding:18px 20px;background:var(--bg)}
.ovroot .center::-webkit-scrollbar{width:4px}
.ovroot .center::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}

.ovroot .pghdr{margin-bottom:18px}
.ovroot .pgttl{display:flex;align-items:center;gap:10px;margin-bottom:5px}
.ovroot .pgttl h1{font-size:22px;font-weight:700;color:var(--ink);letter-spacing:-0.5px}
.ovroot .pg-badge{
  background:var(--accent-lt);color:var(--accent);
  font-size:11.5px;font-weight:600;
  padding:3px 10px;border-radius:20px;
}
.ovroot .pgdesc{font-size:12.5px;color:var(--muted);margin:0}

/* Tile Grid — KPI kartları */
.ovroot .kpis{
  display:grid;grid-template-columns:repeat(5,1fr);
  gap:10px;margin-bottom:16px;
}
.ovroot .kpi{
  background:var(--white);
  border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;
  transition:border-color .1s,box-shadow .1s;
  cursor:default;
}
.ovroot .kpi:hover{border-color:var(--border2);box-shadow:0 2px 8px rgba(0,0,0,.05)}
.ovroot .kpi .kl{
  font-size:11px;font-weight:600;
  text-transform:uppercase;letter-spacing:.5px;
  color:var(--dim);margin-bottom:8px;
}
.ovroot .kpi .kn{
  font-size:26px;font-weight:700;color:var(--ink);
  letter-spacing:-1px;line-height:1;
  font-variant-numeric:tabular-nums;
}
.ovroot .kpi .kn .pct{font-size:15px;color:var(--dim);font-weight:500}
.ovroot .kpi .kd{font-size:11.5px;color:var(--dim);margin-top:6px}
.ovroot .kpi .kd .u{color:var(--low);font-weight:600}

/* Card container */
.ovroot .st{display:flex;align-items:center;justify-content:space-between;margin:18px 0 10px}
.ovroot .st h2{font-size:14px;font-weight:600;color:var(--ink)}
.ovroot .st .ep{
  font-size:11.5px;color:var(--dim);
  background:var(--surface2);border:1px solid var(--border);
  padding:4px 10px;border-radius:20px;
}
.ovroot .tbl{
  background:var(--white);border:1px solid var(--border);
  border-radius:12px;overflow-x:auto;-webkit-overflow-scrolling:touch;
}
.ovroot table{width:100%;border-collapse:collapse;font-size:12.5px}
.ovroot thead th{
  background:var(--surface2);
  text-align:left;padding:9px 14px;
  font-size:11px;font-weight:600;color:var(--muted);
  text-transform:uppercase;letter-spacing:.4px;
  border-bottom:1px solid var(--border);
}
.ovroot thead th.c{text-align:center}
.ovroot thead th.r{text-align:right}
.ovroot tbody td{padding:10px 14px;border-bottom:1px solid var(--border)}
.ovroot tbody tr:last-child td{border:0}
.ovroot tbody tr:hover td{background:var(--surface2)}
.ovroot td.c{text-align:center}
.ovroot td.r{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.ovroot .pnum{font-variant-numeric:tabular-nums;color:var(--dim);font-weight:600}
.ovroot .nm{font-weight:600}
.ovroot .nat{color:var(--dim);font-size:11px}

/* Pill badge */
.ovroot .risk{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:20px;font-size:11.5px;font-weight:600}
.ovroot .risk .rd{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.ovroot .risk-low{background:var(--low-bg);color:var(--low)}
.ovroot .risk-mid{background:var(--mid-bg);color:var(--mid)}
.ovroot .risk-high{background:var(--high-bg);color:var(--high)}
.ovroot .risk-crit{background:var(--crit-bg);color:var(--crit)}

/* Kondisyon bar */
.ovroot .cond{display:inline-block;width:52px;height:5px;border-radius:3px;background:var(--border);overflow:hidden;vertical-align:middle}
.ovroot .cond i{display:block;height:100%;border-radius:3px}

/* ── SAĞ KOLON ── */
.ovroot .right{
  background:var(--bg);border-left:1px solid var(--border);
  overflow-y:auto;padding:14px;
}
.ovroot .right::-webkit-scrollbar{width:4px}
.ovroot .right::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}

.ovroot .rc{
  background:var(--white);border:1px solid var(--border);
  border-radius:12px;padding:14px;margin-bottom:10px;
  transition:border-color .1s;
}
.ovroot .rc h3{
  font-size:12.5px;font-weight:600;color:var(--ink);
  margin-bottom:11px;
  display:flex;align-items:center;justify-content:space-between;
}
.ovroot .rc h3 .tiny{font-size:11px;color:var(--dim);font-weight:400}
.ovroot .nm-vs{display:flex;align-items:center;justify-content:center;gap:14px;margin:6px 0 4px}
.ovroot .nm-vs .t{font-size:17px;font-weight:700;color:var(--ink)}
.ovroot .nm-vs .t.away{color:var(--muted)}
.ovroot .nm-vs .x{font-size:12px;color:var(--dim)}
.ovroot .nm-when{text-align:center;font-size:11.5px;color:var(--muted);margin-bottom:12px}
.ovroot .probbar{
  height:6px;border-radius:3px;background:var(--surface2);
  display:flex;overflow:hidden;margin-bottom:8px;gap:2px;
}
.ovroot .probbar i{display:block;height:100%;border-radius:3px}
.ovroot .probleg{display:flex;justify-content:space-between}
.ovroot .probleg .pi{text-align:center;flex:1}
.ovroot .probleg .pv{font-weight:700;font-size:14px}
.ovroot .probleg .pl{font-size:10px;color:var(--dim);margin-top:2px;text-transform:uppercase;letter-spacing:.3px}
.ovroot .alrt{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);font-size:12.5px}
.ovroot .alrt:last-child{border:0;padding-bottom:0}
.ovroot .alrt .ai{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.ovroot .alrt .am{line-height:1.4;flex:1}
.ovroot .alrt .am .tm{display:block;font-size:11px;color:var(--dim);margin-top:2px}
.ovroot .task{display:flex;align-items:center;gap:9px;padding:8px 0;border-bottom:1px solid var(--border);font-size:12.5px}
.ovroot .task:last-child{border:0}
.ovroot .task .cb{width:16px;height:16px;border-radius:5px;border:1.5px solid var(--border2);flex-shrink:0;background:var(--white)}
.ovroot .task .tt{flex:1}

/* Segment kontrol */
.ovroot .seg{
  display:inline-flex;background:var(--surface2);
  border:1px solid var(--border);border-radius:10px;padding:3px;gap:2px;
}
.ovroot .seg button{
  background:transparent;border:0;
  color:var(--muted);font-size:12px;font-weight:500;
  padding:5px 12px;border-radius:7px;cursor:pointer;font-family:inherit;
  transition:background .08s,color .08s;
}
.ovroot .seg button.on{background:var(--white);color:var(--ink);font-weight:600;box-shadow:0 1px 3px rgba(0,0,0,.08)}

/* Pozisyon rozeti */
.ovroot .pos{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:30px;padding:2px 7px;border-radius:6px;
  font-size:11px;font-weight:600;
  background:var(--surface2);color:var(--muted);
}

/* İstatistik satırı */
.ovroot .stat{display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--border);font-size:12.5px}
.ovroot .stat:last-child{border:0}
.ovroot .stat .sv{font-weight:700;font-variant-numeric:tabular-nums}

/* Mini bar */
.ovroot .mbar{height:5px;border-radius:3px;background:var(--surface2);overflow:hidden;margin:3px 0 9px}
.ovroot .mbar i{display:block;height:100%;border-radius:3px}

/* Donut (sağ kolon) */
.ovroot .donut-wrap{display:flex;align-items:center;gap:14px}

/* Skeleton */
.ovroot .sk{display:block;border-radius:6px;background:var(--surface2);animation:sk-sh 1.4s ease infinite;background-size:400% 100%}
@keyframes sk-sh{0%{opacity:1}50%{opacity:.5}100%{opacity:1}}
.ovroot .sk-line{height:12px;margin:6px 0;border-radius:6px}
.ovroot .sk-kn{height:24px;width:52px;margin:2px 0 5px;border-radius:6px}

/* Boş durum */
.ovroot .empty{text-align:center;padding:32px 20px}
.ovroot .empty .ei{font-size:28px;margin-bottom:8px;opacity:.6}
.ovroot .empty .et{font-size:13.5px;color:var(--muted);font-weight:600}
.ovroot .empty .es{font-size:12px;color:var(--dim);margin-top:4px}

/* Demo şerit */
.ovroot .demobar{
  display:flex;align-items:center;gap:10px;
  background:#fdf6e0;border:1px solid #ecd9a0;border-left:3px solid #d9a514;
  border-radius:10px;padding:10px 12px;margin-bottom:16px;
  font-size:12.5px;color:#7a5b10;
}
.ovroot .demobar b{color:#5c440b}
.ovroot .demobar .db-cta{
  margin-left:auto;color:var(--accent);text-decoration:none;
  font-size:11.5px;font-weight:600;
  background:var(--accent-lt);border:1px solid var(--accent);
  padding:5px 11px;border-radius:8px;white-space:nowrap;
  transition:background .1s;
}
.ovroot .demobar .db-cta:hover{background:#d2e7d2}

/* ─────────────────────────────────────────────
   ANIMASYONLAR — giriş + mikro etkileşim
───────────────────────────────────────────── */
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes popIn{0%{opacity:0;transform:scale(.96)}100%{opacity:1;transform:none}}

/* Sayfa içeriği yumuşak belirsin */
.ovroot .pghdr{animation:fadeIn .35s ease both}
.ovroot .center{animation:fadeIn .3s ease both}

/* KPI kartları kademeli (stagger) belirir */
.ovroot .kpis .kpi{animation:fadeUp .45s cubic-bezier(.2,.7,.2,1) both}
.ovroot .kpis .kpi:nth-child(1){animation-delay:.03s}
.ovroot .kpis .kpi:nth-child(2){animation-delay:.08s}
.ovroot .kpis .kpi:nth-child(3){animation-delay:.13s}
.ovroot .kpis .kpi:nth-child(4){animation-delay:.18s}
.ovroot .kpis .kpi:nth-child(5){animation-delay:.23s}
.ovroot .kpis .kpi:nth-child(6){animation-delay:.28s}

/* Kartlar/sağ panel widget'ları belirir */
.ovroot .rc,.ovroot .st{animation:fadeUp .5s cubic-bezier(.2,.7,.2,1) both}
.ovroot .live-strip{animation:popIn .4s cubic-bezier(.2,.8,.2,1) both}

/* Mikro etkileşim — hover yükselme + yumuşak gölge */
.ovroot .kpi{transition:transform .16s ease,border-color .14s,box-shadow .16s}
.ovroot .kpi:hover{transform:translateY(-3px);border-color:var(--border2);box-shadow:0 8px 20px rgba(70,80,55,.14)}
.ovroot .rc{transition:transform .16s ease,border-color .14s,box-shadow .16s}
.ovroot .rc:hover{box-shadow:0 6px 16px rgba(70,80,55,.12)}
.ovroot tbody tr{transition:background .12s}
.ovroot .ntab,.ovroot .sni,.ovroot .seg button{transition:background .12s,color .12s,transform .12s}
.ovroot .ntab:active,.ovroot .sni:active{transform:scale(.97)}
.ovroot .sni.active{box-shadow:inset 2px 0 0 var(--accent)}

/* Hareketi azalt tercihi olanlar için animasyonları kapat */
@media (prefers-reduced-motion:reduce){
  .ovroot *,.ovroot *::before,.ovroot *::after{animation:none!important;transition:none!important}
}

/* Tıklanır widget'lar (kontrol paneli kartları + satır linkleri) */
.ovroot .clickable{cursor:pointer;transition:transform .16s ease,border-color .14s,box-shadow .16s}
.ovroot .clickable:hover{transform:translateY(-2px);border-color:var(--accent);box-shadow:0 8px 20px rgba(70,80,55,.14)}
.ovroot .clickable:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.ovroot .rowlink{cursor:pointer;border-radius:8px;transition:background .08s}
.ovroot .rowlink:hover{background:var(--surface2)}
.ovroot .rowlink:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}

/* ─────────────────────────────────────────────
   RESPONSIVE — tablet & mobil
───────────────────────────────────────────── */

/* Geniş tablet yatay (iPad Pro vb.): kolonlar daralır */
@media (max-width:1280px){
  .ovroot .cbody{grid-template-columns:184px 1fr 244px}
  .ovroot .kpis{grid-template-columns:repeat(3,1fr)}
}

/* Tablet (dikey iPad / küçük yatay): sidebar çekmeceye dönüşür,
   sağ panel içeriğin altına iner, tek akış kaydırma. */
@media (max-width:1024px){
  .ovroot .menu-btn{display:flex}
  .ovroot .nav-backdrop{display:block}
  .ovroot .cbody{display:block;overflow-y:auto;height:calc(100vh - 50px);-webkit-overflow-scrolling:touch}
  .ovroot .sidebar{
    position:fixed;left:0;top:50px;bottom:0;width:260px;z-index:70;
    border-right:1px solid var(--border);
    box-shadow:6px 0 24px rgba(70,80,55,.22);
    transform:translateX(-104%);
    transition:transform .24s cubic-bezier(.2,.8,.2,1);
  }
  .ovroot.nav-open .sidebar{transform:none}
  .ovroot .center{height:auto;overflow:visible;padding:16px}
  .ovroot .right{border-left:0;border-top:1px solid var(--border);overflow:visible}
  .ovroot .kpis{grid-template-columns:repeat(3,1fr)}
  .ovroot .datebox{display:none}
  /* Yoğun tablolar ezilmek yerine yatay kaydırılsın (.tbl overflow-x:auto). */
  .ovroot .tbl table{min-width:560px}
}

/* Telefon / küçük tablet dikey */
@media (max-width:767px){
  .ovroot .kpis{grid-template-columns:repeat(2,1fr)}
  .ovroot .kpi .kn{font-size:22px}
  .ovroot .pgttl h1{font-size:18px}
  .ovroot .ntab{padding:6px 10px;font-size:12px}
  .ovroot .center{padding:14px;padding-bottom:78px}
}
@media (max-width:560px){
  .ovroot .logo svg{height:26px!important}
}

/* Mobil alt tab bar — yalnız telefonda (tablette hamburger var) */
.ovroot .btabs{display:none}
@media (max-width:767px){
  .ovroot .btabs{
    display:flex;position:fixed;left:0;right:0;bottom:0;height:60px;
    background:var(--white);border-top:1px solid var(--border);
    z-index:50;padding-bottom:env(safe-area-inset-bottom,0px);
    box-shadow:0 -4px 16px rgba(70,80,55,.14);
  }
  .ovroot .btab{
    flex:1;display:flex;flex-direction:column;align-items:center;
    justify-content:center;gap:3px;
    color:var(--dim);text-decoration:none;font-size:10px;font-weight:500;
  }
  .ovroot .btab .bi{font-size:18px;line-height:1}
  .ovroot .btab.active{color:var(--accent)}
}

/* Dokunmatik cihaz (parmak): hedefleri 44px'e büyüt, hover yerine bas-geri-bırak */
@media (pointer:coarse){
  .ovroot .sni{padding:11px 12px;font-size:13.5px;min-height:44px}
  .ovroot .sni i{font-size:18px}
  .ovroot .sgrp{padding:16px 12px 7px;min-height:34px}
  .ovroot .ntab{padding:10px 14px;min-height:40px}
  .ovroot .seg button{min-height:38px;padding:8px 14px}
  .ovroot tbody td{padding:13px 14px}
  .ovroot .menu-btn{width:44px;height:44px}
  .ovroot .btabs{height:64px}
  /* Hover-kalıcı efektler dokunmatikte yapışmasın */
  .ovroot .kpi:hover,.ovroot .clickable:hover{transform:none}
}
`;
