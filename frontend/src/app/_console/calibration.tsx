"use client";

/**
 * Kalibrasyon & Güven görselleştirmesi — sistemin GERÇEK geçmiş maçlardaki
 * tahminlerini gerçek sonuçla kıyaslar. Güvenilirlik eğrisi (söylediği %X gerçekten
 * %X mi oluyor) + beceri (şansa karşı) + Güven Skoru. Veri lib/calibration.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import type { CalibrationReport, ReliabilityBin, Outcome, MarketResult, LeagueRatings } from "@/lib/calibration";
import type { EngineLedger } from "@/lib/decision-ledger";
import { predictFixture, predictEnsemble } from "@/lib/poisson-predict";
import { loadActions, clearActions, type LoggedAction } from "@/lib/action-log";
import { engineRecords, type EngineRecord } from "@/lib/engine-record";

const OUT_LABEL: Record<Outcome, string> = { H: "Ev sahibi", D: "Beraberlik", A: "Deplasman" };
const OUT_SHORT: Record<Outcome, string> = { H: "1", D: "X", A: "2" };

/** Güvenilirlik eğrisi: x = tahmin edilen olasılık, y = gerçekleşen sıklık.
 * Köşegen = mükemmel kalibrasyon. Nokta köşegenin altındaysa → fazla iddialı. */
export function ReliabilityDiagram({ bins }: { bins: ReliabilityBin[] }) {
  const W = 380, H = 300, padL = 40, padB = 34, padT = 12, padR = 14;
  const sx = (v: number) => padL + v * (W - padL - padR);
  const sy = (v: number) => H - padB - v * (H - padB - padT);
  const maxC = Math.max(...bins.map((b) => b.count), 1);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}>
      {/* ızgara */}
      {ticks.map((t) => (
        <g key={t}>
          <line x1={sx(t)} y1={sy(0)} x2={sx(t)} y2={sy(1)} stroke="var(--line)" strokeWidth={0.6} />
          <line x1={sx(0)} y1={sy(t)} x2={sx(1)} y2={sy(t)} stroke="var(--line)" strokeWidth={0.6} />
          <text x={sx(t)} y={H - padB + 14} fontSize={8.5} fill="var(--dim)" textAnchor="middle" fontFamily="JetBrains Mono">%{Math.round(t * 100)}</text>
          <text x={padL - 6} y={sy(t) + 3} fontSize={8.5} fill="var(--dim)" textAnchor="end" fontFamily="JetBrains Mono">%{Math.round(t * 100)}</text>
        </g>
      ))}
      {/* mükemmel kalibrasyon köşegeni */}
      <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="var(--mid)" strokeWidth={1.4} strokeDasharray="5 4" opacity={0.7} />
      <text x={sx(0.97)} y={sy(0.97) - 5} fontSize={8.5} fill="var(--mid)" textAnchor="end">mükemmel</text>
      {/* model eğrisi */}
      <polyline
        points={bins.map((b) => `${sx(b.predicted)},${sy(b.actual)}`).join(" ")}
        fill="none" stroke="var(--accent)" strokeWidth={2}
      />
      {bins.map((b, i) => (
        <g key={i}>
          <line x1={sx(b.predicted)} y1={sy(b.actual)} x2={sx(b.predicted)} y2={sy(b.predicted)} stroke="var(--crit)" strokeWidth={0.8} opacity={0.4} />
          <circle cx={sx(b.predicted)} cy={sy(b.actual)} r={3 + (b.count / maxC) * 7} fill="var(--accent)" fillOpacity={0.85} stroke="var(--panel)" strokeWidth={1.2} />
        </g>
      ))}
      {/* eksen başlıkları */}
      <text x={sx(0.5)} y={H - 2} fontSize={9} fill="var(--muted)" textAnchor="middle">model güveni (tahmin)</text>
      <text x={12} y={sy(0.5)} fontSize={9} fill="var(--muted)" textAnchor="middle" transform={`rotate(-90 12 ${sy(0.5)})`}>gerçekleşen sıklık</text>
    </svg>
  );
}

