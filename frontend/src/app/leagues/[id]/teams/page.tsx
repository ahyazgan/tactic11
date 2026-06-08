"use client";

/**
 * Lig Takımları — bir ligin takım listesi. ConsoleShell çatısında.
 *
 * DEMO_MODE açıkken canlı API'ye hiç dokunmaz; "Süper Lig — 34. Hafta" evreninin
 * dolu takım listesini (18 takım, FK Demo + Rakip SK dahil) puan/form/xG güç
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
import { ConsoleShell } from "../../../_console/shell";
import { RiskDonut, LegendRow } from "../../../_console/viz";

interface League { external_id: number; name: string; season: number; country: string | null }
interface Team { sport: string; external_id: number; name: string; country: string | null; founded: number | null }

// --------------------------------------------------------------------------- //
// DEMO EVRENİ — Süper Lig 34. Hafta takım listesi (bu dosyaya özel, inline)
// "/teams" sıralamasıyla aynı evren: FK Demo zirve yarışında, Rakip SK sıradaki
// rakibimiz. Her takıma sabit teamId → satır /teams/{teamId} detayına gider.
// --------------------------------------------------------------------------- //

type Form = "G" | "B" | "M";

interface DemoTeam {
  teamId: number;    // /teams/{id} rotası için sabit kimlik
  rank: number;
  name: string;
  short: string;
  city: string;
  founded: number;
  played: number;
  win: number;
  draw: number;
  loss: number;
  gf: number;
  ga: number;
  xgf: number;       // beklenen attığı gol (sezon)
  xga: number;       // beklenen yediği gol (sezon)
  form: Form[];      // son 5 maç (en yeni en sağda)
  us?: boolean;      // FK Demo
  next?: boolean;    // sıradaki rakibimiz
}

const DEMO_TEAMS: DemoTeam[] = [
  { teamId: 201, rank: 1, name: "Anadolu Spor", short: "AND", city: "Ankara", founded: 1923, played: 33, win: 22, draw: 6, loss: 5, gf: 64, ga: 29, xgf: 60.4, xga: 31.2, form: ["G", "G", "B", "G", "G"] },
  { teamId: 100, rank: 2, name: "FK Demo", short: "FKD", city: "İstanbul", founded: 1908, played: 33, win: 21, draw: 7, loss: 5, gf: 61, ga: 28, xgf: 58.9, xga: 27.6, form: ["G", "B", "G", "G", "G"], us: true },
  { teamId: 202, rank: 3, name: "Marmara United", short: "MAR", city: "İstanbul", founded: 1911, played: 33, win: 20, draw: 6, loss: 7, gf: 58, ga: 33, xgf: 55.1, xga: 35.0, form: ["G", "G", "M", "G", "B"] },
  { teamId: 203, rank: 4, name: "Ege Atletik", short: "EGE", city: "İzmir", founded: 1914, played: 33, win: 18, draw: 8, loss: 7, gf: 52, ga: 34, xgf: 50.7, xga: 36.4, form: ["B", "G", "G", "B", "G"] },
  { teamId: 204, rank: 5, name: "Karadeniz FK", short: "KAR", city: "Trabzon", founded: 1967, played: 33, win: 17, draw: 7, loss: 9, gf: 49, ga: 38, xgf: 47.8, xga: 39.9, form: ["G", "M", "G", "G", "B"] },
  { teamId: 205, rank: 6, name: "Başkent Gücü", short: "BAS", city: "Ankara", founded: 1945, played: 33, win: 16, draw: 8, loss: 9, gf: 47, ga: 40, xgf: 45.2, xga: 41.1, form: ["B", "B", "G", "M", "G"] },
  { teamId: 206, rank: 7, name: "Toros SK", short: "TOR", city: "Antalya", founded: 1966, played: 33, win: 15, draw: 9, loss: 9, gf: 44, ga: 41, xgf: 43.6, xga: 42.0, form: ["G", "B", "M", "G", "B"] },
  { teamId: 207, rank: 8, name: "Doğu Çelik", short: "DOG", city: "Kayseri", founded: 1966, played: 33, win: 14, draw: 9, loss: 10, gf: 42, ga: 42, xgf: 41.0, xga: 43.5, form: ["M", "G", "B", "G", "M"] },
  { teamId: 208, rank: 9, name: "Akdeniz FK", short: "AKD", city: "Mersin", founded: 1925, played: 33, win: 13, draw: 10, loss: 10, gf: 40, ga: 43, xgf: 39.7, xga: 44.2, form: ["B", "M", "G", "B", "G"] },
  { teamId: 209, rank: 10, name: "Yıldız Spor", short: "YIL", city: "Bursa", founded: 1963, played: 33, win: 12, draw: 11, loss: 10, gf: 39, ga: 41, xgf: 38.1, xga: 42.8, form: ["B", "G", "B", "M", "B"] },
  { teamId: 101, rank: 11, name: "Rakip SK", short: "RKP", city: "İzmir", founded: 1912, played: 33, win: 12, draw: 9, loss: 12, gf: 41, ga: 44, xgf: 38.9, xga: 45.7, form: ["M", "B", "G", "M", "G"], next: true },
  { teamId: 210, rank: 12, name: "Boğaz United", short: "BOG", city: "İstanbul", founded: 1933, played: 33, win: 11, draw: 10, loss: 12, gf: 37, ga: 45, xgf: 36.4, xga: 46.0, form: ["G", "M", "B", "M", "B"] },
  { teamId: 211, rank: 13, name: "Step Atletik", short: "STP", city: "Konya", founded: 1922, played: 33, win: 10, draw: 11, loss: 12, gf: 35, ga: 46, xgf: 34.8, xga: 46.9, form: ["B", "M", "M", "B", "G"] },
  { teamId: 212, rank: 14, name: "Volkan FK", short: "VOL", city: "Adana", founded: 1954, played: 33, win: 10, draw: 9, loss: 14, gf: 34, ga: 49, xgf: 33.2, xga: 50.3, form: ["M", "M", "B", "G", "M"] },
  { teamId: 213, rank: 15, name: "Fırat Spor", short: "FIR", city: "Elazığ", founded: 1967, played: 33, win: 9, draw: 10, loss: 14, gf: 32, ga: 50, xgf: 31.9, xga: 51.1, form: ["M", "B", "M", "B", "M"] },
  { teamId: 214, rank: 16, name: "Demir Çelik SK", short: "DMR", city: "Karabük", founded: 1969, played: 33, win: 8, draw: 9, loss: 16, gf: 30, ga: 54, xgf: 29.6, xga: 55.4, form: ["M", "G", "M", "M", "B"] },
  { teamId: 215, rank: 17, name: "Granit FK", short: "GRA", city: "Eskişehir", founded: 1965, played: 33, win: 6, draw: 10, loss: 17, gf: 27, ga: 58, xgf: 26.8, xga: 57.9, form: ["M", "M", "B", "M", "M"] },
  { teamId: 216, rank: 18, name: "Şafak United", short: "SAF", city: "Samsun", founded: 1965, played: 33, win: 5, draw: 8, loss: 20, gf: 24, ga: 63, xgf: 24.1, xga: 61.5, form: ["M", "M", "M", "B", "M"] },
];

const LEAGUE = "Süper Lig";
const SEASON = "2025/26 · 34. Hafta";

const FORM_VAR: Record<Form, string> = { G: "var(--low)", B: "var(--mid)", M: "var(--crit)" };

function points(t: DemoTeam): number {
  return t.win * 3 + t.draw;
}

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

  const shown = teams.filter((t) => {
    if (scope === "top") return t.rank <= 5;
    if (scope === "drop") return t.rank >= 14;
    return true;
  });

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
        <div className="nm-vs"><span className="t">{us.name}</span><span className="x">vs</span><span className="t away">{next.name}</span></div>
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
        <div className="kpi"><div className="kl">FK Demo</div><div className="kn" style={{ color: "var(--accent)" }}>{us.rank}<span className="pct">.</span></div><div className="kd"><span className="u">{points(us)} puan</span> · lidere {gapToLeader <= 0 ? 0 : gapToLeader}</div></div>
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
            <th className="c">#</th>
            <th>Takım</th>
            <th>Şehir</th>
            <th className="c">O</th>
            <th className="c">G</th>
            <th className="c">B</th>
            <th className="c">M</th>
            <th className="c">A-Y</th>
            <th className="c">Av</th>
            <th className="c">Form</th>
            <th className="r">P</th>
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
                    <span className="pos" style={{ marginRight: 8 }}>{t.short}</span>
                    <span className="nm" style={{ color: t.us ? "var(--accent)" : "var(--ink)" }}>{t.name}</span>
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
                    <td><span className="nm">{t.name}</span>{t.us && <span className="nat"> · biz</span>}</td>
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
      {isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {error && <div className="pgdesc">Yüklenemedi ya da yetki yok.</div>}
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
