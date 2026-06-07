"use client";

/**
 * Oyuncu Profili — birleşik görünüm: rol tipolojisi + fiziksel risk + tıbbi
 * (rehab) + benzer oyuncular. Tüm modülleri tek sayfada bağlar.
 *
 * Backend:
 *   GET /admin/scout/player-role/{id}   — rol tipolojisi (engine.player_role)
 *   GET /admin/scout/similar/{id}       — benzer oyuncular
 *   GET /physical-tests/{id}/risk       — yük/fiziksel risk
 *   GET /players/{id}/rehab/active      — aktif sakatlık/rehab
 */

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel } from "@/components/ui";

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

interface RoleResp {
  value: { primary_role: string; confidence: number; secondary_role: string };
}
interface SimResp {
  value: { top_matches: { player_external_id: number; similarity: number }[] };
}
interface RiskResp {
  risk_label: string;
  risk_score: number;
  summary: string;
  flags: { protocol: string }[];
}
interface Rehab {
  injury_type: string;
  status: string;
  expected_return: string | null;
}

const RISK_COLOR: Record<string, string> = {
  Düşük: "text-ok",
  Orta: "text-warn",
  Yüksek: "text-high",
  Kritik: "text-danger",
};
const STATUS_LABEL: Record<string, string> = {
  active: "Sakat",
  recovering: "İyileşiyor",
  cleared: "Hazır",
};

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10px] text-textdim bg-surface2 border border-border rounded px-2 py-0.5">
      {children}
    </span>
  );
}

export default function PlayerProfilePage() {
  const params = useParams();
  const id = String(params?.id ?? "");

  const role = useSWR<RoleResp>(id ? `/admin/scout/player-role/${id}` : null, apiFetch, {
    shouldRetryOnError: false,
  });
  const sim = useSWR<SimResp>(id ? `/admin/scout/similar/${id}` : null, apiFetch, {
    shouldRetryOnError: false,
  });
  const risk = useSWR<RiskResp>(id ? `/physical-tests/${id}/risk` : null, apiFetch, {
    shouldRetryOnError: false,
  });
  const rehab = useSWR<Rehab[]>(id ? `/players/${id}/rehab/active` : null, apiFetch, {
    shouldRetryOnError: false,
  });

  const r = role.data?.value;
  const matches = sim.data?.value.top_matches ?? [];
  const rehabs = rehab.data ?? [];

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">
            Oyuncu Profili <span className="font-mono text-textmut">#{id}</span>
          </h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Rol tipolojisi, fiziksel risk, tıbbi durum ve benzer oyuncular tek bakışta.
          </p>
        </div>
        <Link
          href={`/players/${id}/tactical`}
          className="text-[11px] uppercase px-3 py-1 rounded border border-borderlt text-accent hover:bg-surface2"
        >
          Taktik profil →
        </Link>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <Panel title="Rol & Profil" actions={<Tag>player-role</Tag>}>
          {role.isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
          {role.error && <p className="text-[12px] text-textmut">Yeterli maç verisi yok.</p>}
          {r && (
            <div className="space-y-2">
              <div>
                <div className="text-2xl font-bold text-text">
                  {ROLE_LABEL[r.primary_role] ?? r.primary_role}
                </div>
                <div className="text-[11px] text-textmut font-mono mt-0.5">
                  güven {(r.confidence * 100).toFixed(0)}%
                </div>
              </div>
              {r.secondary_role && r.secondary_role !== "unknown" && (
                <div className="text-[12px] text-textmut">
                  İkincil: {ROLE_LABEL[r.secondary_role] ?? r.secondary_role}
                </div>
              )}
            </div>
          )}
        </Panel>

        <Panel title="Fiziksel Risk" actions={<Tag>physical-tests/risk</Tag>}>
          {risk.isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
          {risk.error && <p className="text-[12px] text-textmut">Test verisi yok.</p>}
          {risk.data && (
            <div className="space-y-2">
              <div className="flex items-baseline gap-3">
                <span className={`text-xl font-bold ${RISK_COLOR[risk.data.risk_label] ?? "text-textmut"}`}>
                  {risk.data.risk_label}
                </span>
                <span className="font-mono text-[12px] text-textmut">
                  {(risk.data.risk_score * 100).toFixed(0)}/100
                </span>
              </div>
              <p className="text-[12px] text-textmut">{risk.data.summary}</p>
              {risk.data.flags.length > 0 && (
                <div className="text-[11px] text-high font-mono">
                  {risk.data.flags.map((f) => f.protocol).join(" · ")}
                </div>
              )}
            </div>
          )}
        </Panel>

        <Panel title="Tıbbi Durum" actions={<Tag>rehab/active</Tag>}>
          {rehab.isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
          {rehabs.length === 0 && !rehab.isLoading && (
            <p className="text-[12px] text-ok">Aktif sakatlık yok — hazır.</p>
          )}
          {rehabs.length > 0 && (
            <ul className="text-[12px] space-y-1">
              {rehabs.map((rh, i) => (
                <li key={i} className="flex items-center justify-between border-b border-border/40 py-1">
                  <span className="text-text">{rh.injury_type}</span>
                  <span className="text-textmut font-mono">
                    {STATUS_LABEL[rh.status] ?? rh.status} · {rh.expected_return ?? "—"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Benzer Oyuncular" actions={<Tag>scout/similar</Tag>}>
          {sim.isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
          {matches.length === 0 && !sim.isLoading && (
            <p className="text-[12px] text-textmut">Benzer oyuncu bulunamadı.</p>
          )}
          {matches.length > 0 && (
            <ul className="text-[12px] space-y-1">
              {matches.slice(0, 6).map((m) => (
                <li key={m.player_external_id} className="flex items-center justify-between py-0.5">
                  <Link href={`/players/${m.player_external_id}`} className="font-mono text-accent">
                    #{m.player_external_id}
                  </Link>
                  <span className="font-mono text-textmut">
                    {(m.similarity * 100).toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
