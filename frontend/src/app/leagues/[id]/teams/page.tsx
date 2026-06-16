"use client";

/**
 * Lig Takımları — bir ligin takım listesi. ConsoleShell çatısında.
 *
 * DEMO_MODE açıkken canlı API'ye hiç dokunmaz; "Süper Lig — 34. Hafta" evreninin
 * dolu takım listesini (18 takım, Beşiktaş + Antalyaspor dahil) puan/form/xG güç
 * metrikleriyle gösterir. Satıra tıkla → takım detayı (/teams/{id}). Boş-state /
 * "ID gir" prompt'u / spinner / "yetki yok" YOK.
 *
 * DEMO kapalıyken eski canlı-API (GET /teams/{leagueId}) davranışına döner.
 */

import * as React from "react";
import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  DEMO_TEAM_ROWS,
  demoTeamPoints,
  type DemoForm,
  type DemoTeamRow,
} from "@/lib/demo-teams";
import { Crest } from "@/lib/teams";
import { useSort, SortableTh, sortCompare } from "@/lib/sortable";
import { ConsoleShell } from "../../../_console/shell";
import { LoadingState, ErrorState } from "@/components/ui";
import { RiskDonut, LegendRow } from "../../../_console/viz";

interface League { external_id: number; name: string; season: number; country: string | null }
interface Team { sport: string; external_id: number; name: string; country: string | null; founded: number | null }

// --------------------------------------------------------------------------- //
// DEMO EVRENİ — Süper Lig 34. Hafta takım listesi.
// Veri TEK kaynaktan: lib/demo-teams.ts (takım detayı /teams/{id} de aynı
// kaynağı okur → tıklanan takım detayda da aynı kimlikle açılır).
// --------------------------------------------------------------------------- //

type Form = DemoForm;
type DemoTeam = DemoTeamRow;

const DEMO_TEAMS: DemoTeam[] = DEMO_TEAM_ROWS;

const LEAGUE = "Süper Lig";
const SEASON = "2025/26 · 34. Hafta";

const FORM_VAR: Record<Form, string> = { G: "var(--low)", B: "var(--mid)", M: "var(--crit)" };

const points = demoTeamPoints;

/** Sıra bandına göre satır vurgusu: şampiyonluk / Avrupa / orta / düşme. */
function zoneColor(rank: number): string {
  if (rank <= 2) return "var(--low)";       // şampiyonluk yarışı
  if (rank <= 5) return "var(--accent)";    // Avrupa kupaları
  if (rank >= 16) return "var(--crit)";     // düşme hattı
  return "var(--dim)";
}

function zoneLabel(rank: number): string | null {
  if (rank === 1) return "Lider";
  if (rank <= 5) return "Avrupa";
  if (rank >= 16) return "Düşme";
  return null;
}

const formPts = (t: DemoTeam) => t.form.reduce((s, f) => s + (f === "G" ? 3 : f === "B" ? 1 : 0), 0);

/** Mini form rozetleri (son 5 maç). */
function FormPips({ form }: { form: Form[] }) {
  return (
    <span style={{ display: "inline-flex", gap: 4 }}>
      {form.map((f, i) => (
        <span
          key={i}
          title={f === "G" ? "Galibiyet" : f === "B" ? "Beraberlik" : "Mağlubiyet"}
          style={{
            width: 16,
            height: 16,
            borderRadius: 5,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 10,
            fontWeight: 700,
            color: "#fff",
            background: FORM_VAR[f],
            fontFamily: "JetBrains Mono",
          }}
        >
          {f}
        </span>
      ))}
    </span>
  );
}

type Scope = "all" | "top" | "drop";

export default function LeagueTeamsConsolePage() {
  if (DEMO_MODE) return <LeagueTeamsDemo />;
  return <LeagueTeamsLive />;
}

// --------------------------------------------------------------------------- //
// DEMO İÇERİK
// --------------------------------------------------------------------------- //

