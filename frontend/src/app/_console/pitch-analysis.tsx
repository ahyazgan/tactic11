"use client";

/**
 * Saha-Üstü Derin Taktik Analiz görselleştirmesi — lib/deep-tactical çıktısını
 * GERÇEK bir futbol sahasında gösterir: rakibin savunma bloğu (11 ortalama pozisyon)
 * + blok yüksekliği bandı + faz metrikleri + oyuncu rolleri + sayısal kalıplar.
 */

import * as React from "react";
import type { DeepTactical, PhaseStat, PassNetwork } from "@/lib/deep-tactical";
import type { KeyPlayer } from "@/lib/statsbomb-match";

const THEM = "var(--high)";
const HUB = "var(--accent)";

const PW = 420, PH = 280, PMX = 6, PMY = 6;
const ppx = (x: number) => PMX + (x / 100) * (PW - 2 * PMX);
const ppy = (y: number) => PMY + (y / 100) * (PH - 2 * PMY);

/** Saha çizgileri (paylaşılan). */
function PitchLines() {
  return (
    <>
      <rect x={PMX} y={PMY} width={PW - 2 * PMX} height={PH - 2 * PMY} fill="none" stroke="var(--line2)" strokeWidth={1.4} rx={4} />
      <line x1={PW / 2} y1={PMY} x2={PW / 2} y2={PH - PMY} stroke="var(--line2)" strokeWidth={1} />
      <circle cx={PW / 2} cy={PH / 2} r={34} fill="none" stroke="var(--line2)" strokeWidth={1} />
      <rect x={PMX} y={PH / 2 - 64} width={62} height={128} fill="none" stroke="var(--line2)" strokeWidth={1} />
      <rect x={PW - PMX - 62} y={PH / 2 - 64} width={62} height={128} fill="none" stroke="var(--line2)" strokeWidth={1} />
    </>
  );
}

/** Pas ağı — düğümler (dokunuşa göre boyut) + kenarlar (bağlantı ağırlığı). */
export function PassNetworkPitch({ net }: { net: PassNetwork }) {
  const byNum = new Map(net.nodes.map((n) => [n.num, n]));
  const maxW = Math.max(...net.edges.map((e) => e.weight), 1);
  return (
    <svg viewBox={`0 0 ${PW} ${PH}`} width="100%" style={{ display: "block", borderRadius: 10, background: "color-mix(in srgb, var(--low) 9%, var(--panel))" }}>
      <PitchLines />
      <text x={PW - PMX - 8} y={PH - PMY - 6} fontSize={9} fill="var(--dim)" textAnchor="end">hücum yönü →</text>
      {/* kenarlar */}
      {net.edges.map((e, i) => {
        const a = byNum.get(e.from), b = byNum.get(e.to);
        if (!a || !b) return null;
        const t = e.weight / maxW;
        return <line key={i} x1={ppx(a.x)} y1={ppy(a.y)} x2={ppx(b.x)} y2={ppy(b.y)} stroke={THEM} strokeWidth={0.6 + t * 3.4} opacity={0.12 + t * 0.4} />;
      })}
      {/* düğümler */}
      {net.nodes.map((n) => {
        const isHub = n.num === net.hubNum;
        const r = 6 + (n.involvement / 100) * 9;
        return (
          <g key={n.num}>
            <circle cx={ppx(n.x)} cy={ppy(n.y)} r={r} fill="var(--panel)" stroke={isHub ? HUB : THEM} strokeWidth={isHub ? 2.6 : 1.8} />
            <text x={ppx(n.x)} y={ppy(n.y) + 0.5} fontSize={9.5} fill="var(--ink)" textAnchor="middle" dominantBaseline="middle" fontFamily="JetBrains Mono" fontWeight={700}>{n.num}</text>
            {n.name && <text x={ppx(n.x)} y={ppy(n.y) + r + 9} fontSize={8} fill={isHub ? HUB : "var(--dim)"} textAnchor="middle" fontWeight={isHub ? 700 : 400}>{n.name}</text>}
          </g>
        );
      })}
    </svg>
  );
}

