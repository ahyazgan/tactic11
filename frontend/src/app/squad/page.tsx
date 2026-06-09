"use client";

/**
 * Kadro — Teknik Ekip Konsolu. ConsoleShell çatısını kullanır.
 * Oyuncu listesi (kondisyon + risk) + durum filtresi + sağ kolonda
 * durum dağılımı ve en riskli oyuncular. Gerçek veri: GET /physical-tests/players.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoPlayerRows } from "@/lib/demo-data";
import { useSort, SortableTh, sortCompare } from "@/lib/sortable";
import { ConsoleShell } from "../_console/shell";
import { RiskDonut, LegendRow } from "../_console/viz";

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
  // Demo modunda canlı API'ye dokunma; dolu mock kadroyu göster (boş tablo olmaz).
  const { data } = useSWR<PlayerRow[]>(DEMO_MODE ? null : "/physical-tests/players", apiFetch, {
    shouldRetryOnError: false,
  });
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
            <div className="alrt" key={p.player_id}>
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
                <tr key={p.player_id}>
                  <td className="pnum c">{i + 1}</td>
                  <td><span className="nm">{p.player_name}</span> <span className="nat">#{p.player_id}</span></td>
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
    </ConsoleShell>
  );
}
