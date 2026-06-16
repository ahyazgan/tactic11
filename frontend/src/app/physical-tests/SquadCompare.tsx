"use client";

/**
 * Kadro Karşılaştırma — bir protokolde kadro sıralaması + kadro-içi yüzdelik.
 *
 * Her oyuncunun SON değeri → norm rating (elit/iyi/ortalama/zayıf) + yüzdelik
 * (100 = en iyi, yön-duyarlı). DEMO: demoHistoryFor; production:
 * GET /physical-tests/squad-comparison?protocol=. "Kim elit, kim zayıf" tek bakışta.
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { PROTO_NAME } from "@/lib/derived-tests";
import {
  demoSquadComparison, RATING_VAR, COMPARABLE_PROTOCOLS, type SquadComparison,
} from "@/lib/squad-compare";

const chip = (active: boolean): React.CSSProperties => ({
  padding: "6px 12px", borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: "pointer",
  fontFamily: "inherit", border: active ? 0 : "1px solid var(--line)",
  background: active ? "var(--besiktas)" : "var(--panel)", color: active ? "#fff" : "var(--ink)",
});

export function SquadCompare() {
  const [proto, setProto] = React.useState("cmj");
  const apiData = useSWR<SquadComparison>(
    DEMO_MODE ? null : `/physical-tests/squad-comparison?protocol=${proto}`, apiFetch);
  const data: SquadComparison | null = DEMO_MODE ? demoSquadComparison(proto) : (apiData.data ?? null);

  return (
    <>
      <div className="st"><h2>Kadro Karşılaştırma</h2><span className="ep">protokol bazında sıralama + yüzdelik</span></div>
      <div className="rc" style={{ margin: "0 0 16px" }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          {COMPARABLE_PROTOCOLS.map((k) => (
            <button key={k} type="button" onClick={() => setProto(k)} style={chip(k === proto)}>
              {PROTO_NAME[k] ?? k}
            </button>
          ))}
        </div>

        {!data || !data.rows.length ? (
          <div style={{ fontSize: 12.5, color: "var(--muted)" }}>Bu protokol için karşılaştırılacak veri yok.</div>
        ) : (
          <>
            <div style={{ fontSize: 11.5, color: "var(--dim)", marginBottom: 10 }}>
              {data.protocol_name} · {data.unit} · {data.higher_is_better ? "yüksek iyi" : "düşük iyi"} · {data.n} oyuncu · yüzdelik = kadronun % kaçından iyi
            </div>
            {data.rows.map((r, i) => {
              const v = RATING_VAR[r.rating];
              const pct = r.percentile ?? 0;
              return (
                <div key={r.player_id} style={{ display: "grid", gridTemplateColumns: "24px 1fr auto", gap: 12, alignItems: "center", padding: "7px 0", borderTop: i ? "1px solid var(--line)" : undefined }}>
                  <span className="pnum c" style={{ color: i < 3 ? "var(--ink)" : "var(--dim)" }}>{i + 1}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                      <span className="nm">{r.player_name}</span>
                      <span className="risk" style={{ background: "transparent", color: v, fontSize: 10.5, textTransform: "uppercase", border: `1px solid ${v}`, borderRadius: 5, padding: "0 6px" }}>{r.rating}</span>
                    </div>
                    <span className="mbar" style={{ display: "block", marginTop: 4, maxWidth: 320 }}>
                      <i style={{ width: `${pct}%`, background: v }} />
                    </span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 13 }}>{r.value}<span style={{ color: "var(--dim)", fontSize: 11 }}> {data.unit}</span></div>
                    <div style={{ fontFamily: "JetBrains Mono", fontSize: 10.5, color: "var(--dim)" }}>%{r.percentile ?? "—"}</div>
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </>
  );
}
