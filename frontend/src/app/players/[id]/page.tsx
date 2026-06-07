"use client";

/**
 * Oyuncu Profili — rol tipolojisi + fiziksel risk + tıbbi + benzer + yük riski.
 * ConsoleShell çatısında.
 * Backend: /admin/scout/player-role/{id}, /admin/scout/similar/{id},
 *   /physical-tests/{id}/risk, /players/{id}/rehab/active, /admin/players/{id}/injury-risk.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../../_console/shell";

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
const INJURY_LEVEL: Record<string, { label: string; v: string }> = {
  low: { label: "Düşük", v: "var(--low)" },
  moderate: { label: "Orta", v: "var(--mid)" },
  high: { label: "Yüksek", v: "var(--high)" },
  severe: { label: "Çok Yüksek", v: "var(--crit)" },
};
const ACWR_FLAG: Record<string, string> = { safe: "Güvenli bölge", undertrained: "Az yüklenme", danger: "Tehlikeli bölge", unknown: "Veri yetersiz" };
const STATUS_LABEL: Record<string, string> = { active: "Sakat", recovering: "İyileşiyor", cleared: "Hazır" };

export default function PlayerProfileConsolePage() {
  const params = useParams();
  const id = String(params?.id ?? "");

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
          <h3>Rol & Profil <span className="tiny">player-role</span></h3>
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
