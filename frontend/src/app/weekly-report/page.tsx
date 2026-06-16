"use client";

/**
 * Haftalık Rapor — direktöre hazır tek-sayfa digest. ConsoleShell, FM26 açık tema.
 *
 * Veri-güdümlü: sağlık/yük squadReadiness motorundan, maç + VAEP/90 demoLive'dan
 * türetilir. Özellikler: hafta seçici (geçmiş haftalar), önceki haftaya kıyas (Δ),
 * mini grafikler (sparkline/bar), düzenlenebilir TD notu, rapor şablonu (bölüm
 * aç/kapa) ve tarayıcı-içi PDF (window.print). Backend açılınca app/api/reports.py
 * (reportlab) + scheduler + e-posta'ya bağlanır.
 */

import * as React from "react";
import useSWR from "swr";
import { ConsoleShell } from "../_console/shell";
import { InsightFeed } from "../_console/insights";
import { weeklyInsights } from "@/lib/weekly-insights";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoLive, DEMO_CLUB, DEMO_OPPONENT } from "@/lib/demo-data";
import { squadReadiness, type ReadinessDecision } from "@/lib/readiness";
import { loadSessions, type LoadSession } from "@/lib/load";
import { loadWellness, type WellnessEntry } from "@/lib/wellness";
import { loadDerivedRecords, type SavedRecord } from "@/lib/derived-tests";

const NOTE_KEY = "manager2_weekly_note"; // TD notu (hafta no eklenir) localStorage
const TPL_KEY = "manager2_weekly_template"; // rapor şablonu (bölüm aç/kapa)

// ── Demo trend serileri (sparkline) — backend'de gerçek geçmişten beslenecek ──
const WEEK_LOAD = [62, 78, 85, 88, 70, 54, 0]; // MG-6…MG iç yük (AU%); zirve MG-4
const XG_TREND = [1.55, 0.88, 1.63, 1.06, 2.41, 1.84, 1.22]; // son 7 maç xG (lehte)

const fmt2 = (n: number) => (Math.round(n * 100) / 100).toFixed(2);
const sgn = (n: number, d = 0) => (n >= 0 ? "+" : "") + n.toFixed(d);

/** Karar flag'lerinden ACWR sayısal değerini çek (ör. "1.54" → 1.54). */
interface WeeklyDigestResponse {
  summary: string;
  output: {
    league_external_id: number;
    lookback_days?: number;
    teams_analyzed?: number;
    [k: string]: unknown;
  };
}

const DIGEST_LEAGUE_ID = 203;  // varsayılan Süper Lig — UI dropdown ileride

function BackendDigestPanel(): React.ReactElement | null {
  const apiPath = !DEMO_MODE
    ? `/admin/leagues/${DIGEST_LEAGUE_ID}/weekly-digest?lookback_days=7`
    : null;
  const { data, error, isLoading } = useSWR<WeeklyDigestResponse>(
    apiPath, apiFetch, { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  if (DEMO_MODE) return null;  // demo'da gizle (asıl sayfa zaten dolu)
  if (isLoading) {
    return (
      <div className="rc" style={{ marginBottom: 16, padding: "10px 14px" }}>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>
          Backend digest yükleniyor…
        </span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="rc" style={{ marginBottom: 16, padding: "10px 14px",
        borderLeft: "3px solid var(--high)" }}>
        <span style={{ color: "var(--muted)", fontSize: 12 }}>
          Backend digest yüklenemedi (lig {DIGEST_LEAGUE_ID})
        </span>
      </div>
    );
  }
  if (!data) return null;
  return (
    <div className="rc" style={{
      marginBottom: 16, padding: "12px 16px",
      borderLeft: "3px solid var(--accent)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8,
        marginBottom: 6 }}>
        <span style={{ fontSize: 14 }}>📰</span>
        <h3 style={{ fontSize: 11.5, textTransform: "uppercase",
          letterSpacing: 0.7, color: "var(--muted)", margin: 0,
          fontWeight: 700 }}>Backend Lig Digest</h3>
        <span style={{ marginLeft: "auto", fontSize: 10,
          color: "var(--dim)" }}>
          lig {data.output.league_external_id} · {data.output.teams_analyzed ?? "?"} takım
        </span>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.6 }}>
        {data.summary}
      </div>
    </div>
  );
}

function acwrOf(decision: ReadinessDecision): number | null {
  const f = decision.flags.find((x) => x.metric === "ACWR");
  if (!f) return null;
  const v = parseFloat(f.value);
  return Number.isFinite(v) ? v : null;
}

