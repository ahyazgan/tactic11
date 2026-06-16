"use client";

/**
 * Karar Takip — kayıtlı tüm kararların listesi + isabet özet.
 *
 * Backend: GET /admin/decisions/recent?limit=N[&team_external_id=X]
 *   → { summary: { total, positive, negative, neutral, pending, hit_rate,
 *                  by_decision_type }, decisions: [...] }
 *
 * DEMO_MODE: sentetik geçmiş.
 */

import { useState } from "react";
import useSWR, { mutate as swrMutate } from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { ConsoleShell } from "../../_console/shell";
import { LoadingState } from "@/components/ui";

interface DecisionRow {
  id: number;
  match_id: number;
  team_id: number;
  minute: number;
  decision_type: string;
  subject_player_id: number | null;
  related_player_id: number | null;
  notes: string | null;
  recommended: boolean;
  confidence: number | null;
  outcome: string | null;
  outcome_value: number | null;
  outcome_notes: string | null;
  created_at: string | null;
}

interface RecentDecisionsResponse {
  summary: {
    total: number;
    resolved: number;
    pending: number;
    positive: number;
    negative: number;
    neutral: number;
    hit_rate: number | null;
    by_decision_type: Record<string, number>;
  };
  decisions: DecisionRow[];
}

// --------------------------------------------------------------------------- //
// Demo veri — DEMO_MODE on
// --------------------------------------------------------------------------- //

function demoData(): RecentDecisionsResponse {
  // 12 sentetik karar — 3 pending (kullanıcı ✓/✗/○ deneyebilsin),
  // 6 pozitif + 2 negatif + 1 nötr → hit_rate %66.7 (zengin sparkline)
  const decisions: DecisionRow[] = [
    { id: 22, match_id: 9302, team_id: 11, minute: 82, decision_type: "substitution",
      subject_player_id: 14, related_player_id: 25, notes: "Hücum takviye, son 15 dk",
      recommended: true, confidence: 0.79, outcome: "pending",
      outcome_value: null, outcome_notes: null,
      created_at: "2026-06-14T19:28:01Z" },
    { id: 21, match_id: 9302, team_id: 11, minute: 70, decision_type: "tactical_instruction",
      subject_player_id: null, related_player_id: null,
      notes: "Pres yüksekliği düşür — fatigue yığını",
      recommended: true, confidence: 0.74, outcome: "pending",
      outcome_value: null, outcome_notes: null,
      created_at: "2026-06-14T19:15:43Z" },
    { id: 20, match_id: 9302, team_id: 11, minute: 55, decision_type: "tactical_instruction",
      subject_player_id: null, related_player_id: null,
      notes: "Sağ kanat overload",
      recommended: false, confidence: null, outcome: "pending",
      outcome_value: null, outcome_notes: null,
      created_at: "2026-06-14T19:00:20Z" },
    { id: 19, match_id: 9301, team_id: 11, minute: 88, decision_type: "substitution",
      subject_player_id: 3, related_player_id: 17,
      notes: "Yıldız geri çek, sonuç kilitle",
      recommended: true, confidence: 0.85, outcome: "positive",
      outcome_value: 0.7, outcome_notes: "3-2 korundu",
      created_at: "2026-06-13T20:32:01Z" },
    { id: 18, match_id: 9301, team_id: 11, minute: 78, decision_type: "substitution",
      subject_player_id: 12, related_player_id: 23,
      notes: "Yorgun, defansif takviye",
      recommended: true, confidence: 0.81, outcome: "positive",
      outcome_value: 0.6, outcome_notes: "Kontra durdu",
      created_at: "2026-06-13T20:18:12Z" },
    { id: 17, match_id: 9301, team_id: 11, minute: 65, decision_type: "tactical_instruction",
      subject_player_id: null, related_player_id: null,
      notes: "Pres yüksekliği düşür",
      recommended: true, confidence: 0.72, outcome: "positive",
      outcome_value: 0.6, outcome_notes: "Rakip ritmi kırıldı",
      created_at: "2026-06-13T20:05:45Z" },
    { id: 16, match_id: 9300, team_id: 11, minute: 82, decision_type: "formation_change",
      subject_player_id: null, related_player_id: null, notes: "4-2-3-1 → 4-3-3",
      recommended: true, confidence: 0.78, outcome: "positive",
      outcome_value: 0.8, outcome_notes: "85'te beraberlik golü geldi",
      created_at: "2026-06-08T19:34:21Z" },
    { id: 15, match_id: 9300, team_id: 11, minute: 70, decision_type: "substitution",
      subject_player_id: 7, related_player_id: 19,
      notes: "Yıldız aç → hücumcu girdi",
      recommended: true, confidence: 0.69, outcome: "negative",
      outcome_value: -0.3, outcome_notes: "Etki yok, kontradan yedik",
      created_at: "2026-06-08T19:22:10Z" },
    { id: 14, match_id: 9299, team_id: 11, minute: 55, decision_type: "tactical_instruction",
      subject_player_id: null, related_player_id: null,
      notes: "Kanat değişikliği — sağa overload",
      recommended: false, confidence: null, outcome: "positive",
      outcome_value: 0.5, outcome_notes: "Sağdan 2 köşe geldi",
      created_at: "2026-06-01T20:00:00Z" },
    { id: 13, match_id: 9299, team_id: 11, minute: 80, decision_type: "formation_change",
      subject_player_id: null, related_player_id: null,
      notes: "4-3-3 → 4-4-2 (skoru koru)",
      recommended: true, confidence: 0.66, outcome: "neutral",
      outcome_value: 0.0, outcome_notes: "Skor değişmedi",
      created_at: "2026-06-01T19:48:18Z" },
    { id: 12, match_id: 9298, team_id: 11, minute: 60, decision_type: "tactical_instruction",
      subject_player_id: null, related_player_id: null,
      notes: "Top oyununu yavaşlat",
      recommended: true, confidence: 0.71, outcome: "positive",
      outcome_value: 0.5, outcome_notes: "Tempo düştü, kontrol arttı",
      created_at: "2026-05-25T17:50:00Z" },
    { id: 11, match_id: 9298, team_id: 11, minute: 75, decision_type: "substitution",
      subject_player_id: 8, related_player_id: 21,
      notes: "Sakatlık şüphesi — değiş",
      recommended: false, confidence: null, outcome: "negative",
      outcome_value: -0.2, outcome_notes: "Yedek hazır değildi, etkisiz",
      created_at: "2026-05-25T18:05:00Z" },
  ];
  return {
    summary: {
      total: 12, resolved: 9, pending: 3,
      positive: 6, negative: 2, neutral: 1,
      hit_rate: 0.667,
      by_decision_type: {
        substitution: 5, tactical_instruction: 5, formation_change: 2,
      },
    },
    decisions,
  };
}

