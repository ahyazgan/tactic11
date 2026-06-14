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
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { ConsoleShell } from "../../_console/shell";

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
  return {
    summary: {
      total: 18, resolved: 14, pending: 4,
      positive: 10, negative: 3, neutral: 1,
      hit_rate: 0.714,
      by_decision_type: {
        substitution: 8, formation_change: 4,
        tactical_instruction: 5, other: 1,
      },
    },
    decisions: [
      { id: 18, match_id: 9301, team_id: 11, minute: 78, decision_type: "substitution",
        subject_player_id: 12, related_player_id: 23, notes: "Yorgun, defansif takviye",
        recommended: true, confidence: 0.81, outcome: "pending",
        outcome_value: null, outcome_notes: null,
        created_at: "2026-06-13T20:18:12Z" },
      { id: 17, match_id: 9301, team_id: 11, minute: 65, decision_type: "tactical_instruction",
        subject_player_id: null, related_player_id: null, notes: "Pres yüksekliği düşür",
        recommended: true, confidence: 0.72, outcome: "positive",
        outcome_value: 0.6, outcome_notes: "Rakip ritmi kırıldı",
        created_at: "2026-06-13T20:05:45Z" },
      { id: 16, match_id: 9300, team_id: 11, minute: 82, decision_type: "formation_change",
        subject_player_id: null, related_player_id: null, notes: "4-2-3-1 → 4-3-3",
        recommended: true, confidence: 0.78, outcome: "positive",
        outcome_value: 0.8, outcome_notes: "85'te beraberlik golü geldi",
        created_at: "2026-06-08T19:34:21Z" },
      { id: 15, match_id: 9300, team_id: 11, minute: 70, decision_type: "substitution",
        subject_player_id: 7, related_player_id: 19, notes: "Yıldız aç → hücumcu girdi",
        recommended: true, confidence: 0.69, outcome: "negative",
        outcome_value: -0.3, outcome_notes: "Etki yok, kontradan yedik",
        created_at: "2026-06-08T19:22:10Z" },
      { id: 14, match_id: 9299, team_id: 11, minute: 55, decision_type: "tactical_instruction",
        subject_player_id: null, related_player_id: null, notes: "Kanat değişikliği — sağa overload",
        recommended: false, confidence: null, outcome: "positive",
        outcome_value: 0.5, outcome_notes: "Sağdan 2 köşe geldi",
        created_at: "2026-06-01T20:00:00Z" },
    ],
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

function SummaryCards({ summary }: { summary: RecentDecisionsResponse["summary"] }) {
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
        <div style={{ fontSize: 24, fontWeight: 800, color: hrTone, marginTop: 4 }}>
          {hrPct}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
          {summary.resolved} sonuçlanmış karar üzerinden
        </div>
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

function DecisionsTable({ rows }: { rows: DecisionRow[] }) {
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
              <td className="c" style={{ fontSize: 11.5,
                color: outcomeColor(r.outcome), fontWeight: 700 }}>
                {outcomeLabel(r.outcome)}
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

  const apiPath = !DEMO_MODE
    ? `/admin/decisions/recent?limit=${limit}`
      + (teamFilter ? `&team_external_id=${teamFilter}` : "")
    : null;
  const { data: liveData, error, isLoading } = useSWR<RecentDecisionsResponse>(
    apiPath, apiFetch, { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const data = DEMO_MODE ? demoData() : liveData;

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
        <div className="pgdesc">Yükleniyor…</div>
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
      {summary && <SummaryCards summary={summary} />}
      <div className="st" style={{ marginTop: 8, marginBottom: 8 }}>
        <h2>Son Kararlar</h2>
        <span className="ep">en yeni önce, max {limit}</span>
      </div>
      <DecisionsTable rows={rows} />
    </ConsoleShell>
  );
}