// ── Hafta verisi modeli ───────────────────────────────────────────────────
interface WeekData {
  no: number; range: string; oppLabel: string; score: [number, number];
  xgF: number; xgA: number;
  matchLines: string[];
  ready: number; total: number; risky: number; criticalName: string; avgAcwr: number; highAcwr: number;
  perfLines: string[];
}

// Geçmiş haftalar — statik anlık görüntü (backend'de rapor kaydından gelir).
const WEEK_32: WeekData = {
  no: 32, range: "19–25 May", oppLabel: "Gaziantep FK (E)", score: [3, 1], xgF: 2.41, xgA: 1.02,
  matchLines: [
    "Beşiktaş 3–1 Gaziantep FK (32. Hafta) — galibiyet.",
    "xG 2.41–1.02 (fark +1.39); oyunun kontrolü baştan sona bizde.",
    "23', 51', 67' goller; 78' yenilen tek gol duran toptan.",
  ],
  ready: 17, total: 24, risky: 1, criticalName: "Emmanuel Agbadou", avgAcwr: 1.19, highAcwr: 2,
  perfLines: [
    "Oh Hyeon-Gyu VAEP/90 0.51 — 2 gol katkısı.",
    "Milot Rashica 3 anahtar pas, sağ kanat üretimin merkezinde.",
    "Pres yoğunluğu (PPDA) sezon ortalamasının altında — agresif hafta.",
  ],
};
const WEEK_33: WeekData = {
  no: 33, range: "26 May–01 Haz", oppLabel: "Konyaspor (D)", score: [2, 0], xgF: 1.84, xgA: 0.71,
  matchLines: [
    "Beşiktaş 2–0 Konyaspor (33. Hafta, deplasman) — galibiyet.",
    "xG 1.84–0.71 (fark +1.13); deplasmanda verimli ve kontrollü.",
    "34', 72' goller; gol yemeden (clean sheet) tamamlandı.",
  ],
  ready: 18, total: 24, risky: 2, criticalName: "Orkun Kökçü", avgAcwr: 1.22, highAcwr: 3,
  perfLines: [
    "Jota Silva VAEP/90 0.44 — kanatta etkili.",
    "Wilfred Ndidi orta sahada top kazanımında lider.",
    "İkinci yarı tempo korundu; geç gol güvence getirdi.",
  ],
};

// ── Mini görselleştirmeler ────────────────────────────────────────────────
function Sparkline({ data, color = "var(--accent)", w = 96, h = 28 }: { data: number[]; color?: string; w?: number; h?: number }) {
  const lo = Math.min(...data), hi = Math.max(...data);
  const span = hi - lo || 1;
  const x = (i: number) => (data.length <= 1 ? w / 2 : (i / (data.length - 1)) * (w - 4) + 2);
  const y = (v: number) => h - 3 - ((v - lo) / span) * (h - 6);
  const pts = data.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} style={{ display: "block" }} aria-hidden="true">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(data.length - 1)} cy={y(data[data.length - 1])} r={2.6} fill={color} />
    </svg>
  );
}

function MiniBars({ data, color = "var(--accent)", w = 96, h = 28 }: { data: number[]; color?: string; w?: number; h?: number }) {
  const hi = Math.max(...data, 1);
  const bw = (w - (data.length - 1) * 3) / data.length;
  return (
    <svg width={w} height={h} style={{ display: "block" }} aria-hidden="true">
      {data.map((v, i) => {
        const bh = Math.max(2, (v / hi) * (h - 4));
        return <rect key={i} x={i * (bw + 3)} y={h - bh} width={bw} height={bh} rx={1.5} fill={color} opacity={v === hi ? 1 : 0.5} />;
      })}
    </svg>
  );
}

/** Δ rozeti: yön + iyi/kötü renk. goodUp=false ise artış kötüdür (ör. risk, ACWR). */
function Delta({ now, prev, goodUp = true, digits = 0 }: { now: number; prev: number; goodUp?: boolean; digits?: number }) {
  const d = Math.round((now - prev) * 10 ** digits) / 10 ** digits;
  if (Math.abs(d) < 10 ** -digits / 2) return <span style={{ color: "var(--dim)", fontSize: 11, fontWeight: 600 }}>±0</span>;
  const up = d > 0;
  const good = up === goodUp;
  return (
    <span style={{ color: good ? "var(--low)" : "var(--crit)", fontSize: 11, fontWeight: 700 }}>
      {up ? "▲" : "▼"} {Math.abs(d).toFixed(digits)}
    </span>
  );
}