/** Isı haritası — 12×8 dokunuş yoğunluğu (gerçek event konumlarından). */
export function HeatMap({ heat, color = "var(--high)" }: { heat: number[][]; color?: string }) {
  const cols = heat.length, rows = heat[0]?.length ?? 8;
  const max = Math.max(...heat.flat(), 1);
  const cw = (PW - 2 * PMX) / cols, ch = (PH - 2 * PMY) / rows;
  return (
    <svg viewBox={`0 0 ${PW} ${PH}`} width="100%" style={{ display: "block", borderRadius: 10, background: "color-mix(in srgb, var(--low) 9%, var(--panel))" }}>
      {heat.map((colArr, c) => colArr.map((v, r) => (
        <rect key={`${c}-${r}`} x={PMX + c * cw} y={PMY + r * ch} width={cw} height={ch}
          fill={color} fillOpacity={(v / max) * 0.62} />
      )))}
      <PitchLines />
      <text x={PW - PMX - 8} y={PH - PMY - 6} fontSize={9} fill="var(--dim)" textAnchor="end">hücum yönü →</text>
    </svg>
  );
}

/** Şut haritası — gerçek şut konumları, xG'ye göre boyut, gole göre renk. */
export function ShotMap({ shots, color = "var(--high)" }: { shots: { x: number; y: number; xg: number; goal: boolean }[]; color?: string }) {
  return (
    <svg viewBox={`0 0 ${PW} ${PH}`} width="100%" style={{ display: "block", borderRadius: 10, background: "color-mix(in srgb, var(--low) 9%, var(--panel))" }}>
      <PitchLines />
      <text x={PW - PMX - 8} y={PH - PMY - 6} fontSize={9} fill="var(--dim)" textAnchor="end">kale →</text>
      {shots.map((s, i) => {
        const r = 2.5 + Math.sqrt(s.xg) * 13;
        return (
          <circle key={i} cx={ppx(s.x)} cy={ppy(s.y)} r={r}
            fill={s.goal ? "var(--low)" : color} fillOpacity={s.goal ? 0.7 : 0.18}
            stroke={s.goal ? "var(--low)" : color} strokeWidth={s.goal ? 2 : 1} />
        );
      })}
    </svg>
  );
}

/** Progresyon okları — topu kaleye taşıyan en tehditli paslar (gerçek event'lerden). */
export function ProgressionMap({ passes, color = "var(--high)" }: { passes: { x1: number; y1: number; x2: number; y2: number; xt: number }[]; color?: string }) {
  const maxXt = Math.max(...passes.map((p) => p.xt), 0.01);
  const head = (x1: number, y1: number, x2: number, y2: number, s = 5) => {
    const a = Math.atan2(ppy(y2) - ppy(y1), ppx(x2) - ppx(x1));
    return `M ${ppx(x2)} ${ppy(y2)} L ${ppx(x2) - s * Math.cos(a - 0.5)} ${ppy(y2) - s * Math.sin(a - 0.5)} M ${ppx(x2)} ${ppy(y2)} L ${ppx(x2) - s * Math.cos(a + 0.5)} ${ppy(y2) - s * Math.sin(a + 0.5)}`;
  };
  return (
    <svg viewBox={`0 0 ${PW} ${PH}`} width="100%" style={{ display: "block", borderRadius: 10, background: "color-mix(in srgb, var(--low) 9%, var(--panel))" }}>
      <PitchLines />
      <text x={PW - PMX - 8} y={PH - PMY - 6} fontSize={9} fill="var(--dim)" textAnchor="end">hücum yönü →</text>
      {passes.map((p, i) => {
        const t = p.xt / maxXt;
        const w = 1 + t * 2.6, op = 0.3 + t * 0.55;
        return (
          <g key={i} opacity={op}>
            <line x1={ppx(p.x1)} y1={ppy(p.y1)} x2={ppx(p.x2)} y2={ppy(p.y2)} stroke={color} strokeWidth={w} strokeLinecap="round" />
            <path d={head(p.x1, p.y1, p.x2, p.y2)} stroke={color} strokeWidth={w} fill="none" strokeLinecap="round" />
            <circle cx={ppx(p.x1)} cy={ppy(p.y1)} r={1.8} fill={color} />
          </g>
        );
      })}
    </svg>
  );
}

