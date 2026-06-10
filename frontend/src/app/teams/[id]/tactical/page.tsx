"use client";

/**
 * Takım Taktiksel Profili — dizilim + pres/blok metrikleri. ConsoleShell çatısında.
 *
 * DEMO_MODE: canlı API'ye (/admin/teams/{id}/tactical-profile) hiç dokunmaz; Beşiktaş
 * için zengin, tutarlı bir taktik profil gösterir (dizilim haritası, pres/blok KPI'ları,
 * koridor tercihi, build-up, geçiş hızı, son 10 maç trendi). Demo evreniyle (demoSquad
 * dizilimi, Antalyaspor eşleşmesi, demoWeaknesses) uyumlu.
 * DEMO kapalı: eski canlı-API + chart bileşenleri davranışına döner.
 */

import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { DEMO_CLUB, DEMO_OPPONENT, demoSquad, demoWeaknesses } from "@/lib/demo-data";
import { engineLabel } from "@/lib/labels";
import { ChannelPreferenceBar } from "@/components/charts/ChannelPreferenceBar";
import { CoachingIdentityRadar } from "@/components/charts/CoachingIdentityRadar";
import { RecoveryZoneStacked } from "@/components/charts/RecoveryZoneStacked";
import { ConsoleShell } from "../../../_console/shell";

interface EngineValue {
  value: Record<string, unknown>;
  audit?: {
    engine: string;
    metric: string;
    formula: string;
  };
}

interface TacticalProfile {
  team_id: number;
  last_n: number;
  matches_analyzed: number[];
  events_loaded: number;
  event_counts?: {
    passes: number;
    carries: number;
    defensive_actions: number;
    shots: number;
  };
  tactical_profile: Record<string, EngineValue | { error: string }>;
  note?: string;
}

function MetricCard({
  title,
  metric,
  primary,
  secondary,
  badge,
}: {
  title: string;
  metric?: EngineValue | { error: string };
  primary: string;
  secondary?: string;
  badge?: string | null;
}) {
  if (!metric) {
    return (
      <div className="card">
        <h3 className="text-xs uppercase text-muted mb-2">{title}</h3>
        <p className="text-muted text-sm">—</p>
      </div>
    );
  }
  if ("error" in metric) {
    return (
      <div className="card border-red-500/30">
        <h3 className="text-xs uppercase text-muted mb-2">{title}</h3>
        <p className="text-xs text-red-400">{metric.error.slice(0, 80)}</p>
      </div>
    );
  }
  const v = metric.value as Record<string, unknown>;
  const primaryVal = v[primary];
  const secondaryVal = secondary ? v[secondary] : null;
  const badgeVal = badge ? v[badge] : null;
  return (
    <div className="card">
      <h3 className="text-xs uppercase text-muted mb-2">{title}</h3>
      <div className="text-2xl font-mono mb-1">
        {typeof primaryVal === "number" ? primaryVal.toFixed(2) : String(primaryVal ?? "—")}
      </div>
      {secondaryVal !== null && secondaryVal !== undefined && (
        <div className="text-xs text-muted">
          {secondary}: <span className="font-mono">{String(secondaryVal)}</span>
        </div>
      )}
      {badgeVal !== null && badgeVal !== undefined && (
        <div className="inline-block mt-2 px-2 py-0.5 rounded bg-accent/20 text-xs uppercase">
          {String(badgeVal)}
        </div>
      )}
    </div>
  );
}

function LiveTacticalPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const teamId = params.id;
  const lastN = search.get("last_n") ?? "10";
  const opponentId = search.get("opponent_id");
  const qs = opponentId
    ? `?last_n=${lastN}&opponent_id=${opponentId}`
    : `?last_n=${lastN}`;

  const { data, error, isLoading } = useSWR<TacticalProfile>(
    `/admin/teams/${teamId}/tactical-profile${qs}`,
    apiFetch,
  );

  if (error) {
    return (
      <main className="max-w-6xl mx-auto p-6">
        <p className="text-red-400">Yüklenemedi: {String(error)}</p>
      </main>
    );
  }
  if (isLoading || !data) {
    return (
      <main className="max-w-6xl mx-auto p-6">
        <p className="text-muted">Yükleniyor...</p>
      </main>
    );
  }
  if (data.events_loaded === 0) {
    return (
      <main className="max-w-6xl mx-auto p-6">
        <h1 className="text-2xl font-bold mb-4">
          Takım #{teamId} — Taktiksel Profil
        </h1>
        <div className="card">
          <p className="text-muted">
            events tablosunda bu takım için kayıt yok.
          </p>
          <p className="text-xs text-muted mt-2">
            Ingest çağırın: <code className="font-mono">python -m
            scripts.ingest_statsbomb_events --tenant t-default --team {teamId}</code>
          </p>
        </div>
      </main>
    );
  }

  const tp = data.tactical_profile;
  return (
    <main className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-2">
        Takım #{teamId} — Taktiksel Profil
      </h1>
      <p className="text-sm text-muted mb-6">
        Son {data.matches_analyzed.length} maç ({data.events_loaded} event)
        {opponentId && ` · vs #${opponentId}`}
      </p>

      <h2 className="text-lg font-semibold mt-2 mb-3">Pres & Savunma</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <MetricCard title="PPDA"
          metric={tp.ppda} primary="ppda" secondary="opp_passes_in_press_zone" />
        <MetricCard title="Pressing Trigger"
          metric={tp.pressing_trigger} primary="avg_recovery_time_min"
          secondary="fast_recovery_ratio" badge="style_label" />
        <MetricCard title="Savunma Hattı"
          metric={tp.defensive_line} primary="avg_x"
          secondary="actions_counted" badge="line_label" />
        <MetricCard title="Recovery Zone"
          metric={tp.recovery_zone_heat} primary="attacking_share"
          secondary="defensive_share" badge="style_label" />
        <MetricCard title="Compactness"
          metric={tp.compactness} primary="overall_stdev" badge="label" />
        <MetricCard title="Defensive Duels"
          metric={tp.defensive_duels} primary="win_rate"
          secondary="duels_won" />
        <MetricCard title="Counter-Press"
          metric={tp.counter_press_triggers} primary="pressure_responses"
          badge="dominant_trigger" />
        <MetricCard title="Set-piece Zones"
          metric={tp.set_piece_zones} primary="total_shots"
          badge="most_threatening_zone" />
      </div>

      <h2 className="text-lg font-semibold mt-2 mb-3">Hücum & Geçiş</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <MetricCard title="Tempo"
          metric={tp.tempo} primary="passes_per_minute" badge="label" />
        <MetricCard title="Direct Play"
          metric={tp.direct_play} primary="avg_directness" badge="style_label" />
        <MetricCard title="Transition Speed"
          metric={tp.transition} primary="avg_time_to_shot_min"
          secondary="fast_counter_ratio" badge="style_label" />
        <MetricCard title="Possession Quality"
          metric={tp.possession_quality} primary="quality_score"
          secondary="avg_passes_per_sequence" badge="label" />
        <MetricCard title="Channel Pref."
          metric={tp.channel_preference} primary="left_share"
          secondary="right_share" badge="dominant_channel" />
        <MetricCard title="Final 3rd Entries"
          metric={tp.final_third_entries} primary="total_entries"
          secondary="pass_share" badge="dominant_entry_channel" />
        <MetricCard title="Cross Effectiveness"
          metric={tp.cross_effectiveness} primary="total_crosses"
          secondary="shots_from_crosses" badge="most_effective_zone" />
        <MetricCard title="Cutback Frequency"
          metric={tp.cutback_frequency} primary="cutbacks_per_match"
          secondary="goals_from_cutbacks" />
      </div>

      <h2 className="text-lg font-semibold mt-2 mb-3">Toplam Tehdit</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <MetricCard title="Team xT"
          metric={tp.team_xt} primary="total_xt" />
        <MetricCard title="Build-up"
          metric={tp.build_up_pattern} primary="long_ball_ratio"
          secondary="counter_attack_share" badge="dominant_start_zone" />
        <MetricCard title="Press Resistance"
          metric={tp.press_resistance} primary="completion_rate_under_press"
          secondary="passes_under_press" />
        {tp.field_tilt && (
          <MetricCard title="Field Tilt"
            metric={tp.field_tilt} primary="team_a_tilt"
            secondary="team_b_tilt" />
        )}
        {tp.coaching_identity && (
          <MetricCard title="Coaching Identity"
            metric={tp.coaching_identity} primary="archetype"
            secondary="top_features" />
        )}
      </div>

      <h2 className="text-lg font-semibold mt-6 mb-3">Görsel Analiz</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
        {tp.channel_preference && !("error" in tp.channel_preference) && (
          <ChannelPreferenceBar
            left={Number(tp.channel_preference.value.left_share) || 0}
            central={Number(tp.channel_preference.value.central_share) || 0}
            right={Number(tp.channel_preference.value.right_share) || 0}
          />
        )}
        {tp.recovery_zone_heat && !("error" in tp.recovery_zone_heat) && (
          <RecoveryZoneStacked
            defensive={Number(tp.recovery_zone_heat.value.defensive_share) || 0}
            middle={Number(tp.recovery_zone_heat.value.middle_share) || 0}
            attacking={Number(tp.recovery_zone_heat.value.attacking_share) || 0}
          />
        )}
        {tp.coaching_identity && !("error" in tp.coaching_identity)
          && Boolean(tp.coaching_identity.value.vector) && (
          <CoachingIdentityRadar
            vector={tp.coaching_identity.value.vector as never}
            archetype={String(tp.coaching_identity.value.archetype || "")}
          />
        )}
      </div>

      <p className="text-xs text-muted mt-4">
        Audit: tüm metriklerin formülü{" "}
        <code className="font-mono">/admin/teams/{teamId}/tactical-profile</code>{" "}
        endpoint yanıtının <code>audit.formula</code> alanında.
      </p>
    </main>
  );
}

