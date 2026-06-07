"use client";

/**
 * Lig Takımları — bir ligin takım listesi. ConsoleShell çatısında.
 * Satıra tıkla → takım detayı. Veri: GET /teams/{leagueId}.
 */

import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../../../_console/shell";

interface League { external_id: number; name: string; season: number; country: string | null }
interface Team { sport: string; external_id: number; name: string; country: string | null; founded: number | null }

export default function LeagueTeamsConsolePage() {
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
