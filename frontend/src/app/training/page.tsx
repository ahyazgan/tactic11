"use client";

/**
 * Antrenman Planı — maça özel haftalık mikro-döngü (microcycle). ConsoleShell çatısında.
 *
 * DEMO_MODE açıkken canlı API'ye (/leagues, /teams) hiç dokunmaz; bu dosyada inline
 * tanımlı dolu mock veriyle Beşiktaş'ın "Antalyaspor" maçına hazırlık programını gösterir:
 * haftalık yük eğrisi (SVG), gün-gün antrenman planı, antrenman odakları (rakip zaaflarına
 * göre) ve oyuncu-bazlı yük/uygunluk tablosu. Backend bağlanınca lig→takım seçimine döner.
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { ConsoleShell } from "../_console/shell";
import { RiskDonut, LegendRow } from "../_console/viz";

interface League { external_id: number; name: string }
interface Team { external_id: number; name: string }

// --------------------------------------------------------------------------- //
// DEMO VERİSİ (yalnızca bu sayfaya özel, inline)
// --------------------------------------------------------------------------- //

const DEMO_CLUB = "Beşiktaş";
const DEMO_OPPONENT = "Antalyaspor";

/** Maç gününe (MG) göre konumlandırılmış mikro-döngü. MG-1 = maçtan bir gün önce. */
interface TrainingDay {
  day: string;          // "Pzt"
  label: string;        // "MG-4"
  type: string;         // "Yüklenme" | "Toparlanma" | "Taktik" | ...
  focus: string;        // antrenman teması
  load: number;         // 0-100 planlanan iç yük (RPE × süre normalize)
  minutes: number;      // saha süresi (dk)
  intensity: "Yüksek" | "Orta" | "Düşük" | "Dinlenme";
}

const demoWeek: TrainingDay[] = [
  { day: "Pzt", label: "MG+1", type: "Toparlanma", focus: "Rejeneresyon + havuz/masaj (oynayanlar)", load: 22, minutes: 35, intensity: "Düşük" },
  { day: "Sal", label: "MG-5", type: "İzin", focus: "Dinlenme günü — bireysel mobilite", load: 0, minutes: 0, intensity: "Dinlenme" },
  { day: "Çar", label: "MG-4", type: "Yüklenme", focus: "Yüksek hacim: dayanıklılık + kuvvet bloğu", load: 88, minutes: 95, intensity: "Yüksek" },
  { day: "Per", label: "MG-3", type: "Yüklenme", focus: "Pozisyon oyunu + yön değiştirme (COD)", load: 74, minutes: 85, intensity: "Yüksek" },
  { day: "Cum", label: "MG-2", type: "Taktik", focus: "Maç senaryoları: sağ kanat 1v1 + duran top", load: 52, minutes: 70, intensity: "Orta" },
  { day: "Cmt", label: "MG-1", type: "Aktivasyon", focus: "Hız aktivasyonu + son taktik provası", load: 30, minutes: 45, intensity: "Düşük" },
  { day: "Paz", label: "MG", type: "Maç", focus: `${DEMO_CLUB} — ${DEMO_OPPONENT} · 20:00`, load: 100, minutes: 90, intensity: "Yüksek" },
];

/** Maça özel antrenman odakları — rakip zaaflarına bağlanır. */
interface TrainingFocus {
  title: string;
  detail: string;
  block: string;     // hangi antrenman gününde
  priority: "yüksek" | "orta";
}

const demoFocus: TrainingFocus[] = [
  { title: "Sağ kanat 1v1 bitiriciliği", detail: "Rakip sağ bek arkası maç başına ort. 6 kez açılıyor. Milot Rashica için izole 1v1 + içeri kat etme tekrarları.", block: "MG-2 · Taktik", priority: "yüksek" },
  { title: "Duran top — far-post varyasyonu", detail: "Rakip zonal savunmada ikinci direği örtemiyor (son 8 maçta 4 gol yedi). Köşelerde far-post koşu kalıbı çalışıldı.", block: "MG-2 · Taktik", priority: "yüksek" },
  { title: "Geçiş savunması (ön libero)", detail: "İlk 15 dk yüksek pres bekleniyor. Top kaybı sonrası ön libero koruması ve geri pres senkronu.", block: "MG-3 · Pozisyon", priority: "orta" },
  { title: "Geç dakika tempo bankası", detail: "Rakip 75. dk sonrası tempo düşürüyor. Tekrarlı sprint dayanıklılığı (RSA) ile son 15 dk üstünlüğü hedefleniyor.", block: "MG-4 · Yüklenme", priority: "orta" },
];

