"use client";

/**
 * Takım Detayı — son form + rating + kadro/güç özeti. ConsoleShell çatısında.
 *
 * DEMO_MODE: backend'siz, dolu "Beşiktaş" takım profili (form serisi, rating,
 * pozisyon bazlı güç, kilit oyuncular, sıradaki maç). Canlı veri: GET
 * /teams/{id}/form, GET /teams/{id}/rating.
 */

import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  DEMO_CLUB,
  demoSquad,
  demoNextMatch,
  type SquadPlayer,
  type Position,
} from "@/lib/demo-data";
import { ConsoleShell } from "../../_console/shell";
import { RiskDonut, LegendRow } from "../../_console/viz";

interface Confidence { score: number; label: string; drivers: string[] }
interface FormResponse {
  value: {
    matches_played: number;
    wins: number;
    draws: number;
    losses: number;
    goals_for: number;
    goals_against: number;
    points_per_game: number;
    last_results: ("W" | "D" | "L")[];
  };
  confidence: Confidence | null;
}
interface RatingResponse {
  value: { rating: number; home_rating: number | null; away_rating: number | null; matches_considered: number };
  confidence: Confidence | null;
}

function ResultDot({ r }: { r: "W" | "D" | "L" }) {
  const bg = r === "W" ? "var(--low)" : r === "L" ? "var(--crit)" : "var(--dim)";
  return <span style={{ display: "inline-flex", width: 24, height: 24, borderRadius: 5, alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#fff", background: bg }}>{r}</span>;
}

// --------------------------------------------------------------------------- //
// DEMO: "Beşiktaş" takım profili (tek demo evreni — id sadece başlıkta).
// --------------------------------------------------------------------------- //

const DEMO_FORM: FormResponse = {
  value: {
    matches_played: 10,
    wins: 6,
    draws: 2,
    losses: 2,
    goals_for: 19,
    goals_against: 11,
    points_per_game: 2.0,
    // En yeni en sağda: son maç galibiyet.
    last_results: ["W", "L", "W", "W", "D", "W", "L", "D", "W", "W"],
  },
  confidence: { score: 0.82, label: "yüksek", drivers: ["10 maçlık örneklem", "tutarlı xG farkı", "ev/deplasman dengeli"] },
};

const DEMO_RATING: RatingResponse = {
  value: { rating: 1.42, home_rating: 1.71, away_rating: 1.08, matches_considered: 18 },
  confidence: { score: 0.79, label: "yüksek", drivers: ["18 maç değerlendirildi", "xG tabanlı", "ev avantajı belirgin"] },
};

// Lig sıralaması bağlamı (rozet/şerit için).
const DEMO_LEAGUE = {
  competition: "Süper Lig — 34. Hafta",
  rank: 4,
  teams: 18,
  points: 58,
  xgFor: 1.74,
  xgAgainst: 1.06,
  cleanSheets: 4,
};

// xG farkı serisi (son 10 maç, + bize) — inline SVG sparkline için.
const DEMO_XGDIFF: number[] = [0.4, -0.2, 0.9, 0.6, 0.1, 1.1, -0.5, 0.2, 0.8, 0.7];

const POS_LABEL: Record<Position, string> = { GK: "Kaleci", DF: "Defans", MF: "Orta Saha", FW: "Forvet" };
const POS_COLOR: Record<Position, string> = { GK: "var(--dim)", DF: "var(--low)", MF: "var(--accent)", FW: "var(--high)" };

/** Bir grup oyuncunun ortalama kondisyonu (güç vekili olarak). */
function avgCond(players: SquadPlayer[]): number {
  return players.length ? Math.round(players.reduce((a, p) => a + p.condition, 0) / players.length) : 0;
}

function condColor(v: number): string {
  return v >= 85 ? "var(--low)" : v >= 72 ? "var(--mid)" : "var(--high)";
}

/** Son 10 xG-farkı için küçük inline alan grafiği (0 hattı ortada). */
function XgDiffSpark({ data }: { data: number[] }) {
  const w = 260, h = 64, pad = 4;
  const max = Math.max(1, ...data.map((d) => Math.abs(d)));
  const step = (w - pad * 2) / (data.length - 1);
  const x = (i: number) => pad + i * step;
  const y = (v: number) => h / 2 - (v / max) * (h / 2 - pad);
  const pts = data.map((d, i) => `${x(i)},${y(d)}`).join(" ");
  const area = `${pad},${h / 2} ${pts} ${x(data.length - 1)},${h / 2}`;
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }} preserveAspectRatio="none">
      <line x1={pad} y1={h / 2} x2={w - pad} y2={h / 2} stroke="var(--border2)" strokeWidth={1} strokeDasharray="3 3" />
      <polygon points={area} fill="var(--low)" opacity={0.1} />
      <polyline points={pts} fill="none" stroke="var(--low)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      {data.map((d, i) => (
        <circle key={i} cx={x(i)} cy={y(d)} r={2.4} fill={d >= 0 ? "var(--low)" : "var(--crit)"} />
      ))}
    </svg>
  );
}

