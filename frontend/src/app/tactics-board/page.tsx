"use client";

/**
 * Taktik Tahtası — 2D saha çizim tahtası (demo). ConsoleShell, FM26 açık tema.
 *
 * Formasyon seç → oyuncular sahaya dizilir; çizim araçları + kayıtlı tahtalar +
 * PDF ihraç (demo). Gerçek sürümde sürükle-bırak + animasyon eklenecek.
 */

import * as React from "react";
import { ConsoleShell } from "../_console/shell";

interface Token { x: number; y: number; n: number; role: string }

// x: 0 (kendi kale) → 100 (rakip kale), y: 0 (üst) → 100 (alt)
const FORMATIONS: Record<string, Token[]> = {
  "4-3-3": [
    { x: 6, y: 50, n: 1, role: "KL" },
    { x: 24, y: 16, n: 2, role: "SğB" }, { x: 22, y: 38, n: 4, role: "STP" }, { x: 22, y: 62, n: 5, role: "STP" }, { x: 24, y: 84, n: 3, role: "SlB" },
    { x: 45, y: 30, n: 8, role: "OS" }, { x: 42, y: 50, n: 6, role: "ÖL" }, { x: 45, y: 70, n: 10, role: "OS" },
    { x: 72, y: 20, n: 7, role: "SğK" }, { x: 78, y: 50, n: 9, role: "SF" }, { x: 72, y: 80, n: 11, role: "SlK" },
  ],
  "4-4-2": [
    { x: 6, y: 50, n: 1, role: "KL" },
    { x: 24, y: 16, n: 2, role: "SğB" }, { x: 22, y: 38, n: 4, role: "STP" }, { x: 22, y: 62, n: 5, role: "STP" }, { x: 24, y: 84, n: 3, role: "SlB" },
    { x: 50, y: 16, n: 7, role: "SğO" }, { x: 46, y: 40, n: 8, role: "OS" }, { x: 46, y: 60, n: 6, role: "OS" }, { x: 50, y: 84, n: 11, role: "SlO" },
    { x: 76, y: 38, n: 9, role: "SF" }, { x: 76, y: 62, n: 10, role: "SF" },
  ],
  "3-5-2": [
    { x: 6, y: 50, n: 1, role: "KL" },
    { x: 22, y: 30, n: 4, role: "STP" }, { x: 20, y: 50, n: 5, role: "STP" }, { x: 22, y: 70, n: 15, role: "STP" },
    { x: 44, y: 12, n: 2, role: "SğK" }, { x: 46, y: 36, n: 8, role: "OS" }, { x: 42, y: 50, n: 6, role: "ÖL" }, { x: 46, y: 64, n: 10, role: "OS" }, { x: 44, y: 88, n: 3, role: "SlK" },
    { x: 76, y: 40, n: 9, role: "SF" }, { x: 76, y: 60, n: 7, role: "SF" },
  ],
};

const SAVED = [
  { name: "Antalyaspor — yüksek pres", form: "4-3-3", date: "2026-06-06", tag: "Maç planı" },
  { name: "Geriye düşünce 3-5-2", form: "3-5-2", date: "2026-06-04", tag: "Senaryo" },
  { name: "Duran top — far post", form: "4-4-2", date: "2026-06-02", tag: "Duran top" },
];

const TOOLS = [
  { ic: "ti-pointer", label: "Seç" },
  { ic: "ti-arrow-up-right", label: "Ok / koşu" },
  { ic: "ti-line", label: "Pas çizgisi" },
  { ic: "ti-circle", label: "Bölge" },
  { ic: "ti-pencil", label: "Serbest çizim" },
  { ic: "ti-eraser", label: "Sil" },
];

function Pitch({ tokens }: { tokens: Token[] }) {
  const W = 680, H = 440, pad = 14;
  const px = (x: number) => pad + (x / 100) * (W - pad * 2);
  const py = (y: number) => pad + (y / 100) * (H - pad * 2);
  const line = "rgba(255,255,255,0.55)";
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block", borderRadius: 12 }}>
      <defs>
        <linearGradient id="grass" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#3f9d57" /><stop offset="0.5" stopColor="#46a85e" /><stop offset="1" stopColor="#3f9d57" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width={W} height={H} rx="12" fill="url(#grass)" />
      {/* şerit deseni */}
      {Array.from({ length: 6 }).map((_, i) => (
        <rect key={i} x={pad + i * ((W - pad * 2) / 6)} y={pad} width={(W - pad * 2) / 6} height={H - pad * 2} fill={i % 2 ? "rgba(255,255,255,0.04)" : "transparent"} />
      ))}
      {/* çizgiler */}
      <rect x={pad} y={pad} width={W - pad * 2} height={H - pad * 2} fill="none" stroke={line} strokeWidth="2" />
      <line x1={W / 2} y1={pad} x2={W / 2} y2={H - pad} stroke={line} strokeWidth="2" />
      <circle cx={W / 2} cy={H / 2} r="46" fill="none" stroke={line} strokeWidth="2" />
      <circle cx={W / 2} cy={H / 2} r="3" fill={line} />
      {/* ceza sahaları */}
      <rect x={pad} y={H / 2 - 80} width="78" height="160" fill="none" stroke={line} strokeWidth="2" />
      <rect x={W - pad - 78} y={H / 2 - 80} width="78" height="160" fill="none" stroke={line} strokeWidth="2" />
      <rect x={pad} y={H / 2 - 38} width="30" height="76" fill="none" stroke={line} strokeWidth="2" />
      <rect x={W - pad - 30} y={H / 2 - 38} width="30" height="76" fill="none" stroke={line} strokeWidth="2" />
      {/* örnek taktik ok (sağ kanat 1v1) */}
      <defs><marker id="ah" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6 Z" fill="#ffd23f" /></marker></defs>
      <path d={`M ${px(72)} ${py(20)} Q ${px(86)} ${py(14)} ${px(92)} ${py(34)}`} fill="none" stroke="#ffd23f" strokeWidth="2.5" strokeDasharray="5 4" markerEnd="url(#ah)" />
      {/* oyuncular */}
      {tokens.map((t) => (
        <g key={t.n}>
          <circle cx={px(t.x)} cy={py(t.y)} r="15" fill="#5c35d4" stroke="#fff" strokeWidth="2" />
          <text x={px(t.x)} y={py(t.y) + 4} textAnchor="middle" fill="#fff" style={{ fontSize: 12, fontWeight: 700, fontFamily: "JetBrains Mono" }}>{t.n}</text>
          <text x={px(t.x)} y={py(t.y) + 27} textAnchor="middle" fill="rgba(255,255,255,0.9)" style={{ fontSize: 9, fontWeight: 600 }}>{t.role}</text>
        </g>
      ))}
    </svg>
  );
}

