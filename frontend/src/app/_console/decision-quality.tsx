"use client";

/**
 * Karar Kalitesi — sistem kendini tartıyor (engine.backtest + engine.decision_impact)
 *
 * Karar defteri (`decision-impact.tsx`) "hangi karar tuttu"yu söyler.
 * Bu kart bir üst soruyu sorar:
 *   1. Sistem "%70 güvenle öner" dediğinde gerçekten %70 tutuyor mu? (kalibrasyon)
 *   2. Sistemin önerdiği kararlar koçun kendi başına aldıklarından iyi mi?
 *
 * GET /admin/teams/{id}/decisions/quality
 *
 * DİKKAT — iki farklı "isabet" var, karıştırmayın:
 * - `confidence_calibration.accuracy` → 0.5 eşiğinde sınıflandırma doğruluğu
 * - `recommended_vs_own.*.hit_rate`   → pozitif çıkan karar oranı
 * Bu yüzden kartta kalibrasyon tarafında "isabet" kelimesi kullanılmıyor;
 * "sistem diyor" vs "gerçekleşen" ikilisi gösteriliyor.
 */

import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface CalibrationBin {
  lower: number; upper: number; n: number; mean_predicted: number; observed_rate: number;
}
interface GroupStat { n: number; hit_rate: number | null; mean_xg_delta: number }
export interface DecisionQuality {
  team_id: number; window_minutes: number; matches_used: number; measured_decisions: number;
  confidence_calibration: {
    n: number; accuracy: number; brier_score: number;
    mean_predicted: number; observed_rate: number;
    well_calibrated: boolean; bins: CalibrationBin[];
  };
  recommended_vs_own: { recommended: GroupStat; own: GroupStat; xg_lift: number | null };
  verdict: string; note?: string;
}

