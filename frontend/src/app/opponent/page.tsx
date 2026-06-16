"use client";

/**
 * Rakip Raporu — eşleşme grid: bizim güç × rakip zaaf (kanal bazlı).
 * ConsoleShell çatısında.
 *
 * DEMO_MODE açıkken canlı API'ye hiç dokunmaz; "Antalyaspor" için dolu, gerçekçi
 * scout raporu gösterir (dizilim, kanal eşleşmesi, zaaflar, tehdit, eşleşme avantajı).
 * DEMO kapalıyken eski canlı-API davranışı (iki takım ID gir → matchup-grid) korunur.
 *
 * Backend: GET /admin/teams/{team_id}/matchup-grid?opponent_id={id}&last_n=5.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { Crest } from "@/lib/teams";
import { compareDna, weaknessMap, matchPlan } from "@/lib/tactical-dna";
import { ConsoleShell } from "../_console/shell";
import { LoadingState, ErrorState } from "@/components/ui";
import { DnaComparisonBody, MatchPlanBody } from "../_console/tactical-radar";
import { TacticalDeepDive } from "../_console/tactical-deepdive";

interface ChannelM {
  channel: string;
  our_attacks: number;
  opp_def_actions: number;
  our_strength: number;
  opp_weakness: number;
  matchup_score: number;
  verdict: string;
}
interface GridResp {
  value?: {
    matches_analyzed: number;
    by_channel: ChannelM[];
    best_channel: string;
    worst_channel: string;
    recommendation: string;
  };
  note?: string;
}

const CHANNEL_LABEL: Record<string, string> = {
  left: "Sol kanat",
  center: "Merkez",
  right: "Sağ kanat",
  left_halfspace: "Sol yarı alan",
  right_halfspace: "Sağ yarı alan",
};
const VERDICT_VAR: Record<string, string> = {
  exploit: "var(--low)",
  neutral: "var(--muted)",
  avoid: "var(--crit)",
};
const VERDICT_LABEL: Record<string, string> = {
  exploit: "Sömür",
  neutral: "Nötr",
  avoid: "Kaçın",
};

function pct(v: number): string {
  return (v * 100).toFixed(0) + "%";
}

const inputStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 10px",
  borderRadius: "7px",
  width: "130px",
  fontFamily: "inherit",
};

// ─────────────────────────────────────────────────────────────────────────────
// DEMO EVRENİ — "Antalyaspor" scout raporu (bu dosyaya özel, paylaşılan veriyi
// değiştirmeden). İsimler/evren demo-data.ts ile tutarlı (Beşiktaş vs Antalyaspor).
// ─────────────────────────────────────────────────────────────────────────────

const DEMO_OPP = "Antalyaspor";
const DEMO_COMP = "Süper Lig — 34. Hafta";

// Kanal bazlı eşleşme (bizim güç × rakip zaaf) — canlı GridResp ile aynı şekil.
const demoChannels: ChannelM[] = [
  { channel: "right", our_attacks: 41, opp_def_actions: 12, our_strength: 0.78, opp_weakness: 0.71, matchup_score: 0.74, verdict: "exploit" },
  { channel: "right_halfspace", our_attacks: 33, opp_def_actions: 16, our_strength: 0.64, opp_weakness: 0.58, matchup_score: 0.61, verdict: "exploit" },
  { channel: "center", our_attacks: 28, opp_def_actions: 31, our_strength: 0.52, opp_weakness: 0.34, matchup_score: 0.43, verdict: "neutral" },
  { channel: "left_halfspace", our_attacks: 24, opp_def_actions: 22, our_strength: 0.49, opp_weakness: 0.41, matchup_score: 0.45, verdict: "neutral" },
  { channel: "left", our_attacks: 19, opp_def_actions: 34, our_strength: 0.44, opp_weakness: 0.22, matchup_score: 0.29, verdict: "avoid" },
];

const DEMO_BEST = "right";
const DEMO_WORST = "left";
const DEMO_RECO =
  "Hücum yükünü sağ koridora kaydır: Milot Rashica (7) ile rakip sol bekin arkasını sömür (eşleşme skoru 74). " +
  "Sol kanattan ısrar etme — rakip o tarafta agresif savunuyor (kaçın). Duran toplarda far-post (ikinci direk) açık.";

// Üst bilgi kartı
const demoMeta = {
  matches_analyzed: 5,
  formation: "4-2-3-1",
  build_up: "Kısa kuruluş + kaleci ayağı",
  press: "Orta blok, geç tetik",
  threat_level: "Orta",
  last5: "G B M G M", // son 5 form (bizim gözle rakip)
};

// Rakip dizilim — saha üstü 11 nokta (yüzde koordinat: x sahanın eni, y boyu).
// y düşük = rakip kalesi (üst), y yüksek = bizim kale (alt). Sağ/sol bizim bakışımıza göre.
interface FormationDot { x: number; y: number; n: number; role: string; weak?: boolean }
const demoFormation: FormationDot[] = [
  { x: 50, y: 8, n: 1, role: "Kaleci" },
  // Defans (4'lü)
  { x: 18, y: 26, n: 3, role: "Sol Bek" },
  { x: 38, y: 22, n: 4, role: "Stoper" },
  { x: 62, y: 22, n: 5, role: "Stoper" },
  { x: 82, y: 26, n: 2, role: "Sağ Bek", weak: true }, // hücumda yüksek → arkası boş
  // Çift pivot (2)
  { x: 38, y: 44, n: 6, role: "Ön Libero", weak: true }, // geç dakika yoruluyor
  { x: 62, y: 44, n: 8, role: "Box-to-box" },
  // Üçlü hat
  { x: 20, y: 62, n: 11, role: "Sol Kanat" },
  { x: 50, y: 60, n: 10, role: "10 Numara" },
  { x: 80, y: 62, n: 7, role: "Sağ Kanat" },
  // Santrfor
  { x: 50, y: 80, n: 9, role: "Santrfor" },
];

// Tehdit oyuncuları (rakibin bizi en çok zorlayabileceği profiller).
// Not: demo evreninde rakip oyuncular mevki + forma no ile anonim gösterilir
// (gerçek kadro entegrasyonu sağlayıcı bağlanınca isimleri doldurur).
interface Threat { shirt: number; role: string; metric: string; level: "yüksek" | "orta" | "düşük" }
const demoThreats: Threat[] = [
  { shirt: 9, role: "Santrfor", metric: "12 gol · 0.58 xG/maç · hava topu %61", level: "yüksek" },
  { shirt: 10, role: "10 Numara", metric: "9 asist · maç başına 2.4 kilit pas", level: "yüksek" },
  { shirt: 7, role: "Sağ Kanat", metric: "dakikada 1.8 dripling · %64 başarı", level: "orta" },
  { shirt: 6, role: "Ön Libero", metric: "top kazanma lideri ama 60. dk sonrası -%30", level: "orta" },
];

// Eşleşme avantajı (bizim oyuncu vs rakip oyuncu)
interface DuelM { ours: string; theirs: string; advantage: number; note: string }
const demoDuels: DuelM[] = [
  { ours: "Milot Rashica (7) — Sağ Kanat", theirs: "Sol Bek", advantage: 72, note: "1v1 hız ve dripling üstünlüğü" },
  { ours: "Salih Uçan (8) — Merkez", theirs: "6 Numara", advantage: 63, note: "Pres kırma ve ileri pas kalitesi" },
  { ours: "Oh Hyeon-Gyu (9) — Santrfor", theirs: "Stoper ikilisi", advantage: 58, note: "Hava topu ve derinlik tehdidi" },
  { ours: "Ersin Destanoğlu (1) — Kaleci", theirs: "Santrfor (#9)", advantage: 47, note: "Hava toplarında dikkat — far-post" },
  { ours: "Rıdvan Yılmaz (3) — Sol Bek", theirs: "Sağ Kanat (#7)", advantage: 38, note: "Savunmada zorlanabilir — destek gerekli" },
];

// Maç bazlı kümülatif xG/şut hikâyesi (son 5 maç rakip yediği/attığı) — inline SVG çizgi.
interface FormPoint { match: string; gf: number; ga: number; res: "G" | "B" | "M" }
const demoForm: FormPoint[] = [
  { match: "H-5", gf: 2, ga: 1, res: "G" },
  { match: "H-4", gf: 1, ga: 1, res: "B" },
  { match: "H-3", gf: 0, ga: 2, res: "M" },
  { match: "H-2", gf: 3, ga: 1, res: "G" },
  { match: "H-1", gf: 1, ga: 2, res: "M" },
];

const SEV_VAR: Record<string, string> = {
  "yüksek": "var(--crit)",
  "orta": "var(--mid)",
  "düşük": "var(--muted)",
};

/** Saha + dizilim mini-pitch (saf SVG). */
function PitchDiagram() {
  const W = 300;
  const H = 200;
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block", borderRadius: 10 }} role="img" aria-label="Rakip dizilim diyagramı">
      {/* saha zemini */}
      <rect x={0} y={0} width={W} height={H} fill="var(--surface2)" />
      <rect x={6} y={6} width={W - 12} height={H - 12} fill="none" stroke="var(--border2)" strokeWidth={1.2} rx={4} />
      {/* orta çizgi + daire */}
      <line x1={6} y1={H / 2} x2={W - 6} y2={H / 2} stroke="var(--border2)" strokeWidth={1} />
      <circle cx={W / 2} cy={H / 2} r={26} fill="none" stroke="var(--border2)" strokeWidth={1} />
      {/* ceza sahaları */}
      <rect x={W / 2 - 48} y={6} width={96} height={34} fill="none" stroke="var(--border2)" strokeWidth={1} />
      <rect x={W / 2 - 48} y={H - 40} width={96} height={34} fill="none" stroke="var(--border2)" strokeWidth={1} />
      {/* sömürülecek sağ koridor vurgusu (rakip sağ bek arkası → bizim sol-üst) */}
      <rect x={W - 6 - 64} y={6} width={64} height={H / 2 - 6} fill="var(--low)" opacity={0.1} />
      <text x={W - 38} y={24} textAnchor="middle" fill="var(--low)" style={{ fontSize: 8, fontWeight: 700 }}>SÖMÜR</text>
      {/* oyuncu noktaları */}
      {demoFormation.map((d) => {
        const cx = (d.x / 100) * W;
        const cy = (d.y / 100) * H;
        const fill = d.weak ? "var(--crit)" : "var(--accent)";
        return (
          <g key={d.n}>
            <circle cx={cx} cy={cy} r={9} fill={fill} stroke="#fff" strokeWidth={1.4} />
            <text x={cx} y={cy + 3} textAnchor="middle" fill="#fff" style={{ fontSize: 9, fontWeight: 700, fontFamily: "JetBrains Mono" }}>{d.n}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** Son 5 maç gol-attı/yedi mini çizgi (saf SVG). */
function FormChart() {
  const W = 300;
  const H = 96;
  const pad = 22;
  const maxV = 3;
  const xAt = (i: number) => pad + (i / (demoForm.length - 1)) * (W - pad * 2);
  const yAt = (v: number) => H - 14 - (v / maxV) * (H - 30);
  const line = (key: "gf" | "ga") =>
    demoForm.map((p, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(p[key]).toFixed(1)}`).join(" ");
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }} role="img" aria-label="Rakip son 5 maç gol grafiği">
      {[0, 1, 2, 3].map((g) => (
        <line key={g} x1={pad} y1={yAt(g)} x2={W - pad} y2={yAt(g)} stroke="var(--border)" strokeWidth={0.8} />
      ))}
      <path d={line("gf")} fill="none" stroke="var(--low)" strokeWidth={2} />
      <path d={line("ga")} fill="none" stroke="var(--crit)" strokeWidth={2} strokeDasharray="4 3" />
      {demoForm.map((p, i) => (
        <g key={p.match}>
          <circle cx={xAt(i)} cy={yAt(p.gf)} r={3} fill="var(--low)" />
          <circle cx={xAt(i)} cy={yAt(p.ga)} r={3} fill="var(--crit)" />
          <text x={xAt(i)} y={H - 2} textAnchor="middle" fill="var(--dim)" style={{ fontSize: 8 }}>{p.match}</text>
        </g>
      ))}
    </svg>
  );
}

export default function OpponentConsolePage() {
  const [team, setTeam] = React.useState("");
  const [opp, setOpp] = React.useState("");
  const [q, setQ] = React.useState<{ t: string; o: string } | null>(null);

  // Demo modunda canlı API'ye hiç dokunma (boş-state / spinner olmaz).
  const { data, isLoading, error } = useSWR<GridResp>(
    DEMO_MODE ? null : q ? `/admin/teams/${q.t}/matchup-grid?opponent_id=${q.o}&last_n=5` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  // Demo'da dolu mock grid; canlıda SWR sonucu.
  const v = DEMO_MODE
    ? {
        matches_analyzed: demoMeta.matches_analyzed,
        by_channel: demoChannels,
        best_channel: DEMO_BEST,
        worst_channel: DEMO_WORST,
        recommendation: DEMO_RECO,
      }
    : data?.value;

  const right = v ? (
    <>
      <div className="rc">
        <h3>Koridor Önerisi <span className="tiny">{v.matches_analyzed} maç</span></h3>
        <div className="stat"><span style={{ color: "var(--low)", fontWeight: 700 }}>En iyi</span><span className="sv" style={{ color: "var(--low)" }}>{CHANNEL_LABEL[v.best_channel] ?? v.best_channel}</span></div>
        <div className="stat"><span style={{ color: "var(--crit)", fontWeight: 700 }}>En zayıf</span><span className="sv" style={{ color: "var(--crit)" }}>{CHANNEL_LABEL[v.worst_channel] ?? v.worst_channel}</span></div>
        <div style={{ fontSize: "12.5px", color: "var(--ink)", marginTop: 12, lineHeight: 1.55 }}>{v.recommendation}</div>
      </div>

      {DEMO_MODE && (
        <>
          <div className="rc">
            <h3>Dizilim <span className="tiny">{demoMeta.formation}</span></h3>
            <PitchDiagram />
            <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 11, color: "var(--muted)" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--accent)" }} />Standart</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--crit)" }} />Zaaf noktası</span>
            </div>
          </div>

          <div className="rc">
            <h3>Tehdit Oyuncuları <span className="tiny">{demoThreats.length}</span></h3>
            {demoThreats.map((t) => {
              const tv = t.level === "yüksek" ? "var(--crit)" : t.level === "orta" ? "var(--mid)" : "var(--muted)";
              return (
                <div className="alrt" key={t.shirt}>
                  <span className="ai" style={{ background: tv }} />
                  <div className="am"><b>#{t.shirt} {t.role}</b>
                    <span className="tm">{t.metric}</span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="rc">
            <h3>Son 5 Maç <span className="tiny">{demoMeta.last5}</span></h3>
            <FormChart />
            <div style={{ display: "flex", gap: 14, marginTop: 6, fontSize: 11, color: "var(--muted)" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 12, height: 2, background: "var(--low)" }} />Attığı gol</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 12, height: 2, background: "var(--crit)" }} />Yediği gol</span>
            </div>
          </div>
        </>
      )}
    </>
  ) : (
    <div className="rc">
      <h3>Nasıl Çalışır?</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", lineHeight: 1.5 }}>
        Kanal bazlı eşleşme: bizim güç (final üçte-bir girişleri) × rakip zaaf (savunma aksiyonu boşluğu). Sömürülecek koridoru bulur.
      </div>
    </div>
  );

  // Üst KPI'lar için kanal özetleri
  const exploitCount = DEMO_MODE ? demoChannels.filter((c) => c.verdict === "exploit").length : 0;
  const topScore = DEMO_MODE ? Math.round((demoChannels[0]?.matchup_score ?? 0) * 100) : 0;

  return (
    <ConsoleShell
      active="/opponent"
      title="Rakip Raporu"
      sub={DEMO_MODE ? DEMO_OPP : "Eşleşme grid"}
      desc={DEMO_MODE
        ? `${DEMO_OPP} scout raporu · ${DEMO_COMP}. Kanal bazlı eşleşme, dizilim, zaaflar ve tehdit.`
        : "Kanal bazlı eşleşme: bizim güç × rakip zaaf. Sömürülecek koridoru bulur."}
      source={["statsbomb", "api_football"]}
      right={right}
    >
      {!DEMO_MODE && (
        <div className="st" style={{ marginTop: 0 }}>
          <h2>Eşleşme</h2>
          <form onSubmit={(e) => { e.preventDefault(); if (team.trim() && opp.trim()) setQ({ t: team.trim(), o: opp.trim() }); }} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input value={team} onChange={(e) => setTeam(e.target.value)} placeholder="Bizim takım ID" inputMode="numeric" style={inputStyle} />
            <span style={{ color: "var(--dim)" }}>vs</span>
            <input value={opp} onChange={(e) => setOpp(e.target.value)} placeholder="Rakip ID" inputMode="numeric" style={inputStyle} />
            <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Analiz et</button>
          </form>
        </div>
      )}

      {!DEMO_MODE && !q && <div className="pgdesc">İki takım ID gir (bizim + rakip).</div>}
      {!DEMO_MODE && q && isLoading && <LoadingState label="Hesaplanıyor…" />}
      {!DEMO_MODE && error && <ErrorState title="Analiz üretilemedi ya da yetki yok." />}
      {!DEMO_MODE && data?.note && <div className="pgdesc">{data.note}</div>}

      {/* DEMO: zengin scout şeridi */}
      {DEMO_MODE && (
        <>
          <div className="kpis">
            <div className="kpi"><div className="kl">Rakip</div><div className="kn" style={{ fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}><Crest team={DEMO_OPP} size={24} />{DEMO_OPP}</div><div className="kd">{demoMeta.formation} dizilim</div></div>
            <div className="kpi"><div className="kl">Analiz</div><div className="kn">{demoMeta.matches_analyzed}</div><div className="kd">son maç</div></div>
            <div className="kpi"><div className="kl">Sömürülecek Koridor</div><div className="kn" style={{ color: "var(--low)" }}>{exploitCount}</div><div className="kd">en iyi: sağ kanat</div></div>
            <div className="kpi"><div className="kl">En Yüksek Eşleşme</div><div className="kn" style={{ color: "var(--low)" }}>{topScore}</div><div className="kd">sağ kanat skoru</div></div>
            <div className="kpi"><div className="kl">Tehdit Seviyesi</div><div className="kn" style={{ color: "var(--mid)" }}>{demoMeta.threat_level}</div><div className="kd">2 yüksek tehdit</div></div>
          </div>

          {/* Taktik DNA — iki takımın oyun stili karşılaştırması + maç planı (temel analiz) */}
          {(() => {
            const cmp = compareDna(100, 101);   // Beşiktaş vs Antalyaspor
            return cmp ? (
              <>
                <div className="st"><h2>Taktik DNA</h2><span className="ep">oyun stili · 8 eksen · maç planı</span></div>
                <div className="rc" style={{ margin: "0 0 12px" }}>
                  <DnaComparisonBody comparison={cmp} />
                </div>
              </>
            ) : null;
          })()}

          {/* Saha analizi (Biz/Rakip geçişli) + pas ağı karşılaştırması */}
          <TacticalDeepDive usId={100} themId={101} />
        </>
      )}

      {v && (
        <>
          <div className="st"><h2>Kanal Analizi</h2><span className="ep">{v.matches_analyzed} maç · bizim güç × rakip zaaf</span></div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th>Kanal</th><th className="c">Girişler</th><th className="r">Bizim Güç</th><th className="r">Rakip Zaaf</th><th className="r">Skor</th><th className="c">Karar</th>
              </tr></thead>
              <tbody>
                {v.by_channel.map((c) => {
                  const vc = VERDICT_VAR[c.verdict] ?? "var(--muted)";
                  const score = Math.round(c.matchup_score * 100);
                  return (
                    <tr key={c.channel}>
                      <td><span className="nm">{CHANNEL_LABEL[c.channel] ?? c.channel}</span></td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)" }}>{c.our_attacks}</td>
                      <td className="r" style={{ color: "var(--muted)" }}>{pct(c.our_strength)}</td>
                      <td className="r" style={{ color: "var(--muted)" }}>{pct(c.opp_weakness)}</td>
                      <td className="r">
                        <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
                          <span style={{ width: 60, height: 5, borderRadius: 3, background: "var(--surface2)", overflow: "hidden", display: "inline-block" }}>
                            <i style={{ display: "block", height: "100%", width: `${score}%`, background: vc }} />
                          </span>
                          <span style={{ color: "var(--ink)", minWidth: 22 }}>{score}</span>
                        </div>
                      </td>
                      <td className="c"><span style={{ fontSize: "10px", textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: `1px solid ${vc}`, color: vc }}>{VERDICT_LABEL[c.verdict] ?? c.verdict}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* DEMO: zaaflar + eşleşme avantajı */}
      {DEMO_MODE && (
        <>
          {(() => {
            const wmap = weaknessMap(101);   // Antalyaspor zaafları — DNA'dan hesaplanır
            return (
              <>
                <div className="st"><h2>Zaaf Haritası</h2><span className="ep">Taktik DNA'dan hesaplandı · {wmap.length} zaaf</span></div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px,1fr))", gap: 10, marginBottom: 12 }}>
                  {wmap.map((w, i) => {
                    const sv = SEV_VAR[w.severity] ?? "var(--muted)";
                    return (
                      <div className="rc" key={i} style={{ margin: 0, borderTop: `2px solid ${sv}` }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                          <b style={{ fontSize: 13 }}>{w.title}</b>
                          <span className="risk" style={{ color: sv, fontSize: 10 }}><span className="rd" style={{ background: sv }} />{w.severity}</span>
                        </div>
                        <div style={{ fontSize: 11.5, color: "var(--dim)", lineHeight: 1.5, marginBottom: 7 }}>{w.reason}</div>
                        <div style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.5 }}>
                          <span style={{ color: "var(--low)", fontWeight: 700 }}>Sömür → </span>{w.exploit}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            );
          })()}

          {(() => {
            const plan = matchPlan(100, 101);
            return plan ? (
              <>
                <div className="st"><h2>Önerilen Oyun Planı</h2><span className="ep">DNA + zaaflardan · diziliş · pres · senaryolar</span></div>
                <div className="rc" style={{ margin: "0 0 12px" }}>
                  <MatchPlanBody plan={plan} />
                </div>
              </>
            ) : null;
          })()}

          <div className="st"><h2>Eşleşme Avantajı</h2><span className="ep">bizim oyuncu vs rakip</span></div>
          <div className="rc" style={{ margin: "0 0 12px", padding: 0, overflow: "hidden" }}>
            {demoDuels.map((m, i) => {
              const adv = m.advantage;
              const c = adv >= 65 ? "var(--low)" : adv >= 50 ? "var(--mid)" : "var(--high)";
              return (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 12, alignItems: "center", padding: "11px 14px", borderTop: i ? "1px solid var(--line)" : undefined }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600 }}>{m.ours} <span style={{ color: "var(--dim)" }}>vs</span> {m.theirs}</div>
                    <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{m.note}</div>
                    <div className="mbar" style={{ marginTop: 6, marginBottom: 0 }}>
                      <i style={{ width: `${adv}%`, background: c }} />
                    </div>
                  </div>
                  <div style={{ fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 18, color: c }}>%{adv}</div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
