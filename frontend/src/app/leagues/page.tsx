"use client";

/**
 * Ligler — sync edilmiş ligler tablosu. ConsoleShell çatısında.
 * Satıra tıkla → o ligin takımları. Veri: GET /leagues.
 */

import useSWR from "swr";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../_console/shell";

interface League {
  sport: string;
  external_id: number;
  name: string;
  season: number;
  country: string | null;
}

export default function LeaguesConsolePage() {
  const router = useRouter();
  const { data, error, isLoading } = useSWR<League[]>("/leagues", apiFetch, { shouldRetryOnError: false });
  const rows = data ?? [];
  const countries = new Set(rows.map((r) => r.country).filter(Boolean)).size;

  const right = (
    <div className="rc">
      <h3>Özet</h3>
      <div className="stat"><span>Lig sayısı</span><span className="sv">{rows.length}</span></div>
      <div className="stat"><span>Ülke</span><span className="sv">{countries}</span></div>
      <div style={{ fontSize: "11.5px", color: "var(--dim)", marginTop: 10, lineHeight: 1.5 }}>
        Bir satıra tıkla → o ligin takım listesi açılır.
      </div>
    </div>
  );

  return (
    <ConsoleShell
      active="/leagues"
      title="Ligler"
      sub="Sync edilmiş ligler"
      desc="Sistemde tanımlı ligler. Takımları görmek için bir lige tıkla."
      right={right}
    >
      {isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {error && <div className="pgdesc">Yüklenemedi ya da yetki yok.</div>}
      <div className="st" style={{ marginTop: 0 }}><h2>Lig Listesi</h2><span className="ep">GET /leagues</span></div>
      <div className="tbl">
        <table>
          <thead><tr><th className="c">#</th><th>Lig</th><th>Ülke</th><th className="c">Sezon</th><th className="r">ID</th></tr></thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                Henüz lig sync edilmedi.
              </td></tr>
            )}
            {rows.map((l, i) => (
              <tr key={l.external_id} onClick={() => router.push(`/leagues/${l.external_id}/teams`)} style={{ cursor: "pointer" }}>
                <td className="pnum c">{i + 1}</td>
                <td><span className="nm">{l.name}</span></td>
                <td style={{ color: "var(--muted)" }}>{l.country ?? "—"}</td>
                <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{l.season}/{l.season + 1}</td>
                <td className="r" style={{ color: "var(--dim)" }}>{l.external_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
