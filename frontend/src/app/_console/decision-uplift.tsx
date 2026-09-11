"use client";

/**
 * Öneri etkisi — uygulanan vs uygulanmayan öneri (engine.decision_uplift)
 *
 * Karar defteri "sonra ne oldu"yu ölçer. Bu kart "öneri YÜZÜNDEN ne oldu"yu
 * sorar: koçun uyguladığı öneriler, uygulamadığı önerilerden (karşı-olgu)
 * daha mı iyi gitti? Kıyas karar öncesi duruma göre katmanlıdır — cetvel
 * ortalamaya dönüş taşır, kötü giderken uygulanan öneri ham kıyasta haksız
 * yere iyi görünür.
 *
 * GET /admin/teams/{id}/decisions/uplift
 *
 * Karşı-olgu yoksa (koç hiç "uygulamadım" işaretlemediyse) kart bunu açıkça
 * söyler; sayı uydurmaz.
 */

import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface ArmStat { n: number; positive: number; hit_rate: number | null; mean_xg_delta: number }
interface StratumStat {
  pre_lo: number; pre_hi: number; applied: ArmStat; not_applied: ArmStat;
  hit_rate_diff: number | null;
}
export interface DecisionUplift {
  team_id: number; window_minutes: number; matches_used: number;
  measured_recommendations: number;
  applied: ArmStat; not_applied: ArmStat; unknown: number;
  raw_hit_rate_diff: number | null; raw_xg_delta_diff: number | null;
  stratified_hit_rate_diff: number | null;
  strata: StratumStat[];
  verdict: string; note: string; formula: string;
}

const pct = (v: number | null | undefined) => (v == null ? "—" : `%${Math.round(v * 100)}`);
const pts = (v: number | null | undefined) =>
  (v == null ? "—" : `${v >= 0 ? "+" : ""}${Math.round(v * 100)} puan`);
const LABEL: React.CSSProperties = {
  fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6,
  color: "var(--muted)", fontWeight: 700,
};
const NUM: React.CSSProperties = { fontFamily: "JetBrains Mono, monospace", fontWeight: 700 };

function verdictTone(verdict: string): string {
  if (verdict === "uplift") return "var(--low)";
  if (verdict === "TERS") return "var(--crit)";
  if (verdict === "fark yok") return "var(--mid)";
  return "var(--dim)";
}