function Kpi({ label, value, sub, color, big }: { label: string; value: React.ReactNode; sub?: string; color?: string; big?: boolean }) {
  return (
    <div className="kpi">
      <div className="kl">{label}</div>
      <div className="kn" style={{ color, fontSize: big ? undefined : 22 }}>{value}</div>
      {sub && <div className="kd">{sub}</div>}
    </div>
  );
}

/** Beceri çubuğu: model Brier vs naif baseline (düşük = iyi). */
function SkillBar({ model, base }: { model: number; base: number }) {
  const max = Math.max(model, base) * 1.08;
  const pct = (v: number) => `${(v / max) * 100}%`;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {[
        { name: "Bizim model", v: model, c: "var(--accent)" },
        { name: "Naif tahmin (taban oranı)", v: base, c: "var(--dim)" },
      ].map((r) => (
        <div key={r.name}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, marginBottom: 3 }}>
            <span style={{ color: "var(--muted)" }}>{r.name}</span>
            <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>{r.v.toFixed(3)}</span>
          </div>
          <div style={{ height: 10, background: "var(--line)", borderRadius: 5, overflow: "hidden" }}>
            <div style={{ width: pct(r.v), height: "100%", background: r.c }} />
          </div>
        </div>
      ))}
      <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 2 }}>Brier hatası — düşük olan daha iyi. Model baseline&apos;ın altında = gerçek tahmin becerisi (şanstan iyi).</div>
    </div>
  );
}

const pct = (v: number) => `%${(v * 100).toFixed(1)}`;

const selStyle: React.CSSProperties = { background: "var(--panel)", border: "1px solid var(--line)", color: "var(--ink)", fontSize: 13, fontWeight: 700, padding: "7px 10px", borderRadius: 8, fontFamily: "inherit", cursor: "pointer", maxWidth: "100%" };

