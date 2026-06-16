"use client";

import { useState } from "react";
import { ConsoleShell } from "../_console/shell";
import { Panel, Pill, EmptyState, LoadingState } from "@/components/ui";
import { apiFetch } from "@/lib/api";

interface PlayerRow {
  player_external_id: string;
  rating: string;
  minute_played: string;
  fatigue_proxy: string;
  note: string;
}

interface SaveResult {
  match_external_id: number;
  created: number;
  updated: number;
  total: number;
}

interface PerfResult {
  player_external_id: number;
  count: number;
  results: {
    consistency?: { value: { consistency_label: string; mean: number; reliability_score: number } };
    trajectory?: { value: { direction: string; slope: number } };
    anomaly?: { value: { overall_risk: string; summary: string } };
    clutch?: { value: { label: string; clutch_factor: number } };
    opponent_adjusted?: { value: { adjusted_mean: number; delta_mean: number } };
  };
}

const MATCH_FLAGS = [
  { key: "big_match", label: "Büyük maç / derbi" },
  { key: "close_game", label: "Yakın skor" },
  { key: "knockout", label: "Eleme" },
  { key: "opp_strong", label: "Güçlü rakip" },
];

function emptyRow(): PlayerRow {
  return {
    player_external_id: "",
    rating: "7.0",
    minute_played: "90",
    fatigue_proxy: "",
    note: "",
  };
}

