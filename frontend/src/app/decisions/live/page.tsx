"use client";

/**
 * Maç-içi Karar Paneli — orkestra şefi (context_engine) çıktısı.
 *
 * Backend: GET /admin/matches/{id}/live-decision?my_team_id=X&current_minute=Y
 *   → 10 engine birleşik panel + context_engine "ŞİMDİ şunu yap" primary aksiyonu.
 *
 * Bu sayfa:
 * 1. Top: ŞİMDİ aksiyonu (büyük başlık + güven + tema)
 * 2. Card grid: 7 engine (momentum, sub_timing, tactical, risk, closing, star_feed, foul_pressure)
 * 3. Match select + dakika slider (60-95)
 * 4. Yıldız oyuncu input — star_feed engine'i için
 *
 * DEMO_MODE: sentetik dolu veri.
 * Canlı: SWR ile /admin/matches/{id}/live-decision çağırır.
 */

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { ConsoleShell } from "../../_console/shell";

const DEFAULT_MATCH_ID = 9300;
const DEFAULT_TEAM_ID = 11;
const DEFAULT_STAR_ID = 5503;
const REPLAY_TICK_MS = 900;
const REPLAY_MINUTE_STEP = 5;
const TIMELINE_MAX = 6;

// --------------------------------------------------------------------------- //
// Tipler — backend live-decision response shape (loose, hata-toleranslı)
// --------------------------------------------------------------------------- //

interface RecipeDetail {
  tempo?: string; positioning?: string; sub_priority?: string;
  set_pieces?: string; extra_note?: string;
}
interface RiskReward {
  take_risk?: boolean; rationale?: string; threshold_breached?: string;
}
interface ClosingStrategy {
  score_state?: string; closing_phase?: string; urgency_level?: string;
  key_message?: string; recipe?: RecipeDetail; risk_reward?: RiskReward;
}
interface MomentumOut {
  score?: number; holder?: string; press_breaking?: boolean;
  xg_swing_alert?: boolean; alert_text?: string | null;
}
interface SubTimingOut {
  package?: string[]; rationale?: string;
  advices?: { player_id: number; verdict: string; impact: number }[];
}
interface StarFeed {
  involvement_state?: string; suggested_action?: string;
  pass_share_pct?: number; tactical_advice?: string;
}
interface FoulPressure {
  tactical_fouling_alert?: boolean; our_high_foul_alert?: boolean;
  escalation_alert?: boolean; referee_card_pressure?: string;
  tactical_advice?: string;
}
interface RiskMonitor {
  card_flags?: { player_external_id: number; message: string; severity: string }[];
  injury_flags?: { player_external_id: number; message: string; severity: string }[];
  time_management?: string;
}
interface ContextPrimary {
  headline?: string; theme_label?: string;
  urgency?: number; confidence?: number; confidence_label?: string;
  rationale?: string;
}
interface ContextDecision {
  one_liner?: string;
  primary?: ContextPrimary | null;
  secondary?: ContextPrimary[];
}
interface LiveDecisionResponse {
  match_id: number;
  current_minute: number;
  score?: string;
  momentum?: MomentumOut;
  sub_timing?: SubTimingOut;
  tactical_triggers?: { type: string; urgency: string; recommendation: string }[];
  risk_monitor?: RiskMonitor;
  closing_strategy?: ClosingStrategy;
  star_feed?: StarFeed;
  foul_pressure?: FoulPressure;
  context?: ContextDecision;
}

// --------------------------------------------------------------------------- //
// Demo veri (DEMO_MODE on)
// --------------------------------------------------------------------------- //

