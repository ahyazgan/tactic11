"use client";

/**
 * Re-test Kıyası — antrenman bloğu öncesi/sonrası, oyuncunun KENDİ baseline'ına göre.
 *
 * Kadro ortalaması değil: her oyuncu için split öncesi ölçümlerin SWC'si
 * (0.2 × SD) eşiktir. Gerileyen üstte; baseline < 3 ölçüm ise "yetersiz"
 * (iddia yok). DEMO: demoHistoryFor; production: GET /physical-tests/retest.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { PROTO_NAME } from "@/lib/derived-tests";
import {
  demoRetestComparison, RETEST_PROTOCOLS, DEMO_DEFAULT_SPLIT, CATEGORY_LABEL, CATEGORY_VAR,
  type RetestComparison, type RetestCategory,
} from "@/lib/retest";

const chip = (active: boolean): React.CSSProperties => ({
  padding: "6px 12px", borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: "pointer",
  fontFamily: "inherit", border: active ? 0 : "1px solid var(--line)",
  background: active ? "var(--besiktas)" : "var(--panel)", color: active ? "#fff" : "var(--ink)",
});

const fmt = (x: number | null, digits = 2) => (x == null ? "—" : x.toFixed(digits));
/** İşaretli sayı; gösterim hassasiyetinde sıfıra yuvarlanan değer "-0.00" olmaz. */
function signed(x: number | null, digits = 2): string {
  if (x == null) return "—";
  const r = Number(x.toFixed(digits));
  return `${r > 0 ? "+" : ""}${r.toFixed(digits)}`;
}

function defaultSplit(): string {
  if (DEMO_MODE) return DEMO_DEFAULT_SPLIT;
  const d = new Date(); d.setDate(d.getDate() - 28);   // varsayılan blok: son 4 hafta
  return d.toISOString().slice(0, 10);
}

export function RetestCompare() {
  const [proto, setProto] = React.useState("cmj");
  const [split, setSplit] = React.useState(defaultSplit);
  const apiData = useSWR<RetestComparison>(
    DEMO_MODE || !split ? null : `/physical-tests/retest?protocol=${proto}&split=${split}`, apiFetch);
  const data: RetestComparison | null = DEMO_MODE ? demoRetestComparison(proto, split) : (apiData.data ?? null);

  // Saniye protokollerinde (sprint) anlamlı fark 3. ondalıkta; diğerlerinde 2 yeter.
  const dDigits = data?.unit === "sn" ? 3 : 2;
  const summary: [RetestCategory, number][] = data
    ? [["declined", data.declined], ["improved", data.improved], ["unchanged", data.unchanged], ["insufficient", data.insufficient]]
    : [];

  return (
    <>
      <div className="st"><h2>Re-test Kıyası</h2><span className="ep">blok öncesi / sonrası · oyuncunun kendi baseline'ına göre</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }} data-testid="retest-panel">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
          {RETEST_PROTOCOLS.map((k) => (
            <button key={k} type="button" onClick={() => setProto(k)} style={chip(k === proto)}>
              {PROTO_NAME[k] ?? k}
            </button>
          ))}
          <label style={{ marginLeft: "auto", fontSize: 12, color: "var(--dim)", display: "flex", alignItems: "center", gap: 6 }}>
            blok başlangıcı
            <input type="date" value={split} onChange={(e) => setSplit(e.target.value)}
              style={{ fontFamily: "inherit", fontSize: 12.5, padding: "5px 8px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)" }} />
          </label>
        </div>

        {!data || !data.rows.length ? (
          <div style={{ fontSize: 12.5, color: "var(--muted)" }}>
            {apiData.error ? `Yüklenemedi: ${String(apiData.error).slice(0, 80)}` : "Seçilen tarihten sonra bu protokolde ölçüm yok."}
          </div>
        ) : (
          <>
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11.5, color: "var(--dim)", marginBottom: 10 }}>
              <span>{data.protocol_name} · {data.unit} · {data.higher_is_better ? "yüksek iyi" : "düşük iyi"} · {data.n} oyuncu</span>
              {summary.map(([c, n]) => (
                <span key={c} style={{ color: CATEGORY_VAR[c], fontWeight: 700 }}>{n} {CATEGORY_LABEL[c]}</span>
              ))}
            </div>
            <div className="tbl">
              <table>
                <thead>
                  <tr>
                    <th>Oyuncu</th>
                    <th className="r">Baseline (n)</th>
                    <th className="r">SWC</th>
                    <th className="r">Sonra</th>
                    <th className="r">Δ</th>
                    <th className="r">Δ%</th>
                    <th>Sonuç</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => {
                    const v = CATEGORY_VAR[r.category];
                    return (
                      <tr key={r.player_id} data-category={r.category}>
                        <td className="nm">{r.player_name}</td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono" }}>{fmt(r.baseline_mean, dDigits)} <span style={{ color: "var(--dim)" }}>({r.baseline_n})</span></td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono", color: "var(--dim)" }}>{r.swc == null ? "—" : `±${r.swc.toFixed(3)}`}</td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>{r.current}</td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono", color: v }}>{signed(r.delta, dDigits)}</td>
                        <td className="r" style={{ fontFamily: "JetBrains Mono", color: v }}>{signed(r.delta_pct, 1)}{r.delta_pct == null ? "" : "%"}</td>
                        <td>
                          <span className="risk" style={{ background: "transparent", color: v, fontSize: 10.5, textTransform: "uppercase", border: `1px solid ${v}`, borderRadius: 5, padding: "0 6px" }}>
                            {CATEGORY_LABEL[r.category]}
                          </span>
                          <span style={{ marginLeft: 8, color: "var(--dim)", fontSize: 11 }}>{r.verdict}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ fontSize: 11.5, color: "var(--dim)", marginTop: 8 }}>
              Baseline = blok başlangıcından önceki ölçümlerin ortalaması; SWC = 0.2 × baseline SD (oyuncunun kendi gürültüsü).
              |Δ| &lt; SWC → değişim yok. Baseline &lt; {data.min_baseline} ölçüm → yetersiz, iddia yok. "Sonra" = blok sonrası son ölçüm.
            </div>
          </>
        )}
      </div>
    </>
  );
}