export function DecisionUpliftCard({ teamId, windowMin = 15 }: {
  teamId: number | null; windowMin?: number;
}) {
  const key = teamId != null
    ? `/admin/teams/${teamId}/decisions/uplift?window_min=${windowMin}` : null;
  const { data, error } = useSWR<DecisionUplift>(key, apiFetch, {
    revalidateOnFocus: false, shouldRetryOnError: false,
  });
  if (teamId == null) return null;

  const noCounterfactual = data && (data.verdict === "karşı-olgu yok" || data.verdict === "uygulanan yok");

  return (
    <div className="rc" style={{ marginBottom: 12 }} data-testid="decision-uplift"
      data-verdict={data?.verdict ?? "yükleniyor"}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>
          Öneri etkisi{" "}
          <span style={{ fontWeight: 400, color: "var(--muted)", fontSize: 11 }}>· uygulanan vs uygulanmayan</span>
        </h3>
        <span style={{ fontSize: 10, color: "var(--muted)" }}>
          {data ? `${data.measured_recommendations} ölçülen öneri · ${data.matches_used} maç` : "…"}
        </span>
      </div>
      {error && (
        <div style={{ fontSize: 11.5, color: "var(--crit)", marginTop: 6 }}>
          Yüklenemedi: {String(error).slice(0, 140)}
        </div>
      )}

      {data && (
        <>
          <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{
              fontSize: 10.5, fontWeight: 800, textTransform: "uppercase", letterSpacing: 0.6,
              color: verdictTone(data.verdict), border: `1px solid ${verdictTone(data.verdict)}`,
              borderRadius: 999, padding: "2px 9px",
            }}>{data.verdict}</span>
            <span style={{ fontSize: 12, color: "var(--ink)", lineHeight: 1.5 }}>{data.note}</span>
          </div>

          {noCounterfactual ? (
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 10, lineHeight: 1.55 }}>
              Maç-içi panelde öneriyi <b>uygulamadığında da</b> işaretle (✗ Uygulamadım).
              O kayıt, aynı durumda öneri uygulanmayınca ne olduğunun tek gözlemidir;
              onsuz sistem yalnız &ldquo;sonra ne oldu&rdquo;yu bilir, öneri etkisini değil.
            </div>
          ) : (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 12, marginTop: 12 }}>
                {([["Uygulanan", data.applied], ["Uygulanmayan", data.not_applied]] as const).map(([label, g]) => (
                  <div key={label}>
                    <div style={LABEL}>{label} <span style={{ color: "var(--dim)" }}>· n={g.n}</span></div>
                    <div style={{ ...NUM, fontSize: 22, color: g.n ? "var(--ink)" : "var(--dim)" }}>
                      {g.n ? pct(g.hit_rate) : "—"}
                    </div>
                    <div style={{ fontSize: 10.5, color: "var(--muted)" }}>
                      {g.n ? `${g.mean_xg_delta >= 0 ? "+" : ""}${g.mean_xg_delta.toFixed(3)} xG/dk` : "kayıt yok"}
                    </div>
                  </div>
                ))}
                <div>
                  <div style={LABEL}>Ham fark</div>
                  <div style={{ ...NUM, fontSize: 22, color: "var(--muted)" }}>{pts(data.raw_hit_rate_diff)}</div>
                  <div style={{ fontSize: 10.5, color: "var(--muted)" }}>karıştırıcı kontrolsüz</div>
                </div>
                <div>
                  <div style={LABEL}>Katmanlı fark</div>
                  <div style={{ ...NUM, fontSize: 22, color: verdictTone(data.verdict) }}>
                    {pts(data.stratified_hit_rate_diff)}
                  </div>
                  <div style={{ fontSize: 10.5, color: "var(--muted)" }}>aynı karar öncesi durumda</div>
                </div>
              </div>

              {data.strata.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ ...LABEL, marginBottom: 6 }}>Karar öncesi duruma göre katmanlar</div>
                  <div style={{ display: "grid", gap: 4 }}>
                    {data.strata.map((s, i) => (
                      <div key={i} style={{
                        display: "grid", gridTemplateColumns: "120px 1fr 1fr 80px", gap: 8,
                        fontSize: 10.5, fontFamily: "JetBrains Mono, monospace", color: "var(--muted)",
                      }}>
                        <span title="önceki pencere xG farkı / dk">
                          {s.pre_lo.toFixed(3)} … {s.pre_hi.toFixed(3)}
                        </span>
                        <span>uyg. {s.applied.n ? `${pct(s.applied.hit_rate)} (n=${s.applied.n})` : "—"}</span>
                        <span>uygulanmayan {s.not_applied.n ? `${pct(s.not_applied.hit_rate)} (n=${s.not_applied.n})` : "—"}</span>
                        <span style={{ color: s.hit_rate_diff == null ? "var(--dim)" : s.hit_rate_diff >= 0 ? "var(--low)" : "var(--crit)" }}>
                          {s.hit_rate_diff == null ? "tek kol" : pts(s.hit_rate_diff)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          <div style={{ fontSize: 10, color: "var(--dim)", marginTop: 10, lineHeight: 1.5 }}>
            Gözlemsel kıyas: koç neyi uyguladığını kendi seçer; katmanlama yalnız karar öncesi
            durumu kontrol eder. {data.unknown > 0 ? `${data.unknown} işaretsiz öneri kıyasa girmedi.` : ""}
          </div>
        </>
      )}
    </div>
  );
}