function demoSnapshot(minute: number): LiveDecisionResponse {
  // Replay senaryo: 60'a kadar normal → 70+ momentum opp + pres breaking
  // → 75+ closing high urgency + foul tactical → 85+ critical + take_risk
  const phase = minute < 65 ? "early"
    : minute < 75 ? "mid"
    : minute < 90 ? "late" : "stoppage";
  const earlyMid = phase === "early" || phase === "mid";
  const lateOrStop = phase === "late" || phase === "stoppage";
  const momentumScore = phase === "early" ? 0.1
    : phase === "mid" ? -0.15 : phase === "late" ? -0.42 : -0.55;
  return {
    match_id: 9300, current_minute: minute, score: "1-1",
    momentum: {
      score: momentumScore,
      holder: momentumScore > 0.2 ? "us"
        : momentumScore < -0.2 ? "opponent" : "balanced",
      press_breaking: lateOrStop,
      xg_swing_alert: phase === "stoppage",
      alert_text: phase === "early"
        ? "Açılış denge — momentum izleme"
        : phase === "mid"
        ? "Rakip orta sahada baskı kuruyor"
        : phase === "late"
        ? "Rakip son 10 dk'da baskıyı kurdu — pres kırılıyor"
        : "Rakip uzatma baskısı + xG patlaması",
    },
    sub_timing: {
      package: ["box_to_box_mid", "wide_winger"],
      rationale: "Berabere + son 15 dk → orta saha tazele + kanat genişlet",
      advices: [
        { player_id: 7, verdict: "now", impact: 0.42 },
        { player_id: 14, verdict: "wait_10", impact: 0.28 },
      ],
    },
    tactical_triggers: [
      { type: "formation", urgency: "high",
        recommendation: "Berabere + son 15 dk → hücum dizilim 4-2-3-1 → 4-3-3" },
    ],
    risk_monitor: {
      card_flags: [{
        player_external_id: 5, severity: "high",
        message: "Player 5 sarı + 4 düello — ikinci sarı riski",
      }],
      injury_flags: [{
        player_external_id: 9, severity: "medium",
        message: "Player 9 fatigue 0.72 — sakatlık riski",
      }],
      time_management: lateOrStop
        ? "Berabere + son dakikalar → dengeli; kazanma fırsatı kolla"
        : "Normal tempo — henüz zaman yönetimi devreye girmedi",
    },
    closing_strategy: phase === "early" ? {
      score_state: "level", closing_phase: "early", urgency_level: "low",
      key_message: "Berabere · erken evre → standart oyun",
      recipe: { tempo: "normal", positioning: "normal", sub_priority: "yok",
        set_pieces: "alma", extra_note: "Kapanış evresi değil — plan koru" },
      risk_reward: { take_risk: false, rationale: "Risk eşiği yok",
        threshold_breached: "none" },
    } : phase === "mid" ? {
      score_state: "level", closing_phase: "mid", urgency_level: "moderate",
      key_message: "Berabere · orta evre → tempo: normal",
      recipe: { tempo: "normal", positioning: "normal", sub_priority: "taze koşucu",
        set_pieces: "alma", extra_note: "Dengeli — momentum izle" },
      risk_reward: { take_risk: false, rationale: "Risk eşiği fırlamadı",
        threshold_breached: "none" },
    } : phase === "late" ? {
      score_state: "level", closing_phase: "late", urgency_level: "high",
      key_message: "Berabere · son 15 dk → tempo: yükselt, ikame: hücumcu",
      recipe: {
        tempo: "yükselt", positioning: "yüksel", sub_priority: "hücumcu",
        set_pieces: "risk-al", extra_note: "3 puan kovalamanın zamanı — kanat genişlet",
      },
      risk_reward: { take_risk: false,
        rationale: "Berabere + dk 80 — risk eşiği henüz fırlamamış",
        threshold_breached: "none" },
    } : {
      score_state: "level", closing_phase: "stoppage", urgency_level: "critical",
      key_message: "Berabere · uzatma → acil tempo, all-out, hücumcu",
      recipe: {
        tempo: "acil", positioning: "all-out", sub_priority: "hücumcu",
        set_pieces: "risk-al",
        extra_note: "Berabere kabul mu? Kazanmak için tam risk",
      },
      risk_reward: { take_risk: true,
        rationale: "Berabere + son 5 dk — kazanmak için risk al",
        threshold_breached: "diff==0 ve dk>=85" },
    },
    star_feed: {
      involvement_state: earlyMid ? "balanced" : "starved",
      suggested_action: earlyMid ? "OK" : "ON",
      pass_share_pct: earlyMid ? 14.2 : 3.4,
      tactical_advice: earlyMid
        ? "Yıldız dengeli besleniyor, tempo standart"
        : "Yıldız top almıyor — kanat oyuncuları içe çek, dik pas hattı yarat",
    },
    foul_pressure: lateOrStop ? {
      tactical_fouling_alert: true, our_high_foul_alert: false,
      escalation_alert: true,
      referee_card_pressure: phase === "stoppage" ? "high" : "moderate",
      tactical_advice: phase === "stoppage"
        ? "Rakip ritim kırma fauluyor — hızlı restart · Hakem kart eşiğinde — temaslı pres düşür"
        : "Rakip ofansif bölgemizde fauluyor — duran top fırsatına dön",
    } : {
      tactical_fouling_alert: false, our_high_foul_alert: false,
      escalation_alert: false, referee_card_pressure: "low",
      tactical_advice: "Faul ritmi normal — standart oyun planına devam",
    },
    context: {
      one_liner: phase === "early"
        ? "İzleme modu — net karar yok, plan koru"
        : phase === "mid"
        ? "ŞİMDİ: Dengeli — momentum izle (güven: orta)"
        : phase === "late"
        ? "ŞİMDİ: Berabere · son 15 dk → tempo: yükselt (güven: yüksek)"
        : "ŞİMDİ: Uzatma → acil tempo, all-out (güven: yüksek)",
      primary: phase === "early" ? null : {
        headline: phase === "mid"
          ? "Dengeli — momentum izle, fırsat kolla"
          : phase === "late"
          ? "Berabere · son 15 dk → tempo: yükselt, ikame: hücumcu"
          : "Berabere · uzatma → acil tempo, all-out",
        theme_label: "oyun yönetimi",
        urgency: phase === "mid" ? 0.45
          : phase === "late" ? 0.8 : 0.95,
        confidence: phase === "mid" ? 0.6
          : phase === "late" ? 0.78 : 0.88,
        confidence_label: phase === "mid" ? "orta" : "yüksek",
        rationale: phase === "mid"
          ? "Momentum hafif negatif; closing reçetesi henüz normal"
          : phase === "late"
          ? `${minute}. dk, berabere — closing_strategy primary; aynı anda: `
            + "foul_pressure (rakip ritim kırıyor), star_feed (yıldız aç) → karar net"
          : `${minute}. dk uzatma, berabere — kazanmak için tam risk; `
            + "foul_pressure (hakem eşiği), star_feed (starved) eşzamanlı",
      },
      secondary: lateOrStop ? [
        { headline: "Yıldız top almıyor — kanat içe çek",
          theme_label: "taktiksel ayar",
          urgency: 0.75, confidence: 0.72, confidence_label: "yüksek",
          rationale: "star_feed: %3.4 pas (starved)" },
      ] : [],
    },
  };
}

