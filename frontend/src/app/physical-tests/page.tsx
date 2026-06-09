"use client";

/**
 * Fiziksel Durum — açık tema (ConsoleShell) genel görünüm panosu.
 *
 * HRV + sprint + CMJ + ACWR yük göstergelerini kadro ısı-haritası olarak
 * birleştirir; takım HRV trendi + hazırlık dağılımı + kritik uyarılar.
 * Detaylı veri girişi / batarya: /physical-tests/entry (koyu panel).
 * Saha tableti: /test-session. DEMO_MODE'da demoSquad'dan deterministik üretim.
 */

import * as React from "react";
import Link from "next/link";
import { demoSquad } from "@/lib/demo-data";
import {
  PROTO_NAME, PROTO_UNIT, loadDerivedRecords, type SavedRecord,
} from "@/lib/derived-tests";
import {
  demoSquadReadiness, LIGHT_VAR, type ReadinessFlag,
} from "@/lib/readiness";
import { ConsoleShell } from "../_console/shell";
import { RiskDonut, LegendRow } from "../_console/viz";

type Band = "Hazır" | "İzlenmeli" | "Riskli";
const BAND_META: Record<Band, { v: string; bg: string }> = {
  "Hazır": { v: "var(--low)", bg: "var(--low-bg)" },
  "İzlenmeli": { v: "var(--mid)", bg: "var(--mid-bg)" },
  "Riskli": { v: "var(--crit)", bg: "var(--crit-bg)" },
};

interface Status {
  shirt: number; name: string; pos: string;
  hrv: number;       // ms (yüksek iyi)
  sprint: number;    // 10m sn (düşük iyi)
  cmj: number;       // cm (yüksek iyi)
  acwr: number;      // akut/kronik
  load: number;      // haftalık iç yük 0..100
  band: Band;
  readiness: number; // 0..100
}

const STATUS: Status[] = demoSquad.slice(0, 16).map((p, i) => {
  const wave = Math.sin((p.player_id + i) * 1.4) * 0.5 + 0.5; // 0..1
  const cond = p.condition;
  const acwr = Math.round((0.85 + (p.risk_score / 100) * 0.78 + wave * 0.1) * 100) / 100;
  const band: Band = p.risk_label === "Kritik" ? "Riskli"
    : p.risk_label === "Yüksek" ? "İzlenmeli"
    : p.risk_label === "Orta" ? (cond >= 82 ? "Hazır" : "İzlenmeli")
    : "Hazır";
  return {
    shirt: p.shirt, name: p.player_name, pos: p.pos_detail,
    hrv: Math.round(58 + (cond - 70) * 0.8 + wave * 10),
    sprint: Math.round((1.70 + ((100 - cond) / 100) * 0.26 + wave * 0.04) * 100) / 100,
    cmj: Math.round(31 + (cond / 100) * 18 + wave * 4),
    acwr,
    load: Math.round(54 + (cond / 100) * 34 + wave * 6),
    band,
    readiness: cond,
  };
});

// Metrik yönüne duyarlı hücre derecesi → renk.
type Tone = "good" | "mid" | "bad";
const TONE: Record<Tone, { v: string; bg: string }> = {
  good: { v: "var(--low)", bg: "var(--low-bg)" },
  mid: { v: "var(--mid)", bg: "var(--mid-bg)" },
  bad: { v: "var(--crit)", bg: "var(--crit-bg)" },
};
function rate(metric: "hrv" | "sprint" | "cmj" | "acwr" | "load", v: number): Tone {
  switch (metric) {
    case "hrv": return v >= 80 ? "good" : v >= 68 ? "mid" : "bad";
    case "sprint": return v <= 1.78 ? "good" : v <= 1.88 ? "mid" : "bad";
    case "cmj": return v >= 42 ? "good" : v >= 35 ? "mid" : "bad";
    case "acwr": return v >= 0.8 && v <= 1.3 ? "good" : v <= 1.5 ? "mid" : "bad";
    case "load": return v <= 75 ? "good" : v <= 85 ? "mid" : "bad";
  }
}

const READY = STATUS.filter((s) => s.band === "Hazır").length;
const WATCH = STATUS.filter((s) => s.band === "İzlenmeli").length;
const RISKY = STATUS.filter((s) => s.band === "Riskli").length;
const AVG_HRV = Math.round(STATUS.reduce((a, s) => a + s.hrv, 0) / STATUS.length);
const AVG_ACWR = Math.round((STATUS.reduce((a, s) => a + s.acwr, 0) / STATUS.length) * 100) / 100;
const FASTEST = STATUS.reduce((b, s) => (s.sprint < b.sprint ? s : b), STATUS[0]);

