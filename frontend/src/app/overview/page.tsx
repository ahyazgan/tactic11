"use client";

/**
 * Genel Bakış — Teknik Ekip Konsolu. ConsoleShell çatısını kullanır.
 * KPI şeridi + yük-riski tablosu + sağ kolon (sıradaki maç / uyarılar / görevler).
 * Gerçek veri: GET /physical-tests/players.
 */

import useSWR from "swr";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { CSSProperties, KeyboardEvent, ReactNode } from "react";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoPlayerRows, demoNextMatch, demoRecentForm, demoRatingTrend, demoLive, demoSquad, type FormResult, type Briefing } from "@/lib/demo-data";
import { SourceMark } from "@/lib/data-source";
import { Crest } from "@/lib/teams";
import { PlayerAvatar } from "@/lib/player-avatar";

// Oyuncu id → pozisyon (avatar rengi; demoPlayerRows pozisyon taşımaz).
const POS_BY_ID: Record<string, string> = Object.fromEntries(
  demoSquad.map((p) => [String(p.player_id), p.position]),
);

// Oyuncu id → forma numarası (ekranda iç id DEĞİL forma gösterilir).
const SHIRT_BY_ID: Record<string, number> = Object.fromEntries(
  demoSquad.map((p) => [String(p.player_id), p.shirt]),
);
import { demoTrackRecord } from "@/lib/track-record";
import { demoNextMatchSimulation } from "@/lib/match-simulation";
import { weeklyInsights } from "@/lib/weekly-insights";
import { ConsoleShell } from "../_console/shell";
import { RiskDonut, LegendRow } from "../_console/viz";
import { TrackRecordBadge } from "../_console/track-record";
import { InsightFeedCompact } from "../_console/insights";

// Küçük inline sparkline (bağımlılıksız) — rating trendi gibi seriler için.
function Sparkline({ values, color = "var(--accent)", width = 132, height = 34 }: { values: number[]; color?: string; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - 4) + 2;
    const y = height - 3 - ((v - min) / span) * (height - 6);
    return [x, y] as const;
  });
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg width={width} height={height} aria-hidden="true" style={{ display: "block" }}>
      <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="2.6" fill={color} />
    </svg>
  );
}

const FORM_VAR: Record<FormResult["r"], string> = { W: "var(--low)", D: "var(--mid)", L: "var(--crit)" };

// Tıklanır kart — widget'ı ilgili detay sayfasına götürür (klavyeyle de çalışır).
function ClickCard({ href, label, className = "rc clickable", style, children }: {
  href: string;
  label: string;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  const router = useRouter();
  const go = () => router.push(href);
  return (
    <div
      className={className}
      role="link"
      tabIndex={0}
      aria-label={label}
      title={label}
      onClick={go}
      onKeyDown={(e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }}
      style={style}
    >
      {children}
    </div>
  );
}

// Form pulları + rating sparkline (form/rating motorlarının panel sunumu).
function FormTrendCard({ form, rating, href }: { form: FormResult[]; rating: number[]; href: string }) {
  const w = form.filter((f) => f.r === "W").length;
  const d = form.filter((f) => f.r === "D").length;
  const l = form.filter((f) => f.r === "L").length;
  const trendUp = rating.length >= 2 && rating[rating.length - 1] >= rating[0];
  return (
    <ClickCard href={href} label="Takım profili — form ve rating detayı" style={{ margin: 0 }}>
      <h3>Form & Rating <span className="tiny" style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><SourceMark id="api_football" height={13} /></span></h3>
      <div style={{ display: "flex", gap: 5, marginBottom: 12 }}>
        {form.map((f, i) => (
          <span key={i} title={`${f.ha === "H" ? "İç" : "Dış"} · ${f.opp} ${f.gf}-${f.ga}`}
            style={{ width: 26, height: 26, borderRadius: 7, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, color: "#fff", background: FORM_VAR[f.r] }}>
            {f.r}
          </span>
        ))}
        <span style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--dim)", alignSelf: "center", fontFamily: "JetBrains Mono" }}>{w}G {d}B {l}M</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <div>
          <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: ".4px" }}>Model rating</div>
          <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: "-1px", color: trendUp ? "var(--low)" : "var(--high)" }}>
            {rating[rating.length - 1]}<span style={{ fontSize: 13, color: "var(--dim)", fontWeight: 500 }}> /100</span>
          </div>
          <div style={{ fontSize: 11, color: trendUp ? "var(--low)" : "var(--high)" }}>{trendUp ? "▲" : "▼"} son 8 hafta {rating[rating.length - 1] - rating[0] >= 0 ? "+" : ""}{rating[rating.length - 1] - rating[0]}</div>
        </div>
        <Sparkline values={rating} color={trendUp ? "var(--low)" : "var(--high)"} />
      </div>
    </ClickCard>
  );
}