// --------------------------------------------------------------------------- //
// Kart bileşenleri
// --------------------------------------------------------------------------- //

function PrimaryBanner({ ctx }: { ctx: ContextDecision | undefined }) {
  const p = ctx?.primary;
  const urgency = p?.urgency ?? 0;
  const conf = Math.round((p?.confidence ?? 0) * 100);
  const tone = urgency >= 0.8 ? "var(--crit)"
    : urgency >= 0.55 ? "var(--high)" : "var(--mid)";
  if (!p) {
    return (
      <div className="rc" style={{ marginBottom: 16, borderLeft: "3px solid var(--dim)" }}>
        <div style={{ fontSize: 13, color: "var(--muted)" }}>
          {ctx?.one_liner || "Henüz net bir aksiyon yok — planı koru, izlemeye devam"}
        </div>
      </div>
    );
  }
  return (
    <div className="rc" style={{
      marginBottom: 16, padding: 0, overflow: "hidden",
      borderLeft: `4px solid ${tone}`,
    }}>
      <div style={{
        padding: "12px 16px", borderBottom: "1px solid var(--line)",
        background: "var(--panel2)", display: "flex", alignItems: "center", gap: 12,
      }}>
        <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.8,
          color: "var(--muted)", fontWeight: 700 }}>ŞİMDİ ŞUNU YAP</span>
        <span style={{ marginLeft: "auto", fontSize: 10, textTransform: "uppercase",
          color: tone, border: `1px solid ${tone}`, borderRadius: 999,
          padding: "2px 9px", fontWeight: 700, letterSpacing: 0.6 }}>
          {p.theme_label}
        </span>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>
          güven: <b style={{ color: "var(--ink)" }}>{p.confidence_label} (%{conf})</b>
        </span>
      </div>
      <div style={{ padding: "16px" }}>
        <div style={{ fontSize: 17, fontWeight: 800, color: "var(--ink)",
          lineHeight: 1.4, marginBottom: 8 }}>
          {p.headline}
        </div>
        <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.6 }}>
          {p.rationale}
        </div>
      </div>
    </div>
  );
}

