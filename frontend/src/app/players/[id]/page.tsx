"use client";

/**
 * Oyuncu Profili — rol/profil + fiziksel risk + tıbbi/rehab + yük riski + test geçmişi.
 * ConsoleShell çatısında.
 *
 * DEMO_MODE (varsayılan): canlı API'ye hiç dokunmaz; URL [id] → demoSquad lookup
 * (örn id=8 Caner Öztürk #10 kritik) ile zengin, inandırıcı Türkçe profil gösterir.
 * Risk/öneri/flag'ler demoRiskFor()'dan, test trendi demoHistoryFor()'dan gelir.
 * DEMO kapalı: eski canlı-API (player-role / similar / physical-tests/risk /
 * rehab/active / injury-risk) davranışına döner.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  demoSquad,
  demoRiskFor,
  demoHistoryFor,
  type SquadPlayer,
  type RiskLabel,
} from "@/lib/demo-data";
import { ConsoleShell } from "../../_console/shell";
import { Gauge } from "../../_console/viz";

const ROLE_LABEL: Record<string, string> = {
  deep_playmaker: "Derin Oyun Kurucu (Regista)",
  box_to_box: "Box-to-Box Orta Saha",
  defensive_mid: "Ön Libero",
  inside_forward: "İçe Kat Eden Forvet",
  wide_forward: "Kanat Forvet",
  target_man: "Hedef Forvet",
  ball_playing_cb: "Topla Oynayan Stoper",
  traditional_cb: "Klasik Stoper",
  goalkeeper: "Kaleci",
  unknown: "Bilinmiyor",
};

interface RoleResp { value: { primary_role: string; confidence: number; secondary_role: string } }
interface SimResp { value: { top_matches: { player_external_id: number; similarity: number }[] } }
interface RiskResp { risk_label: string; risk_score: number; summary: string; flags: { protocol: string }[] }
interface Rehab { injury_type: string; status: string; expected_return: string | null }
interface InjuryResp {
  value: {
    risk_score: number; risk_level: string; acwr: number | null; acwr_flag: string;
    load_factor: number; age_factor: number; frequency_factor: number; recommendation: string;
  };
}

const RISK_VAR: Record<string, string> = { Düşük: "var(--low)", Orta: "var(--mid)", Yüksek: "var(--high)", Kritik: "var(--crit)" };
const RISK_PILL: Record<string, string> = { Düşük: "risk-low", Orta: "risk-mid", Yüksek: "risk-high", Kritik: "risk-crit" };
const INJURY_LEVEL: Record<string, { label: string; v: string }> = {
  low: { label: "Düşük", v: "var(--low)" },
  moderate: { label: "Orta", v: "var(--mid)" },
  high: { label: "Yüksek", v: "var(--high)" },
  severe: { label: "Çok Yüksek", v: "var(--crit)" },
};
const ACWR_FLAG: Record<string, string> = { safe: "Güvenli bölge", undertrained: "Az yüklenme", danger: "Tehlikeli bölge", unknown: "Veri yetersiz" };
const STATUS_LABEL: Record<string, string> = { active: "Sakat", recovering: "İyileşiyor", cleared: "Hazır" };

// --- Demo türetmeleri (sadece bu sayfada, demo-data.ts'i değiştirmeden) ---

// pos_detail → okunur rol + güven (kondisyona göre hafif oynar)
function demoRole(p: SquadPlayer): { primary: string; secondary: string; confidence: number } {
  const map: Record<string, [string, string]> = {
    "Kaleci": ["Modern Kaleci (ayakla oyun kuran)", "Klasik Kaleci"],
    "Stoper": ["Topla Oynayan Stoper", "Klasik Stoper"],
    "Sağ Bek": ["Hücumcu Sağ Bek (kanat bek)", "Geleneksel Sağ Bek"],
    "Sol Bek": ["Hücumcu Sol Bek (kanat bek)", "Geleneksel Sol Bek"],
    "Ön Libero": ["Ön Libero (yıkıcı 6)", "Derin Oyun Kurucu (Regista)"],
    "Merkez OS": ["Box-to-Box Orta Saha", "İleri Uçlu Orta Saha"],
    "10 Numara": ["İleri Uçlu Oyun Kurucu (10)", "Yarı-alan Yaratıcısı"],
    "Sol Kanat": ["İçe Kat Eden Forvet (sol)", "Klasik Sol Açık"],
    "Sağ Kanat": ["İçe Kat Eden Forvet (sağ)", "Klasik Sağ Açık"],
    "Santrfor": ["Hedef Forvet (post oyunu)", "Derinlik Forveti"],
  };
  const [primary, secondary] = map[p.pos_detail] ?? ["Çok Yönlü Oyuncu", "—"];
  const conf = Math.round(72 + (p.condition - 70) * 0.4); // 60..90 bandı
  return { primary, secondary, confidence: Math.max(58, Math.min(94, conf)) };
}

// Risk etiketinden ACWR + yük faktörleri türet (gerçekçi, deterministik)
function demoLoad(p: SquadPlayer): {
  acwr: number; acwrFlag: string; load: number; age: number; freq: number;
  riskLevel: keyof typeof INJURY_LEVEL; recommendation: string;
} {
  const byLabel: Record<RiskLabel, { acwr: number; flag: string; level: keyof typeof INJURY_LEVEL }> = {
    "Kritik": { acwr: 1.62, flag: "danger", level: "severe" },
    "Yüksek": { acwr: 1.41, flag: "danger", level: "high" },
    "Orta": { acwr: 1.18, flag: "safe", level: "moderate" },
    "Düşük": { acwr: 0.97, flag: "safe", level: "low" },
  };
  const b = byLabel[p.risk_label];
  const load = Math.round(p.risk_score * 0.85 + (100 - p.condition) * 0.25);
  const age = Math.round(Math.max(0, (p.age - 24)) * 6 + 14);
  const freq = Math.round(p.risk_score * 0.6 + 18);
  const recByLevel: Record<keyof typeof INJURY_LEVEL, string> = {
    severe: "Akut yük zirvede — bu hafta yüksek şiddetli koşuyu %40 azalt, maçta 60. dk sonrası değişiklik planla.",
    high: "Yük artışı dik — antrenmanda sprint hacmini sınırla, maç-içi dakika sınırı düşün.",
    moderate: "İzlemede — yükü kademeli artır, bir sonraki test penceresinde yeniden değerlendir.",
    low: "Tam maç yüküne hazır — mevcut programa devam, rutin haftalık takip yeterli.",
  };
  return {
    acwr: b.acwr, acwrFlag: b.flag, load, age, freq, riskLevel: b.level,
    recommendation: recByLevel[b.level],
  };
}

// Rehab/tıbbi durum: kritik/yüksek riskli oyunculara aktif protokol ver
function demoRehab(p: SquadPlayer): Rehab[] {
  if (p.risk_label === "Kritik") {
    return [{ injury_type: "Arka adale (hamstring) zorlanması — Grade I", status: "recovering", expected_return: "Belirsiz · maç-içi izleniyor" }];
  }
  if (p.risk_label === "Yüksek") {
    return [{ injury_type: "Yük kaynaklı aşırı kullanım izlemesi", status: "recovering", expected_return: "Bu hafta sonu" }];
  }
  return [];
}

// Benzer oyuncular: aynı pozisyondan, risk skoru yakın olanlar
function demoSimilar(p: SquadPlayer): { player_external_id: number; name: string; similarity: number }[] {
  return demoSquad
    .filter((s) => s.player_id !== p.player_id && s.position === p.position)
    .map((s) => {
      const posMatch = s.pos_detail === p.pos_detail ? 0.12 : 0;
      const ageGap = Math.abs(s.age - p.age) / 40;
      const condGap = Math.abs(s.condition - p.condition) / 100;
      const sim = 0.74 + posMatch - ageGap * 0.35 - condGap * 0.3;
      return { player_external_id: s.player_id, name: s.player_name, similarity: Math.max(0.55, Math.min(0.96, sim)) };
    })
    .sort((a, b) => b.similarity - a.similarity)
    .slice(0, 6);
}

// Sprint-30m test serisi → mini trend (5 ölçüm). Düşük=iyi.
function sprintSeries(playerId: number): { date: string; value: number }[] {
  return demoHistoryFor(playerId)
    .filter((t) => t.protocol === "sprint_30m")
    .map((t) => ({ date: t.test_date.slice(5), value: t.value }));
}

// CMJ (dikey sıçrama) serisi → mini trend. Yüksek=iyi.
function cmjSeries(playerId: number): { date: string; value: number }[] {
  return demoHistoryFor(playerId)
    .filter((t) => t.protocol === "cmj")
    .map((t) => ({ date: t.test_date.slice(5), value: t.value }));
}

/** Mini inline SVG çizgi grafiği (5 nokta). better="low" ise düşüş yeşil. */
function Spark({ points, better, unit }: { points: { date: string; value: number }[]; better: "low" | "high"; unit: string }) {
  if (points.length === 0) return null;
  const w = 132, h = 40, pad = 4;
  const vals = points.map((p) => p.value);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (points.length - 1)) * (w - pad * 2);
  const y = (v: number) => pad + (1 - (v - min) / span) * (h - pad * 2);
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");
  const first = points[0].value, last = points[points.length - 1].value;
  const improving = better === "low" ? last < first : last > first;
  const stroke = improving ? "var(--low)" : "var(--high)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ flexShrink: 0 }}>
        <path d={d} fill="none" stroke={stroke} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        {points.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.value)} r={i === points.length - 1 ? 3 : 1.8} fill={stroke} />
        ))}
      </svg>
      <div style={{ fontFamily: "JetBrains Mono", fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap" }}>
        {last.toFixed(2)} {unit}
        <span style={{ color: stroke, marginLeft: 6 }}>{improving ? "▲ iyi" : "▼ düşüş"}</span>
      </div>
    </div>
  );
}