/** xG zaman çizgisi — maç boyunca kümülatif xG (momentum), iki takım. */
export function XgTimeline({ teams }: { teams: { name: string; color: string; shots: { minute: number; xg: number; goal: boolean }[] }[] }) {
  const w = 560, h = 150, padL = 26, padR = 10, padT = 10, padB = 20;
  const maxMin = Math.max(95, ...teams.flatMap((t) => t.shots.map((s) => s.minute)));
  const series = teams.map((t) => {
    let c = 0;
    const pts = [...t.shots].sort((a, b) => a.minute - b.minute).map((s) => ({ minute: s.minute, cum: (c += s.xg), goal: s.goal }));
    return { ...t, pts, total: c };
  });
  const maxCum = Math.max(0.5, ...series.map((s) => s.total));
  const x = (m: number) => padL + (m / maxMin) * (w - padL - padR);
  const y = (v: number) => h - padB - (v / maxCum) * (h - padT - padB);
  const path = (pts: { minute: number; cum: number }[]) => {
    if (!pts.length) return "";
    let d = `M ${x(0).toFixed(1)} ${y(0).toFixed(1)}`;
    for (const p of pts) d += ` L ${x(p.minute).toFixed(1)} ${y(p.cum).toFixed(1)}`;   // basamak: xG anında atlar
    return d;
  };
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} style={{ display: "block" }}>
      {[0, 0.5, 1].map((g) => { const v = g * maxCum; return (
        <g key={g}><line x1={padL} y1={y(v)} x2={w - padR} y2={y(v)} stroke="var(--line)" strokeWidth={0.7} />
          <text x={2} y={y(v) + 3} fontSize={8.5} fill="var(--dim)" fontFamily="JetBrains Mono">{v.toFixed(1)}</text></g>); })}
      {[0, 15, 30, 45, 60, 75, 90].map((m) => <text key={m} x={x(m)} y={h - 5} fontSize={8.5} fill="var(--dim)" textAnchor="middle" fontFamily="JetBrains Mono">{m}&apos;</text>)}
      <line x1={x(45)} y1={padT} x2={x(45)} y2={h - padB} stroke="var(--line2)" strokeWidth={0.7} strokeDasharray="2 3" />
      {series.map((s) => (
        <g key={s.name}>
          <path d={path(s.pts)} fill="none" stroke={s.color} strokeWidth={2.2} strokeLinejoin="round" />
          {s.pts.filter((p) => p.goal).map((p, i) => <circle key={i} cx={x(p.minute)} cy={y(p.cum)} r={3.5} fill={s.color} stroke="var(--panel)" strokeWidth={1.4} />)}
        </g>
      ))}
    </svg>
  );
}

/** Pas ağı gövdesi: saha + hub + içgörü. */
export function PassNetworkBody({ net }: { net: PassNetwork }) {
  const hub = net.nodes.find((n) => n.num === net.hubNum);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 18, alignItems: "start" }}>
      <div>
        <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6 }}>{net.name} <span style={{ color: "var(--dim)", fontWeight: 400, fontFamily: "JetBrains Mono", fontSize: 11 }}>{net.formation} · topla oyun</span></div>
        <PassNetworkPitch net={net} />
        <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 6, lineHeight: 1.5 }}>
          Düğüm boyutu = top dokunuşu; çizgi kalınlığı = oyuncular arası pas yoğunluğu. <span style={{ color: HUB }}>●</span> oyun kurma merkezi (hub).
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {hub && (
          <div style={{ background: "var(--panel3)", borderRadius: 9, padding: "11px 13px", borderLeft: `3px solid ${HUB}` }}>
            <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 3 }}>Oyun Kurma Merkezi (Hub)</div>
            <div style={{ fontSize: 14, fontWeight: 800, color: HUB }}>#{hub.num} · {hub.pos}</div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3 }}>Topa en çok dokunan oyuncu — oyun bu noktadan kuruluyor. Baskı altına alınırsa ağ kesilir.</div>
          </div>
        )}
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>Yapı Okuması</div>
          <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.6 }}>{net.insight}</div>
        </div>
      </div>
    </div>
  );
}

