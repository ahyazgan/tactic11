"use client";

/**
 * Karar Etkisi — koçun hamlesi işe yaradı mı? (engine.decision_impact)
 *
 * İki kart:
 * - `DecisionTrackRecordCard` — takım defteri: tip ve dakika bandı kırılımlı
 *   isabet + ortalama xG etkisi + en iyi/en kötü karar
 *   (GET /admin/teams/{id}/decisions/track-record)
 * - `MatchDecisionImpactCard` — tek maçtaki kararların öncesi/sonrası ölçümü
 *   (GET /admin/matches/{id}/decisions/learning) + "Ölç ve kaydet"
 *   (POST .../auto-outcome) ile outcome alanını doldurup güven döngüsünü kapatır
 *
 * Ölçüm vekildir: skor durumu, kart, rakip hamlesi de aynı anda etkiler.
 * Bu yüzden her yerde "etkisi ölçüldü" denir, "kararın doğruydu" denmez.
 */

import { useState } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

export interface WindowMetrics {
  minutes: number; xg_for: number; xg_against: number; xg_diff: number; xt: number;
  shots_for: number; shots_against: number; goals_for: number; goals_against: number;
  final_third_pass_share: number; defensive_actions: number;
}
export interface DecisionImpact {
  decision_id: number; minute: number; decision_type: string; decision_label: string;
  pre: WindowMetrics; post: WindowMetrics;
  xg_diff_delta: number; xt_delta: number; shots_delta: number; goals_delta: number;
  field_tilt_delta: number; verdict: string; verdict_reason: string;
  confidence: number; window_minutes: number;
}
interface TypeStat { decision_type: string; label: string; n: number; positive: number; negative: number; neutral: number; hit_rate: number | null; mean_xg_delta: number }
interface BandStat { band: string; n: number; hit_rate: number | null; mean_xg_delta: number }
interface TrackRecord {
  team_id: number; matches: number; matches_with_events: number;
  decisions: number; measured: number; positive: number; negative: number; neutral: number;
  hit_rate: number | null; mean_xg_delta: number;
  by_type: TypeStat[]; by_minute_band: BandStat[];
  best: DecisionImpact | null; worst: DecisionImpact | null; formula?: string;
}
interface LearningResponse {
  decisions_analyzed?: number; window_minutes?: number; impacts?: DecisionImpact[];
  note?: string; events_loaded?: number; decisions?: number;
}

const VERDICT_TR: Record<string, string> = {
  positive: "işe yaradı", negative: "ters gitti", neutral: "nötr",
  insufficient_data: "ölçülemedi",
};
const VERDICT_COLOR: Record<string, string> = {
  positive: "var(--low)", negative: "var(--crit)", neutral: "var(--mid)",
  insufficient_data: "var(--dim)",
};