export default function PlayerProfileConsolePage() {
  const params = useParams();
  const id = String(params?.id ?? "");

  if (DEMO_MODE) {
    const player = demoSquad.find((p) => String(p.player_id) === id) ?? demoSquad[0];
    return <PlayerProfileDemo player={player} />;
  }
  return <PlayerProfileLive id={id} />;
}

/* ────────────────────────────────────────────────────────────
   DEMO İÇERİĞİ — backend'siz, dolu profil
──────────────────────────────────────────────────────────── */
function PlayerProfileDemo({ player }: { player: SquadPlayer }) {
  const role = demoRole(player);
  const risk = demoRiskFor(player.player_id);
  const load = demoLoad(player);
  const rehabs = demoRehab(player);
  const similar = demoSimilar(player);
  const sprint = sprintSeries(player.player_id);
  const cmj = cmjSeries(player.player_id);

  const riskScore100 = Math.round(risk.risk_score * 100);
  const riskVar = RISK_VAR[risk.risk_label] ?? "var(--muted)";
  const lvl = INJURY_LEVEL[load.riskLevel];

  const right = (
    <>
      <div className="rc">
        <h3>Tıbbi Durum <span className="tiny">rehab</span></h3>
        {rehabs.length === 0 && (
          <div className="risk risk-low" style={{ fontSize: 12 }}>
            <span className="rd" style={{ background: "var(--low)" }} />Aktif sakatlık yok — hazır
          </div>
        )}
        {rehabs.map((rh, i) => (
          <div className="alrt" key={i} style={{ alignItems: "flex-start" }}>
            <span className="ai" style={{ background: riskVar, marginTop: 4 }} />
            <div className="am">
              <b>{rh.injury_type}</b>
              <span className="tm">{STATUS_LABEL[rh.status] ?? rh.status} · dönüş: {rh.expected_return ?? "—"}</span>
            </div>
          </div>
        ))}
        {player.risk_label === "Kritik" && (
          <div className="stat" style={{ marginTop: 6 }}>
            <span style={{ fontSize: 11.5, color: "var(--muted)" }}>Son sinyal</span>
            <span className="sv" style={{ fontSize: 11.5, color: "var(--crit)" }}>52&apos; arka adale</span>
          </div>
        )}
      </div>

      <div className="rc">
        <h3>Kondisyon <span className="tiny">hazırlık</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Gauge value={player.condition} color={player.condition >= 85 ? "var(--low)" : player.condition >= 72 ? "var(--mid)" : "var(--high)"} label="kondisyon" />
          <div style={{ flex: 1, minWidth: 0, fontSize: 12, color: "var(--muted)" }}>
            {player.condition >= 85
              ? "Tam maç yüküne hazır. Taze."
              : player.condition >= 72
              ? "İzlemede — dakika yönetimi öneriliyor."
              : "Yorgunluk bandında — rotasyon adayı."}
          </div>
        </div>
      </div>

      <div className="rc">
        <h3>Benzer Oyuncular <span className="tiny">scout/similar</span></h3>
        {similar.length === 0 && <div style={{ fontSize: 12, color: "var(--dim)" }}>Aynı mevkide oyuncu yok.</div>}
        {similar.map((m) => (
          <div className="stat" key={m.player_external_id}>
            <Link href={`/players/${m.player_external_id}`} style={{ color: "var(--accent)", textDecoration: "none", fontSize: 12, fontWeight: 600 }}>
              {m.name} <span style={{ color: "var(--dim)", fontWeight: 400 }}>#{m.player_external_id}</span>
            </Link>
            <span className="sv">{(m.similarity * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/squad"
      title={`${player.player_name}`}
      sub={`#${player.shirt} · ${player.pos_detail}`}
      desc={`${role.primary} · ${player.age} yaş · FK Demo. Rol/profil, fiziksel risk, tıbbi durum, yük riski ve test geçmişi tek bakışta.`}
      right={right}
    >
      {/* KPI şeridi */}
      <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
        <div className="kpi">
          <div className="kl">Pozisyon</div>
          <div className="kn" style={{ fontSize: 20 }}>{player.position}</div>
          <div className="kd">{player.pos_detail} · #{player.shirt}</div>
        </div>
        <div className="kpi">
          <div className="kl">Kondisyon</div>
          <div className="kn" style={{ color: player.condition >= 85 ? "var(--low)" : player.condition >= 72 ? "var(--mid)" : "var(--high)" }}>{player.condition}<span className="pct">%</span></div>
          <div className="kd">hazırlık</div>
        </div>
        <div className="kpi">
          <div className="kl">Sakatlık Riski</div>
          <div className="kn" style={{ color: riskVar }}>{riskScore100}<span className="pct">/100</span></div>
          <div className="kd" style={{ color: riskVar }}>{risk.risk_label.toLowerCase()}</div>
        </div>
        <div className="kpi">
          <div className="kl">ACWR</div>
          <div className="kn" style={{ color: lvl.v }}>{load.acwr.toFixed(2)}</div>
          <div className="kd">{ACWR_FLAG[load.acwrFlag]}</div>
        </div>
        <div className="kpi">
          <div className="kl">Yaş</div>
          <div className="kn">{player.age}</div>
          <div className="kd">{player.age >= 30 ? "tecrübeli" : player.age <= 22 ? "genç" : "zirve yaş"}</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Rol & Profil */}
        <div className="rc" style={{ margin: 0 }}>
          <h3>Rol &amp; Profil <span className="tiny">player-role</span></h3>
          <div style={{ fontSize: 18, fontWeight: 800, color: "var(--ink)" }}>{role.primary}</div>
          <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "JetBrains Mono", marginTop: 3 }}>güven %{role.confidence}</div>
          <div className="mbar" style={{ marginTop: 6 }}><i style={{ width: `${role.confidence}%`, background: "var(--accent)" }} /></div>
          {role.secondary && role.secondary !== "—" && (
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>İkincil rol: <b style={{ color: "var(--ink)" }}>{role.secondary}</b></div>
          )}
        </div>

        {/* Fiziksel Risk */}
        <div className="rc" style={{ margin: 0 }}>
          <h3>Fiziksel Risk <span className="tiny">physical-tests/risk</span></h3>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className={`risk ${RISK_PILL[risk.risk_label] ?? ""}`} style={{ fontSize: 12.5 }}>
              <span className="rd" style={{ background: riskVar }} />{risk.risk_label}
            </span>
            <span style={{ fontFamily: "JetBrains Mono", fontSize: 13, fontWeight: 700, color: riskVar }}>{riskScore100}/100</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>{risk.summary}</div>
          {risk.flags.length > 0 && (
            <div style={{ marginTop: 8 }}>
              {risk.flags.map((f, i) => (
                <div key={i} className="stat" style={{ borderColor: "var(--border)" }}>
                  <span style={{ fontSize: 11.5, color: "var(--muted)" }}>{f.message}</span>
                  <span className="sv" style={{ fontSize: 11, color: "var(--high)" }}>{f.value} {f.unit}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Test Geçmişi & Trend */}
        <div className="rc" style={{ margin: 0, gridColumn: "1 / -1" }}>
          <h3>Test Geçmişi &amp; Trend <span className="tiny">son 5 ölçüm</span></h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
            <div>
              <div style={{ fontSize: 11.5, color: "var(--dim)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.4 }}>Sprint 30m (düşük = iyi)</div>
              <Spark points={sprint} better="low" unit="sn" />
            </div>
            <div>
              <div style={{ fontSize: 11.5, color: "var(--dim)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.4 }}>Dikey Sıçrama / CMJ (yüksek = iyi)</div>
              <Spark points={cmj} better="high" unit="cm" />
            </div>
          </div>
          <div className="tbl" style={{ marginTop: 12 }}>
            <table>
              <thead><tr>
                <th>Tarih</th>
                <th className="r">Sprint 30m</th>
                <th className="r">CMJ</th>
                <th className="c">Durum</th>
              </tr></thead>
              <tbody>
                {sprint.map((s, i) => {
                  const c = cmj[i];
                  const sprintBad = i > 0 && s.value > sprint[i - 1].value;
                  return (
                    <tr key={i}>
                      <td style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11.5 }}>{s.date}</td>
                      <td className="r" style={{ color: sprintBad ? "var(--high)" : "var(--ink)" }}>{s.value.toFixed(2)} sn</td>
                      <td className="r">{c ? `${c.value.toFixed(1)} cm` : "—"}</td>
                      <td className="c">
                        <span className={`risk ${sprintBad ? "risk-high" : "risk-low"}`} style={{ fontSize: 11 }}>
                          <span className="rd" style={{ background: sprintBad ? "var(--high)" : "var(--low)" }} />
                          {sprintBad ? "geriledi" : "stabil"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Sakatlık Riski (Yük) */}
        <div className="rc" style={{ margin: 0, gridColumn: "1 / -1" }}>
          <h3>Sakatlık Riski (Yük) <span className="tiny">injury-risk</span></h3>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <span style={{ fontSize: 24, fontWeight: 800, fontFamily: "JetBrains Mono", color: lvl.v }}>{Math.round(load.load * 0.5 + riskScore100 * 0.5)}<span style={{ fontSize: 12, color: "var(--dim)" }}>/100</span></span>
            <span style={{ fontSize: 13, fontWeight: 700, color: lvl.v }}>{lvl.label}</span>
            <span style={{ fontSize: 11, fontFamily: "JetBrains Mono", color: "var(--muted)" }}>ACWR {load.acwr.toFixed(2)} · {ACWR_FLAG[load.acwrFlag]}</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginTop: 12 }}>
            {([
              { label: "Yük faktörü", v: load.load },
              { label: "Yaş faktörü", v: load.age },
              { label: "Sıklık faktörü", v: load.freq },
            ] as const).map((f) => (
              <div key={f.label}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: "var(--muted)", marginBottom: 2 }}>
                  <span>{f.label}</span><span style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>{f.v}</span>
                </div>
                <div className="mbar"><i style={{ width: `${Math.min(100, f.v)}%`, background: f.v >= 70 ? "var(--high)" : f.v >= 45 ? "var(--mid)" : "var(--low)" }} /></div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 12.5, color: "var(--ink)", marginTop: 10, lineHeight: 1.5 }}>{load.recommendation}</div>
        </div>

        {/* Öneriler */}
        <div className="rc" style={{ margin: 0, gridColumn: "1 / -1" }}>
          <h3>Teknik Ekip Önerileri <span className="tiny">{risk.recommendations.length} madde</span></h3>
          {risk.recommendations.length === 0 && <div style={{ fontSize: 12, color: "var(--dim)" }}>Özel öneri yok — rutin takip yeterli.</div>}
          {risk.recommendations.map((rec, i) => (
            <div className="task" key={i}>
              <span className="cb" />
              <span className="tt">{rec}</span>
            </div>
          ))}
        </div>
      </div>
    </ConsoleShell>
  );
}

/* ────────────────────────────────────────────────────────────
   CANLI İÇERİK — DEMO_MODE kapalıyken (eski API davranışı)
──────────────────────────────────────────────────────────── */
function PlayerProfileLive({ id }: { id: string }) {
  const role = useSWR<RoleResp>(id ? `/admin/scout/player-role/${id}` : null, apiFetch, { shouldRetryOnError: false });
  const sim = useSWR<SimResp>(id ? `/admin/scout/similar/${id}` : null, apiFetch, { shouldRetryOnError: false });
  const risk = useSWR<RiskResp>(id ? `/physical-tests/${id}/risk` : null, apiFetch, { shouldRetryOnError: false });
  const rehab = useSWR<Rehab[]>(id ? `/players/${id}/rehab/active` : null, apiFetch, { shouldRetryOnError: false });
  const injury = useSWR<InjuryResp>(id ? `/admin/players/${id}/injury-risk` : null, apiFetch, { shouldRetryOnError: false });

  const r = role.data?.value;
  const inj = injury.data?.value;
  const matches = sim.data?.value.top_matches ?? [];
  const rehabs = rehab.data ?? [];

  const right = (
    <>
      <div className="rc">
        <h3>Tıbbi Durum <span className="tiny">rehab/active</span></h3>
        {rehab.isLoading && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yükleniyor…</div>}
        {rehabs.length === 0 && !rehab.isLoading && <div style={{ fontSize: "12px", color: "var(--low)" }}>Aktif sakatlık yok — hazır.</div>}
        {rehabs.map((rh, i) => (
          <div className="stat" key={i}>
            <span style={{ fontSize: 12 }}>{rh.injury_type}</span>
            <span className="sv" style={{ fontFamily: "inherit", fontSize: 11.5 }}>{STATUS_LABEL[rh.status] ?? rh.status} · {rh.expected_return ?? "—"}</span>
          </div>
        ))}
      </div>
      <div className="rc">
        <h3>Benzer Oyuncular <span className="tiny">scout/similar</span></h3>
        {sim.isLoading && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yükleniyor…</div>}
        {matches.length === 0 && !sim.isLoading && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Benzer oyuncu bulunamadı.</div>}
        {matches.slice(0, 6).map((m) => (
          <div className="stat" key={m.player_external_id}>
            <Link href={`/players/${m.player_external_id}`} style={{ fontFamily: "JetBrains Mono", color: "var(--low)", textDecoration: "none" }}>#{m.player_external_id}</Link>
            <span className="sv">{(m.similarity * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/squad"
      title={`Oyuncu #${id}`}
      sub="Birleşik profil"
      desc="Rol tipolojisi, fiziksel risk, tıbbi durum ve yük riski tek bakışta."
      right={right}
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {/* Rol & Profil */}
        <div className="rc" style={{ margin: 0 }}>
          <h3>Rol &amp; Profil <span className="tiny">player-role</span></h3>
          {role.isLoading && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yükleniyor…</div>}
          {role.error && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yeterli maç verisi yok.</div>}
          {r && (
            <>
              <div style={{ fontSize: 18, fontWeight: 800, color: "var(--ink)" }}>{ROLE_LABEL[r.primary_role] ?? r.primary_role}</div>
              <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "JetBrains Mono", marginTop: 3 }}>güven {(r.confidence * 100).toFixed(0)}%</div>
              {r.secondary_role && r.secondary_role !== "unknown" && (
                <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 6 }}>İkincil: {ROLE_LABEL[r.secondary_role] ?? r.secondary_role}</div>
              )}
            </>
          )}
        </div>

        {/* Fiziksel Risk */}
        <div className="rc" style={{ margin: 0 }}>
          <h3>Fiziksel Risk <span className="tiny">physical-tests/risk</span></h3>
          {risk.isLoading && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yükleniyor…</div>}
          {risk.error && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Test verisi yok.</div>}
          {risk.data && (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <span style={{ fontSize: 18, fontWeight: 800, color: RISK_VAR[risk.data.risk_label] ?? "var(--muted)" }}>{risk.data.risk_label}</span>
                <span style={{ fontFamily: "JetBrains Mono", fontSize: 12, color: "var(--muted)" }}>{(risk.data.risk_score * 100).toFixed(0)}/100</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 6 }}>{risk.data.summary}</div>
              {risk.data.flags.length > 0 && <div style={{ fontSize: 11, color: "var(--high)", fontFamily: "JetBrains Mono", marginTop: 6 }}>{risk.data.flags.map((f) => f.protocol).join(" · ")}</div>}
            </>
          )}
        </div>

        {/* Sakatlık Riski (Yük) */}
        <div className="rc" style={{ margin: 0, gridColumn: "1 / -1" }}>
          <h3>Sakatlık Riski (Yük) <span className="tiny">injury-risk</span></h3>
          {injury.isLoading && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Yükleniyor…</div>}
          {injury.error && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Maç/yük verisi yok.</div>}
          {inj && (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <span style={{ fontSize: 24, fontWeight: 800, fontFamily: "JetBrains Mono", color: INJURY_LEVEL[inj.risk_level]?.v ?? "var(--muted)" }}>{Math.round(inj.risk_score)}<span style={{ fontSize: 12, color: "var(--dim)" }}>/100</span></span>
                <span style={{ fontSize: 13, fontWeight: 700, color: INJURY_LEVEL[inj.risk_level]?.v ?? "var(--muted)" }}>{INJURY_LEVEL[inj.risk_level]?.label ?? inj.risk_level}</span>
              </div>
              <div style={{ fontSize: 11, fontFamily: "JetBrains Mono", color: "var(--muted)", marginTop: 6 }}>ACWR {inj.acwr !== null ? inj.acwr.toFixed(2) : "—"} · {ACWR_FLAG[inj.acwr_flag] ?? inj.acwr_flag}</div>
              <div style={{ display: "flex", gap: 12, fontSize: 11, fontFamily: "JetBrains Mono", color: "var(--muted)", marginTop: 4 }}>
                <span>yük {Math.round(inj.load_factor)}</span><span>yaş {Math.round(inj.age_factor)}</span><span>sıklık {Math.round(inj.frequency_factor)}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--ink)", marginTop: 8 }}>{inj.recommendation}</div>
            </>
          )}
        </div>
      </div>
    </ConsoleShell>
  );
}