const BRIEF_VAR: Record<string, string> = { "Maç Öncesi": "var(--accent)", "Haftalık": "var(--low)", "Scout": "var(--mid)" };

// Son AI agent çıktıları (AgentOutput) feed'i. Her satır ilgili rapora gider.
function BriefingFeed({ items, hrefFor }: { items: Briefing[]; hrefFor: (b: Briefing) => string }) {
  const router = useRouter();
  return (
    <div className="rc" style={{ margin: 0 }}>
      <h3>AI Brifing Akışı <span className="tiny" style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><SourceMark id="claude" height={13} /></span></h3>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {items.map((b, i) => {
          const c = BRIEF_VAR[b.type] ?? "var(--dim)";
          const href = hrefFor(b);
          return (
            <div
              key={i}
              className="rowlink"
              role="link"
              tabIndex={0}
              aria-label={`${b.title} — rapora git`}
              onClick={() => router.push(href)}
              onKeyDown={(e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push(href); } }}
              style={{ padding: "9px 6px", margin: "0 -6px", borderTop: i ? "1px solid var(--line)" : undefined }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                <span style={{ fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".4px", color: c, border: `1px solid ${c}`, borderRadius: 5, padding: "1px 6px" }}>{b.type}</span>
                <b style={{ fontSize: 12.5, flex: 1 }}>{b.title}</b>
                <span style={{ fontSize: 10.5, color: "var(--dim)", fontFamily: "JetBrains Mono" }}>{b.when}</span>
              </div>
              <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>{b.summary}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface PlayerRow {
  player_id: string;
  player_name: string;
  test_count: number;
  latest_test_date: string | null;
  risk_label: string;
  risk_score: number;
}

// --------------------------------------------------------------------------- //
// GERÇEK-MOD (DEMO kapalı) — backend tipleri + yardımcılar
// --------------------------------------------------------------------------- //
interface TeamRow { external_id: number; name: string }
interface FormValue { wins: number; draws: number; losses: number; points_per_game: number; goal_diff_per_match?: number }
interface RatingValue { rating: number; points_per_game?: number }
interface MatchRow { external_id: number; home_team_external_id: number; away_team_external_id: number; kickoff?: string | null }
interface PredictValue { prob_home_win: number; prob_draw: number; prob_away_win: number; most_likely_score?: [number, number] }
interface AgentOutputRow { id: number; agent_name: string; subject_type: string; subject_id: number; summary: string; updated_at: string }

// agent_name → okunur brifing tipi (BRIEF_VAR renk haritasıyla uyumlu kalsın diye
// bilinenler "Maç Öncesi/Haftalık/Scout"a map'lenir; gerisi adı korur).
const AGENT_TYPE: Record<string, string> = {
  pre_match_report: "Maç Öncesi", PreMatchReportAgent: "Maç Öncesi",
  post_match_report: "Maç Sonu",  PostMatchReportAgent: "Maç Sonu",
  weekly_digest: "Haftalık",      WeeklyDigestAgent: "Haftalık",
  opponent_scout: "Scout",        OpponentScoutAgent: "Scout",
};
function humanAgent(name: string): string { return AGENT_TYPE[name] ?? name; }

// Maç listesinden (kickoff desc) bir sonraki oynanacak maç; yoksa en yeni maç.
function pickNextMatch(rows: MatchRow[] | undefined): MatchRow | undefined {
  if (!rows || rows.length === 0) return undefined;
  const now = Date.now();
  const upcoming = rows
    .filter((m) => m.kickoff && new Date(m.kickoff).getTime() >= now)
    .sort((a, b) => new Date(a.kickoff!).getTime() - new Date(b.kickoff!).getTime());
  return upcoming[0] ?? rows[0];
}

// Gerçek-mod Form & Rating kartı — form motoru per-maç dizisi vermez; W/D/L
// sayıları + maç-başı puan + model rating gösterilir (demo'daki sparkline yok).
function FormTrendCardReal({ form, rating, href }: { form?: FormValue; rating?: RatingValue; href: string }) {
  if (!form && !rating) {
    return <div className="rc" style={{ margin: 0, color: "var(--dim)", fontSize: 12.5 }}>Form verisi yok.</div>;
  }
  const total = form ? form.wins + form.draws + form.losses : 0;
  const bars: { k: string; n: number; c: string }[] = form ? [
    { k: "G", n: form.wins, c: "var(--low)" },
    { k: "B", n: form.draws, c: "var(--mid)" },
    { k: "M", n: form.losses, c: "var(--crit)" },
  ] : [];
  return (
    <ClickCard href={href} label="Takım profili — form ve rating detayı" style={{ margin: 0 }}>
      <h3>Form & Rating <span className="tiny" style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><SourceMark id="api_football" height={13} /></span></h3>
      {form && (
        <>
          <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", marginBottom: 8, background: "var(--panel3)" }}>
            {bars.map((b) => b.n > 0 && <i key={b.k} style={{ width: `${(b.n / total) * 100}%`, background: b.c }} />)}
          </div>
          <div style={{ display: "flex", gap: 14, marginBottom: 12, fontSize: 12 }}>
            {bars.map((b) => (
              <span key={b.k} style={{ color: "var(--muted)" }}><b style={{ color: b.c, fontFamily: "JetBrains Mono" }}>{b.n}</b> {b.k === "G" ? "galibiyet" : b.k === "B" ? "berabere" : "mağlubiyet"}</span>
            ))}
            <span style={{ marginLeft: "auto", color: "var(--dim)", fontFamily: "JetBrains Mono" }}>ppg {form.points_per_game?.toFixed(2) ?? "—"}</span>
          </div>
        </>
      )}
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: ".4px" }}>Model rating</span>
        <span style={{ fontSize: 24, fontWeight: 800, letterSpacing: "-1px", color: "var(--ink)" }}>{rating ? Math.round(rating.rating) : "—"}<span style={{ fontSize: 13, color: "var(--dim)", fontWeight: 500 }}> /100</span></span>
      </div>
    </ClickCard>
  );
}

const RISK_VAR: Record<string, string> = {
  Kritik: "var(--crit)",
  Yüksek: "var(--high)",
  Orta: "var(--mid)",
  Düşük: "var(--low)",
};

function condColor(v: number): string {
  return v >= 85 ? "var(--low)" : v >= 72 ? "var(--mid)" : "var(--high)";
}

export default function OverviewConsolePage() {
  const router = useRouter();
  const { data, error, isLoading } = useSWR<PlayerRow[]>(
    DEMO_MODE ? null : "/physical-tests/players", apiFetch, {
    shouldRetryOnError: false,
  });
  const players = DEMO_MODE ? (demoPlayerRows as PlayerRow[]) : (data ?? []);

  // Gerçek-mod ek veriler — tenant-kapsamlı. "Birincil takım" = /teams ilki.
  const { data: teams } = useSWR<TeamRow[]>(DEMO_MODE ? null : "/teams", apiFetch, { shouldRetryOnError: false });
  const myTeam = teams?.[0];
  const myTeamId = myTeam?.external_id;
  const teamName = (id?: number) => teams?.find((t) => t.external_id === id)?.name ?? (id != null ? `#${id}` : "—");
  const { data: formResp } = useSWR<{ value: FormValue }>(!DEMO_MODE && myTeamId ? `/teams/${myTeamId}/form?last_n=5` : null, apiFetch, { shouldRetryOnError: false });
  const { data: ratingResp } = useSWR<{ value: RatingValue }>(!DEMO_MODE && myTeamId ? `/teams/${myTeamId}/rating` : null, apiFetch, { shouldRetryOnError: false });
  const { data: matchesResp } = useSWR<MatchRow[]>(!DEMO_MODE && myTeamId ? `/teams/${myTeamId}/matches` : null, apiFetch, { shouldRetryOnError: false });
  const nextMatch = pickNextMatch(matchesResp);
  const { data: predictResp } = useSWR<{ value: PredictValue }>(!DEMO_MODE && nextMatch ? `/matches/${nextMatch.external_id}/predict?use_ml=true` : null, apiFetch, { shouldRetryOnError: false });
  const { data: agentOutputs } = useSWR<AgentOutputRow[]>(DEMO_MODE ? null : "/admin/agent-outputs?limit=12", apiFetch, { shouldRetryOnError: false });

  // Sıradaki maç: biz ev sahibi miyiz? olasılıkları bizim perspektifimize çevir.
  const weAreHome = nextMatch ? nextMatch.home_team_external_id === myTeamId : true;
  const pv = predictResp?.value;
  const realWin = pv ? (weAreHome ? pv.prob_home_win : pv.prob_away_win) : null;
  const realLoss = pv ? (weAreHome ? pv.prob_away_win : pv.prob_home_win) : null;
  const realDraw = pv ? pv.prob_draw : null;
  const oppName = nextMatch ? teamName(weAreHome ? nextMatch.away_team_external_id : nextMatch.home_team_external_id) : "—";
  const nextKickoff = nextMatch?.kickoff ? new Date(nextMatch.kickoff) : null;
  const realBriefings: Briefing[] = (agentOutputs ?? []).map((o) => ({
    type: humanAgent(o.agent_name),
    title: `${o.subject_type} #${o.subject_id}`,
    when: o.updated_at.slice(0, 16).replace("T", " "),
    summary: o.summary,
  }));
  // Backend bağlı değil / boş → demo şeridi göster.
  const offline = !isLoading && (!!error || players.length === 0);
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

  const dlow = players.filter((p) => p.risk_label === "Düşük").length;
  const dmid = players.filter((p) => p.risk_label === "Orta").length;
  const dhigh = players.filter((p) => p.risk_label === "Yüksek").length;
  const dcrit = players.filter((p) => p.risk_label === "Kritik").length;
  const segments = [
    { value: dlow, color: "var(--low)" },
    { value: dmid, color: "var(--mid)" },
    { value: dhigh, color: "var(--high)" },
    { value: dcrit, color: "var(--crit)" },
  ];

  // Sıradaki maç kartı — demo'da olasılıklar simülasyon motorundan (Poisson-Dixon-Coles),
  // statik değerler değil; canlıda backend predict'ten.
  const nmSim = DEMO_MODE ? demoNextMatchSimulation() : null;
  const nmWin = nmSim ? nmSim.probHomeWin : realWin;
  const nmDraw = nmSim ? nmSim.probDraw : realDraw;
  const nmLoss = nmSim ? nmSim.probAwayWin : realLoss;
  const nmHome = DEMO_MODE ? "Beşiktaş" : (myTeam?.name ?? "—");
  const nmAway = DEMO_MODE ? demoNextMatch.away : oppName;
  const nmHeader = DEMO_MODE
    ? `${demoNextMatch.date} · ${demoNextMatch.kickoff}`
    : (nextKickoff ? nextKickoff.toLocaleString("tr-TR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "— · —");
  const nmWhen = DEMO_MODE
    ? `${demoNextMatch.competition}${demoNextMatch.venue ? ` · ${demoNextMatch.venue}` : ""}`
    : (nextMatch ? `${weAreHome ? "İç saha" : "Deplasman"}` : "Maç verisi için Maçlar sekmesi");
  const pct = (x: number | null | undefined) => (x != null ? `%${Math.round(x * 100)}` : "—");
  const wpx = (x: number | null | undefined) => (x != null ? Math.round(x * 100) : 33);

  // Widget hedefleri — her kart dolu bir detay sayfasına gider (demo'da 9001 =
  // sıradaki maç fikstür id'si; maç detayı demo'da tek evrenden beslenir).
  const matchHref = DEMO_MODE ? "/matches/9001" : (nextMatch ? `/matches/${nextMatch.external_id}` : "/matches");
  const teamHref = DEMO_MODE ? "/teams/100" : (myTeamId != null ? `/teams/${myTeamId}` : "/teams");
  const briefHref = (b: Briefing) =>
    b.type === "Maç Öncesi" || b.type === "Maç Sonu" ? matchHref
      : b.type === "Scout" ? "/scout"
      : "/weekly-report";

  const right = (
    <>
      <ClickCard href="/medical" label="Tıbbi merkez — kadro sağlığı detayı">
        <h3>Kadro Sağlığı <span className="tiny">{total} oyuncu</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut segments={segments} centerLabel={total} centerSub="kadro" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <LegendRow color="var(--low)" label="Düşük" value={dlow} />
            <LegendRow color="var(--mid)" label="Orta" value={dmid} />
            <LegendRow color="var(--high)" label="Yüksek" value={dhigh} />
            <LegendRow color="var(--crit)" label="Kritik" value={dcrit} />
          </div>
        </div>
      </ClickCard>

      <ClickCard href={matchHref} label="Maç önizleme ve plan">
        <h3>Sıradaki Maç <span className="tiny">{nmHeader}</span></h3>
        <div className="nm-vs"><span className="t" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Crest team={nmHome} size={18} />{nmHome}</span><span className="x">vs</span><span className="t away" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>{nmAway}<Crest team={nmAway} size={18} /></span></div>
        <div className="nm-when">{nmWhen}</div>
        <div className="probbar">
          <i style={{ width: `${wpx(nmWin)}%`, background: "var(--low)" }} />
          <i style={{ width: `${wpx(nmDraw)}%`, background: "var(--dim)" }} />
          <i style={{ width: `${wpx(nmLoss)}%`, background: "var(--high)" }} />
        </div>
        <div className="probleg">
          <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>{pct(nmWin)}</div><div className="pl">Galibiyet</div></div>
          <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>{pct(nmDraw)}</div><div className="pl">Berabere</div></div>
          <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>{pct(nmLoss)}</div><div className="pl">Mağlubiyet</div></div>
        </div>
        {DEMO_MODE && (
          <div style={{ marginTop: 9, display: "flex", justifyContent: "center" }} onClick={(e) => e.stopPropagation()}>
            <Link href="/calibration" style={{ textDecoration: "none" }}><TrackRecordBadge tr={demoTrackRecord()} type="match" compact /></Link>
          </div>
        )}
        {DEMO_MODE && demoNextMatch.aiPreview && (
          <div style={{ marginTop: 11, paddingTop: 10, borderTop: "1px solid var(--line)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
              <SourceMark id="claude" height={12} />
              <span style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: ".4px", color: "var(--dim)" }}>maç önizleme</span>
            </div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>{demoNextMatch.aiPreview}</div>
          </div>
        )}
      </ClickCard>

      <div className="rc">
        <h3>Uyarılar <span className="tiny">{alerts.length} aktif</span></h3>
        {alerts.length === 0 && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Kritik/yüksek riskli oyuncu yok.</div>}
        {alerts.map((a) => {
          const rv = RISK_VAR[a.risk_label] ?? "var(--dim)";
          return (
            <div
              className="alrt rowlink"
              key={a.player_id}
              role="link"
              tabIndex={0}
              aria-label={`${a.player_name} oyuncu profili`}
              title={`${a.player_name} — oyuncu profili`}
              onClick={() => router.push(`/players/${a.player_id}`)}
              onKeyDown={(e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push(`/players/${a.player_id}`); } }}
            >
              <PlayerAvatar name={a.player_name} position={POS_BY_ID[a.player_id]} size={26} style={{ marginRight: 9, boxShadow: `0 0 0 2px ${rv}` }} />
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
            <div className="task rowlink" role="link" tabIndex={0} title="Kadro ekranına git"
              onClick={() => router.push("/squad")}
              onKeyDown={(e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push("/squad"); } }}>
              <span className="cb" /><span className="tt">{risky} riskli oyuncu için kadro kararı</span></div>
            <div className="task rowlink" role="link" tabIndex={0} title="Fiziksel testlere git"
              onClick={() => router.push("/physical-tests")}
              onKeyDown={(e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push("/physical-tests"); } }}>
              <span className="cb" /><span className="tt">Re-test planı (yüksek risk)</span></div>
          </>
        ) : (
          <div style={{ fontSize: "12px", color: "var(--dim)" }}>Bekleyen görev yok.</div>
        )}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/overview"
      title="Genel Bakış"
      sub="Teknik ekip kontrol paneli"
      desc="Kadro durumu ve yük-riski öncelikleri aşağıda. Sayılar canlı veriden."
      navBadge={risky}
      right={right}
    >
      {DEMO_MODE && (
        <Link href="/matches/demo/live" style={{ textDecoration: "none" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 15px", marginBottom: 16, borderRadius: 12, border: "1px solid var(--crit)", background: "linear-gradient(90deg, rgba(220,38,38,0.10), transparent 70%)", cursor: "pointer" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 800, textTransform: "uppercase", letterSpacing: ".5px", color: "var(--crit)", flexShrink: 0 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--crit)", boxShadow: "0 0 7px var(--crit)" }} />Canlı
            </span>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)" }}>{demoLive.home} {demoLive.score[0]}-{demoLive.score[1]} {demoLive.away}</span>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>{demoLive.minute}&apos; · momentum {demoLive.momentumHolder}</span>
            <span style={{ marginLeft: "auto", fontSize: 11.5, fontWeight: 600, color: "var(--crit)", flexShrink: 0 }}>Konsola git →</span>
          </div>
        </Link>
      )}

      {offline && (
        <div className="demobar">
          <span style={{ fontSize: 15 }}>🔌</span>
          <span><b>Demo modu</b> — veri sunucusu (backend) bağlı değil, sayılar 0 görünüyor. Bağlanınca tüm ekranlar gerçek veriyle dolar.</span>
          <a className="db-cta" href="https://github.com/ahyazgan/tactic11#-canlıya-alma-3-dakika" target="_blank" rel="noreferrer">Nasıl bağlanır?</a>
        </div>
      )}

      <div className="kpis">
        {isLoading ? (
          [0, 1, 2, 3, 4].map((i) => (
            <div className="kpi" key={i}>
              <div className="kl"><span className="sk sk-line" style={{ width: 56 }} /></div>
              <div className="kn"><span className="sk sk-kn" /></div>
              <div className="kd"><span className="sk sk-line" style={{ width: 84 }} /></div>
            </div>
          ))
        ) : (
          <>
            <ClickCard className="kpi clickable" href="/squad" label="Kadro ekranı"><div className="kl">Kadro</div><div className="kn">{total}</div><div className="kd"><span className="u">{ready} hazır</span> · {risky} riskli</div></ClickCard>
            <ClickCard className="kpi clickable" href="/physical-tests" label="Fiziksel testler"><div className="kl">Toplam Test</div><div className="kn">{totalTests}</div><div className="kd">{total} oyuncu</div></ClickCard>
            <ClickCard className="kpi clickable" href="/performance" label="Sezon performansı ve batarya"><div className="kl">Ort. Kondisyon</div><div className="kn">{avgCond}<span className="pct">%</span></div><div className="kd">risk skorundan</div></ClickCard>
            <ClickCard className="kpi clickable" href="/medical" label="Tıbbi merkez — riskli oyuncular"><div className="kl">Kritik/Yüksek</div><div className="kn" style={{ color: risky ? "var(--high)" : "var(--low)" }}>{risky}</div><div className="kd">acil takip</div></ClickCard>
            <ClickCard className="kpi clickable" href="/squad" label="Kadro — sahaya hazır oyuncular"><div className="kl">Hazır</div><div className="kn" style={{ color: "var(--low)" }}>{ready}</div><div className="kd">düşük risk</div></ClickCard>
          </>
        )}
      </div>

      <div className="rc" style={{ margin: "0 0 16px 0" }}>
        <h3>Analist Modülleri <span className="tiny">manuel veri girişi + saf hesap motorları</span></h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginTop: 8 }}>
          <ClickCard className="rc clickable" href="/mac-notla" label="Maçı Notla — 1-10 oyuncu notu giriş" style={{ margin: 0 }}>
            <div className="kl">Maçı Notla</div>
            <div className="kd" style={{ marginTop: 6 }}>Oyuncuları 1-10 notla + maç bağlamını işaretle → performans motorlarını besle</div>
          </ClickCard>
          <ClickCard className="rc clickable" href="/performans" label="Performans Analizi — 8 bölüm" style={{ margin: 0 }}>
            <div className="kl">Performans Analizi</div>
            <div className="kd" style={{ marginTop: 6 }}>Tutarlılık · trajectory · anomali · clutch · kadro formu · karşılaştırma</div>
          </ClickCard>
          <ClickCard className="rc clickable" href="/taktik-komuta" label="Taktik Komuta — maç planı + karar danışmanı" style={{ margin: 0 }}>
            <div className="kl">Taktik Komuta</div>
            <div className="kd" style={{ marginTop: 6 }}>Maç planı (H+I+K) · fırsat penceresi (L) · TD karar danışmanı (N)</div>
          </ClickCard>
        </div>
      </div>

      {DEMO_MODE ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
          <FormTrendCard form={demoRecentForm} rating={demoRatingTrend} href={teamHref} />
          <div className="rc" style={{ margin: 0 }}>
            <h3>Bu Haftanın İçgörüleri <span className="tiny" style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><SourceMark id="claude" height={13} /> 4 motordan otomatik</span></h3>
            <InsightFeedCompact data={weeklyInsights()} limit={4} />
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
          <FormTrendCardReal form={formResp?.value} rating={ratingResp?.value} href={teamHref} />
          {realBriefings.length > 0 ? (
            <BriefingFeed items={realBriefings} hrefFor={briefHref} />
          ) : (
            <div className="rc" style={{ margin: 0, color: "var(--dim)", fontSize: 12.5 }}>
              <h3>AI Brifing Akışı <span className="tiny" style={{ display: "inline-flex", gap: 5, alignItems: "center" }}><SourceMark id="claude" height={13} /></span></h3>
              Henüz agent çıktısı yok (daily brief tetiklenince dolar).
            </div>
          )}
        </div>
      )}

      <div className="st"><h2>Yük Riski — Kadro Durumu</h2><span className="ep">GET /physical-tests/players</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th><th>Oyuncu</th><th className="c">Test</th>
            <th className="c">Kondisyon</th><th className="c">Son Test</th><th className="c">Risk</th><th className="r">Skor</th>
          </tr></thead>
          <tbody>
            {isLoading && [0, 1, 2, 3, 4, 5].map((i) => (
              <tr key={`sk${i}`}>
                <td className="c"><span className="sk sk-line" style={{ width: 16, margin: "0 auto" }} /></td>
                <td><span className="sk sk-line" style={{ width: "60%" }} /></td>
                <td className="c"><span className="sk sk-line" style={{ width: 24, margin: "0 auto" }} /></td>
                <td className="c"><span className="sk sk-line" style={{ width: 56, margin: "0 auto" }} /></td>
                <td className="c"><span className="sk sk-line" style={{ width: 60, margin: "0 auto" }} /></td>
                <td className="c"><span className="sk sk-line" style={{ width: 50, margin: "0 auto" }} /></td>
                <td className="r"><span className="sk sk-line" style={{ width: 28, marginLeft: "auto" }} /></td>
              </tr>
            ))}
            {!isLoading && players.length === 0 && (
              <tr><td colSpan={7}>
                <div className="empty">
                  <div className="ei">📋</div>
                  <div className="et">Henüz test verisi yok</div>
                  <div className="es">Backend bağlanınca kadro yük-riski burada listelenir.</div>
                </div>
              </td></tr>
            )}
            {players.map((p, i) => {
              const cond = Math.round(100 - p.risk_score * 100);
              const rv = RISK_VAR[p.risk_label] ?? "var(--dim)";
              return (
                <tr
                  key={p.player_id}
                  onClick={() => router.push(`/players/${p.player_id}`)}
                  title={`${p.player_name} — oyuncu profili`}
                  style={{ cursor: "pointer" }}
                >
                  <td className="pnum c">{i + 1}</td>
                  <td><span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}><PlayerAvatar name={p.player_name} position={POS_BY_ID[p.player_id]} size={20} /><span className="nm">{p.player_name}</span> <span className="nat">#{SHIRT_BY_ID[p.player_id] ?? p.player_id}</span></span></td>
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
    </ConsoleShell>
  );
}