function LeagueTeamsDemo() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const leagueId = params.id;
  const [scope, setScope] = React.useState<Scope>("all");

  const teams = DEMO_TEAMS;
  const us = teams.find((t) => t.us)!;
  const next = teams.find((t) => t.next)!;
  const leader = teams[0];
  const gapToLeader = points(leader) - points(us);

  // Lig geneli en iyi hücum / savunma.
  const bestAttack = [...teams].sort((a, b) => b.gf - a.gf)[0];
  const bestDefense = [...teams].sort((a, b) => a.ga - b.ga)[0];

  // Sağ kolon donut: ligin sıra bölgeleri.
  const zone = [
    { label: "Şampiyonluk (1-2)", n: teams.filter((t) => t.rank <= 2).length, v: "var(--low)" },
    { label: "Avrupa (3-5)", n: teams.filter((t) => t.rank >= 3 && t.rank <= 5).length, v: "var(--accent)" },
    { label: "Orta sıra (6-15)", n: teams.filter((t) => t.rank >= 6 && t.rank <= 15).length, v: "var(--dim)" },
    { label: "Düşme hattı (16-18)", n: teams.filter((t) => t.rank >= 16).length, v: "var(--crit)" },
  ];

  // En formda 5 takım (son 5 maçtan puan).
  const inForm = [...teams].sort((a, b) => formPts(b) - formPts(a)).slice(0, 5);

  const filtered = teams.filter((t) => {
    if (scope === "top") return t.rank <= 5;
    if (scope === "drop") return t.rank >= 14;
    return true;
  });

  // Sıralama: varsayılan lig sırası (rank artan). Sütun başlığına tıkla → o metrik.
  const sort = useSort<"rank" | "name" | "played" | "win" | "draw" | "loss" | "diff" | "points">("rank", "asc");
  const valOf = (t: DemoTeam, k: typeof sort.key) =>
    k === "diff" ? t.gf - t.ga : k === "points" ? points(t) : t[k];
  const shown = [...filtered].sort((a, b) => sortCompare(valOf(a, sort.key), valOf(b, sort.key), sort.dir));

  const right = (
    <>
      <div className="rc">
        <h3>Lig Bilgisi <span className="tiny">#{leagueId}</span></h3>
        <div className="stat"><span>Ad</span><span className="sv" style={{ fontFamily: "inherit" }}>{LEAGUE}</span></div>
        <div className="stat"><span>Ülke</span><span className="sv" style={{ fontFamily: "inherit" }}>Türkiye</span></div>
        <div className="stat"><span>Sezon</span><span className="sv">2025/26</span></div>
        <div className="stat"><span>Hafta</span><span className="sv">34/38</span></div>
        <div className="stat"><span>Takım sayısı</span><span className="sv">{teams.length}</span></div>
      </div>

      <div className="rc">
        <h3>Lig Bölgeleri <span className="tiny">{teams.length} takım</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut segments={zone.map((z) => ({ value: z.n, color: z.v }))} centerLabel={teams.length} centerSub="takım" />
          <div style={{ flex: 1, minWidth: 0 }}>
            {zone.map((z) => (
              <LegendRow key={z.label} color={z.v} label={z.label} value={z.n} />
            ))}
          </div>
        </div>
      </div>

      <div className="rc">
        <h3>Sıradaki Rakip <span className="tiny">{LEAGUE} · 34. Hafta</span></h3>
        <div className="nm-vs"><span className="t" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><Crest team={us.name} size={18} />{us.name}</span><span className="x">vs</span><span className="t away" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>{next.name}<Crest team={next.name} size={18} /></span></div>
        <div className="nm-when">Ev sahibi · {next.name} ligde {next.rank}. sırada</div>
        <div className="stat"><span>Bizim sıramız</span><span className="sv" style={{ color: "var(--low)" }}>{us.rank}.</span></div>
        <div className="stat"><span>Rakip sırası</span><span className="sv">{next.rank}.</span></div>
        <div className="stat"><span>Rakip son 5 (puan)</span><span className="sv" style={{ color: "var(--mid)" }}>{formPts(next)}/15</span></div>
        <div className="stat"><span>Rakip averajı</span><span className="sv" style={{ color: next.gf - next.ga >= 0 ? "var(--low)" : "var(--crit)" }}>{next.gf - next.ga >= 0 ? "+" : ""}{next.gf - next.ga}</span></div>
        <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
          <button
            onClick={() => router.push(`/teams/${next.teamId}`)}
            style={{ flex: 1, fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5, padding: "6px 12px", borderRadius: 7, border: "1px solid var(--accent)", color: "var(--accent)", background: "var(--accent-lt)", cursor: "pointer", fontWeight: 600, fontFamily: "inherit" }}
          >
            Rakip detayı →
          </button>
        </div>
      </div>

      <div className="rc">
        <h3>En Formda <span className="tiny">son 5 maç</span></h3>
        {inForm.map((t) => (
          <div
            className="alrt"
            key={t.teamId}
            onClick={() => router.push(`/teams/${t.teamId}`)}
            style={{ cursor: "pointer" }}
          >
            <span className="ai" style={{ background: t.us ? "var(--accent)" : "var(--low)" }} />
            <div className="am"><b>{t.name}</b>{t.us ? " · biz" : ""}
              <span className="tm">{formPts(t)}/15 puan · {t.rank}. sıra · averaj {t.gf - t.ga >= 0 ? "+" : ""}{t.gf - t.ga}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/leagues"
      title={LEAGUE}
      sub="Takımlar"
      desc={`${LEAGUE} ${SEASON} takımları — form, gol ve beklenen-gol (xG) ile. Detay için bir takıma tıkla.`}
      right={right}
    >
      <div className="kpis">
        <div className="kpi"><div className="kl">Takım</div><div className="kn">{teams.length}</div><div className="kd">ligde toplam</div></div>
        <div className="kpi"><div className="kl">Beşiktaş</div><div className="kn" style={{ color: "var(--accent)" }}>{us.rank}<span className="pct">.</span></div><div className="kd"><span className="u">{points(us)} puan</span> · lidere {gapToLeader <= 0 ? 0 : gapToLeader}</div></div>
        <div className="kpi"><div className="kl">Averajımız</div><div className="kn" style={{ color: us.gf - us.ga >= 0 ? "var(--low)" : "var(--crit)" }}>{us.gf - us.ga >= 0 ? "+" : ""}{us.gf - us.ga}</div><div className="kd">{us.gf} attık · {us.ga} yedik</div></div>
        <div className="kpi"><div className="kl">En İyi Hücum</div><div className="kn">{bestAttack.gf}</div><div className="kd">{bestAttack.name}</div></div>
        <div className="kpi"><div className="kl">En İyi Savunma</div><div className="kn">{bestDefense.ga}</div><div className="kd">{bestDefense.name}</div></div>
      </div>

      <div className="st" style={{ marginTop: 0 }}>
        <h2>Takım Listesi — Puan Durumu</h2>
        <div className="seg">
          <button className={scope === "all" ? "on" : ""} onClick={() => setScope("all")}>Tümü</button>
          <button className={scope === "top" ? "on" : ""} onClick={() => setScope("top")}>Zirve</button>
          <button className={scope === "drop" ? "on" : ""} onClick={() => setScope("drop")}>Dip</button>
        </div>
      </div>
      <div className="tbl">
        <table>
          <thead><tr>
            <SortableTh active={sort.key === "rank"} dir={sort.dir} label="#" align="c" onClick={() => sort.onSort("rank")} />
            <SortableTh active={sort.key === "name"} dir={sort.dir} label="Takım" onClick={() => sort.onSort("name")} />
            <th>Şehir</th>
            <SortableTh active={sort.key === "played"} dir={sort.dir} label="O" align="c" onClick={() => sort.onSort("played")} />
            <SortableTh active={sort.key === "win"} dir={sort.dir} label="G" align="c" onClick={() => sort.onSort("win")} />
            <SortableTh active={sort.key === "draw"} dir={sort.dir} label="B" align="c" onClick={() => sort.onSort("draw")} />
            <SortableTh active={sort.key === "loss"} dir={sort.dir} label="M" align="c" onClick={() => sort.onSort("loss")} />
            <th className="c">A-Y</th>
            <SortableTh active={sort.key === "diff"} dir={sort.dir} label="Av" align="c" onClick={() => sort.onSort("diff")} />
            <th className="c">Form</th>
            <SortableTh active={sort.key === "points"} dir={sort.dir} label="P" align="r" onClick={() => sort.onSort("points")} />
          </tr></thead>
          <tbody>
            {shown.map((t) => {
              const zc = zoneColor(t.rank);
              const zl = zoneLabel(t.rank);
              const diff = t.gf - t.ga;
              return (
                <tr
                  key={t.teamId}
                  onClick={() => router.push(`/teams/${t.teamId}`)}
                  style={{ cursor: "pointer", background: t.us ? "var(--accent-lt)" : undefined }}
                >
                  <td className="pnum c"><span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 3, height: 14, borderRadius: 2, background: zc }} />{t.rank}
                  </span></td>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, marginRight: 4 }}>
                      <Crest team={t.name} size={20} />
                      <span className="nm" style={{ color: t.us ? "var(--accent)" : "var(--ink)" }}>{t.name}</span>
                    </span>
                    {t.us && <span className="nat"> · biz</span>}
                    {t.next && <span className="nat"> · sıradaki rakip</span>}
                    {zl && !t.us && (
                      <span className="risk" style={{ marginLeft: 8, color: zc, padding: "2px 8px", fontSize: 10.5 }}>
                        <span className="rd" style={{ background: zc }} />{zl}
                      </span>
                    )}
                  </td>
                  <td style={{ color: "var(--muted)" }}>{t.city}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{t.played}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--low)" }}>{t.win}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--mid)" }}>{t.draw}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--crit)" }}>{t.loss}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)", fontSize: 11 }}>{t.gf}:{t.ga}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 600, color: diff >= 0 ? "var(--low)" : "var(--crit)" }}>{diff >= 0 ? "+" : ""}{diff}</td>
                  <td className="c"><FormPips form={t.form} /></td>
                  <td className="r">{points(t)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="st"><h2>Beklenen Gol (xG) — Güç Sıralaması</h2><span className="ep">sezon kümülatif xG / xGA</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th>
            <th>Takım</th>
            <th>Hücum gücü (xG attığı)</th>
            <th>Savunma gücü (xGA yediği)</th>
            <th className="r">Net xG</th>
          </tr></thead>
          <tbody>
            {[...teams]
              .sort((a, b) => (b.xgf - b.xga) - (a.xgf - a.xga))
              .slice(0, 10)
              .map((t, i) => {
                const net = t.xgf - t.xga;
                // Ölçek: en yüksek xGF ~64, en yüksek xGA ~62 → 0..100 bar.
                const atkW = Math.round((t.xgf / 64) * 100);
                const defW = Math.round((t.xga / 62) * 100);
                return (
                  <tr
                    key={t.teamId}
                    onClick={() => router.push(`/teams/${t.teamId}`)}
                    style={{ cursor: "pointer", background: t.us ? "var(--accent-lt)" : undefined }}
                  >
                    <td className="pnum c">{i + 1}</td>
                    <td><span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}><Crest team={t.name} size={18} /><span className="nm">{t.name}</span></span>{t.us && <span className="nat"> · biz</span>}</td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--muted)", minWidth: 34 }}>{t.xgf.toFixed(1)}</span>
                        <span className="mbar" style={{ flex: 1, margin: 0 }}><i style={{ width: `${atkW}%`, background: "var(--low)" }} /></span>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--muted)", minWidth: 34 }}>{t.xga.toFixed(1)}</span>
                        <span className="mbar" style={{ flex: 1, margin: 0 }}><i style={{ width: `${defW}%`, background: "var(--high)" }} /></span>
                      </div>
                    </td>
                    <td className="r" style={{ color: net >= 0 ? "var(--low)" : "var(--crit)" }}>{net >= 0 ? "+" : ""}{net.toFixed(1)}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 12, fontSize: 11.5, color: "var(--dim)" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><i style={{ width: 10, height: 10, borderRadius: 3, background: "var(--low)" }} /> Şampiyonluk / kupa</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><i style={{ width: 10, height: 10, borderRadius: 3, background: "var(--accent)" }} /> Avrupa kupaları</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><i style={{ width: 10, height: 10, borderRadius: 3, background: "var(--crit)" }} /> Düşme hattı</span>
        <span style={{ marginLeft: "auto" }}>Satıra tıkla → takım detayı</span>
      </div>
    </ConsoleShell>
  );
}