export default function TacticsBoardPage() {
  const [form, setForm] = React.useState<keyof typeof FORMATIONS>("4-3-3");
  const [tool, setTool] = React.useState("Seç");

  const right = (
    <>
      <div className="rc">
        <h3>Araçlar</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          {TOOLS.map((t) => (
            <button key={t.label} type="button" onClick={() => setTool(t.label)} style={{
              display: "flex", alignItems: "center", gap: 7, padding: "8px 10px", borderRadius: 8,
              border: `1px solid ${tool === t.label ? "var(--accent)" : "var(--line)"}`,
              background: tool === t.label ? "var(--accent-lt)" : "var(--panel)",
              color: tool === t.label ? "var(--accent)" : "var(--muted)", cursor: "pointer",
              fontSize: 12, fontFamily: "inherit", fontWeight: 600,
            }}>
              <i className={`ti ${t.ic}`} style={{ fontSize: 15 }} /> {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="rc">
        <h3>Kayıtlı Tahtalar <span className="tiny">{SAVED.length}</span></h3>
        {SAVED.map((s, i) => (
          <div className="alrt" key={i} style={{ cursor: "pointer" }}>
            <span className="ai" style={{ background: "var(--accent)" }} />
            <div className="am"><b>{s.name}</b>
              <span className="tm">{s.form} · {s.tag} · {s.date}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="rc">
        <h3>İhraç</h3>
        <button type="button" style={{ width: "100%", padding: "10px", borderRadius: 9, border: 0, background: "var(--besiktas)", color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>
          <i className="ti ti-file-type-pdf" style={{ marginRight: 6 }} />PDF olarak indir
        </button>
        <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 8 }}>Brifing için tek sayfa; animasyon dışa aktarımı (GIF) yakında.</div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/tactics-board"
      title="Taktik Tahtası"
      sub="2D çizim · animasyon"
      desc="Formasyon kur, koşu/pas/bölge çiz, senaryoyu kaydet ve brifing için PDF al."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Saha</h2>
        <div className="seg">
          {(Object.keys(FORMATIONS) as (keyof typeof FORMATIONS)[]).map((f) => (
            <button key={f} className={form === f ? "on" : ""} onClick={() => setForm(f)}>{f}</button>
          ))}
        </div>
      </div>
      <div className="rc" style={{ margin: "0 0 14px", padding: 10 }}>
        <Pitch tokens={FORMATIONS[form]} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, flexWrap: "wrap", gap: 8 }}>
          <span style={{ fontSize: 12, color: "var(--muted)" }}>
            Formasyon <b style={{ color: "var(--ink)" }}>{form}</b> · aktif araç <b style={{ color: "var(--accent)" }}>{tool}</b>
          </span>
          <span style={{ fontSize: 11, color: "var(--dim)" }}>
            <i className="ti ti-info-circle" style={{ marginRight: 4 }} />Demo: sürükle-bırak gerçek sürümde gelir
          </span>
        </div>
      </div>

      <div className="st"><h2>Senaryo Notları</h2><span className="ep">{form}</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div className="rc" style={{ margin: 0, borderTop: "2px solid var(--accent)" }}>
          <b style={{ fontSize: 12.5 }}>Sağ kanat 1v1 (sarı ok)</b>
          <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5, marginTop: 6 }}>
            7 numara izole; rakip sol bek arkasına diyagonal koşu. Top 8 numaradan dik gelir.
          </div>
        </div>
        <div className="rc" style={{ margin: 0, borderTop: "2px solid var(--mid)" }}>
          <b style={{ fontSize: 12.5 }}>Yüksek blok tetikleyici</b>
          <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5, marginTop: 6 }}>
            9 numara kaleci-stoper pasını işaret eder; kanatlar içe kapatır, orta saha adam-adama.
          </div>
        </div>
      </div>
    </ConsoleShell>
  );
}
