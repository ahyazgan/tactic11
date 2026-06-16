"use client";

/**
 * MAÇ ÖNCESİ MODU — maç günü hazırlık brifingi (karar-öncelikli, glanceable).
 *
 * In-match "mode"ların pre-match kardeşi. Analitik duvar DEĞİL (o /match-plan +
 * /opponent'ta). Antrenörün maç sabahı tek bakışta okuyacağı şey: doğrulanmış
 * tahmin → oyun planı → rakip zaafları → anahtar eşleşmeler → önerilen 11 →
 * ilkeler/pres → duran top → senaryolar. Motorlar: match-simulation, tactical-dna
 * (matchPlan), lineup-advice, demo-data. Matchday akışını başlatır → Maç Modu.
 */

import * as React from "react";
import Link from "next/link";
import { demoNextMatchSimulation } from "@/lib/match-simulation";
import { matchPlan, compareDna } from "@/lib/tactical-dna";
import { recommendedXI } from "@/lib/lineup-advice";
import { opponentXI, dangermen, theirGamePlan, type OppPlayer } from "@/lib/opponent-scout";
import { phasePlan, whatIfBranches } from "@/lib/prematch-plan";
import { demoWeaknesses, demoMatchups, demoScenarios, demoPlan } from "@/lib/demo-data";
import { OutcomeBar } from "./match-sim";
import { TacticalRadar } from "./tactical-radar";
import { TrustBadge } from "./trust-badge";

/** Rakip muhtemel 11 — kompakt saha, dangerman'ler vurgulu (projeksiyon). */
function OpponentPitch({ players }: { players: OppPlayer[] }) {
  const W = 440, H = 240, mx = 6;
  const px = (x: number) => mx + (x / 100) * (W - 2 * mx);
  const py = (y: number) => mx + (y / 100) * (H - 2 * mx);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", borderRadius: 10, background: "color-mix(in srgb, var(--high) 7%, var(--panel))" }}>
      <rect x={mx} y={mx} width={W - 2 * mx} height={H - 2 * mx} fill="none" stroke="var(--line2)" strokeWidth={1.3} rx={4} />
      <line x1={W / 2} y1={mx} x2={W / 2} y2={H - mx} stroke="var(--line2)" strokeWidth={1} />
      <circle cx={W / 2} cy={H / 2} r={28} fill="none" stroke="var(--line2)" strokeWidth={1} />
      <text x={W - mx - 8} y={H - mx - 6} fontSize={9} fill="var(--dim)" textAnchor="end">bize doğru →</text>
      {players.map((p) => {
        const dm = p.tier === "high";
        return (
          <g key={p.num}>
            <circle cx={px(p.x)} cy={py(p.y)} r={dm ? 13 : 10} fill="var(--panel)" stroke={dm ? "var(--crit)" : "var(--high)"} strokeWidth={dm ? 2.6 : 1.8} />
            <text x={px(p.x)} y={py(p.y) + 0.5} fontSize={9.5} fill="var(--ink)" textAnchor="middle" dominantBaseline="middle" fontFamily="JetBrains Mono" fontWeight={700}>{p.num}</text>
            <text x={px(p.x)} y={py(p.y) + (dm ? 22 : 19)} fontSize={7.5} fill={dm ? "var(--crit)" : "var(--dim)"} textAnchor="middle" fontWeight={dm ? 700 : 400}>{p.pos}</text>
          </g>
        );
      })}
    </svg>
  );
}

const SEV_COLOR: Record<string, string> = { yüksek: "var(--crit)", orta: "var(--mid)", düşük: "var(--low)" };
const SCEN_COLOR = (s: string) => (s === "Öndeyiz" ? "var(--low)" : s === "Geride" ? "var(--crit)" : "var(--mid)");

