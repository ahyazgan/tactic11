"use client";

/**
 * Genel Bakış — Teknik Ekip Konsolu. ConsoleShell çatısını kullanır.
 * KPI şeridi + yük-riski tablosu + sağ kolon (sıradaki maç / uyarılar / görevler).
 * Gerçek veri: GET /physical-tests/players.
 */

import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoPlayerRows, demoNextMatch } from "@/lib/demo-data";
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

function condColor(v: number): string {
  return v >= 85 ? "var(--low)" : v >= 72 ? "var(--mid)" : "var(--high)";
}

export default function OverviewConsolePage() {
  const { data, error, isLoading } = useSWR<PlayerRow[]>(
    DEMO_MODE ? null : "/physical-tests/players", apiFetch, {
    shouldRetryOnError: false,
  });
  const players = DEMO_MODE ? (demoPlayerRows as PlayerRow[]) : (data ?? []);
  // Backend bağlı değil / boş → demo şeridi göster.
  const offline = !isLoading && (!!error || players.length === 0);
  const total = players.length;
  const totalTests = players.reduce((a, p) => a + p.test_count, 0);
  const risky = players.filter((p) => p.risk_label === "Yüksek" || p.risk_label === "Kritik").length;
  const ready = players.filter((p) => p.risk_label === "Düşük").length;
  const avgCond = total
    ? Math.round(players.reduce((a, p) => a + (100 - p.risk_score * 100), 0) / total)
    : 0;
  const alerts = players
    .filter((p) => p.risk_label === "Kritik" || p.risk_label === "Yüksek")
    .slice(0, 4);

  const dlow = players.filter((p) => p.risk_label === "Düşük").length;
  const dmid = players.filter((p) => p.risk_label === "Orta").length;
  const dhigh = players.filter((p) => p.risk_label === "Yüksek").length;
  const dcrit = players.filter((p) => p.risk_label === "Kritik").length;
  const segments = [
    { value: dlow, color: "var(--low)" },
    { value: dmid, color: "var(--mid)" },
    { value: dhigh, color: "var(--high)" },
    { value: dcrit, color: "var(--crit)" },
  ];

  const right = (
    <>
      <div className="rc">
        <h3>Kadro Sağlığı <span className="tiny">{total} oyuncu</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut segments={segments} centerLabel={total} centerSub="kadro" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <LegendRow color="var(--low)" label="Düşük" value={dlow} />
            <LegendRow color="var(--mid)" label="Orta" value={dmid} />
            <LegendRow color="var(--high)" label="Yüksek" value={dhigh} />
            <LegendRow color="var(--crit)" label="Kritik" value={dcrit} />
          </div>
        </div>
      </div>

      <div className="rc">
        <h3>Sıradaki Maç <span className="tiny">{DEMO_MODE ? `${demoNextMatch.date} · ${demoNextMatch.kickoff}` : "— · —"}</span></h3>
        <div className="nm-vs"><span className="t">{DEMO_MODE ? "FK Demo" : "BJK"}</span><span className="x">vs</span><span className="t away">{DEMO_MODE ? demoNextMatch.away : "—"}</span></div>
        <div className="nm-when">{DEMO_MODE ? demoNextMatch.competition : "Maç verisi için Maçlar sekmesi"}</div>
        <div className="probbar">
          <i style={{ width: `${DEMO_MODE ? Math.round(demoNextMatch.win * 100) : 34}%`, background: "var(--low)" }} />
          <i style={{ width: `${DEMO_MODE ? Math.round(demoNextMatch.draw * 100) : 33}%`, background: "var(--dim)" }} />
          <i style={{ width: `${DEMO_MODE ? Math.round(demoNextMatch.loss * 100) : 33}%`, background: "var(--high)" }} />
        </div>
        <div className="probleg">
          <div className="pi"><div className="pv" style={{ color: "var(--low)" }}>{DEMO_MODE ? `%${Math.round(demoNextMatch.win * 100)}` : "—"}</div><div className="pl">Galibiyet</div></div>
          <div className="pi"><div className="pv" style={{ color: "var(--muted)" }}>{DEMO_MODE ? `%${Math.round(demoNextMatch.draw * 100)}` : "—"}</div><div className="pl">Berabere</div></div>
          <div className="pi"><div className="pv" style={{ color: "var(--high)" }}>{DEMO_MODE ? `%${Math.round(demoNextMatch.loss * 100)}` : "—"}</div><div className="pl">Mağlubiyet</div></div>
        </div>
      </div>

      <div className="rc">
        <h3>Uyarılar <span className="tiny">{alerts.length} aktif</span></h3>
        {alerts.length === 0 && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Kritik/yüksek riskli oyuncu yok.</div>}
        {alerts.map((a) => {
          const rv = RISK_VAR[a.risk_label] ?? "var(--dim)";
          return (
            <div className="alrt" key={a.player_id}>
              <span className="ai" style={{ background: rv }} />
              <div className="am"><b>{a.player_name}</b> {a.risk_label.toLowerCase()} yük riski.
                <span className="tm">risk {Math.round(a.risk_score * 100)}/100</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="rc">
        <h3>Görevler <span className="tiny">{risky ? `0/${risky + 1}` : "0/0"}</span></h3>
        {risky > 0 ? (
          <>
            <div className="task"><span className="cb" /><span className="tt">{risky} riskli oyuncu için kadro kararı</span></div>
            <div className="task"><span className="cb" /><span className="tt">Re-test planı (yüksek risk)</span></div>
          </>
        ) : (
          <div style={{ fontSize: "12px", color: "var(--dim)" }}>Bekleyen görev yok.</div>
        )}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/overview"
      title="Genel Bakış"
      sub="Teknik ekip kontrol paneli"
      desc="Kadro durumu ve yük-riski öncelikleri aşağıda. Sayılar canlı veriden."
      navBadge={risky}
      right={right}
    >
      {offline && (
        <div className="demobar">
          <span style={{ fontSize: 15 }}>🔌</span>
          <span><b>Demo modu</b> — veri sunucusu (backend) bağlı değil, sayılar 0 görünüyor. Bağlanınca tüm ekranlar gerçek veriyle dolar.</span>
          <a className="db-cta" href="https://github.com/ahyazgan/manager2#-canlıya-alma-3-dakika" target="_blank" rel="noreferrer">Nasıl bağlanır?</a>
        </div>
      )}

      <div className="kpis">
        {isLoading ? (
          [0, 1, 2, 3, 4].map((i) => (
            <div className="kpi" key={i}>
              <div className="kl"><span className="sk sk-line" style={{ width: 56 }} /></div>
              <div className="kn"><span className="sk sk-kn" /></div>
              <div className="kd"><span className="sk sk-line" style={{ width: 84 }} /></div>
            </div>
          ))
        ) : (
          <>
            <div className="kpi"><div className="kl">Kadro</div><div className="kn">{total}</div><div className="kd"><span className="u">{ready} hazır</span> · {risky} riskli</div></div>
            <div className="kpi"><div className="kl">Toplam Test</div><div className="kn">{totalTests}</div><div className="kd">{total} oyuncu</div></div>
            <div className="kpi"><div className="kl">Ort. Kondisyon</div><div className="kn">{avgCond}<span className="pct">%</span></div><div className="kd">risk skorundan</div></div>
            <div className="kpi"><div className="kl">Kritik/Yüksek</div><div className="kn" style={{ color: risky ? "var(--high)" : "var(--low)" }}>{risky}</div><div className="kd">acil takip</div></div>
            <div className="kpi"><div className="kl">Hazır</div><div className="kn" style={{ color: "var(--low)" }}>{ready}</div><div className="kd">düşük risk</div></div>
          </>
        )}
      </div>

      <div className="st"><h2>Yük Riski — Kadro Durumu</h2><span className="ep">GET /physical-tests/players</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th><th>Oyuncu</th><th className="c">Test</th>
            <th className="c">Kondisyon</th><th className="c">Son Test</th><th className="c">Risk</th><th className="r">Skor</th>
          </tr></thead>
          <tbody>
            {isLoading && [0, 1, 2, 3, 4, 5].map((i) => (
              <tr key={`sk${i}`}>
                <td className="c"><span className="sk sk-line" style={{ width: 16, margin: "0 auto" }} /></td>
                <td><span className="sk sk-line" style={{ width: "60%" }} /></td>
                <td className="c"><span className="sk sk-line" style={{ width: 24, margin: "0 auto" }} /></td>
                <td className="c"><span className="sk sk-line" style={{ width: 56, margin: "0 auto" }} /></td>
                <td className="c"><span className="sk sk-line" style={{ width: 60, margin: "0 auto" }} /></td>
                <td className="c"><span className="sk sk-line" style={{ width: 50, margin: "0 auto" }} /></td>
                <td className="r"><span className="sk sk-line" style={{ width: 28, marginLeft: "auto" }} /></td>
              </tr>
            ))}
            {!isLoading && players.length === 0 && (
              <tr><td colSpan={7}>
                <div className="empty">
                  <div className="ei">📋</div>
                  <div className="et">Henüz test verisi yok</div>
                  <div className="es">Backend bağlanınca kadro yük-riski burada listelenir.</div>
                </div>
              </td></tr>
            )}
            {players.map((p, i) => {
              const cond = Math.round(100 - p.risk_score * 100);
              const rv = RISK_VAR[p.risk_label] ?? "var(--dim)";
              return (
                <tr key={p.player_id}>
                  <td className="pnum c">{i + 1}</td>
                  <td><span className="nm">{p.player_name}</span> <span className="nat">#{p.player_id}</span></td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{p.test_count}</td>
                  <td className="c"><span className="cond"><i style={{ width: `${cond}%`, background: condColor(cond) }} /></span></td>
                  <td className="c" style={{ color: "var(--dim)", fontFamily: "JetBrains Mono", fontSize: "11px" }}>{p.latest_test_date ?? "—"}</td>
                  <td className="c"><span className="risk" style={{ color: rv }}><span className="rd" style={{ background: rv, boxShadow: `0 0 7px ${rv}` }} />{p.risk_label}</span></td>
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