/** Doğrulanmış modelin CANLI tahmini — gerçek takımlar, öğrenilmiş güçlerle. */
export function FixturePredictor({ leagues, trust }: { leagues: LeagueRatings[]; trust: number }) {
  const [li, setLi] = React.useState(0);
  const lg = leagues[li];
  const [home, setHome] = React.useState(lg.teams[0]?.name ?? "");
  const [away, setAway] = React.useState(lg.teams[1]?.name ?? "");
  const onLeague = (i: number) => { setLi(i); setHome(leagues[i].teams[0]?.name ?? ""); setAway(leagues[i].teams[1]?.name ?? ""); };

  const h = lg.teams.find((t) => t.name === home) ?? lg.teams[0];
  const a = lg.teams.find((t) => t.name === away) ?? lg.teams[1];
  // Ensemble verisi varsa (top-5) doğrulanmış AD+Elo harmanı; yoksa (Danimarka) saf AD.
  const pred = lg.ensW !== undefined && h.elo !== undefined && a.elo !== undefined
    ? predictEnsemble(h.atk, h.def, a.atk, a.def, lg.muH, lg.muA, lg.rho, h.elo, a.elo, lg.ensW, lg.eloHA ?? 65, lg.eloEPG ?? 150, lg.eloAvg ?? 2.7)
    : predictFixture(h.atk, h.def, a.atk, a.def, lg.muH, lg.muA, lg.rho);
  const outcomes: { key: Outcome; label: string; p: number; color: string }[] = [
    { key: "H", label: home, p: pred.pH, color: "var(--accent)" },
    { key: "D", label: "Beraberlik", p: pred.pD, color: "var(--mid)" },
    { key: "A", label: away, p: pred.pA, color: "var(--high)" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <select value={li} onChange={(e) => onLeague(Number(e.target.value))} style={selStyle}>
          {leagues.map((l, i) => <option key={l.comp} value={i}>{l.label}</option>)}
        </select>
        <select value={home} onChange={(e) => setHome(e.target.value)} style={selStyle}>
          {lg.teams.map((t) => <option key={t.name} value={t.name} disabled={t.name === away}>{t.name}</option>)}
        </select>
        <span style={{ color: "var(--dim)", fontSize: 12, fontWeight: 700 }}>(ev) vs</span>
        <select value={away} onChange={(e) => setAway(e.target.value)} style={selStyle}>
          {lg.teams.map((t) => <option key={t.name} value={t.name} disabled={t.name === home}>{t.name}</option>)}
        </select>
        <span style={{ color: "var(--dim)", fontSize: 12, fontWeight: 700 }}>(dep)</span>
      </div>

      {/* 1/X/2 bar */}
      <div>
        <div style={{ display: "flex", height: 30, borderRadius: 8, overflow: "hidden", border: "1px solid var(--line)" }}>
          {outcomes.map((o) => (
            <div key={o.key} title={`${o.label} ${pct(o.p)}`} style={{ width: `${o.p * 100}%`, background: o.color, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 11, fontWeight: 800, fontFamily: "JetBrains Mono", minWidth: 0, overflow: "hidden" }}>
              {o.p > 0.12 ? pct(o.p) : ""}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginTop: 5 }}>
          {outcomes.map((o) => (
            <span key={o.key} style={{ color: o.color, fontWeight: 700, maxWidth: "33%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>● {o.label} {pct(o.p)}</span>
          ))}
        </div>
      </div>

      {/* marketler + en olası skorlar */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
        <div className="kpi"><div className="kl">Beklenen skor</div><div className="kn" style={{ fontSize: 20 }}>{pred.lH.toFixed(1)}–{pred.lA.toFixed(1)}</div><div className="kd">en olası {pred.top[0].score}</div></div>
        <div className="kpi"><div className="kl">Üst 2.5 gol</div><div className="kn" style={{ fontSize: 20 }}>{pct(pred.over)}</div><div className="kd">çok gollü olasılığı</div></div>
        <div className="kpi"><div className="kl">Karşılıklı gol</div><div className="kn" style={{ fontSize: 20 }}>{pct(pred.btts)}</div><div className="kd">iki takım da atar</div></div>
        <div className="kpi">
          <div className="kl">En olası skorlar</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 4 }}>
            {pred.top.slice(0, 3).map((s) => (
              <div key={s.score} style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, fontFamily: "JetBrains Mono" }}>
                <span style={{ fontWeight: 700 }}>{s.score}</span><span style={{ color: "var(--dim)" }}>{pct(s.p)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5, borderLeft: "3px solid var(--low)", paddingLeft: 10 }}>
        Bu tahmin, sayfadaki <b>doğrulanmış modelin</b> öğrendiği gerçek takım güçleriyle üretildi — maç sonucu katmanı out-of-sample <b style={{ color: "var(--low)" }}>güven {trust}</b>.
        Aynı motor Süper Lig verisine bağlanınca senin maçların için bunu, kendi doğrulanmış güveniyle üretir.
      </div>
    </div>
  );
}

/** Karar türüne göre güven — her tahmin tipinin kendi doğrulanmış rakamı. */
export function MarketTrustTable({ markets }: { markets: MarketResult[] }) {
  const trustColor = (t: number) => (t >= 70 ? "var(--low)" : t >= 50 ? "var(--mid)" : "var(--high)");
  const trustWord = (t: number) => (t >= 70 ? "güvenilir" : t >= 50 ? "orta" : "zayıf");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {markets.map((m) => (
        <div key={m.key} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", borderRadius: 9, background: "var(--panel3)", border: "1px solid var(--line)", opacity: m.status === "pending" ? 0.72 : 1 }}>
          <div style={{ width: 52, textAlign: "center", flexShrink: 0 }}>
            {m.status === "validated" ? (
              <>
                <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "JetBrains Mono", lineHeight: 1, color: trustColor(m.trust) }}>{m.trust}</div>
                <div style={{ fontSize: 8.5, color: "var(--dim)" }}>/100</div>
              </>
            ) : (
              <div style={{ fontSize: 16, color: "var(--dim)" }}>—</div>
            )}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--ink)" }}>
              {m.name}
              {m.status === "validated"
                ? <span style={{ fontSize: 9, fontWeight: 700, color: "#fff", background: trustColor(m.trust), borderRadius: 4, padding: "1px 6px", marginLeft: 8 }}>{trustWord(m.trust)}</span>
                : <span style={{ fontSize: 9, fontWeight: 700, color: "var(--ink)", background: "var(--line)", borderRadius: 4, padding: "1px 6px", marginLeft: 8 }}>VERİ BEKLİYOR</span>}
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2, lineHeight: 1.45 }}>{m.note}</div>
          </div>
          {m.status === "validated" && (
            <div style={{ flexShrink: 0, textAlign: "right", fontFamily: "JetBrains Mono", fontSize: 10.5, color: "var(--dim)", lineHeight: 1.5 }}>
              <div>isabet <b style={{ color: "var(--ink)" }}>{pct(m.accuracy)}</b>{m.baseRate != null && <span> / taban {pct(m.baseRate)}</span>}</div>
              <div>ECE {m.ece.toFixed(3)} · beceri +{pct(m.brierSkill)}</div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/** Motor Sicili — maç değerlendirmelerinden biriken motor isabet oranı. */
export function EngineRecord() {
  const [data, setData] = React.useState<{ records: EngineRecord[]; matchCount: number }>({ records: [], matchCount: 0 });
  const [ready, setReady] = React.useState(false);
  React.useEffect(() => { setData(engineRecords()); setReady(true); }, []);
  const acc = (a: number) => `%${Math.round(a * 100)}`;

  return (
    <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--mid)" }}>
      <h3 style={{ margin: "0 0 6px" }}>Motor Sicili <span className="tiny">maçlar boyu isabet · değerlendirmelerden birikir</span></h3>
      {!ready ? null : data.matchCount === 0 ? (
        <div style={{ fontSize: 12, color: "var(--dim)", lineHeight: 1.5 }}>
          Henüz değerlendirilmiş maç yok. <b>Maç Değerlendirmesi</b>&apos;nde &quot;Sicile ekle&quot; ile bir maçı işle — her motorun sezon-isabet oranı burada birikir.
        </div>
      ) : (
        <>
          <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 10, fontFamily: "JetBrains Mono" }}>{data.matchCount} maç değerlendirildi</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {data.records.map((e) => (
              <div key={e.engine} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}>
                <span style={{ width: 120, flexShrink: 0, fontWeight: 600 }}>{e.engine}</span>
                <span className="mbar" style={{ flex: 1, margin: 0 }}><i style={{ width: `${e.accuracy * 100}%`, background: e.accuracy >= 0.7 ? "var(--low)" : e.accuracy >= 0.5 ? "var(--mid)" : "var(--high)" }} /></span>
                <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, width: 80, textAlign: "right" }}>{acc(e.accuracy)} <span style={{ color: "var(--dim)" }}>({e.hit}/{e.graded})</span></span>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 8, lineHeight: 1.5 }}>
            {data.matchCount === 1 ? "Tek maç — sezon boyu birikecek; bu rakamlar arttıkça anlamlanır." : "Maç sayısı arttıkça her motorun isabet oranı istatistiksel anlam kazanır."} Gerçek sezonda otomatik dolar.
          </div>
        </>
      )}
    </div>
  );
}