/* ────────────────────────────────────────────────────────────────────────
   DEMO — Beşiktaş taktiksel profili (backend yok, demo evreniyle uyumlu)
──────────────────────────────────────────────────────────────────────── */

// 4-2-3-1: demoSquad pozisyonlarıyla tutarlı (GK, 2 stoper + 2 bek, 2 ön libero,
// 10 numara, 2 kanat, santrfor). x: 0(sol)..100(sağ), y: 0(kale)..100(rakip kale).
interface FormationSlot { x: number; y: number; pos: string; shirt: number }
const DEMO_FORMATION_NAME = "4-2-3-1";
const DEMO_FORMATION: FormationSlot[] = [
  { x: 50, y: 7, pos: "GK", shirt: 1 },
  { x: 16, y: 26, pos: "SLB", shirt: 3 },
  { x: 38, y: 22, pos: "STP", shirt: 5 },
  { x: 62, y: 22, pos: "STP", shirt: 4 },
  { x: 84, y: 26, pos: "SĞB", shirt: 2 },
  { x: 38, y: 44, pos: "ÖL", shirt: 6 },
  { x: 62, y: 44, pos: "ÖL", shirt: 8 },
  { x: 18, y: 66, pos: "SLK", shirt: 11 },
  { x: 50, y: 64, pos: "10", shirt: 10 },
  { x: 82, y: 66, pos: "SĞK", shirt: 7 },
  { x: 50, y: 86, pos: "SF", shirt: 9 },
];

// Pres & blok / hücum KPI'ları (lig: Süper Lig — 34. Hafta, son 10 maç).
interface TacKpi { label: string; value: string; sub: string; tone?: string }
const DEMO_KPIS: TacKpi[] = [
  { label: "PPDA", value: "8.4", sub: "lig sıra 3 — yüksek pres", tone: "var(--low)" },
  { label: "Savunma Hattı", value: "48.3m", sub: "yüksek blok", tone: "var(--mid)" },
  { label: "Top Geri Kazanım", value: "12.1s", sub: "ort. süre · hızlı", tone: "var(--low)" },
  { label: "Takım xT", value: "1.92", sub: "maç başına tehdit" },
  { label: "Topa Sahip Olma", value: "%57", sub: "lig ort. %50" },
];