export default function TeamDetailConsolePage() {
  const params = useParams<{ id: string }>();
  const teamId = params.id;

  // Demo modunda canlı API'ye dokunma; dolu "Beşiktaş" profilini göster.
  const { data: form } = useSWR<FormResponse>(DEMO_MODE ? null : `/teams/${teamId}/form`, apiFetch, { shouldRetryOnError: false });
  const { data: rating } = useSWR<RatingResponse>(DEMO_MODE ? null : `/teams/${teamId}/rating`, apiFetch, { shouldRetryOnError: false });

  const formData = DEMO_MODE ? DEMO_FORM : form;
  const ratingData = DEMO_MODE ? DEMO_RATING : rating;
  const f = formData?.value;
  const rt = ratingData?.value;

  const teamName = DEMO_MODE ? DEMO_CLUB : `Takım #${teamId}`;

  // Kadro/güç özeti (yalnızca demo evreninde).
  const byPos: Position[] = ["GK", "DF", "MF", "FW"];
  const groups = byPos.map((pos) => {
    const players = demoSquad.filter((p) => p.position === pos);
    return { pos, players, count: players.length, cond: avgCond(players) };
  });
  const squadCond = avgCond(demoSquad);
  const keyPlayers = [...demoSquad].sort((a, b) => b.condition - a.condition).slice(0, 5);

  const right = (
    <>
      <div className="rc">
        <h3>Rating <span className="tiny">xG tabanlı</span></h3>
        {rt ? (
          <>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
              <span style={{ fontSize: 30, fontWeight: 800, fontFamily: "JetBrains Mono" }}>{rt.rating.toFixed(2)}</span>
              <span style={{ fontSize: 11.5, color: "var(--dim)" }}>maç başı net xG</span>
            </div>
            <div className="stat"><span>Ev formu</span><span className="sv" style={{ color: "var(--low)" }}>{rt.home_rating?.toFixed(2) ?? "—"}</span></div>
            <div className="mbar"><i style={{ width: `${Math.min(100, ((rt.home_rating ?? 0) / 2.5) * 100)}%`, background: "var(--low)" }} /></div>
            <div className="stat"><span>Deplasman formu</span><span className="sv" style={{ color: "var(--mid)" }}>{rt.away_rating?.toFixed(2) ?? "—"}</span></div>
            <div className="mbar"><i style={{ width: `${Math.min(100, ((rt.away_rating ?? 0) / 2.5) * 100)}%`, background: "var(--mid)" }} /></div>
            <div className="stat"><span>Değerlendirilen</span><span className="sv">{rt.matches_considered} maç</span></div>
            {ratingData?.confidence && <div className="stat"><span>Model güveni</span><span className="sv">{ratingData.confidence.label}</span></div>}
          </>
        ) : <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yükleniyor…</div>}
      </div>

      {DEMO_MODE && (
        <>
          <div className="rc">
            <h3>Kadro Gücü <span className="tiny">{demoSquad.length} oyuncu</span></h3>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <RiskDonut
                segments={groups.map((g) => ({ value: g.count, color: POS_COLOR[g.pos] }))}
                centerLabel={squadCond}
                centerSub="kondisyon"
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                {groups.map((g) => (
                  <LegendRow key={g.pos} color={POS_COLOR[g.pos]} label={POS_LABEL[g.pos]} value={g.count} />
                ))}
              </div>
            </div>
          </div>

          <div className="rc">
            <h3>Sıradaki Maç <span className="tiny">{demoNextMatch.date} · {demoNextMatch.kickoff}</span></h3>
            <div className="nm-vs"><span className="t">{demoNextMatch.home}</span><span className="x">vs</span><span className="t away">{demoNextMatch.away}</span></div>
            <div className="nm-when">{demoNextMatch.competition}</div>
            <div className="probbar">
              <i style={{ width: `${Math.round(demoNextMatch.win * 100)}%`, background: "var(--low)" }} />
              <i style={{ width: `${Math.round(demoNextMatch.draw * 100)}%`, background: "var(--dim)" }} />
              <i style={{ width: `${Math.round(demoNextMatch.loss * 100)}%`, background: "var(--high)" }} />
            </div>
            <div className="probleg">
              <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>%{Math.round(demoNextMatch.win * 100)}</div><div className="pl">Galibiyet</div></div>
              <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>%{Math.round(demoNextMatch.draw * 100)}</div><div className="pl">Berabere</div></div>
              <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>%{Math.round(demoNextMatch.loss * 100)}</div><div className="pl">Mağlubiyet</div></div>
            </div>
          </div>

          <div className="rc">
            <h3>Kilit Oyuncular <span className="tiny">en hazır 5</span></h3>
            {keyPlayers.map((p) => (
              <div className="alrt" key={p.player_id}>
                <span className="ai" style={{ background: POS_COLOR[p.position] }} />
                <div className="am"><b>{p.player_name}</b> · {p.pos_detail}
                  <span className="tm">kondisyon {p.condition} · #{p.shirt}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );

  return (
    <ConsoleShell
      active="/teams"
      title={teamName}
      sub={DEMO_MODE ? "Form & güç profili" : "Form & rating"}
      desc={DEMO_MODE
        ? `${DEMO_LEAGUE.competition} · ligde ${DEMO_LEAGUE.rank}. sırada. Son form, model rating'i ve kadro güç dağılımı.`
        : "Takımın son form dökümü ve model rating'i."}
      source="api_football"
      right={right}
    >
      {DEMO_MODE && (
        <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
          <div className="kpi"><div className="kl">Lig Sırası</div><div className="kn">{DEMO_LEAGUE.rank}<span className="pct">.</span></div><div className="kd">{DEMO_LEAGUE.teams} takım · {DEMO_LEAGUE.points} puan</div></div>
          <div className="kpi"><div className="kl">Rating</div><div className="kn" style={{ color: "var(--low)" }}>{rt?.rating.toFixed(2)}</div><div className="kd">maç başı net xG</div></div>
          <div className="kpi"><div className="kl">Son 10 Form</div><div className="kn">{f?.wins}-{f?.draws}-{f?.losses}</div><div className="kd">PPG {f?.points_per_game.toFixed(1)}</div></div>
          <div className="kpi"><div className="kl">xG / Maç</div><div className="kn">{DEMO_LEAGUE.xgFor.toFixed(2)}</div><div className="kd">karşı {DEMO_LEAGUE.xgAgainst.toFixed(2)}</div></div>
          <div className="kpi"><div className="kl">Kadro Hazırlığı</div><div className="kn">{squadCond}<span className="pct">%</span></div><div className="kd">ort. kondisyon</div></div>
        </div>
      )}

      <div className="st" style={{ marginTop: DEMO_MODE ? undefined : 0 }}>
        <h2>Son Form</h2>
        {formData?.confidence && <span className="ep">güven: {formData.confidence.label}</span>}
      </div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        {f ? (
          <>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
              <span style={{ fontSize: 30, fontWeight: 800, fontFamily: "JetBrains Mono" }}>{f.wins}-{f.draws}-{f.losses}</span>
              <span style={{ fontSize: 13, color: "var(--muted)" }}>
                PPG <b style={{ color: "var(--ink)", fontFamily: "JetBrains Mono" }}>{f.points_per_game.toFixed(1)}</b>
                {" · "}GF/GA <b style={{ color: "var(--ink)", fontFamily: "JetBrains Mono" }}>{f.goals_for}/{f.goals_against}</b>
                {" · "}averaj <b style={{ color: f.goals_for - f.goals_against >= 0 ? "var(--low)" : "var(--crit)", fontFamily: "JetBrains Mono" }}>{f.goals_for - f.goals_against >= 0 ? "+" : ""}{f.goals_for - f.goals_against}</b>
              </span>
            </div>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: DEMO_MODE ? 14 : 0 }}>
              {f.last_results.slice(0, 10).map((r, i) => <ResultDot key={i} r={r} />)}
              <span style={{ alignSelf: "center", fontSize: 11, color: "var(--dim)", marginLeft: 4 }}>← eski · yeni →</span>
            </div>
            {DEMO_MODE && (
              <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Son 10 maç xG farkı (+ bizim lehimize)</div>
                <XgDiffSpark data={DEMO_XGDIFF} />
              </div>
            )}
          </>
        ) : <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yükleniyor…</div>}
      </div>

      {!DEMO_MODE && (
        <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
          <div className="kpi"><div className="kl">Oynanan</div><div className="kn">{f?.matches_played ?? "—"}</div><div className="kd">maç</div></div>
          <div className="kpi"><div className="kl">Galibiyet</div><div className="kn" style={{ color: "var(--low)" }}>{f?.wins ?? "—"}</div><div className="kd">W</div></div>
          <div className="kpi"><div className="kl">Beraberlik</div><div className="kn" style={{ color: "var(--mid)" }}>{f?.draws ?? "—"}</div><div className="kd">D</div></div>
          <div className="kpi"><div className="kl">Mağlubiyet</div><div className="kn" style={{ color: "var(--crit)" }}>{f?.losses ?? "—"}</div><div className="kd">L</div></div>
        </div>
      )}

      {DEMO_MODE && (
        <>
          <div className="st"><h2>Hatlara Göre Güç</h2><span className="ep">kondisyon vekili</span></div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th>Hat</th><th className="c">Oyuncu</th><th className="c">Ort. Yaş</th>
                <th>Güç (kondisyon)</th><th className="r">Skor</th>
              </tr></thead>
              <tbody>
                {groups.map((g) => {
                  const ages = g.players.map((p) => p.age);
                  const avgAge = ages.length ? Math.round(ages.reduce((a, b) => a + b, 0) / ages.length) : 0;
                  return (
                    <tr key={g.pos}>
                      <td><span className="pos" style={{ color: POS_COLOR[g.pos] }}>{g.pos}</span> <span className="nm" style={{ marginLeft: 6 }}>{POS_LABEL[g.pos]}</span></td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{g.count}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{avgAge}</td>
                      <td><span className="cond" style={{ width: 120 }}><i style={{ width: `${g.cond}%`, background: condColor(g.cond) }} /></span></td>
                      <td className="r" style={{ color: condColor(g.cond) }}>{g.cond}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="st"><h2>Kadro</h2><span className="ep">{demoSquad.length} oyuncu · {DEMO_CLUB}</span></div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th className="c">#</th><th>Oyuncu</th><th className="c">Mevki</th>
                <th className="c">Yaş</th><th>Kondisyon</th><th className="c">Risk</th>
              </tr></thead>
              <tbody>
                {demoSquad.map((p) => {
                  const rv = p.risk_label === "Kritik" ? "var(--crit)" : p.risk_label === "Yüksek" ? "var(--high)" : p.risk_label === "Orta" ? "var(--mid)" : "var(--low)";
                  return (
                    <tr key={p.player_id}>
                      <td className="pnum c">{p.shirt}</td>
                      <td><span className="nm">{p.player_name}</span> <span className="nat">{p.pos_detail}</span></td>
                      <td className="c"><span className="pos" style={{ color: POS_COLOR[p.position] }}>{p.position}</span></td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{p.age}</td>
                      <td><span className="cond" style={{ width: 90 }}><i style={{ width: `${p.condition}%`, background: condColor(p.condition) }} /></span> <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--muted)", marginLeft: 6 }}>{p.condition}</span></td>
                      <td className="c"><span className="risk" style={{ color: rv }}><span className="rd" style={{ background: rv, boxShadow: `0 0 7px ${rv}` }} />{p.risk_label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