const pct = (v: number | null | undefined) => (v == null ? "—" : `%${Math.round(v * 100)}`);
const signed = (v: number, digits = 3) => `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;
const LABEL: React.CSSProperties = {
  fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6,
  color: "var(--muted)", fontWeight: 700,
};
const NUM: React.CSSProperties = { fontFamily: "JetBrains Mono, monospace", fontWeight: 700 };

/** Güven ekseni: sistemin iddiası (dikey çizgi) ile gerçekleşen (çubuk) yan yana. */
function CalibrationBins({ bins }: { bins: CalibrationBin[] }) {
  const used = bins.filter((b) => b.n > 0);
  if (used.length === 0) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ ...LABEL, marginBottom: 6 }}>Güven aralığına göre gerçekleşme</div>
      <div style={{ display: "grid", gap: 5 }}>
        {used.map((b) => {
          const gap = b.observed_rate - b.mean_predicted;
          const honest = Math.abs(gap) <= 0.15;
          return (
            <div key={`${b.lower}-${b.upper}`}
              style={{ display: "grid", gridTemplateColumns: "62px 1fr 92px", gap: 8, alignItems: "center" }}>
              <span style={{ fontSize: 10, fontFamily: "JetBrains Mono, monospace", color: "var(--muted)" }}>
                %{Math.round(b.lower * 100)}–{Math.round(b.upper * 100)}
              </span>
              <div style={{ position: "relative", height: 12, background: "var(--panel2)", borderRadius: 3 }}>
                <div style={{
                  width: `${Math.min(100, b.observed_rate * 100)}%`, height: "100%",
                  background: honest ? "var(--low)" : "var(--mid)", borderRadius: 3,
                }} />
                <div title={`sistem: %${Math.round(b.mean_predicted * 100)}`} style={{
                  position: "absolute", top: -2, bottom: -2,
                  left: `${Math.min(100, b.mean_predicted * 100)}%`, width: 2, background: "var(--ink)",
                }} />
              </div>
              <span style={{ fontSize: 10, color: "var(--dim)", fontFamily: "JetBrains Mono, monospace" }}>
                n={b.n} · {gap >= 0 ? "+" : ""}{Math.round(gap * 100)}p
              </span>
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 9.5, color: "var(--dim)", marginTop: 5, lineHeight: 1.45 }}>
        Çubuk = gerçekleşen oran · dikey çizgi = sistemin o aralıkta iddia ettiği güven.
        İkisi ne kadar yakınsa güven o kadar dürüst.
      </div>
    </div>
  );
}

/** Sistem güveni kalibre mi + öneriler koçun kendi kararlarından iyi mi. */
export function DecisionQualityCard({ teamId, windowMin = 15 }: {
  teamId: number | null; windowMin?: number;
}) {
  const key = teamId != null
    ? `/admin/teams/${teamId}/decisions/quality?window_min=${windowMin}` : null;
  const { data, error } = useSWR<DecisionQuality>(key, apiFetch, {
    revalidateOnFocus: false, shouldRetryOnError: false,
  });
  if (teamId == null) return null;

  const cal = data?.confidence_calibration;
  const cmp = data?.recommended_vs_own;
  const thin = (cal?.n ?? 0) < 20;

  return (
    <div className="rc" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>
          Karar kalitesi{" "}
          <span style={{ fontWeight: 400, color: "var(--muted)", fontSize: 11 }}>· sistem kendini tartıyor</span>
        </h3>
        <span style={{ fontSize: 10, color: "var(--muted)" }}>
          {data ? `${data.measured_decisions} ölçülen karar · ${data.matches_used} maç` : "…"}
        </span>
      </div>
      {error && (
        <div style={{ fontSize: 11.5, color: "var(--crit)", marginTop: 6 }}>
          Yüklenemedi: {String(error).slice(0, 140)}
        </div>
      )}

      {data && cal && cmp && (
        <>
          <div style={{ fontSize: 12.5, color: "var(--ink)", marginTop: 8, lineHeight: 1.5 }}>{data.verdict}</div>

          {cal.n > 0 && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 12, marginTop: 12 }}>
                <div>
                  <div style={LABEL}>Sistem diyor</div>
                  <div style={{ ...NUM, fontSize: 22, color: "var(--muted)" }}>{pct(cal.mean_predicted)}</div>
                </div>
                <div>
                  <div style={LABEL}>Gerçekleşen</div>
                  <div style={{ ...NUM, fontSize: 22, color: cal.well_calibrated ? "var(--low)" : "var(--mid)" }}>
                    {pct(cal.observed_rate)}
                  </div>
                </div>
                <div>
                  <div style={LABEL}>Brier</div>
                  <div style={{ ...NUM, fontSize: 22, color: "var(--ink)" }}>{cal.brier_score.toFixed(3)}</div>
                  <div style={{ fontSize: 9, color: "var(--dim)" }}>düşük = iyi</div>
                </div>
                <div>
                  <div style={LABEL}>Örneklem</div>
                  <div style={{ ...NUM, fontSize: 22, color: thin ? "var(--mid)" : "var(--ink)" }}>{cal.n}</div>
                  <div style={{ fontSize: 9, color: "var(--dim)" }}>{thin ? "yön göstergesi" : "anlamlı"}</div>
                </div>
              </div>
              <CalibrationBins bins={cal.bins} />
            </>
          )}

          <div style={{ marginTop: 14, paddingTop: 10, borderTop: "1px solid var(--line)" }}>
            <div style={{ ...LABEL, marginBottom: 6 }}>Sistemin önerdiği vs koçun kendi kararı</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
              {([["Öneriden", cmp.recommended], ["Koçun kendi", cmp.own]] as const).map(([label, g]) => (
                <div key={label}>
                  <div style={{ fontSize: 11, color: "var(--muted)" }}>
                    {label} <span style={{ color: "var(--dim)" }}>· n={g.n}</span>
                  </div>
                  <div style={{ ...NUM, fontSize: 18, color: g.n ? "var(--ink)" : "var(--dim)" }}>
                    {g.n ? pct(g.hit_rate) : "—"}
                  </div>
                  <div style={{ fontSize: 10.5, color: "var(--muted)" }}>
                    {g.n ? `${signed(g.mean_xg_delta)} xG/dk` : "ölçülen karar yok"}
                  </div>
                </div>
              ))}
              <div>
                <div style={{ fontSize: 11, color: "var(--muted)" }}>Fark (lift)</div>
                <div style={{
                  ...NUM, fontSize: 18,
                  color: cmp.xg_lift == null ? "var(--dim)" : cmp.xg_lift > 0 ? "var(--low)" : "var(--crit)",
                }}>
                  {cmp.xg_lift == null ? "—" : signed(cmp.xg_lift, 4)}
                </div>
                <div style={{ fontSize: 10.5, color: "var(--muted)" }}>
                  {cmp.xg_lift == null ? "iki grupta da karar gerekir"
                    : cmp.xg_lift > 0 ? "öneriler önde" : "koç önde"}
                </div>
              </div>
            </div>
          </div>

          <div style={{ fontSize: 10, color: "var(--dim)", marginTop: 10, lineHeight: 1.5 }}>
            {data.note ? `${data.note} ` : ""}
            Karşılaştırma gözlemsel: öneriler ve koçun kendi kararları farklı maç durumlarında
            alınır, bu yüzden fark nedensellik değil yön gösterir.
          </div>
        </>
      )}
    </div>
  );
}