/** Yatay futbol sahası (rakip soldan sağa hücum eder) + savunma bloğu. */
export function PitchShape({ profile }: { profile: DeepTactical }) {
  const W = 420, H = 280, mx = 6, my = 6;
  const px = (x: number) => mx + (x / 100) * (W - 2 * mx);
  const py = (y: number) => my + (y / 100) * (H - 2 * my);
  // Savunma hattı x'i (en geri saha oyuncularının ortalaması) → blok bandı.
  const defs = profile.blockShape.filter((p) => p.pos.includes("B") || p.pos === "CB" || p.pos === "RWB" || p.pos === "LWB");
  const lineX = defs.length ? defs.reduce((s, p) => s + p.x, 0) / defs.length : 22;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", borderRadius: 10, background: "color-mix(in srgb, var(--low) 9%, var(--panel))" }}>
      {/* saha çizgileri */}
      <rect x={mx} y={my} width={W - 2 * mx} height={H - 2 * my} fill="none" stroke="var(--line2)" strokeWidth={1.4} rx={4} />
      <line x1={W / 2} y1={my} x2={W / 2} y2={H - my} stroke="var(--line2)" strokeWidth={1} />
      <circle cx={W / 2} cy={H / 2} r={34} fill="none" stroke="var(--line2)" strokeWidth={1} />
      {/* ceza sahaları */}
      <rect x={mx} y={H / 2 - 64} width={62} height={128} fill="none" stroke="var(--line2)" strokeWidth={1} />
      <rect x={W - mx - 62} y={H / 2 - 64} width={62} height={128} fill="none" stroke="var(--line2)" strokeWidth={1} />
      {/* blok yüksekliği bandı (kendi kalesinden savunma hattına) */}
      <rect x={mx} y={my} width={px(lineX) - mx} height={H - 2 * my} fill={THEM} fillOpacity={0.06} />
      <line x1={px(lineX)} y1={my} x2={px(lineX)} y2={H - my} stroke={THEM} strokeWidth={1} strokeDasharray="4 3" opacity={0.5} />
      <text x={px(lineX) + 4} y={my + 12} fontSize={9} fill={THEM} opacity={0.8}>savunma hattı ~{profile.blockHeightM}m</text>
      {/* hücum yönü oku */}
      <text x={W - mx - 8} y={H - my - 6} fontSize={9} fill="var(--dim)" textAnchor="end">hücum yönü →</text>
      {/* oyuncular */}
      {profile.blockShape.map((p) => (
        <g key={p.num}>
          <circle cx={px(p.x)} cy={py(p.y)} r={11} fill="var(--panel)" stroke={THEM} strokeWidth={1.8} />
          <text x={px(p.x)} y={py(p.y) + 0.5} fontSize={9.5} fill="var(--ink)" textAnchor="middle" dominantBaseline="middle" fontFamily="JetBrains Mono" fontWeight={700}>{p.num}</text>
          <text x={px(p.x)} y={py(p.y) + 19} fontSize={7.5} fill="var(--dim)" textAnchor="middle">{p.pos}</text>
        </g>
      ))}
    </svg>
  );
}