// Pres/blok metrik tablosu (engine + değer + lig kıyas barı 0..100).
interface PressRow { metric: string; engine: string; value: string; bar: number; tone: string; note: string }
const DEMO_PRESS_ROWS: PressRow[] = [
  { metric: "PPDA (pres yoğunluğu)", engine: "pressing_engine", value: "8.4", bar: 78, tone: "var(--low)", note: "Düşük PPDA = agresif pres; lig 3.'sü" },
  { metric: "Counter-press (5sn)", engine: "counter_press", value: "%64", bar: 64, tone: "var(--low)", note: "Top kaybı sonrası ilk 5 sn'de geri kazanım" },
  { metric: "Savunma hattı yüksekliği", engine: "defensive_line", value: "48.3m", bar: 71, tone: "var(--mid)", note: "Yüksek blok — arkada boşluk riski" },
  { metric: "Blok kompaktlığı (std)", engine: "compactness", value: "9.1m", bar: 68, tone: "var(--mid)", note: "Hatlar arası mesafe makul derli toplu" },
  { metric: "Savunma düellosu kazanma", engine: "defensive_duels", value: "%58", bar: 58, tone: "var(--mid)", note: "144 düellonun 84'ü kazanıldı" },
  { metric: "Pres direnci (baskı altı pas)", engine: "press_resistance", value: "%81", bar: 81, tone: "var(--low)", note: "Yüksek pres altında pas isabeti güçlü" },
];

// Hücum & geçiş metrikleri.
const DEMO_ATTACK_ROWS: PressRow[] = [
  { metric: "Tempo (pas/dk)", engine: "tempo_engine", value: "14.2", bar: 72, tone: "var(--low)", note: "Hızlı kombinasyon — yüksek devir" },
  { metric: "Doğrudan oyun (directness)", engine: "direct_play", value: "0.42", bar: 42, tone: "var(--mid)", note: "Dengeli: ne tam kısa ne tam uzun" },
  { metric: "Geçiş hızı (şuta süre)", engine: "transition", value: "8.7s", bar: 76, tone: "var(--low)", note: "Top kazanımından şuta ort. süre kısa" },
  { metric: "Hızlı kontra oranı", engine: "transition", value: "%31", bar: 31, tone: "var(--mid)", note: "Geçişlerin üçte biri direkt kontra" },
  { metric: "Son 1/3 girişleri", engine: "final_third", value: "38/maç", bar: 70, tone: "var(--low)", note: "Baskın koridor: sağ kanat" },
  { metric: "Build-up uzun top oranı", engine: "build_up", value: "%24", bar: 24, tone: "var(--low)", note: "Arkadan kurma ağırlıklı, uzun top az" },
];

// Koridor tercihi (sol/orta/sağ) — sağ kanat baskın (Milot Rashica 7 ile uyumlu).
const DEMO_CHANNELS = { left: 28, central: 31, right: 41 };

// Top geri kazanım bölgesi (savunma/orta/hücum üçlük payı).
const DEMO_RECOVERY = { defensive: 24, middle: 44, attacking: 32 };

// Koçluk kimliği radar verisi (0..1 eksenler).
const DEMO_IDENTITY: { axis: string; v: number }[] = [
  { axis: "Pres", v: 0.82 },
  { axis: "Topa Sahiplik", v: 0.74 },
  { axis: "Geçiş Hızı", v: 0.78 },
  { axis: "Doğrudan Oyun", v: 0.42 },
  { axis: "Yükseklik", v: 0.71 },
  { axis: "Kanat Kullanımı", v: 0.66 },
];
const DEMO_ARCHETYPE = "Yüksek pres + dikey geçiş";

// Son 10 maç PPDA trendi (düşük = daha agresif pres). Sparkline için.
const DEMO_PPDA_TREND = [10.2, 9.6, 9.1, 9.8, 8.7, 8.9, 8.2, 8.6, 8.0, 8.4];

const SEV_TONE: Record<string, string> = {
  "yüksek": "var(--crit)",
  "orta": "var(--mid)",
  "düşük": "var(--low)",
};

/** Min-maks ölçekli inline sparkline (düşük-iyi metrik için ters renk uçları). */
function Sparkline({ data, w = 220, h = 48 }: { data: number[]; w?: number; h?: number }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pad = 4;
  const step = (w - pad * 2) / (data.length - 1);
  const pts = data.map((d, i) => {
    const x = pad + i * step;
    // düşük PPDA daha iyi → düşük değer yukarıda (y küçük)
    const y = pad + ((d - min) / span) * (h - pad * 2);
    return [x, y] as const;
  });
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      {pts.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r={i === pts.length - 1 ? 3.4 : 2} fill={i === pts.length - 1 ? "var(--low)" : "var(--accent)"} />
      ))}
      <line x1={last[0]} y1={0} x2={last[0]} y2={h} stroke="var(--border2)" strokeWidth={1} strokeDasharray="2 3" />
    </svg>
  );
}