/** Uygulanan Öneriler — analistin maç-içi teyit ettiği aksiyonlar (action-log). */
export function AppliedActions() {
  const [actions, setActions] = React.useState<LoggedAction[]>([]);
  const [ready, setReady] = React.useState(false);
  React.useEffect(() => { setActions(loadActions()); setReady(true); }, []);
  const applied = actions.filter((a) => a.verb === "applied");
  const dismissed = actions.filter((a) => a.verb === "dismissed");

  return (
    <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--low)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <h3 style={{ margin: 0 }}>Uygulanan Öneriler <span className="tiny">analist teyidi · maç modundan</span></h3>
        {actions.length > 0 && <button onClick={() => { clearActions(); setActions([]); }} style={{ background: "none", border: "none", color: "var(--dim)", fontSize: 10.5, cursor: "pointer", textDecoration: "underline" }}>temizle</button>}
      </div>
      {!ready ? null : actions.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--dim)", lineHeight: 1.5 }}>
          Henüz teyit edilmiş aksiyon yok. <b>Maç Modu</b>&apos;nda bir öneriyi <b>Uygula/Atla</b> ile işaretle — burada birikir.
        </div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 16, marginBottom: 10, fontFamily: "JetBrains Mono", fontSize: 12 }}>
            <span><b style={{ color: "var(--low)" }}>{applied.length}</b> uygulandı</span>
            <span><b style={{ color: "var(--dim)" }}>{dismissed.length}</b> atlandı</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {actions.map((a) => (
              <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11.5, padding: "4px 0", borderTop: "1px solid var(--line)" }}>
                <span style={{ width: 16, textAlign: "center", color: a.verb === "applied" ? "var(--low)" : "var(--dim)", fontWeight: 800 }}>{a.verb === "applied" ? "✓" : "✕"}</span>
                <span style={{ fontFamily: "JetBrains Mono", color: "var(--dim)", flexShrink: 0 }}>{a.minute}&apos;</span>
                <span style={{ flex: 1, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.label}</span>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", lineHeight: 1.5, marginTop: 8, borderTop: "1px solid var(--line)", paddingTop: 7 }}>
            &quot;Uygulandı&quot; = reconcile&apos;ın insan yarısı (aksiyon teyit edildi). İkinci yarı — işe yaradı mı — gerçek sonuç verisiyle kapanır.
          </div>
        </>
      )}
    </div>
  );
}

