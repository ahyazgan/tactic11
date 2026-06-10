"use client";

/**
 * Kadro — Teknik Ekip Konsolu. ConsoleShell çatısını kullanır.
 * Oyuncu listesi (kondisyon + risk) + durum filtresi + sağ kolonda
 * durum dağılımı ve en riskli oyuncular. Gerçek veri: GET /physical-tests/players.
 */

import * as React from "react";
import useSWR from "swr";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoPlayerRows, demoSquad } from "@/lib/demo-data";
import { PlayerAvatar } from "@/lib/player-avatar";
import {
  SM_SEASON,
  SM_TEAM_ID,
  smAge,
  smMediaUrl,
  type SmSquadMember,
} from "@/lib/sportmonks";
import { useSort, SortableTh, sortCompare } from "@/lib/sortable";
import { ConsoleShell } from "../_console/shell";
import { RiskDonut, LegendRow } from "../_console/viz";

// Backend pozisyon kodu (G/D/M/F) → PlayerAvatar pozisyonu + TR etiket.
const SM_POS: Record<string, { avatar: string; label: string }> = {
  G: { avatar: "GK", label: "Kaleci" },
  D: { avatar: "DF", label: "Defans" },
  M: { avatar: "MF", label: "Orta Saha" },
  F: { avatar: "FW", label: "Forvet" },
};

