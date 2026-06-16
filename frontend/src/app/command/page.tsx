"use client";

/**
 * Komuta Merkezi — tüm zeka motorlarının canlı çıktısı TEK ekranda.
 * "Uygulamayı aç, AI'nın bildiği her şeyi gör." Her kart kaynak sayfaya gider.
 *
 * Toplanan motorlar: maç simülasyonu, sakatlık risk endeksi, kadro reçetesi (11),
 * track-record, gelişim projeksiyonu, haftalık içgörüler. Saf+deterministik (demo).
 */

import * as React from "react";
import Link from "next/link";
import { DEMO_OPPONENT, demoSquad } from "@/lib/demo-data";
import { demoNextMatchSimulation } from "@/lib/match-simulation";
import { squadAvailability, recommendedXI } from "@/lib/lineup-advice";
import { squadRiskRanked, LEVEL_VAR, LEVEL_LABEL } from "@/lib/injury-risk";
import { demoTrackRecord } from "@/lib/track-record";
import { weeklyInsights } from "@/lib/weekly-insights";
import { computeDevelopmentFor, PHASE_LABEL, PHASE_VAR } from "@/lib/player-development";
import { commandIntel } from "@/lib/command-brief";
import { demoWinProbNow } from "@/lib/live-win-probability";
import { ConsoleShell } from "../_console/shell";
import { OutcomeBar, MarketChips } from "../_console/match-sim";
import { FormationPitch } from "../_console/lineup";
import { TrackRecordBadge, TypeBreakdown } from "../_console/track-record";
import { InsightFeedCompact } from "../_console/insights";
import { DecisionsQueue } from "../_console/decisions-queue";

const STATE_BADGE: Record<"pre" | "live" | "post", { label: string; color: string }> = {
  pre: { label: "MAÇ ÖNCESİ", color: "var(--accent)" },
  live: { label: "CANLI", color: "var(--crit)" },
  post: { label: "MAÇ SONRASI", color: "var(--muted)" },
};

const rateColor = (r: number) => r >= 0.7 ? "var(--low)" : r >= 0.55 ? "var(--mid)" : "var(--high)";

/** Kaynak sayfaya giden tıklanabilir kart sarmalayıcı. */
function Card({ href, title, tag, children, span }: { href: string; title: string; tag?: string; children: React.ReactNode; span?: boolean }) {
  return (
    <Link href={href} className="rowlink" style={{ textDecoration: "none", display: "block", gridColumn: span ? "1 / -1" : undefined }}>
      <div className="rc" style={{ margin: 0, height: "100%" }}>
        <h3>{title} {tag && <span className="tiny">{tag}</span>}</h3>
        {children}
      </div>
    </Link>
  );
}