/** Karar Kanıt Defteri — her motorun şu anki gerçek iddiaları + doğrulama durumu. */
export function DecisionLedger({ ledgers }: { ledgers: EngineLedger[] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 14 }}>
      {ledgers.map((l) => (
        <div key={l.engine} className="rc" style={{ margin: 0, borderLeft: `3px solid ${l.validated ? "var(--low)" : "var(--mid)"}` }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <h3 style={{ margin: 0 }}>{l.title}</h3>
            {l.validated
              ? <span style={{ fontSize: 9.5, fontWeight: 700, color: "#fff", background: "var(--low)", borderRadius: 4, padding: "2px 7px" }}>DOĞRULANDI · {l.trust}</span>
              : <span style={{ fontSize: 9.5, fontWeight: 700, color: "var(--ink)", background: "var(--line)", borderRadius: 4, padding: "2px 7px" }}>BİRİKİYOR · {l.resolved} sonuçlandı</span>}
          </div>

          {/* Şu anki açık iddialar (gerçek, canlı motordan) */}
          <div style={{ fontSize: 10, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 5 }}>Şu anki açık iddialar ({l.open.length})</div>
          {l.open.length === 0
            ? <div style={{ fontSize: 11.5, color: "var(--dim)", fontStyle: "italic", marginBottom: 8 }}>Şu an açık iddia yok.</div>
            : (
              <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 10 }}>
                {l.open.map((c, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 8, fontSize: 11.5 }}>
                    <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: "var(--accent)", flexShrink: 0, fontSize: 10.5 }}>%{Math.round(c.confidence * 100)}</span>
                    <span style={{ color: "var(--ink)", lineHeight: 1.4 }}>
                      <b>{c.subject}</b> — {c.claim} <span style={{ color: "var(--dim)" }}>({c.horizon})</span>
                    </span>
                  </div>
                ))}
              </div>
            )}

          {/* Nasıl doğrulanır */}
          <div style={{ fontSize: 10.5, color: "var(--muted)", lineHeight: 1.5, borderTop: "1px solid var(--line)", paddingTop: 7 }}>
            <div><b style={{ color: "var(--ink)" }}>Reconcile:</b> {l.resolveRule}</div>
            <div style={{ marginTop: 3, color: "var(--dim)" }}>{l.needNote}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function CalibrationBody({ report: r }: { report: CalibrationReport }) {
  const trustColor = r.trust >= 70 ? "var(--low)" : r.trust >= 50 ? "var(--mid)" : "var(--high)";
  const trustWord = r.trust >= 70 ? "güvenilir" : r.trust >= 50 ? "orta" : "zayıf";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Out-of-sample rozeti */}
      <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--low)", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.5, color: "#fff", background: "var(--low)", borderRadius: 4, padding: "2px 8px" }}>OUT-OF-SAMPLE</span>
        <span style={{ fontSize: 12, color: "var(--ink)" }}>
          Model <b>{r.trainMatches.toLocaleString("tr")}</b> maçta (2017-2022) eğitildi; tüm rakamlar modelin <b>hiç görmediği</b> {r.splitSeason} sezonunda
          (<b>{r.matches.toLocaleString("tr")}</b> maç) ölçüldü. Hiperparametreler yalnız train'de ayarlandı → test setine uydurma yok.
        </span>
      </div>

      {/* Manşet (test seti · %95 güven aralıklı) */}
      <div className="kpis" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
        <Kpi label="Güven Skoru" value={`${r.trust}`} sub={`/100 · ${trustWord}`} color={trustColor} big />
        <Kpi label="İsabet (out-of-sample)" value={pct(r.accuracy)} sub={`%95 GA ${pct(r.ci.accuracy[0])}–${pct(r.ci.accuracy[1])}`} />
        <Kpi label="Kalibrasyon hatası" value={r.ece.toFixed(3)} sub={`ECE · GA ${r.ci.ece[0].toFixed(3)}–${r.ci.ece[1].toFixed(3)}`} color={r.ece < 0.03 ? "var(--low)" : undefined} />
        <Kpi label="Beceri (şansa karşı)" value={`+${pct(r.brierSkill)}`} sub="Brier skill score" color="var(--low)" />
        <Kpi label="Brier" value={r.brier.toFixed(3)} sub={`GA ${r.ci.brier[0].toFixed(3)}–${r.ci.brier[1].toFixed(3)}`} />
        <Kpi label="Log-loss" value={r.logLoss.toFixed(3)} sub={`baseline ${r.baselineLogLoss.toFixed(3)}`} />
      </div>

      {/* Karar türüne göre güven — her tahmin tipi kendi rakamıyla */}
      <div>
        <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 2 }}>Karar Türüne Göre Güven <span className="tiny">her tahmin ayrı doğrulandı</span></div>
        <div style={{ fontSize: 11, color: "var(--dim)", marginBottom: 8 }}>Sistem her tahminine aynı güveni vermez — hangisine ne kadar güvenebileceğini dürüstçe söyler. Doğrulanamayanlar açıkça işaretli.</div>
        <MarketTrustTable markets={r.markets} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 18, alignItems: "start" }}>
        {/* Güvenilirlik eğrisi */}
        <div>
          <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 2 }}>Güvenilirlik Eğrisi</div>
          <div style={{ fontSize: 11, color: "var(--dim)", marginBottom: 6 }}>&quot;%X dediğinde gerçekten %X mi oluyor?&quot; — nokta köşegende = dürüst güven.</div>
          <ReliabilityDiagram bins={r.bins} />
          <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
            Köşegene yakınlık = güven rakamı gerçeği yansıtıyor. Köşegenin <b>altı</b> = fazla iddialı, <b>üstü</b> = fazla temkinli. Nokta büyüklüğü = o güven aralığındaki maç sayısı.
          </div>
        </div>

        {/* Beceri + güven aralığı tablosu */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 8 }}>Şanstan İyi mi? <span className="tiny">beceri kanıtı</span></div>
            <SkillBar model={r.brier} base={r.baselineBrier} />
          </div>
          <div>
            <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Güven aralığına göre gerçek isabet</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
              <thead><tr style={{ color: "var(--dim)", fontSize: 9.5, textAlign: "right" }}>
                <th style={{ textAlign: "left", padding: "0 0 5px" }}>Model dedi</th><th style={{ padding: "0 0 5px" }}>Gerçek</th><th style={{ padding: "0 0 5px" }}>Maç</th><th style={{ padding: "0 0 5px", minWidth: 70 }}>Uyum</th>
              </tr></thead>
              <tbody>
                {r.bins.map((b, i) => {
                  const diff = Math.abs(b.predicted - b.actual);
                  const ok = diff < 0.05;
                  return (
                    <tr key={i} style={{ borderTop: "1px solid var(--line)", textAlign: "right" }}>
                      <td style={{ textAlign: "left", padding: "5px 0", fontFamily: "JetBrains Mono" }}>%{Math.round(b.lo * 100)}–{Math.round(b.hi * 100)}</td>
                      <td style={{ padding: "5px 0", fontFamily: "JetBrains Mono", fontWeight: 700 }}>%{Math.round(b.actual * 100)}</td>
                      <td style={{ padding: "5px 0", color: "var(--dim)" }}>{b.count}</td>
                      <td style={{ padding: "5px 0" }}>
                        <span style={{ fontSize: 9.5, fontWeight: 700, color: "#fff", background: ok ? "var(--low)" : "var(--mid)", borderRadius: 4, padding: "1px 6px" }}>{ok ? "tam" : b.actual < b.predicted ? "iddialı" : "temkinli"}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Model karşılaştırma — derin model vs eski Elo (aynı test seti) */}
      <div>
        <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 2 }}>Model Karşılaştırma <span className="tiny">aynı görülmemiş test setinde</span></div>
        <div style={{ fontSize: 11, color: "var(--dim)", marginBottom: 8 }}>Derin model (hücum/savunma + Dixon-Coles) vs eski tek-Elo. Düşük Brier/log-loss/ECE = iyi.</div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
            <thead><tr style={{ color: "var(--dim)", fontSize: 9.5, textAlign: "right" }}>
              <th style={{ textAlign: "left", padding: "0 0 6px" }}>Model</th>
              <th style={{ padding: "0 8px 6px" }}>İsabet</th><th style={{ padding: "0 8px 6px" }}>Brier ↓</th>
              <th style={{ padding: "0 8px 6px" }}>Log-loss ↓</th><th style={{ padding: "0 8px 6px" }}>ECE ↓</th><th style={{ padding: "0 0 6px 8px" }}>Beceri ↑</th>
            </tr></thead>
            <tbody>
              {r.models.map((m, i) => {
                const lead = i === 0;
                return (
                  <tr key={m.name} style={{ borderTop: "1px solid var(--line)", textAlign: "right", color: lead ? "var(--ink)" : "var(--muted)" }}>
                    <td style={{ textAlign: "left", padding: "7px 0", fontWeight: lead ? 800 : 500 }}>
                      {lead && <span style={{ fontSize: 9, fontWeight: 700, color: "#fff", background: "var(--accent)", borderRadius: 3, padding: "1px 5px", marginRight: 6 }}>AKTİF</span>}
                      {m.name}
                    </td>
                    <td style={{ padding: "7px 8px", fontFamily: "JetBrains Mono" }}>{pct(m.accuracy)}</td>
                    <td style={{ padding: "7px 8px", fontFamily: "JetBrains Mono" }}>{m.brier.toFixed(4)}</td>
                    <td style={{ padding: "7px 8px", fontFamily: "JetBrains Mono" }}>{m.logLoss.toFixed(4)}</td>
                    <td style={{ padding: "7px 8px", fontFamily: "JetBrains Mono", fontWeight: lead ? 700 : 400, color: lead && m.ece < r.models[1].ece ? "var(--low)" : undefined }}>{m.ece.toFixed(4)}</td>
                    <td style={{ padding: "7px 0 7px 8px", fontFamily: "JetBrains Mono" }}>+{pct(m.brierSkill)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 6, lineHeight: 1.5 }}>
          Derin model olasılıkları belirgin daha kalibre (ECE düşük) ve log-loss&apos;u daha iyi — yani <b>güven rakamı daha dürüst</b>. Bu, &quot;%X dediğinde gerçekten %X oluyor&quot; demektir.
        </div>
      </div>

      {/* Lig kırılımı + örnek defter */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 18, alignItems: "start" }}>
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>Lig kırılımı</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
            <tbody>
              {r.byComp.map((c) => (
                <tr key={c.comp} style={{ borderTop: "1px solid var(--line)" }}>
                  <td style={{ padding: "6px 0", fontWeight: 600 }}>{c.comp}</td>
                  <td style={{ padding: "6px 0", textAlign: "right", color: "var(--dim)", fontFamily: "JetBrains Mono" }}>{c.matches} maç</td>
                  <td style={{ padding: "6px 0 6px 12px", textAlign: "right", fontFamily: "JetBrains Mono", fontWeight: 700 }}>%{(c.accuracy * 100).toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <div style={{ fontSize: 10.5, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>Örnek defter <span className="tiny">son maçlar · tahmin → gerçek</span></div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {r.sample.slice(0, 9).map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0", borderTop: i ? "1px solid var(--line)" : "none", fontSize: 11.5 }}>
                <span style={{ width: 16, textAlign: "center", color: s.hit ? "var(--low)" : "var(--high)", fontWeight: 800 }}>{s.hit ? "✓" : "✗"}</span>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.home} – {s.away}</span>
                <span style={{ color: "var(--dim)", fontFamily: "JetBrains Mono", fontSize: 10.5 }}>tahmin {OUT_SHORT[s.pick]} %{Math.round(s.conf * 100)}</span>
                <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, minWidth: 30, textAlign: "right" }}>{s.scoreline}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────
   Öğrenilmiş kalibrasyon sıcaklığı — backend /admin/calibration-model-status.
   Reconciled tahminlerden öğrenilen T'yi + log-loss kazancını gösterir.
───────────────────────────────────────────── */
interface CalModelStatus {
  status: "untrained" | "stale" | "fresh";
  best_temperature?: number;
  sample_count?: number;
  log_loss_before?: number;
  log_loss_after?: number;
  improved?: boolean;
  expires_at?: string;
}

export function LearnedTemperature() {
  const { data, error } = useSWR<CalModelStatus>(
    "/admin/calibration-model-status",
    apiFetch,
    { shouldRetryOnError: false },
  );

  if (error) {
    return (
      <div style={{ fontSize: 12, color: "var(--muted)" }}>
        Durum alınamadı (admin yetkisi gerekir).
      </div>
    );
  }
  if (!data) {
    return <div style={{ fontSize: 12, color: "var(--dim)" }}>Yükleniyor…</div>;
  }
  if (data.status !== "fresh" || data.best_temperature == null) {
    return (
      <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.6 }}>
        {data.status === "stale"
          ? "Öğrenilmiş sıcaklık süresi geçti — yeni sonuçlarla yeniden eğitilecek."
          : "Henüz öğrenilmedi. Yeterli sonuçlanmış tahmin biriktiğinde sistem, ham olasılıkları dürüstleştiren sıcaklığı (T) otomatik öğrenir."}
      </div>
    );
  }

  const t = data.best_temperature;
  const before = data.log_loss_before ?? 0;
  const after = data.log_loss_after ?? 0;
  const gainPct = before > 0 ? ((before - after) / before) * 100 : 0;
  const direction = t > 1 ? "yumuşatıyor (aşırı-güveni kırıyor)"
    : t < 1 ? "keskinleştiriyor" : "değiştirmiyor";

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 18, alignItems: "center" }}>
      <div>
        <div style={{ fontSize: 28, fontWeight: 800, color: "var(--accent)", lineHeight: 1 }}>
          T = {t}
        </div>
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4 }}>
          tahminleri {direction}
        </div>
      </div>
      <div style={{ borderLeft: "1px solid var(--line)", paddingLeft: 18 }}>
        <div style={{ fontSize: 12.5, color: "var(--ink)" }}>
          log-loss <b>{before.toFixed(3)}</b> → <b style={{ color: data.improved ? "var(--low)" : "var(--ink)" }}>{after.toFixed(3)}</b>
          {data.improved && (
            <span style={{ color: "var(--low)", fontWeight: 700 }}> (−%{gainPct.toFixed(1)})</span>
          )}
        </div>
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4 }}>
          {data.sample_count ?? 0} sonuçlanmış tahminden öğrenildi · canlı tahminlere otomatik uygulanır
        </div>
      </div>
    </div>
  );
}