/** Oyuncu-bazlı haftalık yük + maça uygunluk. ACWR = akut/kronik iş yükü oranı. */
type Avail = "Hazır" | "Yönetiliyor" | "Şüpheli" | "Yok";
interface PlayerLoad {
  shirt: number;
  name: string;
  pos: string;
  weekLoad: number;   // 0-100 planlanan haftalık iç yük
  acwr: number;       // 0.6 - 1.8 ideal ~0.8-1.3
  availability: Avail;
  note: string;
}

const demoLoads: PlayerLoad[] = [
  { shirt: 1, name: "Ersin Destanoğlu", pos: "Kaleci", weekLoad: 58, acwr: 0.95, availability: "Hazır", note: "Kaleci özel programı" },
  { shirt: 2, name: "Amir Murillo", pos: "Sağ Bek", weekLoad: 79, acwr: 1.18, availability: "Hazır", note: "Tam katılım" },
  { shirt: 4, name: "Tiago Djaló", pos: "Stoper", weekLoad: 71, acwr: 1.42, availability: "Yönetiliyor", note: "MG-4 hacmi %30 azaltıldı" },
  { shirt: 5, name: "Emmanuel Agbadou", pos: "Stoper", weekLoad: 84, acwr: 1.05, availability: "Hazır", note: "Tam katılım" },
  { shirt: 3, name: "Rıdvan Yılmaz", pos: "Sol Bek", weekLoad: 68, acwr: 1.46, availability: "Yönetiliyor", note: "Sprint hacmi sınırlı" },
  { shirt: 6, name: "Wilfred Ndidi", pos: "Ön Libero", weekLoad: 82, acwr: 1.15, availability: "Hazır", note: "Tam katılım" },
  { shirt: 8, name: "Salih Uçan", pos: "Merkez OS", weekLoad: 86, acwr: 1.02, availability: "Hazır", note: "Tam katılım" },
  { shirt: 10, name: "Orkun Kökçü", pos: "10 Numara", weekLoad: 41, acwr: 1.62, availability: "Şüpheli", note: "Arka adale — MG-4/3 bireysel, MG-1 testi" },
  { shirt: 11, name: "Cengiz Ünder", pos: "Sol Kanat", weekLoad: 77, acwr: 1.21, availability: "Hazır", note: "Tam katılım" },
  { shirt: 9, name: "Oh Hyeon-Gyu", pos: "Santrfor", weekLoad: 83, acwr: 1.08, availability: "Hazır", note: "Bitiricilik ekstra blok" },
  { shirt: 7, name: "Milot Rashica", pos: "Sağ Kanat", weekLoad: 88, acwr: 1.12, availability: "Hazır", note: "1v1 odak — maçın anahtarı" },
  { shirt: 15, name: "Felix Uduokhai", pos: "Stoper", weekLoad: 62, acwr: 1.44, availability: "Yönetiliyor", note: "Yaş + yük; rotasyon adayı" },
  { shirt: 14, name: "Junior Olaitan", pos: "10 Numara", weekLoad: 80, acwr: 0.98, availability: "Hazır", note: "Caner'in yedeği — taze tutuluyor" },
  { shirt: 17, name: "Jota Silva", pos: "Sol Kanat", weekLoad: 73, acwr: 0.88, availability: "Hazır", note: "Rotasyon için ideal" },
  { shirt: 24, name: "Taylan Bulut", pos: "Sağ Bek", weekLoad: 70, acwr: 0.91, availability: "Hazır", note: "Rotasyon için ideal" },
  { shirt: 19, name: "El Bilal Touré", pos: "Santrfor", weekLoad: 64, acwr: 1.38, availability: "Yönetiliyor", note: "Plan B hava topu hedefi" },
];