function EngineCard({
  title, accent, children,
}: { title: string; accent?: string; children: React.ReactNode }) {
  return (
    <div className="rc" style={{
      marginBottom: 12,
      borderLeft: accent ? `3px solid ${accent}` : undefined,
    }}>
      <h3 style={{ fontSize: 11.5, textTransform: "uppercase",
        letterSpacing: 0.7, color: "var(--muted)", margin: "0 0 10px",
        fontWeight: 700 }}>{title}</h3>
      <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.6 }}>
        {children}
      </div>
    </div>
  );
}

function MomentumCard({ data }: { data?: MomentumOut }) {
  if (!data) return null;
  const score = data.score ?? 0;
  const tone = score > 0.2 ? "var(--low)" : score < -0.2 ? "var(--high)" : "var(--mid)";
  return (
    <EngineCard title="Momentum" accent={tone}>
      <div><b>Sahip:</b> {data.holder ?? "—"} ({score >= 0 ? "+" : ""}{score.toFixed(2)})</div>
      {data.press_breaking && <div style={{ color: "var(--high)" }}>⚠ Pres kırılıyor</div>}
      {data.xg_swing_alert && <div style={{ color: "var(--crit)" }}>⚠ xG swing</div>}
      {data.alert_text && (
        <div style={{ marginTop: 6, color: "var(--muted)", fontSize: 11.5 }}>
          {data.alert_text}
        </div>
      )}
    </EngineCard>
  );
}

function ClosingCard({ data }: { data?: ClosingStrategy }) {
  if (!data) return null;
  const tone = data.urgency_level === "critical" ? "var(--crit)"
    : data.urgency_level === "high" ? "var(--high)" : "var(--mid)";
  return (
    <EngineCard title="Kapanış reçetesi" accent={tone}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{data.key_message}</div>
      <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.7 }}>
        <div>tempo: <b style={{ color: "var(--ink)" }}>{data.recipe?.tempo}</b></div>
        <div>dizilim: <b style={{ color: "var(--ink)" }}>{data.recipe?.positioning}</b></div>
        <div>ikame: <b style={{ color: "var(--ink)" }}>{data.recipe?.sub_priority}</b></div>
        <div>duran top: <b style={{ color: "var(--ink)" }}>{data.recipe?.set_pieces}</b></div>
      </div>
      {data.recipe?.extra_note && (
        <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--muted)" }}>
          {data.recipe.extra_note}
        </div>
      )}
      {data.risk_reward?.take_risk && (
        <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--high)" }}>
          ⚠ Risk eşiği fırlamış: {data.risk_reward.rationale}
        </div>
      )}
    </EngineCard>
  );
}

function StarFeedCard({ data }: { data?: StarFeed }) {
  if (!data) return null;
  const state = data.involvement_state ?? "balanced";
  const tone = state === "starved" ? "var(--high)"
    : state === "well-fed" ? "var(--mid)" : "var(--low)";
  return (
    <EngineCard title="Yıldız beslemesi" accent={tone}>
      <div><b>Durum:</b> {state} ({data.pass_share_pct?.toFixed(1)}% pas)</div>
      <div><b>Aksiyon:</b> {data.suggested_action}</div>
      <div style={{ marginTop: 6, fontSize: 11.5, color: "var(--muted)" }}>
        {data.tactical_advice}
      </div>
    </EngineCard>
  );
}