// --------------------------------------------------------------------------- //
// Bileşenler
// --------------------------------------------------------------------------- //

function outcomeColor(outcome: string | null): string {
  if (outcome === "positive") return "var(--low)";
  if (outcome === "negative") return "var(--crit)";
  if (outcome === "neutral") return "var(--mid)";
  return "var(--dim)";
}
function outcomeLabel(outcome: string | null): string {
  if (outcome === "positive") return "✓ Doğru";
  if (outcome === "negative") return "✗ Yanlış";
  if (outcome === "neutral") return "○ Nötr";
  if (outcome === "pending") return "⏳ Bekliyor";
  return "—";
}

/**
 * HitRateSparkline — kronolojik olarak rolling-window isabet trendi.
 * Karar listesi yeni-önce sıralı; reverse + her tick'te rolling mean.
 */
function HitRateSparkline({ rows }: { rows: DecisionRow[] }) {
  const resolved = rows
    .slice().reverse()  // chrono order
    .filter((r) => r.outcome && r.outcome !== "pending");
  if (resolved.length < 2) return null;
  const window = Math.max(3, Math.min(8, Math.floor(resolved.length / 2)));
  const points: number[] = [];
  for (let i = 0; i < resolved.length; i++) {
    const slice = resolved.slice(Math.max(0, i - window + 1), i + 1);
    const pos = slice.filter((r) => r.outcome === "positive").length;
    points.push(pos / slice.length);
  }
  const w = 100, h = 28;
  const path = points.map((p, i) => {
    const x = (i / (points.length - 1)) * w;
    const y = h - (p * h);
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const last = points[points.length - 1];
  const tone = last >= 0.66 ? "var(--low)"
    : last >= 0.4 ? "var(--mid)" : "var(--crit)";
  return (
    <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8 }}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}
        style={{ overflow: "visible" }}>
        <line x1="0" y1={h * 0.5} x2={w} y2={h * 0.5}
          stroke="var(--line)" strokeDasharray="2 3" />
        <path d={path} fill="none" stroke={tone} strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={w} cy={h - (last * h)} r="3" fill={tone} />
      </svg>
      <span style={{ fontSize: 10, color: "var(--muted)" }}>
        rolling-{window}
      </span>
    </div>
  );
}