const pct = (v: number | null | undefined) => (v == null ? "—" : `%${Math.round(v * 100)}`);
const signed = (v: number, digits = 3) => `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;

/** Öncesi/sonrası tek metrik için karşılaştırma çubuğu (dakika başına). */
function BeforeAfter({ label, pre, post, digits = 2, unit = "" }: {
  label: string; pre: number; post: number; digits?: number; unit?: string;
}) {
  const max = Math.max(Math.abs(pre), Math.abs(post), 1e-6);
  // Renk gösterilen hassasiyete göre: 0.384 → 0.379 ikisi de "0.38" yazarken
  // birinin kırmızı olması tutarsız görünüyordu.
  const shown = (v: number) => Number(v.toFixed(digits));
  const improved = shown(post) >= shown(pre);
  const bar = (v: number, color: string) => (
    <div style={{ height: 5, background: "var(--panel2)", borderRadius: 3, overflow: "hidden" }}>
      <div style={{ width: `${Math.min(100, (Math.abs(v) / max) * 100)}%`, height: "100%", background: color }} />
    </div>
  );
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 9.5, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 3 }}>
        <div>
          <div style={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace", color: "var(--muted)" }}>{pre.toFixed(digits)}{unit}</div>
          {bar(pre, "var(--dim)")}
          <div style={{ fontSize: 9, color: "var(--dim)" }}>önce</div>
        </div>
        <div>
          <div style={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace", color: "var(--ink)" }}>{post.toFixed(digits)}{unit}</div>
          {bar(post, improved ? "var(--low)" : "var(--crit)")}
          <div style={{ fontSize: 9, color: "var(--dim)" }}>sonra</div>
        </div>
      </div>
    </div>
  );
}

function ImpactRow({ imp }: { imp: DecisionImpact }) {
  const measured = imp.verdict !== "insufficient_data";
  return (
    <div style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12.5, color: "var(--ink)" }}>
          <b style={{ fontFamily: "JetBrains Mono, monospace" }}>{Math.round(imp.minute)}&apos;</b> · {imp.decision_label}
        </span>
        <span style={{ fontSize: 11, fontWeight: 700, color: VERDICT_COLOR[imp.verdict] }}>
          {VERDICT_TR[imp.verdict] ?? imp.verdict}
          {measured && <span style={{ color: "var(--muted)", fontWeight: 400 }}> · güven {pct(imp.confidence)}</span>}
        </span>
      </div>
      <div style={{ fontSize: 10.5, color: "var(--muted)", marginTop: 2 }}>{imp.verdict_reason}</div>
      {measured && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 12, marginTop: 8 }}>
          <BeforeAfter label="xG farkı /dk" pre={imp.pre.xg_diff} post={imp.post.xg_diff} digits={3} />
          <BeforeAfter label="xT /dk" pre={imp.pre.xt} post={imp.post.xt} digits={3} />
          <BeforeAfter label="şut /dk" pre={imp.pre.shots_for} post={imp.post.shots_for} />
          <BeforeAfter label="saha eğimi" pre={imp.pre.final_third_pass_share} post={imp.post.final_third_pass_share} />
        </div>
      )}
      <div style={{ fontSize: 9.5, color: "var(--dim)", marginTop: 4 }}>
        pencere {imp.pre.minutes}/{imp.post.minutes} dk (önce/sonra)
      </div>
    </div>
  );
}

/** Tek maçtaki kararların ölçümü + döngüyü kapatan "Ölç ve kaydet". */
export function MatchDecisionImpactCard({ matchId, windowMin = 15 }: { matchId: number | null; windowMin?: number }) {
  const key = matchId != null ? `/admin/matches/${matchId}/decisions/learning?window_min=${windowMin}` : null;
  const { data, error, mutate } = useSWR<LearningResponse>(key, apiFetch, {
    revalidateOnFocus: false, shouldRetryOnError: false,
  });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  if (matchId == null) return null;

  const impacts = data?.impacts ?? [];
  const save = async () => {
    setSaving(true); setMsg(null);
    try {
      const r = await apiFetch<{ written: number; skipped_manual: number; skipped_insufficient: number }>(
        `/admin/matches/${matchId}/decisions/auto-outcome?window_min=${windowMin}`, { method: "POST" },
      );
      setMsg(`${r.written} karar sonucu kaydedildi` +
        (r.skipped_manual ? ` · ${r.skipped_manual} elle girilmiş atlandı` : "") +
        (r.skipped_insufficient ? ` · ${r.skipped_insufficient} ölçülemedi` : ""));
      await mutate();
    } catch (e) {
      setMsg(`Hata: ${String(e).slice(0, 140)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rc" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Maç #{matchId} · karar etkisi</h3>
        <span style={{ fontSize: 10, color: "var(--muted)" }}>{windowMin} dk öncesi/sonrası · dakika başına</span>
      </div>
      {error && <div style={{ fontSize: 11.5, color: "var(--crit)", marginTop: 6 }}>Yüklenemedi: {String(error).slice(0, 140)}</div>}
      {data?.note && <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>{data.note}</div>}
      {impacts.map((i) => <ImpactRow key={i.decision_id} imp={i} />)}
      {impacts.length > 0 && (
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
          <button type="button" onClick={save} disabled={saving}
            style={{ padding: "7px 12px", background: "var(--accent)", color: "#fff", border: "1px solid var(--line)", borderRadius: 4, cursor: "pointer", fontSize: 12, fontWeight: 700 }}>
            {saving ? "Kaydediliyor…" : "Ölç ve kaydet"}
          </button>
          <span style={{ fontSize: 10.5, color: "var(--muted)" }}>
            Sonuçlar karar defterine yazılır; sistem bir sonraki maçta bu tip öneriye daha az/çok güvenir.
          </span>
          {msg && <span style={{ fontSize: 11, color: msg.startsWith("Hata") ? "var(--crit)" : "var(--low)" }}>{msg}</span>}
        </div>
      )}
    </div>
  );
}