/** Oyuncu-seviyesi teknik tablo — gerçek event'lerden bireysel katkı (etki sırası). */
export function KeyPlayersTable({ players, color = "var(--accent)", limit = 7, onSelect, selectedNum }: { players: KeyPlayer[]; color?: string; limit?: number; onSelect?: (p: KeyPlayer) => void; selectedNum?: number }) {
  const rows = players.slice(0, limit);
  const TAG_COLOR: Record<string, string> = {
    "Bitirici": "var(--crit)", "Tehdit üreten": "var(--accent)", "Asist tehdidi": "var(--high)",
    "İlerleten": "var(--mid)", "Oyun kurucu": "var(--low)", "Top kazanan": "var(--muted)", "Dengeleyici": "var(--dim)",
  };
  const num = (v: number | string) => <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>{v}</span>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
        <thead>
          <tr style={{ textAlign: "right", color: "var(--dim)", fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.4 }}>
            <th style={{ textAlign: "left", padding: "0 8px 7px 0", fontWeight: 600 }}>Oyuncu</th>
            <th style={{ textAlign: "left", padding: "0 8px 7px 0", fontWeight: 600 }}>Rol</th>
            <th style={{ padding: "0 7px 7px", fontWeight: 600 }} title="topa dokunuş">Dok.</th>
            <th style={{ padding: "0 7px 7px", fontWeight: 600 }} title="tamamlanan pas (% isabet)">Pas</th>
            <th style={{ padding: "0 7px 7px", fontWeight: 600 }} title="ilerletme pası">İlrl.</th>
            <th style={{ padding: "0 7px 7px", fontWeight: 600 }} title="üretilen tehdit (Expected Threat)">xT</th>
            <th style={{ padding: "0 7px 7px", fontWeight: 600 }} title="kilit pas (şut/gol asisti)">Klt.</th>
            <th style={{ padding: "0 7px 7px", fontWeight: 600 }} title="şut · xG">Şut/xG</th>
            <th style={{ padding: "0 7px 7px", fontWeight: 600 }} title="savunma aksiyonu">Sav.</th>
            <th style={{ padding: "0 0 7px 7px", fontWeight: 600, minWidth: 64 }} title="bileşik teknik etki">Etki</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p, i) => (
            <tr key={p.num} onClick={() => onSelect?.(p)} style={{ borderTop: "1px solid var(--line)", textAlign: "right", color: "var(--ink)", cursor: onSelect ? "pointer" : "default", background: selectedNum === p.num ? "color-mix(in srgb, " + color + " 10%, transparent)" : undefined }}>
              <td style={{ textAlign: "left", padding: "7px 8px 7px 0", whiteSpace: "nowrap" }}>
                <span style={{ fontFamily: "JetBrains Mono", color: "var(--dim)", fontSize: 10 }}>#{p.num}</span> <b>{p.short}</b>
                <span style={{ color: "var(--dim)", fontSize: 9.5, marginLeft: 4 }}>{p.pos}</span>
              </td>
              <td style={{ textAlign: "left", padding: "7px 8px 7px 0" }}>
                <span style={{ fontSize: 9.5, fontWeight: 700, color: "#fff", background: TAG_COLOR[p.tag] || "var(--dim)", borderRadius: 4, padding: "1px 6px", whiteSpace: "nowrap" }}>{p.tag}</span>
              </td>
              <td style={{ padding: "7px 7px" }}>{num(p.touches)}</td>
              <td style={{ padding: "7px 7px" }}>{num(p.passC)}<span style={{ color: "var(--dim)", fontSize: 9.5 }}> %{p.passAcc}</span></td>
              <td style={{ padding: "7px 7px" }}>{num(p.prog)}</td>
              <td style={{ padding: "7px 7px", color: p.xt >= 0.8 ? color : "var(--ink)" }}>{num(p.xt.toFixed(2))}</td>
              <td style={{ padding: "7px 7px" }}>{num(p.keyP)}</td>
              <td style={{ padding: "7px 7px" }}>{num(p.shots)}<span style={{ color: "var(--dim)", fontSize: 9.5 }}> {p.xg.toFixed(2)}</span></td>
              <td style={{ padding: "7px 7px" }}>{num(p.def)}</td>
              <td style={{ padding: "7px 0 7px 7px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-end" }}>
                  <div style={{ flex: 1, height: 5, background: "var(--line)", borderRadius: 3, overflow: "hidden", maxWidth: 42 }}>
                    <div style={{ width: `${p.impact}%`, height: "100%", background: color, opacity: 1 - i * 0.07 }} />
                  </div>
                  {num(p.impact)}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Oyuncu pas haritası — tamamlanan paslar (ileri = vurgulu), gerçek event'lerden. */
export function PlayerPassMap({ passes, color = "var(--accent)" }: { passes: number[][]; color?: string }) {
  const maxFwd = Math.max(...passes.map((p) => p[2] - p[0]), 1);
  return (
    <svg viewBox={`0 0 ${PW} ${PH}`} width="100%" style={{ display: "block", borderRadius: 10, background: "color-mix(in srgb, var(--low) 9%, var(--panel))" }}>
      <PitchLines />
      <text x={PW - PMX - 8} y={PH - PMY - 6} fontSize={9} fill="var(--dim)" textAnchor="end">hücum yönü →</text>
      {passes.map((p, i) => {
        const fwd = (p[2] - p[0]) / maxFwd;
        const op = 0.3 + Math.max(0, fwd) * 0.55;
        const a = Math.atan2(ppy(p[3]) - ppy(p[1]), ppx(p[2]) - ppx(p[0]));
        const hx = ppx(p[2]), hy = ppy(p[3]);
        return (
          <g key={i} opacity={op}>
            <line x1={ppx(p[0])} y1={ppy(p[1])} x2={hx} y2={hy} stroke={color} strokeWidth={1.4} strokeLinecap="round" />
            <path d={`M ${hx} ${hy} L ${hx - 5 * Math.cos(a - 0.5)} ${hy - 5 * Math.sin(a - 0.5)} M ${hx} ${hy} L ${hx - 5 * Math.cos(a + 0.5)} ${hy - 5 * Math.sin(a + 0.5)}`} stroke={color} strokeWidth={1.4} fill="none" strokeLinecap="round" />
            <circle cx={ppx(p[0])} cy={ppy(p[1])} r={1.6} fill={color} />
          </g>
        );
      })}
    </svg>
  );
}

const RADAR_AXES: { key: keyof KeyPlayer; label: string; cap: number }[] = [
  { key: "passAcc", label: "Pas %", cap: 100 },
  { key: "prog", label: "Prog", cap: 14 },
  { key: "xt", label: "xT", cap: 2.5 },
  { key: "keyP", label: "Kilit", cap: 4 },
  { key: "xg", label: "xG", cap: 0.9 },
  { key: "carries", label: "Taşıma", cap: 12 },
  { key: "def", label: "Savunma", cap: 55 },
];

/** Oyuncu teknik radarı — 7 eksen, metriklerden normalize (0-1). */
export function PlayerRadar({ player, color = "var(--accent)", size = 230 }: { player: KeyPlayer; color?: string; size?: number }) {
  const cx = size / 2, cy = size / 2, R = size / 2 - 30;
  const n = RADAR_AXES.length;
  const pt = (i: number, r: number) => {
    const ang = -Math.PI / 2 + (i / n) * 2 * Math.PI;
    return [cx + Math.cos(ang) * r, cy + Math.sin(ang) * r];
  };
  const vals = RADAR_AXES.map((a) => Math.max(0, Math.min(1, (player[a.key] as number) / a.cap)));
  const poly = vals.map((v, i) => pt(i, v * R).join(",")).join(" ");
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width="100%" style={{ display: "block", maxWidth: size }}>
      {[0.25, 0.5, 0.75, 1].map((g) => (
        <polygon key={g} points={RADAR_AXES.map((_, i) => pt(i, g * R).join(",")).join(" ")} fill="none" stroke="var(--line)" strokeWidth={0.7} />
      ))}
      {RADAR_AXES.map((a, i) => {
        const [ex, ey] = pt(i, R);
        const [lx, ly] = pt(i, R + 16);
        return (
          <g key={a.label}>
            <line x1={cx} y1={cy} x2={ex} y2={ey} stroke="var(--line)" strokeWidth={0.7} />
            <text x={lx} y={ly} fontSize={8.5} fill="var(--dim)" textAnchor="middle" dominantBaseline="middle">{a.label}</text>
          </g>
        );
      })}
      <polygon points={poly} fill={color} fillOpacity={0.22} stroke={color} strokeWidth={2} />
      {vals.map((v, i) => { const [x, y] = pt(i, v * R); return <circle key={i} cx={x} cy={y} r={2.4} fill={color} />; })}
    </svg>
  );
}

