"use client";

/**
 * Maç Detayı — tahmin (engine.predict_ml) + maç konsollarına geçiş.
 * ConsoleShell çatısında. Veri: GET /matches/{id}/predict?use_ml=true.
 */

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { ConsoleShell } from "../../_console/shell";

interface PredictResponse {
  value: {
    prob_home_win: number;
    prob_draw: number;
    prob_away_win: number;
    expected_home_goals: number;
    expected_away_goals: number;
    most_likely_score: [number, number];
  };
  confidence: { score: number; label: string; drivers: string[] } | null;
}

export default function MatchDetailConsolePage() {
  const params = useParams<{ id: string }>();
  const matchId = params.id;
  const [teamId, setTeamId] = useState("");

  const { data: predict, error } = useSWR<PredictResponse>(
    `/matches/${matchId}/predict?use_ml=true`,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const v = predict?.value;

  const consoles = [
    { href: `/matches/${matchId}/live?my_team_id=${teamId}&interval_seconds=5&max_minute=90`, label: "Canlı Maç Konsolu", desc: "WebSocket momentum + değişiklik önerisi" },
    { href: `/matches/${matchId}/halftime?my_team_id=${teamId}`, label: "Devre Arası Brief", desc: "1. yarı 7 engine + AI brief" },
    { href: `/matches/${matchId}/sub-chess?my_team_id=${teamId}&current_minute=60`, label: "Değişiklik Senaryoları", desc: "Top-3 sub forward-projection" },
  ];

  const right = (
    <div className="rc">
      <h3>Maç Konsolları</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", marginBottom: 10, lineHeight: 1.5 }}>
        Kendi takımının ID&apos;sini gir → canlı analiz, devre arası ve değişiklik senaryolarına geç.
      </div>
      <input value={teamId} onChange={(e) => setTeamId(e.target.value.replace(/[^0-9]/g, ""))} inputMode="numeric" placeholder="Takım ID (senin takımın)"
        style={{ width: "100%", background: "var(--panel2)", border: "1px solid var(--line)", color: "var(--ink)", fontSize: 12.5, padding: "7px 9px", borderRadius: 7, marginBottom: 10, fontFamily: "inherit" }} />
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {consoles.map((c) => teamId ? (
          <Link key={c.href} href={c.href} style={{ display: "block", background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "9px 11px", textDecoration: "none" }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink)" }}>{c.label}</div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>{c.desc}</div>
          </Link>
        ) : (
          <div key={c.href} style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "9px 11px", opacity: 0.5 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink)" }}>{c.label}</div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>{c.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <ConsoleShell
      active="/matches"
      title={`Maç #${matchId}`}
      sub="Tahmin & konsollar"
      desc="ML tahmini (kazanma olasılıkları, beklenen skor) ve canlı maç konsollarına geçiş."
      right={right}
    >
      {error && <div className="pgdesc">Tahmin alınamadı: {String(error)}</div>}

      {v && (
        <>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
            <div className="kpi"><div className="kl">Ev Galibiyet</div><div className="kn" style={{ color: "var(--low)" }}>{Math.round(v.prob_home_win * 100)}<span className="pct">%</span></div><div className="kd">ev sahibi</div></div>
            <div className="kpi"><div className="kl">Beraberlik</div><div className="kn" style={{ color: "var(--mid)" }}>{Math.round(v.prob_draw * 100)}<span className="pct">%</span></div><div className="kd">eşit</div></div>
            <div className="kpi"><div className="kl">Dep Galibiyet</div><div className="kn" style={{ color: "var(--high)" }}>{Math.round(v.prob_away_win * 100)}<span className="pct">%</span></div><div className="kd">deplasman</div></div>
          </div>

          <div className="st"><h2>Tahmin Detayı</h2>{predict?.confidence && <span className="ep">güven: {predict.confidence.label} ({Math.round(predict.confidence.score * 100)})</span>}</div>
          <div className="tbl" style={{ marginBottom: 14 }}>
            <table>
              <tbody>
                <tr><td>Olasılık dağılımı</td><td className="r">
                  <span className="probbar" style={{ marginBottom: 0, width: 200, display: "inline-flex" }}>
                    <i style={{ width: `${v.prob_home_win * 100}%`, background: "var(--low)" }} />
                    <i style={{ width: `${v.prob_draw * 100}%`, background: "var(--dim)" }} />
                    <i style={{ width: `${v.prob_away_win * 100}%`, background: "var(--high)" }} />
                  </span>
                </td></tr>
                <tr><td>Beklenen skor</td><td className="r">{v.expected_home_goals.toFixed(2)} - {v.expected_away_goals.toFixed(2)}</td></tr>
                <tr><td>En olası skor</td><td className="r">{v.most_likely_score[0]}-{v.most_likely_score[1]}</td></tr>
              </tbody>
            </table>
          </div>
        </>
      )}
      {!v && !error && <div className="pgdesc">Tahmin yükleniyor…</div>}
    </ConsoleShell>
  );
}