/** Saha üstü dizilim haritası — dikey yarım/tam saha, 11 nokta. */
function FormationPitch() {
  const W = 100;
  const H = 150;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", maxHeight: 360 }}>
      {/* zemin */}
      <rect x="2" y="2" width={W - 4} height={H - 4} rx="4" fill="var(--surface2)" stroke="var(--border2)" strokeWidth="0.8" />
      {/* orta çizgi + daire */}
      <line x1="2" y1={H / 2} x2={W - 2} y2={H / 2} stroke="var(--border2)" strokeWidth="0.6" />
      <circle cx={W / 2} cy={H / 2} r="9" fill="none" stroke="var(--border2)" strokeWidth="0.6" />
      {/* ceza sahaları */}
      <rect x={(W - 44) / 2} y="2" width="44" height="18" fill="none" stroke="var(--border2)" strokeWidth="0.6" />
      <rect x={(W - 44) / 2} y={H - 20} width="44" height="18" fill="none" stroke="var(--border2)" strokeWidth="0.6" />
      {DEMO_FORMATION.map((s) => {
        const cx = (s.x / 100) * (W - 12) + 6;
        const cy = H - ((s.y / 100) * (H - 14) + 7); // y=0 kendi kalemiz (alt)
        const crit = s.shirt === 10; // 10 numara (Orkun Kökçü) kritik risk
        return (
          <g key={s.shirt}>
            <circle cx={cx} cy={cy} r="6.4" fill={crit ? "var(--crit)" : "var(--accent)"} stroke="#fff" strokeWidth="0.8" />
            <text x={cx} y={cy + 2.4} textAnchor="middle" fill="#fff" style={{ fontSize: 6, fontWeight: 700, fontFamily: "JetBrains Mono" }}>{s.shirt}</text>
            <text x={cx} y={cy + 11} textAnchor="middle" fill="var(--muted)" style={{ fontSize: 4.2, fontWeight: 600 }}>{s.pos}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** Üç dilimli yatay pay barı (koridor / geri kazanım bölgesi). */
function ShareBar({ parts }: { parts: { label: string; v: number; color: string }[] }) {
  return (
    <div>
      <div className="probbar" style={{ height: 12 }}>
        {parts.map((p) => (
          <i key={p.label} style={{ width: `${p.v}%`, background: p.color }} />
        ))}
      </div>
      <div className="probleg" style={{ marginTop: 6 }}>
        {parts.map((p) => (
          <div className="pi" key={p.label}>
            <div className="pv" style={{ color: p.color }}>%{p.v}</div>
            <div className="pl">{p.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Radar (koçluk kimliği) — 6 eksen, 0..1. */
function IdentityRadar({ axes }: { axes: { axis: string; v: number }[] }) {
  const size = 200;
  const cx = size / 2;
  const cy = size / 2;
  const R = 72;
  const n = axes.length;
  const pt = (i: number, r: number) => {
    const ang = (Math.PI * 2 * i) / n - Math.PI / 2;
    return [cx + Math.cos(ang) * r, cy + Math.sin(ang) * r] as const;
  };
  const rings = [0.25, 0.5, 0.75, 1];
  const poly = axes.map((a, i) => pt(i, R * a.v).join(",")).join(" ");
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width="100%" style={{ display: "block", maxWidth: 280, margin: "0 auto" }}>
      {rings.map((rg) => (
        <polygon
          key={rg}
          points={axes.map((_, i) => pt(i, R * rg).join(",")).join(" ")}
          fill="none"
          stroke="var(--border)"
          strokeWidth="0.8"
        />
      ))}
      {axes.map((a, i) => {
        const [x, y] = pt(i, R);
        return <line key={a.axis} x1={cx} y1={cy} x2={x} y2={y} stroke="var(--border)" strokeWidth="0.8" />;
      })}
      <polygon points={poly} fill="var(--accent)" fillOpacity="0.22" stroke="var(--accent)" strokeWidth="1.6" />
      {axes.map((a, i) => {
        const [x, y] = pt(i, R * a.v);
        return <circle key={a.axis} cx={x} cy={y} r="2.6" fill="var(--accent)" />;
      })}
      {axes.map((a, i) => {
        const [x, y] = pt(i, R + 12);
        return (
          <text key={a.axis} x={x} y={y} textAnchor="middle" dominantBaseline="middle" fill="var(--muted)" style={{ fontSize: 8, fontWeight: 600 }}>
            {a.axis}
          </text>
        );
      })}
    </svg>
  );
}

function MetricTable({ rows }: { rows: PressRow[] }) {
  return (
    <div className="tbl">
      <table>
        <thead>
          <tr>
            <th>Metrik</th>
            <th className="c">Değer</th>
            <th>Lig Kıyas</th>
            <th>Yorum</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.metric}>
              <td>
                <span className="nm">{r.metric}</span>{" "}
                <span className="nat" title={r.engine}>{engineLabel(r.engine)}</span>
              </td>
              <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: r.tone }}>{r.value}</td>
              <td style={{ minWidth: 130 }}>
                <span className="cond" style={{ width: 110 }}>
                  <i style={{ width: `${r.bar}%`, background: r.tone }} />
                </span>
              </td>
              <td style={{ color: "var(--muted)", fontSize: 11.5 }}>{r.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DemoTacticalPage() {
  const params = useParams<{ id: string }>();
  const teamId = params?.id ?? "1";

  // Başlıkta id'yi kullan; demo evreni tek (Beşiktaş vs Antalyaspor) olduğu için
  // metrikler kulüp geneli. Dizilim demoSquad pozisyonlarından türetildi.
  const starters = DEMO_FORMATION.map((s) => demoSquad.find((p) => p.shirt === s.shirt)).filter(Boolean);
  const critStarter = starters.find((p) => p && p.risk_label === "Kritik");

  const right = (
    <>
      <div className="rc">
        <h3>Koçluk Kimliği <span className="tiny">son 10 maç</span></h3>
        <IdentityRadar axes={DEMO_IDENTITY} />
        <div style={{ textAlign: "center", marginTop: 4 }}>
          <span className="pos" style={{ background: "var(--accent-lt)", color: "var(--accent)" }}>{DEMO_ARCHETYPE}</span>
        </div>
      </div>

      <div className="rc">
        <h3>Top Geri Kazanım Bölgesi</h3>
        <ShareBar
          parts={[
            { label: "Savunma", v: DEMO_RECOVERY.defensive, color: "var(--crit)" },
            { label: "Orta", v: DEMO_RECOVERY.middle, color: "var(--mid)" },
            { label: "Hücum", v: DEMO_RECOVERY.attacking, color: "var(--low)" },
          ]}
        />
        <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 10, lineHeight: 1.5 }}>
          Kazanımların yüzde {DEMO_RECOVERY.attacking} kadarı hücum yarısında — yüksek pres profili.
        </div>
      </div>

      <div className="rc">
        <h3>Rakip Zaafları <span className="tiny">{DEMO_OPPONENT}</span></h3>
        {demoWeaknesses.map((w) => {
          const t = SEV_TONE[w.severity] ?? "var(--dim)";
          return (
            <div className="alrt" key={w.title}>
              <span className="ai" style={{ background: t }} />
              <div className="am"><b>{w.title}</b>
                <span className="tm">{w.detail}</span>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/teams"
      title={`${DEMO_CLUB} — Taktiksel Profil`}
      sub={`#${teamId} · ${DEMO_FORMATION_NAME}`}
      desc={`Süper Lig — 34. Hafta · son 10 maç · ${DEMO_OPPONENT} eşleşmesine göre pres/blok ve hücum okuması.`}
      right={right}
    >
      <div className="kpis">
        {DEMO_KPIS.map((k) => (
          <div className="kpi" key={k.label}>
            <div className="kl">{k.label}</div>
            <div className="kn" style={{ color: k.tone, fontSize: 22 }}>{k.value}</div>
            <div className="kd">{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="st" style={{ marginTop: 6 }}>
        <h2>Dizilim & Konumlanma</h2>
        <span className="ep">{DEMO_FORMATION_NAME} · yüksek blok</span>
      </div>
      <div className="rc" style={{ margin: "0 0 16px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 280px) 1fr", gap: 18, alignItems: "center" }}>
          <FormationPitch />
          <div>
            <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.6, marginBottom: 12 }}>
              <b style={{ color: "var(--ink)" }}>{DEMO_CLUB}</b> {DEMO_FORMATION_NAME} ile çift ön libero üzerine kuruyor.
              Sağ kanat (Milot Rashica 7) baskın hücum koridoru; sol bek yüksek çıkıp genişlik veriyor.
              Topu kazanınca 10 numara üzerinden dikey geçiş aranıyor.
            </div>
            <div className="stat"><span>İlk 11 ort. yaş</span><span className="sv">{Math.round(starters.reduce((a, p) => a + (p?.age ?? 0), 0) / (starters.length || 1))}</span></div>
            <div className="stat"><span>İlk 11 ort. kondisyon</span><span className="sv">%{Math.round(starters.reduce((a, p) => a + (p?.condition ?? 0), 0) / (starters.length || 1))}</span></div>
            <div className="stat"><span>Baskın koridor</span><span className="sv">Sağ (%{DEMO_CHANNELS.right})</span></div>
            {critStarter && (
              <div className="stat">
                <span>Kritik risk (ilk 11)</span>
                <span className="risk risk-crit"><span className="rd" style={{ background: "var(--crit)" }} />{critStarter.player_name} (#{critStarter.shirt})</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="st"><h2>Pres & Savunma</h2><span className="ep">pressing / blok motorları</span></div>
      <div style={{ marginBottom: 16 }}>
        <MetricTable rows={DEMO_PRESS_ROWS} />
      </div>

      <div className="st"><h2>Hücum & Geçiş</h2><span className="ep">tempo / transition / build-up</span></div>
      <div style={{ marginBottom: 16 }}>
        <MetricTable rows={DEMO_ATTACK_ROWS} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 8 }}>
        <div>
          <div className="st" style={{ marginTop: 0 }}><h2>Koridor Tercihi</h2><span className="ep">sol / orta / sağ</span></div>
          <div className="rc" style={{ margin: 0 }}>
            <ShareBar
              parts={[
                { label: "Sol", v: DEMO_CHANNELS.left, color: "var(--mid)" },
                { label: "Orta", v: DEMO_CHANNELS.central, color: "var(--dim)" },
                { label: "Sağ", v: DEMO_CHANNELS.right, color: "var(--accent)" },
              ]}
            />
            <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 10, lineHeight: 1.5 }}>
              Hücum yükü sağ kanatta yoğunlaşıyor (%{DEMO_CHANNELS.right}). Rakip sol bek arkası
              bu eğilimle örtüşen birincil hedef.
            </div>
          </div>
        </div>
        <div>
          <div className="st" style={{ marginTop: 0 }}><h2>PPDA Trendi</h2><span className="ep">son 10 maç</span></div>
          <div className="rc" style={{ margin: 0 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 26, fontWeight: 800, fontFamily: "JetBrains Mono", color: "var(--low)" }}>
                {DEMO_PPDA_TREND[DEMO_PPDA_TREND.length - 1].toFixed(1)}
              </span>
              <span style={{ fontSize: 12, color: "var(--low)", fontWeight: 600 }}>
                ↓ pres giderek agresifleşti
              </span>
            </div>
            <Sparkline data={DEMO_PPDA_TREND} w={240} h={56} />
            <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 8, lineHeight: 1.5 }}>
              Düşük PPDA = daha çok pres. Son 10 maçta 10.2 → 8.4 bandına indi.
            </div>
          </div>
        </div>
      </div>

      <p className="pgdesc" style={{ marginTop: 6 }}>
        Demo verisi: backend bağlı değil. Tüm metrikler {DEMO_CLUB} için kurgusal son 10 maç penceresinden türetildi.
      </p>
    </ConsoleShell>
  );
}

export default function TacticalProfilePage() {
  // Demo modunda canlı API/auth'a dokunma — dolu taktik profili göster.
  if (DEMO_MODE) return <DemoTacticalPage />;
  return <LiveTacticalPage />;
}
