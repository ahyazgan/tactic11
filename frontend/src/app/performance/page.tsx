"use client";

/**
 * Performans Testi — tablet veri-giriş ekranı.
 *
 * Saha/laboratuvar kullanımı için tasarlandı: büyük dokunma hedefleri,
 * protokol kütüphanesinden seçim, sayısal değer girişi, anında değerlendirme
 * (norm + güçlü/zayıf) ve KVKK uyumlu PDF rapor indirme.
 *
 * Backend:
 *   GET  /admin/performance/protocols       — protokol kütüphanesi
 *   POST /physical-tests/                    — her sonuç KALICI kayıt (geçmiş/trend/risk)
 *   POST /admin/performance/battery          — batarya değerlendirme (anlık profil)
 *   POST /reports/performance/pdf            — PDF rapor (özel nitelikli veri)
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch, getAccessToken } from "@/lib/api";
import { Panel } from "@/components/ui";

interface Protocol {
  key: string;
  name: string;
  unit: string;
  higher_is_better: boolean;
  description: string;
}

interface TestScore {
  protocol_key: string;
  protocol_name: string;
  raw_value: number;
  unit: string;
  rating: string;
  squad_percentile: number | null;
  note: string;
}

interface BatteryReport {
  player_external_id: number;
  scores: TestScore[];
  weak_areas: string[];
  strong_areas: string[];
}

interface Row {
  id: number;
  protocol_key: string;
  raw_value: string;
}

const RATING_STYLE: Record<string, string> = {
  elit: "text-emerald-400 border-emerald-700",
  iyi: "text-green-400 border-green-700",
  ortalama: "text-amber-400 border-amber-700",
  zayıf: "text-red-400 border-red-700",
};

let _rowSeq = 1;

export default function PerformanceEntryPage() {
  const { data: lib } = useSWR<{ protocols: Protocol[] }>(
    "/admin/performance/protocols",
    apiFetch,
  );
  const protocols = lib?.protocols ?? [];

  const [playerName, setPlayerName] = React.useState("");
  const [playerId, setPlayerId] = React.useState("");
  const [testDate, setTestDate] = React.useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [rows, setRows] = React.useState<Row[]>([
    { id: _rowSeq++, protocol_key: "", raw_value: "" },
  ]);
  const [report, setReport] = React.useState<BatteryReport | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [savedCount, setSavedCount] = React.useState<number | null>(null);

  function updateRow(id: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setRows((rs) => [...rs, { id: _rowSeq++, protocol_key: "", raw_value: "" }]);
  }
  function removeRow(id: number) {
    setRows((rs) => (rs.length > 1 ? rs.filter((r) => r.id !== id) : rs));
  }

  function validResults(): [string, number][] {
    return rows
      .filter((r) => r.protocol_key && r.raw_value.trim() !== "")
      .map((r) => [r.protocol_key, Number(r.raw_value)] as [string, number])
      .filter(([, v]) => !Number.isNaN(v));
  }

  /** Her sonucu /physical-tests/'e KALICI kaydet (best-effort) → geçmiş/trend/risk
   *  akışına girer. Değerlendirmeyi bloklamamak için satır-bazlı hata yutulur. */
  async function persistResults(): Promise<number> {
    let ok = 0;
    for (const [protocol, value] of validResults()) {
      try {
        await apiFetch("/physical-tests/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            player_id: playerId || "0",
            player_name: playerName || `Oyuncu #${playerId || 0}`,
            test_date: testDate,
            protocol,
            value,
          }),
        });
        ok++;
      } catch {
        /* best-effort — bir protokol kaydedilemese de değerlendirme sürsün */
      }
    }
    return ok;
  }

  async function evaluate() {
    setError(null);
    setBusy(true);
    setSavedCount(null);
    try {
      // 1) Kalıcı kayıt (geçmiş/trend/risk için), 2) anında değerlendirme.
      const saved = await persistResults();
      setSavedCount(saved);
      const res = await apiFetch<BatteryReport>("/admin/performance/battery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          player_id: Number(playerId) || 0,
          results: validResults(),
        }),
      });
      setReport(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Değerlendirme başarısız");
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf() {
    setError(null);
    setBusy(true);
    try {
      const token = getAccessToken();
      const res = await fetch("/api/reports/performance/pdf", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          player_name: playerName || `Oyuncu #${playerId || 0}`,
          player_id: Number(playerId) || 0,
          results: validResults(),
          test_date: testDate,
        }),
      });
      if (!res.ok) {
        if (res.status === 503) {
          throw new Error("PDF üretici sunucuda devre dışı (reportlab yok)");
        }
        throw new Error(`PDF üretilemedi (HTTP ${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `performans_oyuncu_${playerId || 0}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "PDF indirme başarısız");
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = validResults().length > 0 && !busy;
  const activeProtocol = (key: string) =>
    protocols.find((p) => p.key === key);

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-center justify-between gap-3 bg-surface2 border border-borderlt rounded-md px-4 py-3">
        <div className="text-[12px] text-text">
          <b>Bu modül yenilendi.</b>{" "}
          <span className="text-textmut">
            Kalıcı kayıt + yük riski + trend + PDF artık <b>Yük Riski</b> panelinde.
          </span>
        </div>
        <Link
          href="/physical-tests"
          className="shrink-0 text-[11px] uppercase tracking-wide px-3 py-1.5 rounded bg-accent text-bg font-semibold"
        >
          Yeni panele git →
        </Link>
      </div>

      <div className="flex items-center gap-1 border-b border-border">
        <Link
          href="/physical-tests"
          className="px-3 py-2 text-[12.5px] font-semibold text-textmut hover:text-text border-b-2 border-transparent"
          title="Risk halkası + kadro + geçmiş"
        >
          Panel
        </Link>
        <span className="px-3 py-2 text-[12.5px] font-semibold text-text border-b-2 border-brand">
          Veri Girişi &amp; Batarya
        </span>
      </div>

      <div>
        <h1 className="text-lg font-semibold text-text">
          Performans Testi — Veri Girişi
        </h1>
        <p className="text-[11px] text-textmut mt-1">
          Sağlık/performans verisi KVKK&apos;da özel nitelikli kişisel veridir;
          erişim ve dışa aktarım denetim kaydına yazılır.
        </p>
      </div>

      <Panel title="Oyuncu">
        <div className="grid sm:grid-cols-3 gap-3">
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider text-textmut">
              Ad
            </span>
            <input
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
              placeholder="Oyuncu adı"
              className="mt-1 w-full bg-surface2 border border-border text-text text-base px-3 h-11 rounded"
            />
          </label>
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider text-textmut">
              Oyuncu ID
            </span>
            <input
              value={playerId}
              onChange={(e) => setPlayerId(e.target.value.replace(/[^0-9]/g, ""))}
              inputMode="numeric"
              placeholder="örn. 42"
              className="mt-1 w-full bg-surface2 border border-border text-text text-base px-3 h-11 rounded"
            />
          </label>
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider text-textmut">
              Test tarihi
            </span>
            <input
              type="date"
              value={testDate}
              onChange={(e) => setTestDate(e.target.value)}
              className="mt-1 w-full bg-surface2 border border-border text-text text-base px-3 h-11 rounded"
            />
          </label>
        </div>
      </Panel>

      <Panel
        title="Test Sonuçları"
        actions={
          <button
            type="button"
            onClick={addRow}
            className="text-[11px] uppercase tracking-wide px-3 py-1 rounded border border-borderlt text-accent hover:bg-surface2"
          >
            + Test ekle
          </button>
        }
      >
        <div className="space-y-3">
          {rows.map((row) => {
            const proto = activeProtocol(row.protocol_key);
            return (
              <div key={row.id} className="space-y-1">
                <div className="flex items-end gap-2">
                  <label className="flex-1 block">
                    <span className="text-[10px] uppercase tracking-wider text-textmut">
                      Protokol
                    </span>
                    <select
                      value={row.protocol_key}
                      onChange={(e) =>
                        updateRow(row.id, { protocol_key: e.target.value })
                      }
                      className="mt-1 w-full bg-surface2 border border-border text-text text-base px-2 h-11 rounded"
                    >
                      <option value="">Test seç…</option>
                      {protocols.map((p) => (
                        <option key={p.key} value={p.key}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="w-32 block">
                    <span className="text-[10px] uppercase tracking-wider text-textmut">
                      Değer {proto ? `(${proto.unit})` : ""}
                    </span>
                    <input
                      value={row.raw_value}
                      onChange={(e) =>
                        updateRow(row.id, {
                          raw_value: e.target.value.replace(/[^0-9.]/g, ""),
                        })
                      }
                      inputMode="decimal"
                      placeholder="0"
                      className="mt-1 w-full bg-surface2 border border-border text-text text-base px-3 h-11 rounded text-right"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => removeRow(row.id)}
                    disabled={rows.length <= 1}
                    aria-label="Satırı sil"
                    className="h-11 w-11 shrink-0 rounded border border-borderlt text-textdim hover:bg-surface2 disabled:opacity-30"
                  >
                    ×
                  </button>
                </div>
                {proto && (
                  <p className="text-[11px] text-textmut leading-snug">
                    {proto.description}
                  </p>
                )}
              </div>
            );
          })}
        </div>

        {error && (
          <p className="mt-3 text-[12px] text-red-400">{error}</p>
        )}
        {savedCount !== null && savedCount > 0 && (
          <p className="mt-3 text-[12px] text-ok">
            {savedCount} sonuç kaydedildi — geçmiş, trend ve risk panellerine işlendi.
          </p>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={evaluate}
            disabled={!canSubmit}
            className="px-4 h-11 rounded bg-accent text-black font-semibold text-sm disabled:opacity-40"
          >
            {busy ? "İşleniyor…" : "Kaydet & Değerlendir"}
          </button>
          <button
            type="button"
            onClick={downloadPdf}
            disabled={!canSubmit}
            className="px-4 h-11 rounded border border-borderlt text-accent text-sm hover:bg-surface2 disabled:opacity-40"
          >
            PDF Rapor indir
          </button>
        </div>
      </Panel>

      {report && (
        <Panel title="Değerlendirme">
          <div className="space-y-2">
            {report.scores.map((s) => (
              <div
                key={s.protocol_key}
                className="flex items-center justify-between gap-3 py-2 border-b border-border last:border-0"
              >
                <div className="min-w-0">
                  <div className="text-sm text-text truncate">
                    {s.protocol_name}
                  </div>
                  <div className="text-[11px] text-textmut">
                    {s.raw_value} {s.unit}
                    {s.squad_percentile != null
                      ? ` · kadro %${s.squad_percentile}`
                      : ""}
                  </div>
                </div>
                <span
                  className={`shrink-0 text-[11px] uppercase tracking-wide px-2 py-1 rounded border ${
                    RATING_STYLE[s.rating] ?? "text-textdim border-borderlt"
                  }`}
                >
                  {s.rating}
                </span>
              </div>
            ))}
          </div>

          {(report.strong_areas.length > 0 ||
            report.weak_areas.length > 0) && (
            <div className="mt-3 grid sm:grid-cols-2 gap-3 text-[12px]">
              {report.strong_areas.length > 0 && (
                <div>
                  <div className="text-emerald-400 uppercase text-[10px] tracking-wider mb-1">
                    Güçlü yönler
                  </div>
                  <div className="text-textmut">
                    {report.strong_areas.join(", ")}
                  </div>
                </div>
              )}
              {report.weak_areas.length > 0 && (
                <div>
                  <div className="text-red-400 uppercase text-[10px] tracking-wider mb-1">
                    Gelişim alanları
                  </div>
                  <div className="text-textmut">
                    {report.weak_areas.join(", ")}
                  </div>
                </div>
              )}
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