/** Takım karar defteri — tip ve dakika bandı kırılımı. */
export function DecisionTrackRecordCard({ teamId, windowMin = 15 }: { teamId: number | null; windowMin?: number }) {
  const key = teamId != null ? `/admin/teams/${teamId}/decisions/track-record?window_min=${windowMin}` : null;
  const { data, error } = useSWR<TrackRecord>(key, apiFetch, { revalidateOnFocus: false, shouldRetryOnError: false });
  if (teamId == null) return null;
  const ready = data && data.measured > 0;
  return (
    <div className="rc" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Karar defteri <span style={{ fontWeight: 400, color: "var(--muted)", fontSize: 11 }}>· ölçülen etki</span></h3>
        <span style={{ fontSize: 10, color: "var(--muted)" }}>
          {data ? `${data.measured}/${data.decisions} karar ölçüldü · ${data.matches_with_events} maç` : "…"}
        </span>
      </div>
      {error && <div style={{ fontSize: 11.5, color: "var(--crit)", marginTop: 6 }}>Yüklenemedi: {String(error).slice(0, 140)}</div>}
      {data && !ready && (
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>
          Henüz ölçülebilir karar yok — kararların event verisi olan maçlarda ve yeterli pencereyle kaydedilmesi gerekir.
        </div>
      )}
      {ready && data && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 12, marginTop: 10 }}>
            <div>
              <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>İsabet</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: "var(--low)", fontFamily: "JetBrains Mono, monospace" }}>{pct(data.hit_rate)}</div>
              <div style={{ fontSize: 9.5, color: "var(--dim)" }}>{data.positive} işe yaradı / {data.negative} ters</div>
            </div>
            <div>
              <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>Ortalama xG etkisi</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: data.mean_xg_delta >= 0 ? "var(--low)" : "var(--crit)", fontFamily: "JetBrains Mono, monospace" }}>
                {signed(data.mean_xg_delta)}
              </div>
              <div style={{ fontSize: 9.5, color: "var(--dim)" }}>dakika başına, karar sonrası</div>
            </div>
            <div>
              <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>Nötr</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: "var(--mid)", fontFamily: "JetBrains Mono, monospace" }}>{data.neutral}</div>
              <div style={{ fontSize: 9.5, color: "var(--dim)" }}>net yön çıkmadı</div>
            </div>
          </div>

          {data.by_type.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>Karar tipine göre</div>
              {data.by_type.map((t) => (
                <div key={t.decision_type} style={{ display: "grid", gridTemplateColumns: "1fr 70px 70px 90px", gap: 8, padding: "5px 0", borderBottom: "1px solid var(--line)", fontSize: 11.5 }}>
                  <span style={{ color: "var(--ink)" }}>{t.label}</span>
                  <span style={{ color: "var(--muted)", textAlign: "right" }}>{t.n} karar</span>
                  <span style={{ textAlign: "right", fontWeight: 700, color: t.hit_rate != null && t.hit_rate >= 0.5 ? "var(--low)" : "var(--crit)" }}>{pct(t.hit_rate)}</span>
                  <span style={{ textAlign: "right", fontFamily: "JetBrains Mono, monospace", color: "var(--muted)" }}>{signed(t.mean_xg_delta)} xG</span>
                </div>
              ))}
            </div>
          )}

          {data.by_minute_band.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>Dakika bandına göre</div>
              <div style={{ display: "grid", gridTemplateColumns: `repeat(${data.by_minute_band.length}, 1fr)`, gap: 8, marginTop: 4 }}>
                {data.by_minute_band.map((b) => (
                  <div key={b.band} style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: b.hit_rate != null && b.hit_rate >= 0.5 ? "var(--low)" : "var(--crit)", fontFamily: "JetBrains Mono, monospace" }}>{pct(b.hit_rate)}</div>
                    <div style={{ fontSize: 10, color: "var(--muted)" }}>{b.band}</div>
                    <div style={{ fontSize: 9, color: "var(--dim)" }}>{b.n} karar</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(data.best || data.worst) && (
            <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
              {data.best && (
                <div style={{ borderLeft: "3px solid var(--low)", paddingLeft: 8 }}>
                  <div style={{ fontSize: 9.5, color: "var(--muted)", textTransform: "uppercase" }}>En iyi karar</div>
                  <div style={{ fontSize: 12 }}>{Math.round(data.best.minute)}&apos; {data.best.decision_label} · <b style={{ color: "var(--low)" }}>{signed(data.best.xg_diff_delta)} xG/dk</b></div>
                </div>
              )}
              {data.worst && (
                <div style={{ borderLeft: "3px solid var(--crit)", paddingLeft: 8 }}>
                  <div style={{ fontSize: 9.5, color: "var(--muted)", textTransform: "uppercase" }}>En kötü karar</div>
                  <div style={{ fontSize: 12 }}>{Math.round(data.worst.minute)}&apos; {data.worst.decision_label} · <b style={{ color: "var(--crit)" }}>{signed(data.worst.xg_diff_delta)} xG/dk</b></div>
                </div>
              )}
            </div>
          )}

          <div style={{ fontSize: 10, color: "var(--dim)", marginTop: 10, lineHeight: 1.5 }}>
            Vekil ölçüm: karar sonrası pencerede skor durumu, kart ve rakip hamlesi de etkilidir.
            Ölçülemeyen kararlar (kısa pencere / event yok) isabet paydasına girmez.
          </div>
        </>
      )}
    </div>
  );
}