export function PrematchModeBody() {
  const sim = demoNextMatchSimulation();
  const plan = matchPlan(100, 101);
  const xi = recommendedXI();
  const matchups = [...demoMatchups].sort((a, b) => b.advantage - a.advantage);
  const oppXI = opponentXI(101);
  const dangers = dangermen(101);
  const theirPlan = theirGamePlan(101);
  const dna = compareDna(100, 101);
  const phases = phasePlan(101);
  const branches = whatIfBranches(101);

  return (
    <div style={{ maxWidth: 600, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Tahmin başlığı */}
      <div className="rc" style={{ margin: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginBottom: 10 }}>
          <span style={{ fontSize: 16, fontWeight: 800 }}>{sim.homeTeam}</span>
          <span style={{ fontSize: 12, fontWeight: 800, color: "var(--dim)" }}>vs</span>
          <span style={{ fontSize: 16, fontWeight: 800 }}>{sim.awayTeam}</span>
          <span style={{ fontSize: 12, fontWeight: 800, color: "#fff", background: "var(--accent)", borderRadius: 5, padding: "3px 9px" }}>MAÇ GÜNÜ</span>
        </div>
        <OutcomeBar sim={sim} />
        <div style={{ display: "flex", justifyContent: "center", gap: 16, marginTop: 8, fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--muted)" }}>
          <span>en olası <b style={{ color: "var(--accent)" }}>{sim.mostLikelyScore[0]}-{sim.mostLikelyScore[1]}</b></span>
          <span>üst 2.5 %{Math.round(sim.over25 * 100)}</span>
          <span>KG %{Math.round(sim.bttsYes * 100)}</span>
        </div>
        <div style={{ marginTop: 10 }}><TrustBadge note="bu tahmin tipi" /></div>
      </div>

      {/* Oyun planı — İLK İŞ */}
      {plan && (
        <div style={{ borderRadius: 12, border: "2px solid var(--accent)", background: "color-mix(in srgb, var(--accent) 8%, var(--panel))", padding: "16px 18px" }}>
          <div style={{ fontSize: 12, fontWeight: 900, letterSpacing: 1, color: "var(--accent)", marginBottom: 8 }}>OYUN PLANI</div>
          <div style={{ fontSize: 19, fontWeight: 900, lineHeight: 1.2, marginBottom: 6 }}>{plan.shape.formation}</div>
          <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.5 }}>{plan.shape.rationale}</div>
        </div>
      )}

      {/* Rakip zaafları — sömür */}
      <div>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>Rakip zaafları — sömür</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {demoWeaknesses.map((w) => {
            const c = SEV_COLOR[w.severity] ?? "var(--mid)";
            return (
              <div key={w.title} style={{ borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: `4px solid ${c}`, padding: "11px 13px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 13.5, fontWeight: 800, flex: 1 }}>{w.title}</span>
                  <span style={{ fontSize: 9.5, fontWeight: 800, color: "#fff", background: c, borderRadius: 4, padding: "2px 7px" }}>{w.severity}</span>
                </div>
                <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.45, marginTop: 3 }}>{w.detail}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── RAKİBİ OKU ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
        <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
        <span style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: 0.8, color: "var(--high)" }}>RAKİBİ OKU</span>
        <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
      </div>

      {/* Rakibin muhtemel 11'i */}
      <div className="rc" style={{ margin: 0 }}>
        <h3 style={{ margin: "0 0 6px" }}>Rakibin Muhtemel 11&apos;i <span className="tiny">{oppXI.formation} · projeksiyon</span></h3>
        <OpponentPitch players={oppXI.players} />
        <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 6, lineHeight: 1.5 }}>
          <span style={{ color: "var(--crit)", fontWeight: 700 }}>● kırmızı = dangerman</span> (markaja al). {oppXI.note}
        </div>
      </div>

      {/* Tehlike haritası — dangerman'ler */}
      <div>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>Tehlike haritası — kimi durduralım</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {dangers.map((d) => {
            const c = d.tier === "high" ? "var(--crit)" : "var(--mid)";
            return (
              <div key={d.num} style={{ borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: `4px solid ${c}`, padding: "11px 13px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 12, color: c, background: "color-mix(in srgb," + " var(--panel3) 100%, transparent)", borderRadius: 4, padding: "1px 6px" }}>#{d.num} {d.pos}</span>
                  <span style={{ fontSize: 13.5, fontWeight: 800, flex: 1 }}>{d.label}</span>
                </div>
                <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.45 }}>{d.threat}</div>
                <div style={{ fontSize: 12, color: "var(--low)", fontWeight: 700, marginTop: 4 }}>↳ Markaj: {d.marking}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Rakibin planı + önlemimiz */}
      <div>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>Rakip bize ne yapacak — ve önlemimiz</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          {theirPlan.map((t, i) => (
            <div key={i} style={{ borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", padding: "11px 13px" }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: "var(--high)" }}>↘ {t.theyWill}</div>
              <div style={{ fontSize: 11, color: "var(--dim)", lineHeight: 1.45, marginTop: 2 }}>{t.because}</div>
              <div style={{ fontSize: 12.5, color: "var(--low)", fontWeight: 700, lineHeight: 1.45, marginTop: 5 }}>↳ Önlem: {t.counter}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Taktik savaş — DNA vs DNA */}
      {dna && (
        <div className="rc" style={{ margin: 0 }}>
          <h3 style={{ margin: "0 0 2px" }}>Taktik Savaş <span className="tiny">DNA karşılaştırma · maç nerede kazanılır</span></h3>
          <div style={{ display: "flex", justifyContent: "center", margin: "6px 0" }}>
            <TacticalRadar us={dna.us} them={dna.them} size={260} />
          </div>
          <div style={{ display: "flex", justifyContent: "center", gap: 16, fontSize: 11, marginBottom: 8 }}>
            <span style={{ color: "var(--accent)", fontWeight: 700 }}>● {dna.us.name}</span>
            <span style={{ color: "var(--high)", fontWeight: 700 }}>● {dna.them.name}</span>
          </div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Savaş alanları (en büyük kontrastlar)</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {dna.contrasts.slice(0, 4).map((c, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 12 }}>
                <span style={{ fontFamily: "JetBrains Mono", fontSize: 10, fontWeight: 700, color: "var(--accent)", background: "color-mix(in srgb, var(--accent) 12%, transparent)", borderRadius: 5, padding: "2px 6px", flexShrink: 0, whiteSpace: "nowrap" }}>{c.axis}</span>
                <span style={{ color: "var(--ink)", lineHeight: 1.45 }}>{c.note}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Anahtar eşleşmeler */}
      <div>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>Anahtar eşleşmeler</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          {matchups.map((m) => {
            const strong = m.advantage >= 55;
            const c = strong ? "var(--low)" : "var(--mid)";
            return (
              <div key={m.ours} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <b>{m.ours}</b> <span style={{ color: "var(--dim)" }}>vs {m.theirs}</span>
                  <span style={{ display: "block", fontSize: 11, color: "var(--muted)" }}>{m.note}{strong ? " — sömür" : " — destek gerek"}</span>
                </span>
                <span className="mbar" style={{ width: 90, margin: 0, flexShrink: 0 }}><i style={{ width: `${m.advantage}%`, background: c }} /></span>
                <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: c, width: 36, textAlign: "right" }}>%{m.advantage}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Önerilen 11 (kompakt) */}
      <div className="rc" style={{ margin: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <h3 style={{ margin: 0 }}>Önerilen 11 <span className="tiny">{xi.formation} · güven %{xi.confidence}</span></h3>
          <Link href="/squad" style={{ fontSize: 11.5, fontWeight: 700, color: "var(--accent)" }}>tam kadro →</Link>
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>
          {xi.restedKey.length
            ? <>Dinlendiriliyor: <b style={{ color: "var(--crit)" }}>{xi.restedKey.map((a) => `${a.player.player_name.split(" ").slice(-1)[0]} (${a.player.shirt})`).join(", ")}</b> — yerlerine en yüksek uygunluklu oyuncular.</>
            : "Riskli oyuncu yok — en güçlü 11 hazır."}
        </div>
      </div>

      {/* İlkeler + pres tetikleri */}
      {plan && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
          <div className="rc" style={{ margin: 0 }}>
            <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Anahtar ilkeler</div>
            <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: "var(--ink)", lineHeight: 1.6 }}>
              {plan.principles.slice(0, 4).map((p, i) => <li key={i}>{p}</li>)}
            </ul>
          </div>
          <div className="rc" style={{ margin: 0 }}>
            <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Pres tetikleri</div>
            <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: "var(--ink)", lineHeight: 1.6 }}>
              {plan.pressTriggers.slice(0, 4).map((p, i) => <li key={i}>{p}</li>)}
            </ul>
          </div>
        </div>
      )}

      {/* Faz-faz plan */}
      <div>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>Faz-faz plan</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 10 }}>
          {phases.map((p) => (
            <div key={p.phase} style={{ borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", padding: "11px 13px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
                <span style={{ fontSize: 16 }}>{p.icon}</span>
                <b style={{ fontSize: 13 }}>{p.phase}</b>
              </div>
              <div style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.5 }}>{p.approach}</div>
              <div style={{ fontSize: 11, color: "var(--accent)", fontWeight: 700, marginTop: 5 }}>↳ {p.key}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Duran top planı */}
      <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--accent)" }}>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 4 }}>Duran top planı</div>
        <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.55 }}>
          <b>Hücum:</b> {demoPlan.set_piece_hint} — köşelerde far-post varyasyonu hazırla.
          <br /><b>Savunma:</b> Kendi köşelerimizde ikinci direği adam-adama kapat (zonal'da boşluk veriyoruz).
        </div>
      </div>

      {/* Senaryolar */}
      <div>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>Senaryo planı</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(165px, 1fr))", gap: 10 }}>
          {demoScenarios.map((s) => {
            const c = SCEN_COLOR(s.state);
            return (
              <div key={s.state} style={{ borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", borderTop: `3px solid ${c}`, padding: "11px 13px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: c }} />
                  <b style={{ fontSize: 12.5 }}>{s.state}</b>
                </div>
                <div style={{ fontSize: 11.5, color: "var(--ink)", lineHeight: 1.45 }}>{s.plan}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Ya olursa — hazır dallar */}
      <div>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>Ya olursa — hazır dallar</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {branches.map((b, i) => (
            <div key={i} style={{ borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: "4px solid var(--mid)", padding: "11px 13px" }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: "var(--mid)" }}>⎇ {b.trigger}</div>
              <div style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.5, marginTop: 4 }}>{b.response}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Maç başlıyor → Maç Modu */}
      <Link href="/match-mode" style={{ textDecoration: "none", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 10, border: "1.5px solid var(--accent)", background: "color-mix(in srgb, var(--accent) 8%, var(--panel))", padding: "11px 14px" }}>
        <span style={{ fontSize: 16 }}>▶</span>
        <span style={{ fontSize: 13, fontWeight: 800, color: "var(--ink)" }}>Maç başlıyor — Maç Modu&apos;na geç</span>
      </Link>
      <div style={{ fontSize: 11, color: "var(--dim)", textAlign: "center", lineHeight: 1.5 }}>
        Maç günü brifingi · karar-öncelikli. Tam analitik döküm{" "}
        <Link href="/opponent" style={{ color: "var(--accent)" }}>Rakip Analizi</Link> ve{" "}
        <Link href="/match-plan" style={{ color: "var(--accent)" }}>Maç Öncesi Plan</Link>&apos;da.
      </div>
    </div>
  );
}