function SummaryCards({
  summary, rows,
}: { summary: RecentDecisionsResponse["summary"]; rows: DecisionRow[] }) {
  const hr = summary.hit_rate;
  const hrPct = hr !== null ? `%${Math.round(hr * 100)}` : "—";
  const hrTone = hr === null ? "var(--dim)"
    : hr >= 0.66 ? "var(--low)"
    : hr >= 0.4 ? "var(--mid)" : "var(--crit)";
  return (
    <div style={{
      display: "grid", gap: 12, marginBottom: 16,
      gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
    }}>
      <div className="rc" style={{ borderLeft: `3px solid ${hrTone}` }}>
        <div style={{ fontSize: 10, textTransform: "uppercase",
          color: "var(--muted)", letterSpacing: 0.7, fontWeight: 700 }}>
          İsabet
        </div>
        <div style={{ fontSize: 30, fontWeight: 900, color: hrTone,
          marginTop: 4, fontFamily: "JetBrains Mono, monospace",
          lineHeight: 1 }}>
          {hrPct}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
          {summary.resolved} sonuçlanmış karar üzerinden
        </div>
        <HitRateSparkline rows={rows} />
      </div>
      <div className="rc">
        <div style={{ fontSize: 10, textTransform: "uppercase",
          color: "var(--muted)", letterSpacing: 0.7, fontWeight: 700 }}>Toplam</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: "var(--ink)",
          marginTop: 4 }}>{summary.total}</div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
          {summary.pending} bekliyor, {summary.resolved} sonuçlandı
        </div>
      </div>
      <div className="rc">
        <div style={{ fontSize: 10, textTransform: "uppercase",
          color: "var(--muted)", letterSpacing: 0.7, fontWeight: 700 }}>Pozitif</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: "var(--low)",
          marginTop: 4 }}>{summary.positive}</div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
          Beklendiği gibi sonuçlandı
        </div>
      </div>
      <div className="rc">
        <div style={{ fontSize: 10, textTransform: "uppercase",
          color: "var(--muted)", letterSpacing: 0.7, fontWeight: 700 }}>Negatif</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: "var(--crit)",
          marginTop: 4 }}>{summary.negative}</div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
          Ters sonuç verdi
        </div>
      </div>
    </div>
  );
}