interface Section { key: string; icon: string; title: string; tone: string; lines: string[]; spark?: React.ReactNode }

const RECIPIENTS = ["Spor Direktörü", "Başkan Yardımcısı", "Teknik Ekip (3)"];
const HISTORY = [
  { week: "31. Hafta — 25 May", status: "Gönderildi" },
  { week: "32. Hafta — 01 Haz", status: "Gönderildi" },
  { week: "33. Hafta — 08 Haz", status: "Gönderildi" },
];

export default function WeeklyReportPage() {
  const [derived, setDerived] = React.useState<SavedRecord[]>([]);
  const [loads, setLoads] = React.useState<LoadSession[]>([]);
  const [wellness, setWellness] = React.useState<WellnessEntry[]>([]);
  const [sent, setSent] = React.useState(false);
  const [note, setNote] = React.useState("");
  const [weekIdx, setWeekIdx] = React.useState(2); // varsayılan: en güncel hafta
  const [tpl, setTpl] = React.useState<Record<string, boolean>>({ mac: true, saglik: true, antrenman: true, performans: true });

  React.useEffect(() => {
    setDerived(loadDerivedRecords());
    setLoads(loadSessions());
    setWellness(loadWellness());
    try {
      const t = window.localStorage.getItem(TPL_KEY);
      if (t) setTpl((prev) => ({ ...prev, ...JSON.parse(t) }));
    } catch { /* yok say */ }
  }, []);

  // ── Bu haftanın (34.) sağlık & performansı: gerçek motordan türet ──
  const rows = React.useMemo(() => squadReadiness(derived, loads, wellness), [derived, loads, wellness]);
  const total = rows.length;
  const ready = rows.filter((r) => r.decision.light === "yeşil").length;
  const risky = rows.filter((r) => r.decision.light === "kırmızı").length;
  const criticalNames = rows.filter((r) => r.decision.light === "kırmızı").slice(0, 3).map((r) => r.player.player_name);
  const acwrVals = rows.map((r) => acwrOf(r.decision)).filter((v): v is number => v != null);
  const avgAcwr = acwrVals.length ? acwrVals.reduce((a, b) => a + b, 0) / acwrVals.length : 0;
  const highAcwr = acwrVals.filter((v) => v > 1.3).length;

  const goals = demoLive.events.filter((e) => e.type === "gol");
  const xgDiff34 = demoLive.homeXg - demoLive.awayXg;
  const outfield = demoLive.lineup.filter((p) => p.pos !== "GK");
  const topVaep = [...outfield].sort((a, b) => b.vaepPer90 - a.vaepPer90)[0];
  const impactSub = outfield.find((p) => p.subbedInMinute != null);

  const week34: WeekData = {
    no: 34, range: "02–08 Haziran", oppLabel: `${DEMO_OPPONENT} (E)`,
    score: [demoLive.score[0], demoLive.score[1]], xgF: demoLive.homeXg, xgA: demoLive.awayXg,
    matchLines: [
      `${demoLive.home} ${demoLive.score[0]}–${demoLive.score[1]} ${demoLive.away} (34. Hafta) — ${demoLive.score[0] === demoLive.score[1] ? "beraberlik" : demoLive.score[0] > demoLive.score[1] ? "galibiyet" : "mağlubiyet"}.`,
      `xG ${fmt2(demoLive.homeXg)}–${fmt2(demoLive.awayXg)} (fark ${sgn(xgDiff34, 2)}); momentum maç sonunda ${demoLive.momentumHolder}'da.`,
      ...goals.map((g) => `${g.minute}' ${g.team === "home" ? demoLive.home : demoLive.away}: ${g.text.replace(/^GOL!\s*/, "")}`),
    ],
    ready, total, risky, criticalName: criticalNames[0] ?? "yok", avgAcwr, highAcwr,
    perfLines: [
      `${topVaep.name} VAEP/90 ${fmt2(topVaep.vaepPer90)} — kadro üretiminde lider.`,
      impactSub ? `${impactSub.name} (impact-sub) ${impactSub.minutes} dk'da VAEP/90 ${fmt2(impactSub.vaepPer90)}.` : "Yedekten giren etkili katkı yok.",
      "Pres yoğunluğu (PPDA) ilk yarı sezon ortalamasının üstünde; 76' sonrası tempo düştü.",
    ],
  };

  const WEEKS = [WEEK_32, WEEK_33, week34];
  const wk = WEEKS[weekIdx];
  const prevW = weekIdx > 0 ? WEEKS[weekIdx - 1] : null;
  const wkXgDiff = wk.xgF - wk.xgA;

  // TD notu hafta-özel: anahtara hafta no ekle, hafta değişince yükle.
  React.useEffect(() => {
    try {
      setNote(window.localStorage.getItem(`${NOTE_KEY}_w${wk.no}`) ?? "");
    } catch { /* yok say */ }
  }, [wk.no]);
  const onNote = (v: string) => {
    setNote(v);
    try { window.localStorage.setItem(`${NOTE_KEY}_w${wk.no}`, v); } catch { /* yok say */ }
  };

  const toggleTpl = (key: string) => {
    setTpl((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try { window.localStorage.setItem(TPL_KEY, JSON.stringify(next)); } catch { /* yok say */ }
      return next;
    });
  };

  const ALL_SECTIONS: Section[] = [
    {
      key: "mac", icon: "ti-ball-football", title: "Maç Özeti", tone: "var(--accent)",
      spark: <Sparkline data={XG_TREND} color="var(--accent)" />,
      lines: wk.matchLines,
    },
    {
      key: "saglik", icon: "ti-heart-rate-monitor", title: "Sağlık & Yük", tone: "var(--crit)",
      spark: <Sparkline data={[16, 17, 18, wk.ready]} color="var(--low)" />,
      lines: [
        `Sahaya hazır ${wk.ready}/${wk.total}${prevW ? ` — geçen haftaya göre ${sgn(wk.ready - prevW.ready)}` : ""}.`,
        wk.risky > 0 ? `${wk.risky} kritik risk: ${wk.criticalName} — sahaya çıkması önerilmez.` : "Kritik risk yok — tüm kadro maça uygun.",
        `Ortalama ACWR ${fmt2(wk.avgAcwr)}; ${wk.highAcwr} oyuncu 1.3 üstü (yük yönetimi).`,
      ],
    },
    {
      key: "antrenman", icon: "ti-run", title: "Antrenman & Yük Dağılımı", tone: "var(--low)",
      spark: <MiniBars data={WEEK_LOAD} color="var(--low)" />,
      lines: [
        "6 saha seansı + 1 izin; haftalık katılım %92.",
        `Zirve yük MG-4 (%${Math.max(...WEEK_LOAD)}), maça doğru kademeli düşüş (tapering).`,
        "MG-2 taktik provası: sağ kanat 1v1 + far-post duran top.",
      ],
    },
    {
      key: "performans", icon: "ti-chart-line", title: "Performans Öne Çıkanlar", tone: "var(--mid)",
      spark: <Sparkline data={outfield.map((p) => p.vaepPer90).sort((a, b) => a - b)} color="var(--mid)" />,
      lines: wk.perfLines,
    },
  ];
  const SECTIONS = ALL_SECTIONS.filter((s) => tpl[s.key]);

  const right = (
    <>
      <div className="rc">
        <h3>Rapor Şablonu <span className="tiny">bölüm aç/kapa</span></h3>
        {ALL_SECTIONS.map((s) => (
          <label key={s.key} style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 12.5, padding: "5px 0", cursor: "pointer" }}>
            <input type="checkbox" checked={!!tpl[s.key]} onChange={() => toggleTpl(s.key)} style={{ accentColor: "var(--accent)", width: 15, height: 15 }} />
            <i className={`ti ${s.icon}`} style={{ color: s.tone, fontSize: 15 }} />
            <span style={{ color: tpl[s.key] ? "var(--ink)" : "var(--dim)" }}>{s.title}</span>
          </label>
        ))}
      </div>
      <div className="rc">
        <h3>Haftaya Karşı <span className="tiny">{prevW ? `${prevW.no}. → ${wk.no}.` : `${wk.no}.`}</span></h3>
        {prevW ? (
          <>
            <div className="stat"><span>Sahaya hazır</span><span className="sv"><Delta now={wk.ready} prev={prevW.ready} goodUp /></span></div>
            <div className="stat"><span>Kritik risk</span><span className="sv"><Delta now={wk.risky} prev={prevW.risky} goodUp={false} /></span></div>
            <div className="stat"><span>Ort. ACWR</span><span className="sv"><Delta now={wk.avgAcwr} prev={prevW.avgAcwr} goodUp={false} digits={2} /></span></div>
            <div className="stat"><span>xG farkı</span><span className="sv"><Delta now={wkXgDiff} prev={prevW.xgF - prevW.xgA} goodUp digits={2} /></span></div>
          </>
        ) : (
          <div style={{ fontSize: 12, color: "var(--dim)", padding: "4px 0" }}>Önceki hafta verisi yok.</div>
        )}
      </div>
      <div className="rc">
        <h3>Alıcılar</h3>
        {RECIPIENTS.map((r) => (
          <div key={r} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, padding: "4px 0" }}>
            <i className="ti ti-mail" style={{ color: "var(--accent)" }} /> {r}
          </div>
        ))}
        <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--muted)" }}><i className="ti ti-clock" style={{ marginRight: 5 }} />Gönderim: Her Pzt 09:00 · PDF</div>
      </div>
      <div className="rc">
        <h3>Geçmiş Raporlar</h3>
        {HISTORY.map((h) => {
          const ok = h.status === "Gönderildi";
          return (
            <div className="stat" key={h.week}>
              <span>{h.week}</span>
              <span className="sv" style={{ color: ok ? "var(--low)" : "var(--mid)" }}>
                <i className={`ti ${ok ? "ti-check" : "ti-clock"}`} style={{ marginRight: 4 }} />{h.status}
              </span>
            </div>
          );
        })}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/weekly-report"
      title="Haftalık Rapor"
      sub="Otomatik digest · direktöre hazır"
      desc="Maç, sağlık, antrenman ve performans özetini gerçek verilerden tek sayfalık PDF olarak üretir; haftalık otomatik gönderilir."
      source="claude"
      right={right}
    >
      <BackendDigestPanel />
      <div className="kpis">
        <div className="kpi"><div className="kl">Hafta</div><div className="kn" style={{ fontSize: 20 }}>{wk.no}.</div><div className="kd">{wk.range}</div></div>
        <div className="kpi"><div className="kl">Maç Sonucu</div><div className="kn" style={{ fontSize: 20 }}>{wk.score[0]}–{wk.score[1]}</div><div className="kd">{wk.oppLabel}</div></div>
        <div className="kpi"><div className="kl">Sahaya Hazır</div><div className="kn" style={{ color: "var(--low)" }}>{wk.ready}<span className="pct">/{wk.total}</span></div><div className="kd">{prevW ? <Delta now={wk.ready} prev={prevW.ready} goodUp /> : "—"} hafta</div></div>
        <div className="kpi"><div className="kl">Ort. ACWR</div><div className="kn" style={{ fontSize: 22, color: wk.avgAcwr > 1.3 ? "var(--mid)" : "var(--low)" }}>{fmt2(wk.avgAcwr)}</div><div className="kd">{prevW ? <Delta now={wk.avgAcwr} prev={prevW.avgAcwr} goodUp={false} digits={2} /> : "—"}</div></div>
        <div className="kpi"><div className="kl">Kritik Uyarı</div><div className="kn" style={{ color: wk.risky > 0 ? "var(--crit)" : "var(--low)" }}>{wk.risky}</div><div className="kd">{wk.risky > 0 ? wk.criticalName : "yok"}</div></div>
      </div>

      <div className="st" style={{ marginTop: 0 }}>
        <h2>Bu Haftanın Kritik İçgörüleri</h2>
        <span className="ep">4 motordan otomatik · önceliklendirilmiş</span>
      </div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <InsightFeed data={weeklyInsights(DEMO_OPPONENT)} />
      </div>

      <div className="st" style={{ marginTop: 0 }}>
        <h2>Rapor Önizleme</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div className="seg">
            {WEEKS.map((w, i) => (
              <button key={w.no} className={weekIdx === i ? "on" : ""} onClick={() => setWeekIdx(i)}>{w.no}. Hafta</button>
            ))}
          </div>
          <button type="button" onClick={() => window.print()} style={{ padding: "8px 14px", borderRadius: 9, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)", fontWeight: 600, fontSize: 12.5, cursor: "pointer", fontFamily: "inherit" }}>
            <i className="ti ti-file-type-pdf" style={{ marginRight: 6 }} />PDF indir
          </button>
          <button type="button" onClick={() => setSent(true)} disabled={sent}
            title="Demo: gerçek e-posta gönderimi backend bağlanınca aktifleşir (SMTP)."
            style={{ padding: "8px 14px", borderRadius: 9, border: 0, background: sent ? "var(--low)" : "var(--besiktas)", color: "#fff", fontWeight: 700, fontSize: 12.5, cursor: sent ? "default" : "pointer", fontFamily: "inherit", opacity: sent ? 0.85 : 1 }}>
            <i className={`ti ${sent ? "ti-check" : "ti-send"}`} style={{ marginRight: 6 }} />{sent ? "Gönderildi (demo)" : "Direktöre gönder (demo)"}
          </button>
        </div>
      </div>

      {/* TD notu — rapora eklenir; yazdırmaya dahil DEĞİL (içeriği kağıtta görünür) */}
      <div className="rc" style={{ margin: "0 0 12px" }}>
        <h3 style={{ marginBottom: 8 }}>
          <i className="ti ti-edit" style={{ marginRight: 6, color: "var(--accent)" }} />Teknik Direktör Notu
          <span className="tiny" style={{ marginLeft: 6 }}>{wk.no}. hafta · otomatik kaydedilir</span>
        </h3>
        <textarea
          value={note}
          onChange={(e) => onNote(e.target.value)}
          placeholder="Direktöre iletmek istediğiniz haftalık değerlendirme / öncelikler… (boşsa rapora eklenmez)"
          rows={3}
          style={{ width: "100%", resize: "vertical", background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 9, padding: "10px 12px", fontSize: 12.5, fontFamily: "inherit", color: "var(--ink)", lineHeight: 1.5 }}
        />
      </div>

      {/* A4 benzeri rapor kağıdı — yazdırılan tek öğe (#report-paper) */}
      <div id="report-paper" className="rc" style={{ margin: 0, padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "18px 22px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--surface2)" }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>{DEMO_CLUB} — Haftalık Teknik Rapor</div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>{wk.no}. Hafta · {wk.range} 2026 · hazırlayan: Teknik Ekip</div>
          </div>
          <div style={{ width: 38, height: 38, borderRadius: 9, background: "var(--accent)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800 }}>FK</div>
        </div>
        {SECTIONS.length === 0 ? (
          <div style={{ padding: "28px 22px", textAlign: "center", color: "var(--dim)", fontSize: 12.5 }}>Tüm bölümler kapalı — sağdaki şablondan en az bir bölüm seçin.</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
            {SECTIONS.map((s, i) => (
              <div key={s.key} style={{ padding: "16px 22px", borderBottom: i < SECTIONS.length - (SECTIONS.length % 2 === 0 ? 2 : 1) ? "1px solid var(--line)" : 0, borderRight: i % 2 === 0 && i < SECTIONS.length - 1 ? "1px solid var(--line)" : 0 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <i className={`ti ${s.icon}`} style={{ fontSize: 16, color: s.tone }} />
                    <b style={{ fontSize: 13 }}>{s.title}</b>
                  </div>
                  {s.spark}
                </div>
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {s.lines.map((l, j) => (
                    <li key={j} style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5, paddingLeft: 14, position: "relative", marginBottom: 5 }}>
                      <span style={{ position: "absolute", left: 0, color: s.tone }}>•</span>{l}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
        {note.trim() && (
          <div style={{ padding: "14px 22px", borderTop: "1px solid var(--line)", background: "var(--surface2)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <i className="ti ti-quote" style={{ fontSize: 15, color: "var(--accent)" }} />
              <b style={{ fontSize: 12.5 }}>Teknik Direktör Notu</b>
            </div>
            <p style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.55, margin: 0, whiteSpace: "pre-wrap" }}>{note.trim()}</p>
          </div>
        )}
        <div style={{ padding: "12px 22px", borderTop: "1px solid var(--line)", fontSize: 11, color: "var(--dim)", display: "flex", justifyContent: "space-between" }}>
          <span>tactic11 · gerçek verilerden otomatik üretildi</span>
          <span>Sonraki gönderim: Pazartesi 09:00</span>
        </div>
      </div>

      {/* PDF indir → tarayıcı yazıcısı: yalnız rapor kağıdını yazdır. */}
      <style dangerouslySetInnerHTML={{ __html: `
        @media print {
          body * { visibility: hidden !important; }
          #report-paper, #report-paper * { visibility: visible !important; }
          #report-paper { position: absolute !important; left: 0; top: 0; width: 100%; border: 0 !important; box-shadow: none !important; }
          @page { margin: 12mm; }
        }
      ` }} />
    </ConsoleShell>
  );
}