const WEEK_TOTAL = demoLoads.reduce((a, p) => a + p.weekLoad, 0);
const DEMO_SESSIONS = demoWeek.filter((d) => d.load > 0 && d.type !== "Maç").length;
const READY_COUNT = demoLoads.filter((p) => p.availability === "Hazır").length;
const PEAK_LOAD = Math.max(...demoWeek.map((d) => d.load));
const AVG_ACWR = Math.round((demoLoads.reduce((a, p) => a + p.acwr, 0) / demoLoads.length) * 100) / 100;
const SHARP = demoLoads.filter((p) => p.acwr >= 0.8 && p.acwr <= 1.3).length;

const intensityColor: Record<string, string> = {
  "Yüksek": "var(--high)",
  "Orta": "var(--mid)",
  "Düşük": "var(--low)",
  "Dinlenme": "var(--dim)",
};

const availMeta: Record<Avail, { v: string; bg: string }> = {
  "Hazır": { v: "var(--low)", bg: "var(--low-bg)" },
  "Yönetiliyor": { v: "var(--mid)", bg: "var(--mid-bg)" },
  "Şüpheli": { v: "var(--high)", bg: "var(--high-bg)" },
  "Yok": { v: "var(--crit)", bg: "var(--crit-bg)" },
};

function acwrColor(v: number): string {
  if (v > 1.5) return "var(--crit)";
  if (v > 1.3) return "var(--high)";
  if (v < 0.8) return "var(--mid)";
  return "var(--low)";
}

/** Haftalık yük eğrisi — saf inline SVG (uydurma kütüphane yok). */
function LoadCurve({ days }: { days: TrainingDay[] }) {
  const W = 560, H = 150, padX = 26, padY = 18;
  const n = days.length;
  const innerW = W - padX * 2;
  const innerH = H - padY * 2;
  const x = (i: number) => padX + (innerW * i) / (n - 1);
  const y = (v: number) => padY + innerH - (innerH * v) / 100;
  const pts = days.map((d, i) => `${x(i)},${y(d.load)}`).join(" ");
  const area = `${padX},${padY + innerH} ${pts} ${padX + innerW},${padY + innerH}`;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }} preserveAspectRatio="none">
      {/* yatay ızgara */}
      {[0, 25, 50, 75, 100].map((g) => (
        <line key={g} x1={padX} x2={padX + innerW} y1={y(g)} y2={y(g)} stroke="var(--line)" strokeWidth={1} strokeDasharray={g === 0 ? "0" : "3 4"} />
      ))}
      <polygon points={area} fill="var(--accent)" opacity={0.08} />
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      {days.map((d, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(d.load)} r={d.type === "Maç" ? 5 : 3.5} fill={intensityColor[d.intensity]} stroke="var(--white)" strokeWidth={1.5} />
          <text x={x(i)} y={H - 3} textAnchor="middle" fill="var(--dim)" style={{ fontSize: 9.5 }}>{d.label}</text>
        </g>
      ))}
    </svg>
  );
}

const selStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 9px",
  borderRadius: "7px",
  fontFamily: "inherit",
  minWidth: "140px",
};