/** Oyuncu derin analizi — ısı + pas haritası + teknik radar (gerçek event'lerden). */
export function PlayerDeepDive({ player, color = "var(--accent)" }: { player: KeyPlayer; color?: string }) {
  const stats: [string, string][] = [
    ["Dokunuş", `${player.touches}`], ["Pas", `${player.passC} (%${player.passAcc})`],
    ["İlerletme", `${player.prog}`], ["xT", player.xt.toFixed(2)],
    ["Kilit pas", `${player.keyP}`], ["Şut/xG", `${player.shots}/${player.xg.toFixed(2)}`],
    ["Top taşıma", `${player.carries}`], ["Savunma", `${player.def}`],
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontFamily: "JetBrains Mono", color: "var(--dim)", fontSize: 13 }}>#{player.num}</span>
        <span style={{ fontSize: 16, fontWeight: 800 }}>{player.short}</span>
        <span style={{ fontSize: 11, color: "var(--dim)" }}>{player.pos}</span>
        <span style={{ marginLeft: "auto", fontSize: 9.5, fontWeight: 700, color: "#fff", background: color, borderRadius: 4, padding: "2px 7px" }}>{player.tag}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14, alignItems: "start" }}>
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 5 }}>Isı haritası</div>
          {player.heat && player.heat.length ? <HeatMap heat={player.heat} color={color} /> : <div style={{ fontSize: 11, color: "var(--dim)" }}>veri yok</div>}
        </div>
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 5 }}>Pas haritası <span style={{ textTransform: "none" }}>· en ileri 18</span></div>
          {player.passes && player.passes.length ? <PlayerPassMap passes={player.passes} color={color} /> : <div style={{ fontSize: 11, color: "var(--dim)" }}>veri yok</div>}
        </div>
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 5 }}>Teknik radar</div>
          <div style={{ display: "flex", justifyContent: "center" }}><PlayerRadar player={player} color={color} /></div>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 8 }}>
        {stats.map(([l, v]) => (
          <div key={l} className="kpi" style={{ padding: "8px 10px" }}>
            <div className="kl">{l}</div>
            <div className="kn" style={{ fontSize: 16 }}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatRow({ s }: { s: PhaseStat }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, marginBottom: 2 }}>
        <span style={{ color: "var(--muted)" }}>{s.label}</span>
        <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: "var(--ink)" }}>{s.value}</span>
      </div>
      {s.bar != null && <div className="mbar"><i style={{ width: `${Math.max(2, s.bar)}%`, background: THEM }} /></div>}
    </div>
  );
}