// --------------------------------------------------------------------------- //
// CANLI İÇERİK (DEMO kapalı) — eski GET /teams/{leagueId} davranışı
// --------------------------------------------------------------------------- //

function LeagueTeamsLive() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const leagueId = params.id;

  const { data: leagues } = useSWR<League[]>("/leagues", apiFetch, { shouldRetryOnError: false });
  const league = leagues?.find((l) => l.external_id === Number(leagueId));
  const { data: teams, error, isLoading } = useSWR<Team[]>(`/teams/${leagueId}`, apiFetch, { shouldRetryOnError: false });
  const rows = teams ?? [];

  const right = (
    <div className="rc">
      <h3>Lig Bilgisi</h3>
      <div className="stat"><span>Ad</span><span className="sv" style={{ fontFamily: "inherit" }}>{league?.name ?? `#${leagueId}`}</span></div>
      <div className="stat"><span>Ülke</span><span className="sv" style={{ fontFamily: "inherit" }}>{league?.country ?? "—"}</span></div>
      {league && <div className="stat"><span>Sezon</span><span className="sv">{league.season}/{league.season + 1}</span></div>}
      <div className="stat"><span>Takım sayısı</span><span className="sv">{rows.length}</span></div>
    </div>
  );

  return (
    <ConsoleShell
      active="/leagues"
      title={league?.name ?? `Lig #${leagueId}`}
      sub="Takımlar"
      desc="Bu ligdeki takımlar. Takım detayı için bir satıra tıkla."
      right={right}
    >
      {isLoading && <LoadingState />}
      {error && <ErrorState title="Yüklenemedi ya da yetki yok." />}
      <div className="st" style={{ marginTop: 0 }}><h2>Takım Listesi</h2><span className="ep">GET /teams/{leagueId}</span></div>
      <div className="tbl">
        <table>
          <thead><tr><th className="c">#</th><th>Takım</th><th>Ülke</th><th className="c">Kuruluş</th><th className="r">ID</th></tr></thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>Bu ligde takım yok.</td></tr>
            )}
            {rows.map((t, i) => (
              <tr key={t.external_id} onClick={() => router.push(`/teams/${t.external_id}`)} style={{ cursor: "pointer" }}>
                <td className="pnum c">{i + 1}</td>
                <td><span className="nm">{t.name}</span></td>
                <td style={{ color: "var(--muted)" }}>{t.country ?? "—"}</td>
                <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{t.founded ?? "—"}</td>
                <td className="r" style={{ color: "var(--dim)" }}>{t.external_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
