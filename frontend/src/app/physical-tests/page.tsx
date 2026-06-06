"use client";

/**
 * Fiziksel Performans Testi — yük/risk modülü UI.
 *
 * Oyuncu seç → test gir → geçmiş + renk kodlu yük riski + protokol trend grafiği.
 * Backend (physical_tests router):
 *   POST /physical-tests/                  — test kaydı
 *   GET  /physical-tests/{player_id}       — geçmiş
 *   GET  /physical-tests/{player_id}/risk  — yük riski raporu
 *   GET  /physical-tests/{player_id}/trend?protocol=... — zaman serisi
 */

import * as React from "react";
import useSWR from "swr";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiFetch } from "@/lib/api";
import { Panel } from "@/components/ui";

interface PhysicalTest {
  id: number;
  player_id: string;
  player_name: string;
  test_date: string;
  protocol: string;
  value: number;
  unit: string | null;
  notes: string | null;
  recorded_by: string | null;
}

interface RiskReport {
  player_id: string;
  player_name: string;
  risk_score: number;
  risk_label: string;
  flags: { protocol: string; message: string }[];
  summary: string;
  recommendations: string[];
}

interface TrendReport {
  player_id: string;
  protocol: string;
  direction: string;
  slope: number;
  lower_is_better: boolean;
  points: { test_date: string; value: number }[];
}

const PROTOCOLS: { key: string; label: string; unit: string }[] = [
  { key: "sprint_10m", label: "10m Sprint", unit: "sn" },
  { key: "sprint_30m", label: "30m Sprint", unit: "sn" },
  { key: "yoyo_irl1", label: "YoYo IR1", unit: "seviye" },
  { key: "yoyo_irl2", label: "YoYo IR2", unit: "seviye" },
  { key: "cmj", label: "CMJ (Sıçrama)", unit: "cm" },
  { key: "sj", label: "Squat Jump", unit: "cm" },
  { key: "isokinetic_quad", label: "İzokinetik Quad", unit: "Nm/kg" },
  { key: "isokinetic_ham", label: "İzokinetik Ham", unit: "Nm/kg" },
  { key: "vo2max", label: "VO2max", unit: "ml/kg/min" },
  { key: "gps_total_dist", label: "GPS Toplam Mesafe", unit: "m" },
  { key: "gps_hir_dist", label: "GPS Yüksek Şiddet", unit: "m" },
  { key: "gps_acc_count", label: "GPS Atak Sayısı", unit: "adet" },
  { key: "body_fat_pct", label: "Vücut Yağı", unit: "%" },
  { key: "custom", label: "Serbest", unit: "" },
];

const RISK_COLORS: Record<string, string> = {
  Düşük: "bg-ok/20 text-ok border-ok/40",
  Orta: "bg-warn/20 text-warn border-warn/40",
  Yüksek: "bg-orange-500/20 text-orange-400 border-orange-500/40",
  Kritik: "bg-danger/20 text-danger border-danger/40",
  "Veri Yok": "bg-surface2 text-textmut border-border",
};

const DIRECTION_LABEL: Record<string, string> = {
  improving: "İyileşiyor ↗",
  worsening: "Kötüleşiyor ↘",
  stable: "Sabit →",
  insufficient: "Yetersiz veri",
};

function protocolLabel(key: string): string {
  return PROTOCOLS.find((p) => p.key === key)?.label ?? key;
}

