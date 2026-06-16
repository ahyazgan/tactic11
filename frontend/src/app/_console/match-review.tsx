"use client";

/**
 * Maç Değerlendirmesi — niceliksel + dürüst retrospektif. Win-prob hikâyesi
 * (eğri + goller + uyarılar), her doğru uyarının win-prob bedeli, motor-bazlı
 * isabet, ve sistemin KAÇIRDIKLARI (false negative). Analist kararı action-log'dan.
 */

import * as React from "react";
import Link from "next/link";
import { matchReview, VERDICT_LABEL, type ReviewVerdict } from "@/lib/match-review";
import { loadActions, type ActionVerb } from "@/lib/action-log";
import { commitMatchReview, isCommitted, removeGrade } from "@/lib/engine-record";

const V_COLOR: Record<ReviewVerdict, string> = { validated: "var(--low)", monitoring: "var(--mid)", pending: "var(--dim)" };

/** Win-prob hikâyesi — ev galibiyet olasılığı eğrisi + goller + uyarı işaretleri. */
function MatchStoryChart({ curve, goals, recs }: { curve: { minute: number; pHome: number }[]; goals: { minute: number; team: "home" | "away" }[]; recs: { minute: number; verdict: ReviewVerdict }[] }) {
  const w = 600, h = 170, padL = 30, padR = 12, padT = 12, padB = 26;
  const maxM = Math.max(...curve.map((c) => c.minute), 67);
  const x = (m: number) => padL + (m / maxM) * (w - padL - padR);
  const y = (p: number) => padT + (1 - p) * (h - padT - padB);
  const path = curve.map((c, i) => `${i ? "L" : "M"} ${x(c.minute).toFixed(1)} ${y(c.pHome).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} style={{ display: "block" }}>
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}>
          <line x1={padL} y1={y(g)} x2={w - padR} y2={y(g)} stroke="var(--line)" strokeWidth={0.7} />
          <text x={4} y={y(g) + 3} fontSize={8.5} fill="var(--dim)" fontFamily="JetBrains Mono">%{g * 100}</text>
        </g>
      ))}
      {[0, 15, 30, 45, 60].map((m) => <text key={m} x={x(m)} y={h - 8} fontSize={8.5} fill="var(--dim)" textAnchor="middle" fontFamily="JetBrains Mono">{m}&apos;</text>)}
      {/* goller — dikey çizgi */}
      {goals.map((g, i) => (
        <g key={i}>
          <line x1={x(g.minute)} y1={padT} x2={x(g.minute)} y2={h - padB} stroke={g.team === "home" ? "var(--accent)" : "var(--high)"} strokeWidth={1.2} strokeDasharray="3 3" opacity={0.6} />
          <text x={x(g.minute)} y={padT + 8} fontSize={9} fill={g.team === "home" ? "var(--accent)" : "var(--high)"} textAnchor="middle">⚽{g.minute}&apos;</text>
        </g>
      ))}
      {/* ev galibiyet olasılığı eğrisi */}
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2.2} strokeLinejoin="round" />
      {/* uyarı işaretleri (x ekseninde bayrak) */}
      {recs.map((r, i) => (
        <g key={i}>
          <line x1={x(r.minute)} y1={h - padB} x2={x(r.minute)} y2={h - padB + 6} stroke={V_COLOR[r.verdict]} strokeWidth={2} />
          <circle cx={x(r.minute)} cy={h - padB + 9} r={3} fill={V_COLOR[r.verdict]} />
        </g>
      ))}
    </svg>
  );
}

export function MatchReviewBody() {
  const r = matchReview();
  const [decisions, setDecisions] = React.useState<Record<string, ActionVerb>>({});
  React.useEffect(() => {
    const map: Record<string, ActionVerb> = {};
    for (const a of loadActions()) map[a.id] = a.verb;
    setDecisions(map);
  }, []);
  const recs = r.items.map((i) => ({ minute: i.minute, verdict: i.verdict }));

  const [committed, setCommitted] = React.useState(false);
  React.useEffect(() => { setCommitted(isCommitted(r.matchId)); }, [r.matchId]);
  const commit = () => { commitMatchReview(r.matchId, r.label, r.byEngine); setCommitted(true); };
  const uncommit = () => { removeGrade(r.matchId); setCommitted(false); };

  return (
    <div style={{ maxWidth: 660, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Manşet */}
      <div className="rc" style={{ margin: 0, textAlign: "center" }}>
        <div style={{ fontSize: 20, fontWeight: 900, fontFamily: "JetBrains Mono" }}>{r.finalNote}</div>
        <div style={{ display: "flex", justifyContent: "center", gap: 20, marginTop: 12 }}>
          <div><div style={{ fontSize: 26, fontWeight: 900, fontFamily: "JetBrains Mono", color: "var(--low)" }}>{r.validated}</div><div style={{ fontSize: 10.5, color: "var(--dim)" }}>doğrulandı</div></div>
          <div><div style={{ fontSize: 26, fontWeight: 900, fontFamily: "JetBrains Mono", color: "var(--mid)" }}>{r.monitoring}</div><div style={{ fontSize: 10.5, color: "var(--dim)" }}>izlemede</div></div>
          <div><div style={{ fontSize: 26, fontWeight: 900, fontFamily: "JetBrains Mono", color: "var(--crit)" }}>{r.misses.length}</div><div style={{ fontSize: 10.5, color: "var(--dim)" }}>kaçırılan</div></div>
        </div>
      </div>

      {/* Win-prob hikâyesi */}
      <div className="rc" style={{ margin: 0 }}>
        <h3 style={{ margin: "0 0 2px" }}>Maçın Hikâyesi <span className="tiny">ev galibiyet olasılığı · ⚽ gol · ▎uyarı</span></h3>
        <MatchStoryChart curve={r.curve} goals={r.goals} recs={recs} />
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4, lineHeight: 1.5 }}>
          Alt çizgideki işaretler sistemin uyarı anları (yeşil=doğrulandı, sarı=izlemede). 23&apos; golle olasılık yükseldi, 45&apos; far-post golüyle düştü.
        </div>
      </div>

      {/* Uyarı-sonuç reconcile listesi (win-prob bedeliyle) */}
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        {r.items.map((it, i) => {
          const c = V_COLOR[it.verdict];
          const dec = it.actionId ? decisions[it.actionId] : undefined;
          return (
            <div key={i} style={{ borderRadius: 10, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: `4px solid ${c}`, padding: "12px 14px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 11.5, color: "var(--dim)" }}>{it.minute}&apos;</span>
                <span style={{ fontSize: 9, fontWeight: 700, color: "var(--muted)", background: "var(--panel3)", borderRadius: 3, padding: "1px 6px" }}>{it.engine}</span>
                <span style={{ fontSize: 13.5, fontWeight: 800, flex: 1 }}>{it.recommendation}</span>
                <span style={{ fontSize: 9.5, fontWeight: 800, color: "#fff", background: c, borderRadius: 4, padding: "2px 7px", whiteSpace: "nowrap" }}>{VERDICT_LABEL[it.verdict]}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{it.evidence}</div>
              {it.winProbCost != null && (
                <div style={{ fontSize: 11.5, fontWeight: 700, color: "var(--crit)", marginTop: 5, fontFamily: "JetBrains Mono" }}>
                  Bedeli: kazanma olasılığı {it.winProbCost} puan ({it.winProbCost < 0 ? "düştü" : "arttı"}) — sistem bunu uyarmıştı.
                </div>
              )}
              {it.actionId && (
                <div style={{ fontSize: 11, marginTop: 6, fontWeight: 700 }}>
                  Analist kararı:{" "}
                  {dec === "applied" ? <span style={{ color: "var(--low)" }}>✓ uygulandı</span>
                    : dec === "dismissed" ? <span style={{ color: "var(--dim)" }}>✕ atlandı</span>
                    : <span style={{ color: "var(--dim)", fontWeight: 400, fontStyle: "italic" }}>karar verilmedi</span>}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Motor-bazlı isabet */}
      <div className="rc" style={{ margin: 0 }}>
        <h3 style={{ margin: "0 0 8px" }}>Motor-Bazlı İsabet <span className="tiny">bu maç · pending hariç</span></h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          {r.byEngine.map((e) => (
            <div key={e.engine} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}>
              <span style={{ width: 120, flexShrink: 0, fontWeight: 600 }}>{e.engine}</span>
              <span className="mbar" style={{ flex: 1, margin: 0 }}><i style={{ width: `${(e.hit / e.graded) * 100}%`, background: e.hit === e.graded ? "var(--low)" : "var(--mid)" }} /></span>
              <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, width: 36, textAlign: "right" }}>{e.hit}/{e.graded}</span>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 8, lineHeight: 1.5 }}>Gerçek sezonda her motorun bu satırları maçlar boyu birikir → motorun kendi isabet oranı (bkz. Kalibrasyon).</div>
      </div>

      {/* Sistemin kaçırdıkları — dürüstlük */}
      <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--crit)" }}>
        <h3 style={{ margin: "0 0 6px", color: "var(--crit)" }}>Sistemin Kaçırdıkları <span className="tiny">false negative · dürüstlük</span></h3>
        {r.misses.length === 0 ? (
          <div style={{ fontSize: 12, color: "var(--muted)" }}>Bu maçta flag&apos;lenmemiş kritik an tespit edilmedi.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {r.misses.map((m, i) => (
              <div key={i} style={{ fontSize: 12, lineHeight: 1.5 }}>
                <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, color: "var(--crit)" }}>{m.minute}&apos;</span>{" "}
                <span style={{ color: "var(--ink)" }}>{m.text}</span>
                <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 2 }}>{m.note}</div>
              </div>
            ))}
          </div>
        )}
        <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 8, lineHeight: 1.5 }}>
          Bir sistemin gerçekliği, sadece isabetlerini değil <b>kaçırdıklarını</b> da göstermesinde. Anlık tehlike tespiti (önceden uyarı) canlı tracking feed&apos;iyle eklenir.
        </div>
      </div>

      {/* Sicile ekle — maçlar boyu motor isabet oranı */}
      <div className="rc" style={{ margin: 0, borderLeft: `3px solid ${committed ? "var(--low)" : "var(--accent)"}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 2 }}>
              {committed ? "✓ Bu maç motor siciline eklendi" : "Bu değerlendirmeyi motor siciline ekle"}
            </div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>
              Her maçın motor isabeti birikir → her motorun gerçek sezon-isabet oranı (tek maç → track record).{" "}
              <Link href="/calibration" style={{ color: "var(--accent)" }}>Kalibrasyon&apos;da gör →</Link>
            </div>
          </div>
          {committed
            ? <button onClick={uncommit} style={{ background: "var(--panel)", color: "var(--muted)", border: "1px solid var(--line)", borderRadius: 8, padding: "9px 16px", fontSize: 12.5, fontWeight: 700, cursor: "pointer" }}>Geri al</button>
            : <button onClick={commit} style={{ background: "var(--accent)", color: "#fff", border: "none", borderRadius: 8, padding: "9px 18px", fontSize: 12.5, fontWeight: 800, cursor: "pointer" }}>Sicile ekle</button>}
        </div>
      </div>

      <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--accent)" }}>
        <div style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.6 }}>
          <b>Dürüst okuma:</b> &quot;Doğrulandı&quot; = uyarı isabetliydi (gerçek olayla görüldü), &quot;uygulasaydık kazanırdık&quot; değil.
          İleriye dönük öneriler maç-sonu gerçek sonuçla kapanır; gerçek sezonda bu rapor her maç otomatik dolar.
        </div>
      </div>
    </div>
  );
}