function FoulPressureCard({ data }: { data?: FoulPressure }) {
  if (!data) return null;
  const ref = data.referee_card_pressure ?? "low";
  const tone = ref === "high" ? "var(--crit)"
    : data.tactical_fouling_alert ? "var(--high)" : "var(--mid)";
  return (
    <EngineCard title="Faul ritmi + hakem" accent={tone}>
      <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 6 }}>
        Hakem kart eşiği: <b style={{ color: "var(--ink)" }}>{ref}</b>
        {data.tactical_fouling_alert && " · rakip ritim kırıyor"}
        {data.escalation_alert && " · yığılma var"}
      </div>
      <div>{data.tactical_advice}</div>
    </EngineCard>
  );
}

function RiskMonitorCard({ data }: { data?: RiskMonitor }) {
  if (!data) return null;
  const cards = data.card_flags ?? [];
  const inj = data.injury_flags ?? [];
  const tone = (cards.length || inj.length) ? "var(--high)" : "var(--mid)";
  return (
    <EngineCard title="Risk & zaman yönetimi" accent={tone}>
      <div style={{ marginBottom: 8, fontSize: 12 }}>{data.time_management}</div>
      {cards.map((f, i) => (
        <div key={"c" + i} style={{ fontSize: 11.5, color: "var(--high)" }}>
          🟨 {f.message}
        </div>
      ))}
      {inj.map((f, i) => (
        <div key={"i" + i} style={{ fontSize: 11.5, color: "var(--crit)" }}>
          🩹 {f.message}
        </div>
      ))}
      {cards.length + inj.length === 0 && (
        <div style={{ fontSize: 11.5, color: "var(--muted)" }}>Aktif risk flag'i yok</div>
      )}
    </EngineCard>
  );
}

function SubTimingCard({ data }: { data?: SubTimingOut }) {
  if (!data) return null;
  const nowList = (data.advices ?? []).filter((a) => a.verdict === "now");
  const tone = nowList.length ? "var(--high)" : "var(--mid)";
  return (
    <EngineCard title="İkame zamanlaması" accent={tone}>
      <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 6 }}>
        {data.rationale}
      </div>
      {data.package && data.package.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <b>Paket:</b> {data.package.join(" + ")}
        </div>
      )}
      {(data.advices ?? []).slice(0, 3).map((a, i) => (
        <div key={i} style={{ fontSize: 11.5 }}>
          • Oyuncu #{a.player_id} → <b>{a.verdict}</b> (etki: {a.impact.toFixed(2)})
        </div>
      ))}
    </EngineCard>
  );
}

function TacticalTriggersCard({
  data,
}: { data?: { type: string; urgency: string; recommendation: string }[] }) {
  if (!data || data.length === 0) return null;
  return (
    <EngineCard title="Taktiksel trigger'lar" accent="var(--mid)">
      {data.map((t, i) => (
        <div key={i} style={{ marginBottom: 6 }}>
          <span style={{ fontSize: 10, textTransform: "uppercase",
            color: "var(--muted)", letterSpacing: 0.6 }}>
            [{t.type}/{t.urgency}]
          </span>
          <div style={{ fontSize: 12.5 }}>{t.recommendation}</div>
        </div>
      ))}
    </EngineCard>
  );
}

interface MatchListItem {
  match_id: number;
  league_external_id: number;
  season: number;
  kickoff: string | null;
  home_team_external_id: number;
  away_team_external_id: number;
  home_score: number | null;
  away_score: number | null;
  event_count: number;
  foul_count: number;
}