export default function CommandCenterPage() {
  const intel = commandIntel();            // sentez: durum + brifing + kararlar + delta KPI
  const isLive = intel.state === "live";
  const sim = demoNextMatchSimulation();
  const avail = squadAvailability();
  const xi = recommendedXI(DEMO_OPPONENT, avail);
  const tr = demoTrackRecord();
  const insights = weeklyInsights();
  const riskTop = squadRiskRanked().slice(0, 4);
  const rested = avail.filter((a) => a.verdict === "dinlendir");
  const win = isLive ? demoWinProbNow() : null;

  // Gelişim radarı: en yüksek büyüme alanı (genç tavan) + en belirgin düşüş.
  const devs = demoSquad
    .map((p) => ({ p, d: computeDevelopmentFor(p.player_id)! }))
    .filter((x) => x.d);
  const risers = [...devs].sort((a, b) => (b.d.potential - b.d.currentOverall) - (a.d.potential - a.d.currentOverall)).slice(0, 3);
  const decliner = [...devs].filter((x) => x.d.phase === "düşüş" || x.d.phase === "plato")
    .sort((a, b) => b.d.currentOverall - a.d.currentOverall)[0];

  const sb = STATE_BADGE[intel.state];

  return (
    <ConsoleShell
      active="/command"
      title="Komuta Merkezi"
      sub="Tüm zeka tek ekranda"
      source="claude"
      desc="Maç simülasyonu, sakatlık riski, önerilen kadro, model isabeti, gelişim ve haftalık öncelikler — hepsi canlı, tek bakışta. Her kart kaynak sayfaya gider."
    >
      {/* #1 Yönetici brifingi — tüm motorlar tek hikâye, duruma uyarlı */}
      <div className="rc" style={{ margin: "0 0 14px", borderLeft: `3px solid ${sb.color}` }}>
        <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
          Yönetici Brifingi
          <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.5, color: "#fff", background: sb.color, borderRadius: 4, padding: "1px 7px" }}>{sb.label}</span>
          <span className="tiny" style={{ marginLeft: "auto" }}>6 motor sentezi</span>
        </h3>
        <div style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.65 }}>
          {intel.brief.map((s, i) => <span key={i}>{s} </span>)}
        </div>
      </div>

      {/* #3 Manşet KPI şeridi — geçen haftaya/maç-öncesine göre delta'lı */}
      <div className="kpis" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        {intel.kpis.map((k) => (
          <div className="kpi" key={k.key}>
            <div className="kl">{k.label}</div>
            <div className="kn" style={{ color: k.color }}>{k.value}</div>
            <div className="kd" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{k.sub}</div>
            {k.delta && (
              <div style={{ fontSize: 9.5, fontFamily: "JetBrains Mono", marginTop: 2, color: k.delta.good ? "var(--low)" : "var(--high)" }}>{k.delta.text}</div>
            )}
          </div>
        ))}
      </div>

      {/* #2 Bugünün Kararları — onayla/ertele */}
      <DecisionsQueue decisions={intel.decisions} />

      {/* Bu haftanın öncelikleri — tam genişlik manşet */}
      <div className="st" style={{ marginTop: 0 }}><h2>Bu Haftanın Öncelikleri</h2><span className="ep">4 motordan otomatik</span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <InsightFeedCompact data={insights} limit={5} />
      </div>

      {/* Motor kartları ızgarası */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12, alignItems: "stretch" }}>
        {/* #4 Maç kartı — canlıyken win-prob, değilse maç-öncesi sim */}
        {win ? (
          <Card href="/matches/demo/live" title="Canlı Maç" tag={`${win.minute}' · CANLI`}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8, display: "flex", alignItems: "center", gap: 8 }}>
              {sim.homeTeam} <span style={{ fontFamily: "JetBrains Mono" }}>{win.scoreHome}-{win.scoreAway}</span> {sim.awayTeam}
            </div>
            <div className="probbar">
              <i style={{ width: `${win.pHome * 100}%`, background: "var(--accent)" }} />
              <i style={{ width: `${win.pDraw * 100}%`, background: "var(--dim)" }} />
              <i style={{ width: `${win.pAway * 100}%`, background: "var(--high)" }} />
            </div>
            <div className="probleg">
              <div className="pi"><div className="pv" style={{ color: "var(--accent)" }}>%{Math.round(win.pHome * 100)}</div><div className="pl">{sim.homeTeam}</div></div>
              <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>%{Math.round(win.pDraw * 100)}</div><div className="pl">Berabere</div></div>
              <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>%{Math.round(win.pAway * 100)}</div><div className="pl">{sim.awayTeam}</div></div>
            </div>
            <div style={{ fontFamily: "JetBrains Mono", fontSize: 10.5, color: "var(--muted)", textAlign: "center", marginTop: 8 }}>
              maç-öncesi %{Math.round(sim.probHomeWin * 100)} → şu an %{Math.round(win.pHome * 100)} · kalan beklenen gol {win.lambdaHomeRem.toFixed(2)}–{win.lambdaAwayRem.toFixed(2)}
            </div>
          </Card>
        ) : (
          <Card href="/match-plan" title="Sıradaki Maç" tag="Poisson · Dixon-Coles">
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{sim.homeTeam} <span style={{ color: "var(--dim)" }}>vs</span> {sim.awayTeam}</div>
            <OutcomeBar sim={sim} />
            <div style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--muted)", textAlign: "center", margin: "8px 0 10px" }}>
              en olası {sim.mostLikelyScore[0]}-{sim.mostLikelyScore[1]} · beklenen gol {sim.lambdaHome.toFixed(1)}–{sim.lambdaAway.toFixed(1)}
            </div>
            <MarketChips sim={sim} />
          </Card>
        )}

        {/* Önerilen 11 */}
        <Card href="/squad" title="Önerilen Kadro" tag={`${xi.formation} · güven %${xi.confidence}`}>
          <FormationPitch advice={xi} />
          <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>
            {rested.length ? <>Dinlendir: <b style={{ color: "var(--crit)" }}>{rested.map((a) => `${a.player.player_name.split(" ").slice(-1)[0]} (${a.player.shirt})`).join(", ")}</b></> : "Riskli oyuncu yok — en güçlü 11 hazır."}
          </div>
        </Card>

        {/* Sakatlık radarı */}
        <Card href="/medical" title="Sakatlık Radarı" tag="risk endeksi">
          {riskTop.map((r) => (
            <div key={r.player.player_id} style={{ marginBottom: 9 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: 12 }}>
                <span style={{ color: "var(--ink)" }}>{r.player.player_name} <span className="nat">#{r.player.shirt}</span></span>
                <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: LEVEL_VAR[r.risk.level] }}>{r.risk.score}<span style={{ color: "var(--dim)", fontWeight: 400, fontSize: 10 }}>/100</span></span>
              </div>
              <div className="mbar" style={{ margin: "3px 0" }}><i style={{ width: `${r.risk.score}%`, background: LEVEL_VAR[r.risk.level] }} /></div>
              <div style={{ fontSize: 10.5, color: "var(--dim)" }}>{LEVEL_LABEL[r.risk.level]} · {r.risk.topDriver?.label ?? "—"}</div>
            </div>
          ))}
        </Card>

        {/* Model güveni */}
        <Card href="/calibration" title="Model Güveni" tag="track record">
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 32, fontWeight: 800, fontFamily: "JetBrains Mono", color: rateColor(tr.hitRate) }}>%{Math.round(tr.hitRate * 100)}</span>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>isabet · {tr.resolved} değerlendirme</span>
            <span style={{ marginLeft: "auto" }}><TrackRecordBadge tr={tr} compact /></span>
          </div>
          <TypeBreakdown tr={tr} />
          <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "JetBrains Mono", marginTop: 8 }}>Brier {tr.brier ?? "—"} · son seri {tr.streak}✓ · açık {tr.open}</div>
        </Card>

        {/* Gelişim radarı */}
        <Card href={`/players/${risers[0]?.p.player_id ?? demoSquad[0].player_id}`} title="Gelişim Radarı" tag="yaş eğrisi projeksiyonu">
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>Yükselen değerler</div>
          {risers.map((x) => (
            <div key={x.p.player_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: 12, marginBottom: 5 }}>
              <span style={{ color: "var(--ink)" }}>{x.p.player_name} <span className="nat">#{x.p.shirt}</span> <span style={{ color: "var(--dim)", fontSize: 10.5 }}>{x.p.age}y</span></span>
              <span style={{ fontFamily: "JetBrains Mono", fontSize: 11.5 }}>{x.d.currentOverall.toFixed(1)} <span style={{ color: "var(--low)" }}>→ {x.d.potential.toFixed(1)} ▲{(x.d.potential - x.d.currentOverall).toFixed(1)}</span></span>
            </div>
          ))}
          {decliner && (
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--line)" }}>
              <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>İzle</div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: 12 }}>
                <span style={{ color: "var(--ink)" }}>{decliner.p.player_name} <span className="nat">#{decliner.p.shirt}</span> <span style={{ color: "var(--dim)", fontSize: 10.5 }}>{decliner.p.age}y</span></span>
                <span className="risk" style={{ color: PHASE_VAR[decliner.d.phase], fontSize: 10 }}><span className="rd" style={{ background: PHASE_VAR[decliner.d.phase] }} />{PHASE_LABEL[decliner.d.phase]}</span>
              </div>
            </div>
          )}
        </Card>

        {/* AI Asistan kısayolu */}
        <Card href="/chat" title="AI Asistan" tag="copilot">
          <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.6 }}>
            Tüm motorlara doğal dille sor — risk, kadro, maç tahmini, gelişim, karşılaştırma. Takip sorularını da hatırlar.
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
            {["Orkun mu Rıdvan mı riskli?", "Kimi dinlendireyim?", "Maçı kazanır mıyız?"].map((q) => (
              <span key={q} style={{ fontSize: 11, color: "var(--accent)", border: "1px solid var(--line)", borderRadius: 999, padding: "3px 10px" }}>{q}</span>
            ))}
          </div>
        </Card>
      </div>
    </ConsoleShell>
  );
}