// Takım ortalama HRV trendi (14 gün) — maç sonrası dip + toparlanma.
const HRV_TREND = [82, 80, 79, 76, 71, 73, 78, 81, 80, 77, 72, 75, 79, AVG_HRV];

// ── Hazırlık Kararı (karar verici) — assess_readiness motorunun kadro çıktısı ──
const READINESS = demoSquadReadiness();
const CANT_PLAY = READINESS.filter((r) => r.decision.light === "kırmızı").length;
const MONITOR = READINESS.filter((r) => r.decision.light === "sarı").length;

function FlagRow({ f }: { f: ReadinessFlag }) {
  const v = LIGHT_VAR[f.severity];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "150px auto 1fr", gap: 10, alignItems: "baseline", fontSize: 12, padding: "5px 0", borderTop: "1px solid var(--line)" }}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: v, flexShrink: 0 }} />
        <b>{f.metric}</b>
      </span>
      <span style={{ fontFamily: "JetBrains Mono", color: v, whiteSpace: "nowrap" }}>{f.value}</span>
      <span style={{ color: "var(--muted)", lineHeight: 1.45 }}>
        {f.action} <span style={{ color: "var(--dim)", fontSize: 11 }}>· eşik {f.threshold} · {f.engine}</span>
      </span>
    </div>
  );
}

// Kadro karar panosu: kırmızı önce; satıra tıkla → o oyuncunun kanıt zinciri.
function ReadinessBoard() {
  const firstRed = READINESS.find((r) => r.decision.light === "kırmızı")?.player.player_id ?? null;
  const [open, setOpen] = React.useState<number | null>(firstRed);
  return (
    <div className="rc" style={{ margin: "0 0 16px", padding: 0, overflow: "hidden" }}>
      {READINESS.map(({ player, decision }, i) => {
        const v = LIGHT_VAR[decision.light];
        const isOpen = open === player.player_id;
        return (
          <div key={player.player_id} style={{ borderTop: i ? "1px solid var(--line)" : undefined }}>
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : player.player_id)}
              style={{ display: "grid", gridTemplateColumns: "auto 1fr auto auto", gap: 12, alignItems: "center", width: "100%", textAlign: "left", padding: "10px 14px", background: isOpen ? "var(--panel2)" : "transparent", border: 0, borderLeft: `3px solid ${v}`, cursor: "pointer", color: "var(--ink)", fontFamily: "inherit" }}
            >
              <span className="pnum">{player.shirt}</span>
              <span style={{ minWidth: 0 }}>
                <span className="nm">{player.player_name}</span>
                <span style={{ color: "var(--muted)", marginLeft: 8, fontSize: 12 }}>{player.pos_detail}</span>
                <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 2 }}>{decision.summary}</div>
              </span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, fontWeight: 700, color: v, textTransform: "uppercase", whiteSpace: "nowrap" }}>
                <span style={{ width: 9, height: 9, borderRadius: "50%", background: v }} />{decision.verdict}
              </span>
              <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--dim)", whiteSpace: "nowrap" }}>
                {decision.red_count > 0 && <span style={{ color: "var(--crit)" }}>{decision.red_count}🔴 </span>}
                {decision.yellow_count > 0 && <span style={{ color: "var(--mid)" }}>{decision.yellow_count}🟡 </span>}
                {isOpen ? "▲" : "▼"}
              </span>
            </button>
            {isOpen && (
              <div style={{ padding: "2px 14px 12px 17px", background: "var(--panel2)" }}>
                {decision.flags.map((f, j) => <FlagRow key={j} f={f} />)}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function HrvTrend({ data }: { data: number[] }) {
  const W = 560, H = 130, padX = 24, padY = 16;
  const n = data.length, iw = W - padX * 2, ih = H - padY * 2;
  const lo = Math.min(...data) - 4, hi = Math.max(...data) + 4;
  const x = (i: number) => padX + (iw * i) / (n - 1);
  const y = (v: number) => padY + ih - (ih * (v - lo)) / (hi - lo);
  const pts = data.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const area = `${padX},${padY + ih} ${pts} ${padX + iw},${padY + ih}`;
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }} preserveAspectRatio="none">
      {[lo, (lo + hi) / 2, hi].map((g, i) => (
        <line key={i} x1={padX} x2={padX + iw} y1={y(g)} y2={y(g)} stroke="var(--line)" strokeWidth={1} strokeDasharray={i === 0 ? "0" : "3 4"} />
      ))}
      <polygon points={area} fill="var(--accent)" opacity={0.08} />
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      {data.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={i === n - 1 ? 4 : 2.5} fill={i === n - 1 ? "var(--accent)" : "var(--accent)"} stroke="var(--white)" strokeWidth={1.5} />)}
    </svg>
  );
}