export default function MacNotlaPage() {
  const [matchId, setMatchId] = useState("");
  const [kickoff, setKickoff] = useState("");
  const [oppRating, setOppRating] = useState("7.0");
  const [flags, setFlags] = useState<Record<string, boolean>>({});
  const [rows, setRows] = useState<PlayerRow[]>([emptyRow(), emptyRow(), emptyRow()]);
  const [saveResult, setSaveResult] = useState<SaveResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Performans yükleme bölümü
  const [perfPlayerId, setPerfPlayerId] = useState("");
  const [perf, setPerf] = useState<PerfResult | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);

  function updateRow(i: number, patch: Partial<PlayerRow>) {
    setRows((prev) => prev.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }

  function toggleFlag(key: string) {
    setFlags((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  async function loadMatch() {
    if (!matchId) return;
    setErr(null);
    try {
      const r = await apiFetch<{ ratings: {
        player_external_id: number; rating: number; minute_played: number;
        fatigue_proxy: number | null; note: string | null;
        opp_rating: number | null; flags: Record<string, boolean>;
      }[] }>(`/admin/ratings/match/${matchId}`);
      if (r.ratings.length > 0) {
        setRows(r.ratings.map((rr) => ({
          player_external_id: String(rr.player_external_id),
          rating: String(rr.rating),
          minute_played: String(rr.minute_played),
          fatigue_proxy: rr.fatigue_proxy != null ? String(rr.fatigue_proxy) : "",
          note: rr.note ?? "",
        })));
        if (r.ratings[0].opp_rating != null) setOppRating(String(r.ratings[0].opp_rating));
        if (r.ratings[0].flags) setFlags(r.ratings[0].flags);
      }
    } catch (e) {
      setErr(String(e));
    }
  }

  async function save() {
    if (!matchId) {
      setErr("Maç ID gir");
      return;
    }
    const ratings = rows
      .filter((r) => r.player_external_id.trim() !== "")
      .map((r) => ({
        player_external_id: parseInt(r.player_external_id),
        rating: parseFloat(r.rating) || 0,
        minute_played: parseFloat(r.minute_played) || 90,
        opp_rating: parseFloat(oppRating) || undefined,
        fatigue_proxy: r.fatigue_proxy ? parseFloat(r.fatigue_proxy) : undefined,
        flags,
        note: r.note || undefined,
      }));
    if (ratings.length === 0) {
      setErr("En az 1 oyuncu notu gir");
      return;
    }
    setErr(null);
    setSaving(true);
    try {
      const res = await apiFetch<SaveResult>("/admin/ratings/match", {
        method: "POST",
        body: JSON.stringify({
          match_external_id: parseInt(matchId),
          kickoff: kickoff ? new Date(kickoff).toISOString() : undefined,
          ratings,
        }),
      });
      setSaveResult(res);
    } catch (e) {
      setErr(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function loadPerformance() {
    if (!perfPlayerId) return;
    setPerfLoading(true);
    try {
      const res = await apiFetch<PerfResult>(
        `/admin/ratings/player/${perfPlayerId}/performance`,
      );
      setPerf(res);
    } catch (e) {
      console.error(e);
    } finally {
      setPerfLoading(false);
    }
  }

  return (
    <ConsoleShell
      active="/mac-notla"
      title="Maçı Notla"
      desc="Oyuncuları 1-10 notla + maç bağlamını işaretle → kaydet. Kaydedilen seri tüm performans motorlarını (tutarlılık / yön / anomali / clutch / rakibe göre) otomatik besler."
    >
      <div className="space-y-6">
      <Panel title="Maç bilgisi">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Maç ID *</span>
            <input
              type="number"
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={matchId}
              onChange={(e) => setMatchId(e.target.value)}
            />
          </label>
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Tarih</span>
            <input
              type="date"
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={kickoff}
              onChange={(e) => setKickoff(e.target.value)}
            />
          </label>
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Rakip gücü (0-10)</span>
            <input
              type="number" step={0.1} min={0} max={10}
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={oppRating}
              onChange={(e) => setOppRating(e.target.value)}
            />
          </label>
          <div className="flex items-end">
            <button
              className="px-3 py-1.5 text-xs border border-border rounded hover:bg-surface2"
              onClick={loadMatch}
            >
              Mevcut maçı yükle
            </button>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {MATCH_FLAGS.map((f) => (
            <button
              key={f.key}
              onClick={() => toggleFlag(f.key)}
              className={`text-xs px-2 py-1 rounded border ${
                flags[f.key]
                  ? "border-accent bg-accent/15 text-accent"
                  : "border-border text-muted hover:bg-surface2"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </Panel>

      <Panel
        title="Oyuncu notları"
        actions={
          <button
            className="text-xs px-2 py-1 border border-border rounded hover:bg-surface2"
            onClick={() => setRows((p) => [...p, emptyRow()])}
          >
            + Oyuncu ekle
          </button>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-muted">
                <th className="p-1 text-left">Oyuncu ID</th>
                <th className="p-1 text-left">Rating (1-10)</th>
                <th className="p-1 text-left">Dakika</th>
                <th className="p-1 text-left">Yorgunluk (0-1)</th>
                <th className="p-1 text-left">Not</th>
                <th className="p-1"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  <td className="p-1">
                    <input
                      type="number"
                      className="w-20 bg-bg border border-border rounded px-2 py-1 text-sm"
                      value={row.player_external_id}
                      onChange={(e) => updateRow(i, { player_external_id: e.target.value })}
                    />
                  </td>
                  <td className="p-1">
                    <input
                      type="number" step={0.1} min={1} max={10}
                      className="w-20 bg-bg border border-border rounded px-2 py-1 text-sm"
                      value={row.rating}
                      onChange={(e) => updateRow(i, { rating: e.target.value })}
                    />
                  </td>
                  <td className="p-1">
                    <input
                      type="number" min={0} max={120}
                      className="w-16 bg-bg border border-border rounded px-2 py-1 text-sm"
                      value={row.minute_played}
                      onChange={(e) => updateRow(i, { minute_played: e.target.value })}
                    />
                  </td>
                  <td className="p-1">
                    <input
                      type="number" step={0.05} min={0} max={1}
                      placeholder="—"
                      className="w-16 bg-bg border border-border rounded px-2 py-1 text-sm"
                      value={row.fatigue_proxy}
                      onChange={(e) => updateRow(i, { fatigue_proxy: e.target.value })}
                    />
                  </td>
                  <td className="p-1">
                    <input
                      type="text"
                      className="w-full bg-bg border border-border rounded px-2 py-1 text-sm"
                      value={row.note}
                      onChange={(e) => updateRow(i, { note: e.target.value })}
                    />
                  </td>
                  <td className="p-1">
                    <button
                      className="text-xs text-bad px-1"
                      onClick={() => setRows((p) => p.filter((_, j) => j !== i))}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex items-center gap-3">
          <button
            className="px-4 py-1.5 bg-accent text-white text-sm rounded"
            onClick={save}
            disabled={saving}
          >
            {saving ? "Kaydediliyor…" : "Kaydet"}
          </button>
          {err && <span className="text-bad text-sm">{err}</span>}
          {saveResult && (
            <span className="text-sm text-good">
              ✓ Kaydedildi — {saveResult.created} yeni, {saveResult.updated} güncellendi
              (toplam {saveResult.total})
            </span>
          )}
        </div>
      </Panel>

      <Panel title="Oyuncu performansı (kayıtlı seriden)">
        <div className="flex items-end gap-3 mb-3">
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Oyuncu ID</span>
            <input
              type="number"
              className="w-28 bg-bg border border-border rounded px-2 py-1 text-sm"
              value={perfPlayerId}
              onChange={(e) => setPerfPlayerId(e.target.value)}
            />
          </label>
          <button
            className="px-3 py-1.5 bg-accent text-white text-sm rounded"
            onClick={loadPerformance}
            disabled={perfLoading}
          >
            {perfLoading ? "Yükleniyor…" : "Performansı getir"}
          </button>
        </div>

        {perfLoading && <LoadingState label="Performans hesaplanıyor…" />}

        {!perfLoading && perf && perf.count === 0 && (
          <EmptyState
            title="Kayıtlı not yok"
            hint="Bu oyuncu için henüz maç notu girilmemiş. Yukarıdan notları kaydet, sonra tekrar getir."
          />
        )}

        {!perfLoading && perf && perf.count > 0 && (
          <div className="space-y-2 text-sm">
            <p className="text-xs text-muted">{perf.count} maç notu üzerinden:</p>
            {perf.results.consistency && (
              <div className="flex items-center gap-2">
                <Pill variant={perf.results.consistency.value.consistency_label === "high" ? "win" : perf.results.consistency.value.consistency_label === "volatile" ? "warn" : "neutral"}>
                  {perf.results.consistency.value.consistency_label}
                </Pill>
                <span>
                  Tutarlılık — mean {perf.results.consistency.value.mean.toFixed(2)},
                  reliability {perf.results.consistency.value.reliability_score.toFixed(0)}
                </span>
              </div>
            )}
            {perf.results.trajectory && (
              <div className="flex items-center gap-2">
                <Pill variant={perf.results.trajectory.value.direction === "improving" ? "win" : perf.results.trajectory.value.direction === "declining" ? "loss" : "neutral"}>
                  {perf.results.trajectory.value.direction}
                </Pill>
                <span>Yön — slope {perf.results.trajectory.value.slope.toFixed(3)}/maç</span>
              </div>
            )}
            {perf.results.anomaly && (
              <div className="flex items-center gap-2">
                <Pill variant={perf.results.anomaly.value.overall_risk === "high" ? "loss" : perf.results.anomaly.value.overall_risk === "medium" ? "warn" : "win"}>
                  risk: {perf.results.anomaly.value.overall_risk}
                </Pill>
                <span className="text-xs text-muted">{perf.results.anomaly.value.summary}</span>
              </div>
            )}
            {perf.results.clutch && (
              <div className="flex items-center gap-2">
                <Pill variant={perf.results.clutch.value.label === "clutch" ? "win" : perf.results.clutch.value.label === "chokes" ? "loss" : "neutral"}>
                  {perf.results.clutch.value.label}
                </Pill>
                <span>Clutch factor {perf.results.clutch.value.clutch_factor.toFixed(2)}</span>
              </div>
            )}
            {perf.results.opponent_adjusted && (
              <div className="flex items-center gap-2">
                <span>
                  Rakibe göre düzeltilmiş: {perf.results.opponent_adjusted.value.adjusted_mean.toFixed(2)}{" "}
                  (Δ {perf.results.opponent_adjusted.value.delta_mean >= 0 ? "+" : ""}
                  {perf.results.opponent_adjusted.value.delta_mean.toFixed(2)})
                </span>
              </div>
            )}
          </div>
        )}
      </Panel>
      </div>
    </ConsoleShell>
  );
}