function DecisionsTable({
  rows, onMarkOutcome,
}: { rows: DecisionRow[];
     onMarkOutcome?: (id: number, outcome: "positive" | "negative" | "neutral") => void }) {
  if (rows.length === 0) {
    return (
      <div className="rc" style={{ textAlign: "center", color: "var(--dim)",
        padding: 24 }}>
        Henüz kayıtlı karar yok — `/decisions/live` ekranından öneri uygula.
      </div>
    );
  }
  return (
    <div className="tbl">
      <table>
        <thead>
          <tr>
            <th>Tarih</th>
            <th>Maç</th>
            <th>Dakika</th>
            <th>Tip</th>
            <th>Not</th>
            <th className="c">Güven</th>
            <th className="c">Öneri</th>
            <th className="c">Sonuç</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td style={{ fontFamily: "JetBrains Mono",
                color: "var(--muted)", fontSize: 11, whiteSpace: "nowrap" }}>
                {r.created_at?.slice(0, 16).replace("T", " ") ?? "—"}
              </td>
              <td style={{ fontFamily: "JetBrains Mono", fontSize: 11.5 }}>
                #{r.match_id}
              </td>
              <td style={{ fontFamily: "JetBrains Mono", fontSize: 12,
                fontWeight: 700 }}>{r.minute}&apos;</td>
              <td style={{ fontSize: 11.5 }}>{r.decision_type}</td>
              <td style={{ fontSize: 11.5, color: "var(--ink)",
                maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis",
                whiteSpace: "nowrap" }} title={r.notes ?? ""}>
                {r.notes ?? <span style={{ color: "var(--dim)" }}>—</span>}
              </td>
              <td className="c" style={{ fontSize: 11.5, fontFamily: "JetBrains Mono" }}>
                {r.confidence !== null ? `%${Math.round(r.confidence * 100)}` : "—"}
              </td>
              <td className="c" style={{ fontSize: 11.5 }}>
                {r.recommended ? "✓" : "—"}
              </td>
              <td className="c">
                {r.outcome === "pending" && onMarkOutcome ? (
                  <div style={{ display: "inline-flex", gap: 4 }}>
                    <button type="button" title="Doğru çıktı"
                      onClick={() => onMarkOutcome(r.id, "positive")}
                      style={{
                        border: "1px solid var(--low)", color: "var(--low)",
                        background: "transparent", borderRadius: 4,
                        padding: "2px 7px", fontSize: 11, cursor: "pointer",
                        fontWeight: 700,
                      }}>✓</button>
                    <button type="button" title="Yanlış çıktı"
                      onClick={() => onMarkOutcome(r.id, "negative")}
                      style={{
                        border: "1px solid var(--crit)", color: "var(--crit)",
                        background: "transparent", borderRadius: 4,
                        padding: "2px 7px", fontSize: 11, cursor: "pointer",
                        fontWeight: 700,
                      }}>✗</button>
                    <button type="button" title="Nötr"
                      onClick={() => onMarkOutcome(r.id, "neutral")}
                      style={{
                        border: "1px solid var(--mid)", color: "var(--mid)",
                        background: "transparent", borderRadius: 4,
                        padding: "2px 7px", fontSize: 11, cursor: "pointer",
                        fontWeight: 700,
                      }}>○</button>
                  </div>
                ) : (
                  <span style={{
                    display: "inline-block", padding: "3px 9px",
                    borderRadius: 999, fontSize: 11, fontWeight: 700,
                    color: outcomeColor(r.outcome),
                    border: `1px solid ${outcomeColor(r.outcome)}`,
                    background: r.outcome === "positive"
                      ? "color-mix(in srgb, var(--low) 8%, transparent)"
                      : r.outcome === "negative"
                      ? "color-mix(in srgb, var(--crit) 8%, transparent)"
                      : "transparent",
                    whiteSpace: "nowrap",
                  }}>
                    {outcomeLabel(r.outcome)}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TypeBreakdown({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  return (
    <div className="rc">
      <h3>Tipe Göre Dağılım</h3>
      {entries.map(([type, n]) => (
        <div className="stat" key={type}>
          <span style={{ fontSize: 12 }}>{type}</span>
          <span className="sv">{n}</span>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Sayfa
// --------------------------------------------------------------------------- //

export default function DecisionsTrackPage() {
  const [limit, setLimit] = useState(30);
  const [teamFilter, setTeamFilter] = useState<string>("");
  // DEMO_MODE: inline outcome mark için lokal patch (ekran tazelenince geri döner)
  const [demoOverrides, setDemoOverrides] = useState<
    Record<number, "positive" | "negative" | "neutral">
  >({});

  const apiPath = !DEMO_MODE
    ? `/admin/decisions/recent?limit=${limit}`
      + (teamFilter ? `&team_external_id=${teamFilter}` : "")
    : null;
  const { data: liveData, error, isLoading } = useSWR<RecentDecisionsResponse>(
    apiPath, apiFetch, { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const rawData = DEMO_MODE ? demoData() : liveData;
  // DEMO_MODE overrides uygula → summary'yi yeniden hesapla
  const data = (() => {
    if (!rawData) return rawData;
    if (Object.keys(demoOverrides).length === 0) return rawData;
    const patched = rawData.decisions.map((d) =>
      demoOverrides[d.id] ? { ...d, outcome: demoOverrides[d.id] } : d,
    );
    const positive = patched.filter((d) => d.outcome === "positive").length;
    const negative = patched.filter((d) => d.outcome === "negative").length;
    const neutral = patched.filter((d) => d.outcome === "neutral").length;
    const pending = patched.filter((d) => d.outcome === "pending").length;
    const resolved = positive + negative + neutral;
    return {
      ...rawData,
      decisions: patched,
      summary: {
        ...rawData.summary,
        positive, negative, neutral, pending, resolved,
        hit_rate: resolved > 0 ? Number((positive / resolved).toFixed(3)) : null,
      },
    };
  })();

  async function handleMarkOutcome(
    id: number, outcome: "positive" | "negative" | "neutral",
  ) {
    if (DEMO_MODE) {
      setDemoOverrides((prev) => ({ ...prev, [id]: outcome }));
      return;
    }
    try {
      await apiFetch(`/admin/decisions/${id}/outcome`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outcome }),
      });
      if (apiPath) swrMutate(apiPath);
    } catch {
      // sessizce yut — SWR refresh tetiklenmedi, kullanıcı tekrar dener
    }
  }

  const right = (
    <>
      <div className="rc">
        <h3>Filtreler</h3>
        <div style={{ display: "grid", gap: 10 }}>
          <label style={{ fontSize: 11.5 }}>
            Limit: <b>{limit}</b>
            <input type="range" min={10} max={100} step={10} value={limit}
              onChange={(e) => setLimit(parseInt(e.target.value))}
              style={{ width: "100%", marginTop: 4 }} />
          </label>
          {!DEMO_MODE && (
            <label style={{ fontSize: 11.5 }}>Takım filtresi (external_id):
              <input type="text" value={teamFilter}
                placeholder="(boş = tümü)"
                onChange={(e) => setTeamFilter(e.target.value.trim())}
                style={{ width: "100%", marginTop: 2, padding: 6,
                  background: "var(--panel2)", color: "var(--ink)",
                  border: "1px solid var(--line)", borderRadius: 4 }} />
            </label>
          )}
        </div>
      </div>
      {data?.summary && <TypeBreakdown counts={data.summary.by_decision_type} />}
      <div className="rc">
        <h3>Açıklama</h3>
        <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.6 }}>
          Her karar için sonradan <b>outcome</b> kaydedilir (positive/negative/
          neutral). İsabet yüzdesi = pozitif / (pozitif+negatif+nötr).
          Pilot kulüpte ilk birkaç hafta bu sayı düşük çıkar; veri biriktikçe
          orkestra güven skoru kalibre olur.
        </div>
      </div>
    </>
  );

  if (!DEMO_MODE && isLoading) {
    return (
      <ConsoleShell active="/decisions/track" title="Karar Takip"
        sub="GET /admin/decisions/recent" right={right}>
        <LoadingState />
      </ConsoleShell>
    );
  }
  if (!DEMO_MODE && error) {
    return (
      <ConsoleShell active="/decisions/track" title="Karar Takip" right={right}>
        <div className="pgdesc">Yüklenemedi: {String(error).slice(0, 200)}</div>
      </ConsoleShell>
    );
  }

  const summary = data?.summary;
  const rows = data?.decisions ?? [];

  return (
    <ConsoleShell
      active="/decisions/track"
      title="Karar Takip"
      sub={summary
        ? `${summary.total} karar · isabet: ${summary.hit_rate !== null
          ? `%${Math.round(summary.hit_rate * 100)}` : "—"}`
        : "—"}
      desc="Maç-içi panelden uygulanan kararların geçmişi + isabet özet. Outcome reconcile job'u tarafından doldurulur (FT olan maçlarda)."
      right={right}
    >
      {summary && <SummaryCards summary={summary} rows={rows} />}
      <div className="st" style={{ marginTop: 8, marginBottom: 8 }}>
        <h2>Son Kararlar</h2>
        <span className="ep">en yeni önce, max {limit}</span>
      </div>
      <DecisionsTable rows={rows} onMarkOutcome={handleMarkOutcome} />
    </ConsoleShell>
  );
}