/** Canlı kadro satırındaki foto: proxy görseli varsa <img>, yoksa baş-harf rozeti. */
function SquadPhoto({ m, size = 26 }: { m: SmSquadMember; size?: number }) {
  const [broken, setBroken] = React.useState(false);
  const url = smMediaUrl(m.photo_url);
  if (!url || broken) {
    return <PlayerAvatar name={m.name} position={m.position ? SM_POS[m.position]?.avatar : undefined} size={size} />;
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt={m.name}
      width={size}
      height={size}
      onError={() => setBroken(true)}
      style={{ borderRadius: "50%", objectFit: "cover", background: "var(--panel)", border: "1px solid var(--line)" }}
    />
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

const RISK_VAR: Record<string, string> = {
  Kritik: "var(--crit)",
  Yüksek: "var(--high)",
  Orta: "var(--mid)",
  Düşük: "var(--low)",
};

// Oyuncu id → pozisyon (avatar rengi için; demoPlayerRows pozisyon taşımaz).
const POS_BY_ID: Record<string, string> = Object.fromEntries(
  demoSquad.map((p) => [String(p.player_id), p.position]),
);

// ── Kadro Derinliği (engine.squad_depth aynası) ──────────────────────────────
// Eşikler app/engine/squad_depth/compute.py ile birebir: pozisyon başına ideal
// minimum + yaşlanma eşiği 31. Demo demoSquad'tan; canlıda GET
// /admin/teams/{id}/squad-depth aynı raporu döner.
const DEPTH_MIN: Record<string, number> = { GK: 2, DF: 6, MF: 5, FW: 4 };
const POS_FULL: Record<string, string> = { GK: "Kaleci", DF: "Defans", MF: "Orta Saha", FW: "Forvet" };
const AGING_AGE = 31;

interface PosDepth {
  pos: string; label: string; count: number; min: number;
  avgAge: number | null; aging: number;
  status: "insufficient" | "adequate" | "surplus"; agingRisk: boolean;
}
const SQUAD_DEPTH: PosDepth[] = (["GK", "DF", "MF", "FW"] as const).map((pos) => {
  const players = demoSquad.filter((p) => p.position === pos);
  const count = players.length;
  const ages = players.map((p) => p.age);
  const avgAge = ages.length ? Math.round((ages.reduce((a, b) => a + b, 0) / ages.length) * 10) / 10 : null;
  const aging = ages.filter((a) => a >= AGING_AGE).length;
  const min = DEPTH_MIN[pos];
  const status: PosDepth["status"] = count < min ? "insufficient" : count > min + 2 ? "surplus" : "adequate";
  const agingRisk = count > 0 && aging / count >= 0.5 && status !== "surplus";
  return { pos, label: POS_FULL[pos], count, min, avgAge, aging, status, agingRisk };
});
const DEPTH_STATUS_VAR: Record<PosDepth["status"], { v: string; txt: string }> = {
  insufficient: { v: "var(--crit)", txt: "yetersiz" },
  adequate: { v: "var(--low)", txt: "yeterli" },
  surplus: { v: "var(--mid)", txt: "fazla" },
};

/** Risk etiketinden kadro durumu türet. */
function statusOf(label: string): { txt: string; v: string } {
  if (label === "Kritik" || label === "Yüksek") return { txt: "Risk", v: "var(--high)" };
  if (label === "Orta") return { txt: "İzlemede", v: "var(--mid)" };
  return { txt: "Hazır", v: "var(--low)" };
}

function condColor(v: number): string {
  return v >= 85 ? "var(--low)" : v >= 72 ? "var(--mid)" : "var(--high)";
}

type Filter = "all" | "ready" | "risk";

export default function SquadConsolePage() {
  const router = useRouter();
  // Demo modunda canlı API'ye dokunma; dolu mock kadroyu göster (boş tablo olmaz).
  const { data } = useSWR<PlayerRow[]>(DEMO_MODE ? null : "/physical-tests/players", apiFetch, {
    shouldRetryOnError: false,
  });
  // Canlı sezon kadrosu — Sportmonks (/sm/squad): foto + sezon-toplam istatistik.
  // Erişim yoksa (503/502) bölüm hiç görünmez; mevcut risk tablosu etkilenmez.
  const { data: smSquad } = useSWR<SmSquadMember[]>(
    DEMO_MODE ? null : `/sm/squad?team_id=${SM_TEAM_ID}&season=${SM_SEASON}`,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const [filter, setFilter] = React.useState<Filter>("all");

  const players = DEMO_MODE ? (demoPlayerRows as PlayerRow[]) : (data ?? []);
  const risky = players.filter((p) => p.risk_label === "Yüksek" || p.risk_label === "Kritik").length;
  const ready = players.filter((p) => p.risk_label === "Düşük").length;
  const watch = players.filter((p) => p.risk_label === "Orta").length;
  const avgCond = players.length
    ? Math.round(players.reduce((a, p) => a + (100 - p.risk_score * 100), 0) / players.length)
    : 0;

  // Durum dağılımı (sağ kolon).
  const dist = [
    { label: "Düşük", n: players.filter((p) => p.risk_label === "Düşük").length, v: "var(--low)" },
    { label: "Orta", n: watch, v: "var(--mid)" },
    { label: "Yüksek", n: players.filter((p) => p.risk_label === "Yüksek").length, v: "var(--high)" },
    { label: "Kritik", n: players.filter((p) => p.risk_label === "Kritik").length, v: "var(--crit)" },
  ];

  const topRisk = [...players]
    .filter((p) => p.risk_label === "Yüksek" || p.risk_label === "Kritik")
    .sort((a, b) => b.risk_score - a.risk_score)
    .slice(0, 5);

  const shown = players.filter((p) => {
    if (filter === "ready") return p.risk_label === "Düşük";
    if (filter === "risk") return p.risk_label === "Yüksek" || p.risk_label === "Kritik";
    return true;
  });

  const sort = useSort<"player_name" | "test_count" | "latest_test_date" | "risk_score">("risk_score");
  const sortedShown = [...shown].sort((a, b) =>
    sortCompare(a[sort.key] ?? "", b[sort.key] ?? "", sort.dir),
  );

  const right = (
    <>
      <div className="rc">
        <h3>Durum Dağılımı <span className="tiny">{players.length} oyuncu</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut segments={dist.map((d) => ({ value: d.n, color: d.v }))} centerLabel={players.length} centerSub="kadro" />
          <div style={{ flex: 1, minWidth: 0 }}>
            {dist.map((d) => (
              <LegendRow key={d.label} color={d.v} label={d.label} value={d.n} />
            ))}
          </div>
        </div>
      </div>

      <div className="rc">
        <h3>En Riskli <span className="tiny">{topRisk.length}</span></h3>
        {topRisk.length === 0 && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Riskli oyuncu yok.</div>}
        {topRisk.map((p) => {
          const rv = RISK_VAR[p.risk_label] ?? "var(--dim)";
          return (
            <div
              className="alrt rowlink"
              key={p.player_id}
              role="link"
              tabIndex={0}
              title={`${p.player_name} — oyuncu profili`}
              onClick={() => router.push(`/players/${p.player_id}`)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push(`/players/${p.player_id}`); } }}
            >
              <span className="ai" style={{ background: rv }} />
              <div className="am"><b>{p.player_name}</b> · {p.risk_label.toLowerCase()}
                <span className="tm">risk {Math.round(p.risk_score * 100)}/100 · {p.test_count} test</span>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/squad"
      title="Kadro"
      sub="Oyuncu listesi ve durum"
      desc="Tüm kadro kondisyon ve yük-riski ile. Filtreyle hazır/riskli oyunculara odaklan."
      navBadge={risky}
      right={right}
    >
      <div className="kpis">
        <div className="kpi"><div className="kl">Kadro Mevcudu</div><div className="kn">{players.length}</div><div className="kd">toplam oyuncu</div></div>
        <div className="kpi"><div className="kl">Hazır</div><div className="kn" style={{ color: "var(--low)" }}>{ready}</div><div className="kd">düşük risk</div></div>
        <div className="kpi"><div className="kl">İzlemede</div><div className="kn" style={{ color: "var(--mid)" }}>{watch}</div><div className="kd">orta risk</div></div>
        <div className="kpi"><div className="kl">Riskli</div><div className="kn" style={{ color: risky ? "var(--high)" : "var(--low)" }}>{risky}</div><div className="kd">yüksek/kritik</div></div>
        <div className="kpi"><div className="kl">Ort. Kondisyon</div><div className="kn">{avgCond}<span className="pct">%</span></div><div className="kd">risk skorundan</div></div>
      </div>

      <div className="st">
        <h2>Oyuncular</h2>
        <div className="seg">
          <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>Tümü</button>
          <button className={filter === "ready" ? "on" : ""} onClick={() => setFilter("ready")}>Hazır</button>
          <button className={filter === "risk" ? "on" : ""} onClick={() => setFilter("risk")}>Riskli</button>
        </div>
      </div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th>
            <SortableTh active={sort.key === "player_name"} dir={sort.dir} label="Oyuncu" onClick={() => sort.onSort("player_name")} />
            <SortableTh active={sort.key === "test_count"} dir={sort.dir} label="Test" align="c" onClick={() => sort.onSort("test_count")} />
            <th className="c">Kondisyon</th>
            <SortableTh active={sort.key === "latest_test_date"} dir={sort.dir} label="Son Test" align="c" onClick={() => sort.onSort("latest_test_date")} />
            <th className="c">Durum</th>
            <SortableTh active={sort.key === "risk_score"} dir={sort.dir} label="Risk" align="r" onClick={() => sort.onSort("risk_score")} />
          </tr></thead>
          <tbody>
            {sortedShown.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                {players.length === 0 ? "Veri yok (backend bağlı değilse boş gelir)." : "Bu filtrede oyuncu yok."}
              </td></tr>
            )}
            {sortedShown.map((p, i) => {
              const cond = Math.round(100 - p.risk_score * 100);
              const rv = RISK_VAR[p.risk_label] ?? "var(--dim)";
              const st = statusOf(p.risk_label);
              return (
                <tr
                  key={p.player_id}
                  role="link"
                  tabIndex={0}
                  onClick={() => router.push(`/players/${p.player_id}`)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); router.push(`/players/${p.player_id}`); } }}
                  title={`${p.player_name} — oyuncu profili & özellikleri`}
                  style={{ cursor: "pointer" }}
                >
                  <td className="pnum c">{i + 1}</td>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                      <PlayerAvatar name={p.player_name} position={POS_BY_ID[p.player_id]} size={22} />
                      <span className="nm">{p.player_name}</span>
                      <span className="nat">#{p.player_id}</span>
                    </span>
                  </td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{p.test_count}</td>
                  <td className="c"><span className="cond"><i style={{ width: `${cond}%`, background: condColor(cond) }} /></span></td>
                  <td className="c" style={{ color: "var(--dim)", fontFamily: "JetBrains Mono", fontSize: "11px" }}>{p.latest_test_date ?? "—"}</td>
                  <td className="c"><span className="risk" style={{ color: st.v }}><span className="rd" style={{ background: st.v, boxShadow: `0 0 7px ${st.v}` }} />{st.txt}</span></td>
                  <td className="r" style={{ color: rv }}>{Math.round(p.risk_score * 100)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {!DEMO_MODE && smSquad && smSquad.length > 0 && (
        <>
          <div className="st">
            <h2>Sezon Kadrosu</h2>
            <span className="ep">GET /sm/squad · {smSquad.length} oyuncu · CANLI</span>
          </div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th className="c">#</th>
                <th>Oyuncu</th>
                <th className="c">Poz</th>
                <th className="c">Yaş</th>
                <th>Uyruk</th>
                <th className="c">Maç</th>
                <th className="c">Dk</th>
                <th className="c">Gol</th>
                <th className="c">Asist</th>
                <th className="r">Sarı</th>
              </tr></thead>
              <tbody>
                {[...smSquad]
                  .sort((a, b) => (b.season.minutes ?? 0) - (a.season.minutes ?? 0))
                  .map((m) => (
                    <tr key={m.player_external_id}>
                      <td className="pnum c">{m.jersey ?? "—"}</td>
                      <td>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                          <SquadPhoto m={m} />
                          <span className="nm">{m.name}</span>
                          {m.captain && <span className="pos" title="Kaptan" style={{ color: "var(--accent)" }}>C</span>}
                        </span>
                      </td>
                      <td className="c" style={{ color: "var(--muted)", fontSize: 11.5 }}>{m.position ? (SM_POS[m.position]?.label ?? m.position) : "—"}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{smAge(m.birth_date) ?? "—"}</td>
                      <td style={{ color: "var(--muted)", fontSize: 11.5 }}>{m.nationality ?? "—"}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono" }}>{m.season.appearances ?? 0}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{m.season.minutes ?? 0}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: (m.season.goals ?? 0) > 0 ? "var(--low)" : "var(--dim)" }}>{m.season.goals ?? 0}</td>
                      <td className="c" style={{ fontFamily: "JetBrains Mono", color: (m.season.assists ?? 0) > 0 ? "var(--accent)" : "var(--dim)" }}>{m.season.assists ?? 0}</td>
                      <td className="r" style={{ fontFamily: "JetBrains Mono", color: (m.season.yellow_cards ?? 0) >= 4 ? "var(--mid)" : "var(--dim)" }}>{m.season.yellow_cards ?? 0}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 6 }}>
            Sezon toplamları Sportmonks'tan canlı; fotoğraflar kendi sunucumuz üzerinden (self-host proxy) gelir.
          </div>
        </>
      )}

      {DEMO_MODE && (
        <>
          <div className="st"><h2>Kadro Derinliği</h2><span className="ep">pozisyon başına derinlik + yaşlanma riski</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}>
            {SQUAD_DEPTH.map((d) => {
              const s = DEPTH_STATUS_VAR[d.status];
              const barPct = Math.min(100, (d.count / Math.max(d.min, d.count)) * 100);
              return (
                <div className="rc" key={d.pos} style={{ margin: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: 13 }}>{d.label}</span>
                    <span className="risk" style={{ color: s.v, padding: "2px 9px", fontSize: 10.5 }}>
                      <span className="rd" style={{ background: s.v }} />{s.txt}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 6 }}>
                    <span style={{ fontSize: 24, fontWeight: 800, fontFamily: "JetBrains Mono", color: s.v }}>{d.count}</span>
                    <span style={{ fontSize: 12, color: "var(--dim)" }}>/ {d.min} ideal</span>
                  </div>
                  <div className="mbar" style={{ marginBottom: 8 }}><i style={{ width: `${barPct}%`, background: s.v }} /></div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: "var(--muted)" }}>
                    <span>ort. yaş <b style={{ color: "var(--ink)", fontFamily: "JetBrains Mono" }}>{d.avgAge ?? "—"}</b></span>
                    {d.agingRisk
                      ? <span style={{ color: "var(--high)" }}>⚠ yaşlanma riski ({d.aging})</span>
                      : <span style={{ color: "var(--dim)" }}>{d.aging} oyuncu 31+</span>}
                  </div>
                </div>
              );
            })}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 8 }}>
            Eşikler: Kaleci 2 · Defans 6 · Orta Saha 5 · Forvet 4 ideal derinlik; yaşlanma riski = pozisyonun yarısı+ 31 yaş üstü ve derinlik fazla değil.
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