function Phase({ title, stats }: { title: string; stats: PhaseStat[] }) {
  return (
    <div>
      <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>{title}</div>
      {stats.map((s) => <StatRow key={s.label} s={s} />)}
    </div>
  );
}

/** Tam derin taktik gövdesi: saha + faz metrikleri + roller + kalıplar. */
export function DeepTacticalBody({ profile }: { profile: DeepTactical }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 18, alignItems: "start" }}>
        <div>
          <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6 }}>{profile.name} <span style={{ color: "var(--dim)", fontWeight: 400, fontFamily: "JetBrains Mono", fontSize: 11 }}>{profile.formation} · savunma anı</span></div>
          <PitchShape profile={profile} />
          <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 6, lineHeight: 1.5 }}>
            Savunma anı ortalama pozisyonlar. Gölgeli alan = bloğun geri çekildiği derinlik; nokta = oyuncu (forma no).
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <Phase title="Oyun Kurma" stats={profile.buildUp} />
          <Phase title="Savunma" stats={profile.defense} />
          <div style={{ gridColumn: "1 / -1" }}><Phase title="Hücum Koridorları" stats={profile.attack} /></div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
        {/* Oyuncu rolleri */}
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>Oyuncu Taktik Rolleri</div>
          {profile.roles.map((r) => (
            <div key={r.num} className="alrt" style={{ alignItems: "flex-start" }}>
              <span className="ai" style={{ background: r.threat ? "var(--crit)" : "var(--muted)", marginTop: 4 }} />
              <div className="am">
                <b>#{r.num} · {r.role}</b>
                <span className="tm">{r.note}</span>
              </div>
            </div>
          ))}
        </div>
        {/* Sayısal kalıplar */}
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>Tespit Edilen Kalıplar</div>
          {profile.tendencies.map((t, i) => (
            <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 7 }}>
              <span style={{ fontFamily: "JetBrains Mono", fontSize: 10, fontWeight: 700, color: THEM, background: "color-mix(in srgb, var(--high) 14%, transparent)", borderRadius: 5, padding: "2px 6px", flexShrink: 0, whiteSpace: "nowrap" }}>{t.stat}</span>
              <span style={{ fontSize: 11.5, color: "var(--ink)", lineHeight: 1.5 }}>{t.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