function Cell({ metric, value, unit }: { metric: "hrv" | "sprint" | "cmj" | "acwr" | "load"; value: number; unit?: string }) {
  const t = TONE[rate(metric, value)];
  return (
    <td className="c">
      <span style={{ display: "inline-block", minWidth: 52, padding: "3px 8px", borderRadius: 7, background: t.bg, color: t.v, fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 12 }}>
        {value}{unit ? ` ${unit}` : ""}
      </span>
    </td>
  );
}

export default function FizikselDurumPage() {
  // Test Hesaplayıcı'da kaydedilen türetilmiş metrikler (localStorage, client-only).
  const [derived, setDerived] = React.useState<SavedRecord[]>([]);
  React.useEffect(() => { setDerived(loadDerivedRecords()); }, []);

  const dist = [
    { label: "Hazır", v: "var(--low)", n: READY },
    { label: "İzlenmeli", v: "var(--mid)", n: WATCH },
    { label: "Riskli", v: "var(--crit)", n: RISKY },
  ];
  const flagged = STATUS.filter((s) => s.band !== "Hazır").sort((a, b) => a.readiness - b.readiness);

  const right = (
    <>
      <div className="rc">
        <h3>Hazırlık Dağılımı <span className="tiny">{STATUS.length} oyuncu</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut segments={dist.map((d) => ({ value: d.n, color: d.v }))} centerLabel={READY} centerSub="hazır" />
          <div style={{ flex: 1, minWidth: 0 }}>
            {dist.map((d) => <LegendRow key={d.label} color={d.v} label={d.label} value={d.n} />)}
          </div>
        </div>
      </div>
      <div className="rc">
        <h3>İzlenecekler <span className="tiny">{flagged.length}</span></h3>
        {flagged.map((s) => {
          const m = BAND_META[s.band];
          return (
            <div className="alrt" key={s.shirt}>
              <span className="ai" style={{ background: m.v }} />
              <div className="am"><b>{s.name}</b> ({s.shirt}) · {s.band.toLowerCase()}
                <span className="tm">HRV {s.hrv} · ACWR {s.acwr.toFixed(2)} · kondisyon {s.readiness}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="rc">
        <h3>Aksiyonlar</h3>
        <Link href="/physical-tests/entry" style={{ display: "block", textAlign: "center", padding: "9px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontWeight: 600, fontSize: 12.5, textDecoration: "none", marginBottom: 8 }}>
          <i className="ti ti-clipboard-data" style={{ marginRight: 6 }} />Detaylı giriş & batarya
        </Link>
        <Link href="/test-session" style={{ display: "block", textAlign: "center", padding: "9px", borderRadius: 9, border: 0, background: "var(--besiktas)", color: "#fff", fontWeight: 700, fontSize: 12.5, textDecoration: "none" }}>
          <i className="ti ti-run" style={{ marginRight: 6 }} />Saha testi başlat
        </Link>
        <Link href="/physical-tests/derive" style={{ display: "block", textAlign: "center", padding: "9px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontWeight: 600, fontSize: 12.5, textDecoration: "none", marginTop: 8 }}>
          <i className="ti ti-calculator" style={{ marginRight: 6 }} />Test hesaplayıcı (FI · RSI · H:Q · RTP)
        </Link>
        <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 10 }}>Son test oturumu: 2026-06-05</div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/physical-tests"
      title="Fiziksel Durum"
      sub="HRV · sprint · yük"
      desc="Kadronun HRV, sprint, sıçrama ve ACWR yük göstergeleri — tek bakışta hazırlık ve risk."
      navBadge={RISKY}
      right={right}
    >
      <div className="kpis">
        <div className="kpi"><div className="kl">Sahaya Hazır</div><div className="kn" style={{ color: "var(--low)" }}>{READY}<span className="pct">/{STATUS.length}</span></div><div className="kd">{WATCH} izlenmeli · {RISKY} riskli</div></div>
        <div className="kpi"><div className="kl">Ort. HRV</div><div className="kn" style={{ color: AVG_HRV >= 78 ? "var(--low)" : "var(--mid)" }}>{AVG_HRV}<span className="pct"> ms</span></div><div className="kd">kalp atış değişkenliği</div></div>
        <div className="kpi"><div className="kl">Ort. ACWR</div><div className="kn" style={{ color: AVG_ACWR > 1.3 ? "var(--high)" : "var(--low)" }}>{AVG_ACWR.toFixed(2)}</div><div className="kd">akut/kronik yük</div></div>
        <div className="kpi"><div className="kl">Karar: Çıkamaz</div><div className="kn" style={{ color: CANT_PLAY ? "var(--crit)" : "var(--low)" }}>{CANT_PLAY}</div><div className="kd">{MONITOR} izle · karar verici</div></div>
        <div className="kpi"><div className="kl">En Hızlı</div><div className="kn" style={{ fontSize: 18 }}>{FASTEST.name.split(" ")[0]}</div><div className="kd">10m {FASTEST.sprint.toFixed(2)}sn</div></div>
      </div>

      <div className="st" style={{ marginTop: 0 }}><h2>Hazırlık Kararı</h2><span className="ep">karar verici · {CANT_PLAY} çıkamaz · {MONITOR} izle · satıra tıkla → gerekçe</span></div>
      <ReadinessBoard />

      <div className="st"><h2>Takım HRV Trendi</h2><span className="ep">son 14 gün · maç sonrası dip</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }}>
        <HrvTrend data={HRV_TREND} />
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8 }}>
          Maç (5. gün) sonrası HRV düştü, toparlanma günleriyle yükseldi. Düşük HRV = yetersiz toparlanma / yüksek stres göstergesi.
        </div>
      </div>

      <div className="st"><h2>Kadro Isı Haritası</h2><span className="ep">yeşil iyi · sarı izle · kırmızı risk</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th><th>Oyuncu</th><th>Mevki</th>
            <th className="c">Hazırlık</th><th className="c">HRV</th><th className="c">Sprint 10m</th>
            <th className="c">CMJ</th><th className="c">ACWR</th><th className="c">Yük</th>
          </tr></thead>
          <tbody>
            {STATUS.map((s) => {
              const m = BAND_META[s.band];
              return (
                <tr key={s.shirt}>
                  <td className="pnum c">{s.shirt}</td>
                  <td><span className="nm">{s.name}</span></td>
                  <td style={{ color: "var(--muted)" }}>{s.pos}</td>
                  <td className="c">
                    <span className="risk" style={{ background: m.bg, color: m.v }}>
                      <span className="rd" style={{ background: m.v }} />{s.band}
                    </span>
                  </td>
                  <Cell metric="hrv" value={s.hrv} />
                  <Cell metric="sprint" value={s.sprint} />
                  <Cell metric="cmj" value={s.cmj} />
                  <Cell metric="acwr" value={s.acwr} />
                  <Cell metric="load" value={s.load} />
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 8 }}>
        HRV ms · Sprint 10m sn (düşük iyi) · CMJ cm · ACWR akut/kronik · Yük haftalık iç yük (0–100). Hücre rengi metriğin yönüne göre.
      </div>

      <div className="st"><h2>Test Hesaplayıcı Kayıtları</h2><span className="ep">{derived.length} kayıt · son girilenler</span></div>
      {derived.length === 0 ? (
        <div className="rc" style={{ margin: 0 }}>
          <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5 }}>
            Henüz türetilmiş test kaydı yok. <Link href="/physical-tests/derive" style={{ color: "var(--accent)", textDecoration: "none" }}>Test Hesaplayıcı</Link>'da
            FI / RSI / H:Q gibi bir metriği hesaplayıp “Kaydet”e bastığında burada listelenir.
          </div>
        </div>
      ) : (
        <div className="tbl">
          <table>
            <thead><tr>
              <th>Oyuncu</th><th>Metrik</th><th className="r">Değer</th>
              <th>Özet</th><th className="c">Tarih</th>
            </tr></thead>
            <tbody>
              {[...derived].sort((a, b) => b.id - a.id).slice(0, 12).map((r) => (
                <tr key={r.id}>
                  <td><span className="nm">{r.player_name}</span></td>
                  <td style={{ color: "var(--muted)" }}>{PROTO_NAME[r.protocol] ?? r.protocol}</td>
                  <td className="r" style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>
                    {r.value}{PROTO_UNIT[r.protocol] ? ` ${PROTO_UNIT[r.protocol]}` : ""}
                  </td>
                  <td style={{ color: "var(--muted)", fontSize: 12 }}>{r.label}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{r.test_date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
        <i className="ti ti-calculator" />
        Bu kayıtlar Test Hesaplayıcı'dan gelir (demo: tarayıcıda saklanır).
        <Link href="/physical-tests/derive" style={{ marginLeft: "auto", color: "var(--accent)", textDecoration: "none" }}>Test Hesaplayıcı →</Link>
      </div>
    </ConsoleShell>
  );
}