export default function PhysicalTestsPage() {
  // Arama: hangi oyuncu görüntüleniyor
  const [query, setQuery] = React.useState<string>("");
  const [searchInput, setSearchInput] = React.useState<string>("");

  // Test giriş formu
  const [playerId, setPlayerId] = React.useState("");
  const [playerName, setPlayerName] = React.useState("");
  const [testDate, setTestDate] = React.useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [protocol, setProtocol] = React.useState("sprint_10m");
  const [value, setValue] = React.useState("");
  const [recordedBy, setRecordedBy] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Trend protokol seçimi
  const [trendProtocol, setTrendProtocol] = React.useState("sprint_10m");

  const history = useSWR<PhysicalTest[]>(
    query ? `/physical-tests/${query}` : null,
    apiFetch,
  );
  const hasData = (history.data?.length ?? 0) > 0;

  const risk = useSWR<RiskReport>(
    query && hasData ? `/physical-tests/${query}/risk` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  const trend = useSWR<TrendReport>(
    query && hasData ? `/physical-tests/${query}/trend?protocol=${trendProtocol}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );

  async function submitTest(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await apiFetch("/physical-tests/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          player_id: playerId,
          player_name: playerName,
          test_date: testDate,
          protocol,
          value: Number(value),
          recorded_by: recordedBy || null,
        }),
      });
      setValue("");
      // Girilen oyuncuyu görüntüle + listeleri tazele
      setQuery(playerId);
      setSearchInput(playerId);
      history.mutate();
      risk.mutate();
      trend.mutate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kayıt başarısız");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-6xl space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-text">Fiziksel Performans Testi</h1>
        <p className="text-[12px] text-textmut mt-0.5">
          Saha test sonuçları + yükleme riski + protokol trendi. Veriler KVKK
          kapsamında özel nitelikli — erişim denetim loguna işlenir.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Test giriş formu */}
        <Panel title="Yeni test kaydı">
          <form onSubmit={submitTest} className="space-y-2 text-[13px]">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Oyuncu ID">
                <input
                  required
                  value={playerId}
                  onChange={(e) => setPlayerId(e.target.value)}
                  className={inputCls}
                  placeholder="API-Football id"
                />
              </Field>
              <Field label="Oyuncu adı">
                <input
                  required
                  value={playerName}
                  onChange={(e) => setPlayerName(e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="Tarih">
                <input
                  type="date"
                  required
                  value={testDate}
                  onChange={(e) => setTestDate(e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="Protokol">
                <select
                  value={protocol}
                  onChange={(e) => setProtocol(e.target.value)}
                  className={inputCls}
                >
                  {PROTOCOLS.map((p) => (
                    <option key={p.key} value={p.key}>
                      {p.label} {p.unit ? `(${p.unit})` : ""}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Değer">
                <input
                  type="number"
                  step="any"
                  required
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="Kaydeden">
                <input
                  value={recordedBy}
                  onChange={(e) => setRecordedBy(e.target.value)}
                  className={inputCls}
                  placeholder="opsiyonel"
                />
              </Field>
            </div>
            {error && <div className="text-[12px] text-danger">{error}</div>}
            <button
              type="submit"
              disabled={busy}
              className="w-full mt-1 py-2 rounded bg-accent text-bg font-medium text-[13px] disabled:opacity-50"
            >
              {busy ? "Kaydediliyor…" : "Kaydet"}
            </button>
          </form>
        </Panel>

        {/* Risk kartı */}
        <Panel title="Yükleme riski">
          {!query && (
            <p className="text-[12px] text-textmut">
              Oyuncu ID gir veya aşağıdan ara.
            </p>
          )}
          {query && !hasData && (
            <p className="text-[12px] text-textmut">
              Bu oyuncu için test kaydı yok.
            </p>
          )}
          {risk.data && (
            <div className="space-y-2">
              <div
                className={`inline-block px-2 py-1 rounded border text-[12px] font-semibold ${
                  RISK_COLORS[risk.data.risk_label] ?? RISK_COLORS["Veri Yok"]
                }`}
              >
                {risk.data.risk_label} · skor {risk.data.risk_score}
              </div>
              <p className="text-[13px] text-text">{risk.data.summary}</p>
              {risk.data.flags.length > 0 && (
                <ul className="text-[12px] text-textmut list-disc pl-4 space-y-0.5">
                  {risk.data.flags.map((f, i) => (
                    <li key={i}>{f.message}</li>
                  ))}
                </ul>
              )}
              {risk.data.recommendations.length > 0 && (
                <div className="text-[12px] text-text">
                  <div className="font-semibold mt-1">Öneriler</div>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {risk.data.recommendations.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>

      {/* Geçmiş + arama */}
      <Panel
        title="Test geçmişi"
        actions={
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(searchInput.trim());
            }}
            className="flex items-center gap-2"
          >
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Oyuncu ID"
              className={`${inputCls} h-7 w-32`}
            />
            <button
              type="submit"
              className="text-[11px] uppercase px-2 py-1 rounded border border-borderlt text-textmut hover:text-text"
            >
              Getir
            </button>
          </form>
        }
      >
        {!hasData && (
          <p className="text-[12px] text-textmut">Kayıt yok.</p>
        )}
        {hasData && (
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-textmut text-left border-b border-border">
                <th className="py-1 pr-2">Tarih</th>
                <th className="py-1 pr-2">Protokol</th>
                <th className="py-1 pr-2 text-right">Değer</th>
                <th className="py-1 pr-2">Birim</th>
                <th className="py-1">Kaydeden</th>
              </tr>
            </thead>
            <tbody>
              {history.data?.map((t) => (
                <tr key={t.id} className="border-b border-border/50">
                  <td className="py-1 pr-2">{t.test_date}</td>
                  <td className="py-1 pr-2">{protocolLabel(t.protocol)}</td>
                  <td className="py-1 pr-2 text-right tabular-nums">{t.value}</td>
                  <td className="py-1 pr-2 text-textmut">{t.unit ?? "—"}</td>
                  <td className="py-1 text-textmut">{t.recorded_by ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {/* Trend grafiği */}
      <Panel
        title="Protokol trendi"
        actions={
          <select
            value={trendProtocol}
            onChange={(e) => setTrendProtocol(e.target.value)}
            className={`${inputCls} h-7`}
          >
            {PROTOCOLS.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </select>
        }
      >
        {!hasData && (
          <p className="text-[12px] text-textmut">Önce bir oyuncu getirin.</p>
        )}
        {hasData && trend.error && (
          <p className="text-[12px] text-textmut">
            {protocolLabel(trendProtocol)} için ölçüm yok.
          </p>
        )}
        {trend.data && trend.data.points.length > 0 && (
          <div>
            <div className="text-[12px] text-textmut mb-2">
              {protocolLabel(trend.data.protocol)} ·{" "}
              <span className="text-text">
                {DIRECTION_LABEL[trend.data.direction] ?? trend.data.direction}
              </span>{" "}
              (eğim {trend.data.slope})
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart
                data={trend.data.points.map((p) => ({
                  label: p.test_date,
                  value: p.value,
                }))}
                margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#888" }} />
                <YAxis tick={{ fontSize: 11, fill: "#888" }} domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{
                    background: "#1a1a1a",
                    border: "1px solid #333",
                    fontSize: 12,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={
                    trend.data.direction === "improving"
                      ? "#22c55e"
                      : trend.data.direction === "worsening"
                      ? "#ef4444"
                      : "#3b82f6"
                  }
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>
    </div>
  );
}

const inputCls =
  "w-full bg-surface2 border border-border text-text text-[13px] px-2 py-1.5 rounded";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[11px] text-textmut mb-0.5">{label}</span>
      {children}
    </label>
  );
}