function Sel({ value, onChange, options, placeholder, disabled }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; placeholder: string; disabled?: boolean;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} style={{ ...selStyle, opacity: disabled ? 0.5 : 1 }}>
      <option value="">{placeholder}</option>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export default function TrainingConsolePage() {
  const [leagueA, setLeagueA] = React.useState("");
  const [leagueB, setLeagueB] = React.useState("");
  const [teamA, setTeamA] = React.useState("");
  const [teamB, setTeamB] = React.useState("");

  // DEMO_MODE açıkken canlı API'ye hiç dokunma (boş selector / spinner olmaz).
  const { data: leagues } = useSWR<League[]>(DEMO_MODE ? null : "/leagues", apiFetch, { shouldRetryOnError: false });
  const { data: teamsA } = useSWR<Team[]>(DEMO_MODE || !leagueA ? null : `/teams/${leagueA}`, apiFetch, { shouldRetryOnError: false });
  const { data: teamsB } = useSWR<Team[]>(DEMO_MODE || !leagueB ? null : `/teams/${leagueB}`, apiFetch, { shouldRetryOnError: false });
  const lgOpts = leagues?.map((l) => ({ value: String(l.external_id), label: l.name })) ?? [];
  const ready = teamA && teamB && teamA !== teamB;

  // İçerik dağılımı (sağ kolon donut): gün tiplerine göre.
  const intensityDist = [
    { label: "Yüksek", v: "var(--high)", n: demoWeek.filter((d) => d.intensity === "Yüksek").length },
    { label: "Orta", v: "var(--mid)", n: demoWeek.filter((d) => d.intensity === "Orta").length },
    { label: "Düşük", v: "var(--low)", n: demoWeek.filter((d) => d.intensity === "Düşük").length },
    { label: "Dinlenme", v: "var(--dim)", n: demoWeek.filter((d) => d.intensity === "Dinlenme").length },
  ];
  const flagged = demoLoads.filter((p) => p.acwr > 1.3);

  const demoRight = (
    <>
      <div className="rc">
        <h3>Sıradaki Maç <span className="tiny">Süper Lig — 34. Hafta</span></h3>
        <div className="nm-vs"><span className="t">{DEMO_CLUB}</span><span className="x">vs</span><span className="t away">{DEMO_OPPONENT}</span></div>
        <div className="nm-when">2026-06-08 · 20:00 · ev sahibi</div>
        <div className="stat"><span>Programa kalan</span><span className="sv">6 antrenman</span></div>
        <div className="stat"><span>Hazırlık fazı</span><span className="sv" style={{ color: "var(--mid)" }}>MG-2 · Taktik</span></div>
        <div className="stat"><span>Sahaya hazır</span><span className="sv" style={{ color: "var(--low)" }}>{READY_COUNT}/{demoLoads.length}</span></div>
      </div>

      <div className="rc">
        <h3>Yük Dağılımı <span className="tiny">7 gün</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut segments={intensityDist.map((d) => ({ value: d.n, color: d.v }))} centerLabel={DEMO_SESSIONS} centerSub="seans" />
          <div style={{ flex: 1, minWidth: 0 }}>
            {intensityDist.map((d) => <LegendRow key={d.label} color={d.v} label={d.label} value={d.n} />)}
          </div>
        </div>
      </div>

      <div className="rc">
        <h3>Yük Uyarıları <span className="tiny">{flagged.length} oyuncu</span></h3>
        {flagged.length === 0 && <div style={{ fontSize: "12px", color: "var(--dim)" }}>ACWR eşik aşan oyuncu yok.</div>}
        {flagged.map((p) => {
          const c = acwrColor(p.acwr);
          return (
            <div className="alrt" key={p.shirt}>
              <span className="ai" style={{ background: c }} />
              <div className="am"><b>{p.name}</b> ({p.shirt}) · {p.availability.toLowerCase()}
                <span className="tm">ACWR {p.acwr.toFixed(2)} — {p.note}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="rc">
        <h3>Antrenörün Notu</h3>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55 }}>
          MG-2'de yükü düşürüp taktik provasına ağırlık verdik. Caner (10) şüpheli — MG-1 sabah testine göre Berkay (14) ilk 11'e hazır tutuluyor.
        </div>
      </div>
    </>
  );

  const liveRight = (
    <div className="rc">
      <h3>Nasıl Çalışır?</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
        Her iki taraf için lig→takım seç. Plan, rakibin zaaflarına göre haftalık antrenman odağını önerir.
      </div>
    </div>
  );

  return (
    <ConsoleShell
      active="/training"
      title="Antrenman Planı"
      sub={DEMO_MODE ? "Maça özel haftalık program" : "Maça özel hazırlık"}
      desc={DEMO_MODE
        ? `${DEMO_CLUB} — ${DEMO_OPPONENT} maçı için 7 günlük mikro-döngü: yük eğrisi, gün-gün plan ve oyuncu uygunluğu.`
        : "Bizim takım + rakip seç → maça özel antrenman planı oluştur."}
      right={DEMO_MODE ? demoRight : liveRight}
    >
      {DEMO_MODE ? (
        <>
          <div className="kpis">
            <div className="kpi"><div className="kl">Haftalık Yük</div><div className="kn">{WEEK_TOTAL}</div><div className="kd">birim · 16 oyuncu</div></div>
            <div className="kpi"><div className="kl">Antrenman</div><div className="kn">{DEMO_SESSIONS}</div><div className="kd">saha seansı + 1 izin</div></div>
            <div className="kpi"><div className="kl">Zirve Yük</div><div className="kn" style={{ color: "var(--high)" }}>{PEAK_LOAD}<span className="pct">%</span></div><div className="kd">MG-4 yüklenme günü</div></div>
            <div className="kpi"><div className="kl">Ort. ACWR</div><div className="kn" style={{ color: acwrColor(AVG_ACWR) }}>{AVG_ACWR.toFixed(2)}</div><div className="kd">{SHARP} oyuncu ideal banttta</div></div>
            <div className="kpi"><div className="kl">Sahaya Hazır</div><div className="kn" style={{ color: "var(--low)" }}>{READY_COUNT}<span className="pct">/{demoLoads.length}</span></div><div className="kd">tam katılım</div></div>
          </div>

          <div className="st" style={{ marginTop: 0 }}><h2>Haftalık Yük Eğrisi</h2><span className="ep">planlanan iç yük</span></div>
          <div className="rc" style={{ margin: "0 0 16px" }}>
            <LoadCurve days={demoWeek} />
            <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
              {intensityDist.filter((d) => d.label !== "Dinlenme").map((d) => (
                <span key={d.label} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)" }}>
                  <span style={{ width: 9, height: 9, borderRadius: 3, background: d.v }} /> {d.label} yoğunluk
                </span>
              ))}
              <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--dim)" }}>Tipik tepe MG-4, maça doğru kademeli düşüş (tapering).</span>
            </div>
          </div>

          <div className="st"><h2>Haftalık Program</h2><span className="ep">mikro-döngü · MG = maç günü</span></div>
          <div className="tbl" style={{ marginBottom: 16 }}>
            <table>
              <thead><tr>
                <th>Gün</th><th className="c">Faz</th><th>Tür</th><th>Odak</th>
                <th className="c">Süre</th><th className="c">Yoğunluk</th><th className="r">Yük</th>
              </tr></thead>
              <tbody>
                {demoWeek.map((d) => {
                  const ic = intensityColor[d.intensity];
                  const isMatch = d.type === "Maç";
                  return (
                    <tr key={d.label} style={isMatch ? { background: "var(--accent-lt)" } : undefined}>
                      <td><span className="nm">{d.day}</span></td>
                      <td className="c"><span className="pos">{d.label}</span></td>
                      <td style={{ fontWeight: isMatch ? 700 : 500, color: isMatch ? "var(--accent)" : "var(--ink)" }}>{d.type}</td>
                      <td style={{ color: "var(--muted)" }}>{d.focus}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{d.minutes ? `${d.minutes}'` : "—"}</td>
                      <td className="c">
                        <span className="risk" style={{ color: ic }}><span className="rd" style={{ background: ic, boxShadow: `0 0 7px ${ic}` }} />{d.intensity}</span>
                      </td>
                      <td className="r">
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
                          <span className="cond" style={{ width: 44 }}><i style={{ width: `${d.load}%`, background: ic }} /></span>
                          <span style={{ fontFamily: "JetBrains Mono", color: ic, minWidth: 24 }}>{d.load}</span>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="st"><h2>Maça Özel Antrenman Odakları</h2><span className="ep">{DEMO_OPPONENT} zaaflarına göre</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
            {demoFocus.map((f, i) => {
              const sv = f.priority === "yüksek" ? "var(--crit)" : "var(--mid)";
              return (
                <div className="rc" key={i} style={{ margin: 0, borderTop: `2px solid ${sv}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                    <b style={{ fontSize: 12.5 }}>{f.title}</b>
                    <span style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.5, color: sv }}>{f.priority}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5, marginBottom: 8 }}>{f.detail}</div>
                  <div style={{ fontSize: 11, color: "var(--dim)", borderTop: "1px solid var(--line)", paddingTop: 6 }}>
                    <span style={{ textTransform: "uppercase", fontSize: 9.5, letterSpacing: 0.5 }}>Blok · </span>{f.block}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="st"><h2>Oyuncu Yük & Uygunluk</h2><span className="ep">ACWR · akut/kronik yük oranı</span></div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th className="c">#</th><th>Oyuncu</th><th>Mevki</th>
                <th className="c">Haftalık Yük</th><th className="c">ACWR</th><th className="c">Uygunluk</th><th>Not</th>
              </tr></thead>
              <tbody>
                {demoLoads.map((p) => {
                  const ac = acwrColor(p.acwr);
                  const am = availMeta[p.availability];
                  return (
                    <tr key={p.shirt}>
                      <td className="pnum c">{p.shirt}</td>
                      <td><span className="nm">{p.name}</span></td>
                      <td style={{ color: "var(--muted)" }}>{p.pos}</td>
                      <td className="c">
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, justifyContent: "center" }}>
                          <span className="cond"><i style={{ width: `${p.weekLoad}%`, background: p.weekLoad >= 80 ? "var(--high)" : p.weekLoad >= 60 ? "var(--mid)" : "var(--low)" }} /></span>
                          <span style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11 }}>{p.weekLoad}</span>
                        </span>
                      </td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: ac }}>{p.acwr.toFixed(2)}</td>
                      <td className="c">
                        <span className="risk" style={{ background: am.bg, color: am.v }}>
                          <span className="rd" style={{ background: am.v }} />{p.availability}
                        </span>
                      </td>
                      <td style={{ color: "var(--dim)", fontSize: 11.5 }}>{p.note}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <div className="st" style={{ marginTop: 0 }}><h2>Takım + Rakip Seç</h2></div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--muted)", marginBottom: 6 }}>Bizim takım</div>
              <div style={{ display: "flex", gap: 6 }}>
                <Sel value={leagueA} onChange={(x) => { setLeagueA(x); setTeamA(""); }} options={lgOpts} placeholder="Lig" />
                <Sel value={teamA} onChange={setTeamA} options={teamsA?.map((t) => ({ value: String(t.external_id), label: t.name })) ?? []} placeholder="Takım" disabled={!leagueA} />
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--muted)", marginBottom: 6 }}>Rakip</div>
              <div style={{ display: "flex", gap: 6 }}>
                <Sel value={leagueB} onChange={(x) => { setLeagueB(x); setTeamB(""); }} options={lgOpts} placeholder="Lig" />
                <Sel value={teamB} onChange={setTeamB} options={teamsB?.map((t) => ({ value: String(t.external_id), label: t.name })) ?? []} placeholder="Takım" disabled={!leagueB} />
              </div>
            </div>
          </div>

          <div className="rc" style={{ margin: 0 }}>
            {ready ? (
              <Link href={`/teams/${teamA}/training-plan?opponent_id=${teamB}`} style={{ display: "inline-block", fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.5, padding: "8px 16px", borderRadius: 7, border: "1px solid var(--line)", color: "#fff", background: "var(--besiktas)", textDecoration: "none", fontWeight: 600 }}>
                Plan oluştur →
              </Link>
            ) : (
              <span style={{ display: "inline-block", fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.5, padding: "8px 16px", borderRadius: 7, border: "1px solid var(--line)", color: "var(--dim)", opacity: 0.6 }}>
                Plan oluştur → (iki farklı takım seç)
              </span>
            )}
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