function MatchSelector({
  value, onSelect,
}: { value: number; onSelect: (m: MatchListItem) => void }) {
  const { data, error, isLoading } = useSWR<{ matches: MatchListItem[]; total: number }>(
    "/admin/matches/with-events?limit=30", apiFetch,
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const matches = data?.matches ?? [];

  if (isLoading) {
    return (
      <label style={{ fontSize: 11.5 }}>
        Maç:
        <div style={{ marginTop: 2, padding: 6, color: "var(--muted)" }}>
          Yükleniyor…
        </div>
      </label>
    );
  }
  if (error || matches.length === 0) {
    return (
      <label style={{ fontSize: 11.5 }}>
        Maç (manuel):
        <input type="number" value={value}
          onChange={(e) => onSelect({
            match_id: parseInt(e.target.value) || 0,
            league_external_id: 0, season: 0, kickoff: null,
            home_team_external_id: 0, away_team_external_id: 0,
            home_score: null, away_score: null,
            event_count: 0, foul_count: 0,
          })}
          style={{ width: "100%", marginTop: 2, padding: 6,
            background: "var(--panel2)", color: "var(--ink)",
            border: "1px solid var(--line)", borderRadius: 4 }} />
        <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
          Ingest'li maç bulunamadı — manuel id gir
        </div>
      </label>
    );
  }
  return (
    <label style={{ fontSize: 11.5 }}>
      Maç ({matches.length}):
      <select
        value={value}
        onChange={(e) => {
          const m = matches.find((x) => x.match_id === parseInt(e.target.value));
          if (m) onSelect(m);
        }}
        style={{ width: "100%", marginTop: 2, padding: 6,
          background: "var(--panel2)", color: "var(--ink)",
          border: "1px solid var(--line)", borderRadius: 4 }}
      >
        {matches.find((m) => m.match_id === value) === undefined && (
          <option value={value}>#{value} (özel)</option>
        )}
        {matches.map((m) => {
          const date = m.kickoff ? m.kickoff.slice(0, 10) : "—";
          const score = (m.home_score !== null && m.away_score !== null)
            ? `${m.home_score}-${m.away_score}` : "—";
          return (
            <option key={m.match_id} value={m.match_id}>
              {date} · #{m.match_id} · {m.home_team_external_id} vs {m.away_team_external_id}
              {" · "}{score} · {m.event_count} ev · {m.foul_count} foul
            </option>
          );
        })}
      </select>
    </label>
  );
}

function TimelineStrip({
  entries, currentMinute,
}: { entries: { minute: number; headline: string; theme_label: string;
                urgency: number; confidence_label: string }[];
     currentMinute: number }) {
  if (entries.length === 0) return null;
  return (
    <div className="rc" style={{
      marginBottom: 16, padding: "12px 14px",
      borderLeft: "3px solid var(--mid)",
    }}>
      <div style={{ display: "flex", alignItems: "center",
        justifyContent: "space-between", marginBottom: 10 }}>
        <h3 style={{ fontSize: 11.5, textTransform: "uppercase",
          letterSpacing: 0.7, color: "var(--muted)", margin: 0,
          fontWeight: 700 }}>Karar Geçmişi</h3>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>
          {entries.length} tick · {entries[0].minute}&apos; → {entries[entries.length-1].minute}&apos;
        </span>
      </div>
      <div style={{ display: "flex", gap: 8, overflowX: "auto",
        paddingBottom: 4 }}>
        {entries.map((e, i) => {
          const isLast = i === entries.length - 1;
          const tone = e.urgency >= 0.8 ? "var(--crit)"
            : e.urgency >= 0.55 ? "var(--high)" : "var(--mid)";
          return (
            <div key={`${e.minute}-${i}`} style={{
              flex: "0 0 auto", minWidth: 200, maxWidth: 240,
              padding: "10px 12px", borderRadius: 6,
              background: isLast ? "var(--panel2)" : "transparent",
              border: `1px solid ${isLast ? tone : "var(--line)"}`,
              borderLeft: `3px solid ${tone}`,
              opacity: isLast ? 1 : 0.75,
            }}>
              <div style={{ display: "flex", alignItems: "center",
                gap: 6, marginBottom: 6 }}>
                <span style={{ fontFamily: "JetBrains Mono",
                  fontWeight: 800, fontSize: 13, color: "var(--ink)" }}>
                  {e.minute}&apos;
                </span>
                <span style={{ fontSize: 9.5, textTransform: "uppercase",
                  color: "var(--muted)", letterSpacing: 0.5 }}>
                  {e.theme_label}
                </span>
                {currentMinute === e.minute && (
                  <span style={{ marginLeft: "auto", fontSize: 9,
                    color: tone, fontWeight: 700 }}>● ŞİMDİ</span>
                )}
              </div>
              <div style={{ fontSize: 11.5, color: "var(--ink)",
                lineHeight: 1.4, overflow: "hidden",
                display: "-webkit-box", WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical" as const }}>
                {e.headline}
              </div>
              <div style={{ marginTop: 4, fontSize: 10,
                color: "var(--muted)" }}>
                güven: {e.confidence_label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Sayfa
// --------------------------------------------------------------------------- //

interface TimelineEntry {
  minute: number;
  headline: string;
  theme_label: string;
  urgency: number;
  confidence_label: string;
}

export default function LiveDecisionPage() {
  const [minute, setMinute] = useState(80);
  const [matchId, setMatchId] = useState(DEFAULT_MATCH_ID);
  const [teamId, setTeamId] = useState(DEFAULT_TEAM_ID);
  const [starId, setStarId] = useState(DEFAULT_STAR_ID);
  const [playing, setPlaying] = useState(false);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const lastMinuteRef = useRef<number | null>(null);

  // DEMO_MODE: yerel veri; CANLI: backend
  const apiPath = !DEMO_MODE
    ? `/admin/matches/${matchId}/live-decision`
      + `?my_team_id=${teamId}&current_minute=${minute}&star_player_id=${starId}`
    : null;
  const { data: liveData, error, isLoading } = useSWR<LiveDecisionResponse>(
    apiPath, apiFetch, { revalidateOnFocus: false, shouldRetryOnError: false },
  );

  const data = DEMO_MODE ? demoSnapshot(minute) : liveData;

  // ▶ Replay otomasyonu — REPLAY_TICK_MS aralıkla dakika ilerletir
  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(() => {
      setMinute((m) => {
        const next = m + REPLAY_MINUTE_STEP;
        if (next > 95) {
          setPlaying(false);
          return m;
        }
        return next;
      });
    }, REPLAY_TICK_MS);
    return () => clearInterval(id);
  }, [playing]);

  // Timeline: her yeni dakika kararını biriktir (aynı dakika tekrarlamasın)
  useEffect(() => {
    const p = data?.context?.primary;
    if (!p || lastMinuteRef.current === minute) return;
    lastMinuteRef.current = minute;
    setTimeline((prev) => [
      ...prev.slice(-(TIMELINE_MAX - 1)),
      {
        minute,
        headline: p.headline ?? "—",
        theme_label: p.theme_label ?? "—",
        urgency: p.urgency ?? 0,
        confidence_label: p.confidence_label ?? "—",
      },
    ]);
  }, [minute, data]);

  function resetTimeline() {
    setTimeline([]);
    lastMinuteRef.current = null;
  }

  const right = (
    <>
      <div className="rc">
        <h3>Kontroller</h3>
        <div style={{ display: "grid", gap: 10 }}>
          <label style={{ fontSize: 11.5 }}>
            Dakika: <b>{minute}&apos;</b>
            <input type="range" min={50} max={95} value={minute}
              onChange={(e) => { setPlaying(false); setMinute(parseInt(e.target.value)); }}
              style={{ width: "100%", marginTop: 4 }} />
          </label>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              type="button"
              onClick={() => {
                if (playing) { setPlaying(false); return; }
                if (minute >= 95) { setMinute(60); resetTimeline(); }
                setPlaying(true);
              }}
              style={{
                flex: 1, padding: "8px 10px",
                background: playing ? "var(--crit)" : "var(--accent, var(--ink))",
                color: playing ? "var(--ink)" : "var(--panel)",
                border: "none", borderRadius: 4, cursor: "pointer",
                fontWeight: 700, fontSize: 12,
              }}
            >
              {playing ? "⏸ Duraklat" : "▶ Replay (60→95)"}
            </button>
            <button
              type="button"
              onClick={() => { resetTimeline(); setMinute(60); }}
              style={{
                padding: "8px 10px", background: "var(--panel2)",
                color: "var(--ink)", border: "1px solid var(--line)",
                borderRadius: 4, cursor: "pointer", fontSize: 12,
              }}
              title="Timeline sıfırla, başa dön"
            >
              ↺
            </button>
          </div>
          {!DEMO_MODE && (
            <>
              <MatchSelector
                value={matchId}
                onSelect={(m) => {
                  setMatchId(m.match_id);
                  setTeamId(m.home_team_external_id);
                  resetTimeline();
                }}
              />
              <label style={{ fontSize: 11.5 }}>Bizim takım external_id:
                <input type="number" value={teamId}
                  onChange={(e) => setTeamId(parseInt(e.target.value) || 0)}
                  style={{ width: "100%", marginTop: 2, padding: 6,
                    background: "var(--panel2)", color: "var(--ink)",
                    border: "1px solid var(--line)", borderRadius: 4 }} />
              </label>
              <label style={{ fontSize: 11.5 }}>Yıldız oyuncu id:
                <input type="number" value={starId}
                  onChange={(e) => setStarId(parseInt(e.target.value) || 0)}
                  style={{ width: "100%", marginTop: 2, padding: 6,
                    background: "var(--panel2)", color: "var(--ink)",
                    border: "1px solid var(--line)", borderRadius: 4 }} />
              </label>
            </>
          )}
        </div>
      </div>
      <div className="rc">
        <h3>Açıklama</h3>
        <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.6 }}>
          10 maç-içi engine'in birleşik karar paneli. Üstteki <b>ŞİMDİ ŞUNU YAP</b>
          kutusu, orkestra şefi (context_engine) tarafından çakışan sinyallerden
          tek aksiyona indirgenmiş primary karardır.
        </div>
      </div>
    </>
  );

  if (!DEMO_MODE && isLoading) {
    return (
      <ConsoleShell active="/decisions" title="Maç-içi Karar"
        sub="GET /admin/matches/{id}/live-decision" right={right}>
        <div className="pgdesc">Yükleniyor…</div>
      </ConsoleShell>
    );
  }
  if (!DEMO_MODE && error) {
    return (
      <ConsoleShell active="/decisions" title="Maç-içi Karar" right={right}>
        <div className="pgdesc">Yüklenemedi: {String(error).slice(0, 200)}</div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell
      active="/decisions"
      title="Maç-içi Karar"
      sub={`Dakika ${minute}' · Skor ${data?.score ?? "—"}`}
      desc="Orkestra şefi 10 engine'in çakışan sinyallerini tek 'ŞİMDİ şunu yap' kararına indirger. Kartlar her engine'in ham çıktısını gösterir."
      right={right}
    >
      <TimelineStrip entries={timeline} currentMinute={minute} />
      <PrimaryBanner ctx={data?.context} />

      <div className="st" style={{ marginTop: 8, marginBottom: 8 }}>
        <h2>Engine Çıktıları</h2>
        <span className="ep">7 ham sinyal · context engine bunları birleştirir</span>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(310px, 1fr))",
        gap: 12,
      }}>
        <ClosingCard data={data?.closing_strategy} />
        <MomentumCard data={data?.momentum} />
        <SubTimingCard data={data?.sub_timing} />
        <TacticalTriggersCard data={data?.tactical_triggers} />
        <RiskMonitorCard data={data?.risk_monitor} />
        <StarFeedCard data={data?.star_feed} />
        <FoulPressureCard data={data?.foul_pressure} />
      </div>

      {data?.context?.secondary && data.context.secondary.length > 0 && (
        <>
          <div className="st" style={{ marginTop: 24, marginBottom: 8 }}>
            <h2>İkincil Aksiyonlar</h2>
            <span className="ep">Farklı temalardaki paralel öneriler</span>
          </div>
          {data.context.secondary.map((s, i) => (
            <div key={i} className="rc" style={{
              marginBottom: 10, borderLeft: "3px solid var(--mid)",
            }}>
              <div style={{ display: "flex", gap: 12, alignItems: "center",
                marginBottom: 6 }}>
                <span style={{ fontSize: 10, textTransform: "uppercase",
                  color: "var(--muted)", letterSpacing: 0.6, fontWeight: 700 }}>
                  {s.theme_label}
                </span>
                <span style={{ fontSize: 11, color: "var(--muted)" }}>
                  güven: <b style={{ color: "var(--ink)" }}>{s.confidence_label}</b>
                </span>
              </div>
              <div style={{ fontSize: 13, color: "var(--ink)" }}>{s.headline}</div>
              {s.rationale && (
                <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4 }}>
                  {s.rationale}
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </ConsoleShell>
  );
}
