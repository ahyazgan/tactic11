"use client";

/**
 * Tıbbi Merkez — sakatlık/rehabilitasyon takibi (return_to_play).
 *
 * Oyuncu seç → aktif rehab kayıtları (sakatlık tipi, durum, dönüş tarihi,
 * kalan gün) + yeni rehab kaydı. Yük geçmişi için Yük Riski paneline link.
 *
 * Backend:
 *   GET  /players/{id}/rehab/active   — aktif rehab kayıtları
 *   POST /players/{id}/rehab          — yeni kayıt
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel } from "@/components/ui";

interface Rehab {
  id: number;
  player_external_id: number;
  injury_type: string;
  injury_start: string;
  expected_return: string | null;
  actual_return: string | null;
  status: string;
  notes: string | null;
}

const STATUS_STYLE: Record<string, string> = {
  active: "text-danger",
  recovering: "text-warn",
  cleared: "text-ok",
};
const STATUS_LABEL: Record<string, string> = {
  active: "Sakat",
  recovering: "İyileşiyor",
  cleared: "Hazır",
};

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return Math.ceil(ms / 86_400_000);
}

const inputCls =
  "w-full bg-surface2 border border-border text-text text-[13px] px-2 py-1.5 rounded";

export default function MedicalPage() {
  const [query, setQuery] = React.useState("");
  const [search, setSearch] = React.useState("");

  // Form
  const [injuryType, setInjuryType] = React.useState("");
  const [status, setStatus] = React.useState("active");
  const [start, setStart] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [expected, setExpected] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const rehab = useSWR<Rehab[]>(
    query ? `/players/${query}/rehab/active` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const rows = rehab.data ?? [];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!query) {
      setErr("Önce bir oyuncu getir.");
      return;
    }
    if (!injuryType.trim()) {
      setErr("Sakatlık tipi gerekli.");
      return;
    }
    setErr(null);
    setBusy(true);
    try {
      await apiFetch(`/players/${query}/rehab`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          injury_type: injuryType.trim(),
          injury_start: start,
          expected_return: expected || null,
          status,
          notes: notes.trim() || null,
        }),
      });
      setInjuryType("");
      setNotes("");
      setExpected("");
      rehab.mutate();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Kayıt başarısız");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Tıbbi Merkez</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Sakatlık & dönüş takibi (return-to-play). Sağlık verisi KVKK&apos;da özel
            niteliklidir; erişim denetim kaydına yazılır.
          </p>
        </div>
        <span className="font-mono text-[10px] text-textdim bg-surface2 border border-border rounded px-2 py-0.5">
          GET /players/&#123;id&#125;/rehab/active
        </span>
      </div>

      <Panel
        title="Oyuncu"
        actions={
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(search.trim());
            }}
            className="flex items-center gap-2"
          >
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
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
        {!query && <p className="text-[12px] text-textmut">Bir oyuncu ID gir.</p>}
        {query && rehab.isLoading && (
          <p className="text-[12px] text-textmut">Yükleniyor…</p>
        )}
        {query && !rehab.isLoading && rows.length === 0 && (
          <p className="text-[12px] text-textmut">
            Aktif rehab kaydı yok.{" "}
            <Link href="/physical-tests" className="text-accent">
              Yük Riski paneli →
            </Link>
          </p>
        )}
        {rows.length > 0 && (
          <div className="grid sm:grid-cols-2 gap-3">
            {rows.map((r) => {
              const left = daysUntil(r.expected_return);
              return (
                <div
                  key={r.id}
                  className="bg-surface2 border border-border rounded-md p-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-semibold text-text">
                      {r.injury_type}
                    </span>
                    <span
                      className={`text-[11px] font-semibold uppercase ${
                        STATUS_STYLE[r.status] ?? "text-textmut"
                      }`}
                    >
                      {STATUS_LABEL[r.status] ?? r.status}
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-textmut font-mono">
                    {r.injury_start} → {r.expected_return ?? "—"}
                  </div>
                  {left !== null && r.status !== "cleared" && (
                    <div className="mt-1 text-[12px] text-text">
                      {left > 0 ? (
                        <>
                          Tahmini dönüşe{" "}
                          <span className="font-mono text-accent">{left}</span> gün
                        </>
                      ) : (
                        <span className="text-warn">Dönüş tarihi geçti</span>
                      )}
                    </div>
                  )}
                  {r.notes && (
                    <div className="mt-1 text-[11px] text-textmut">{r.notes}</div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      <Panel title="Yeni rehab kaydı">
        <form onSubmit={submit} className="space-y-2 text-[13px]">
          <div className="grid sm:grid-cols-2 gap-2">
            <label className="block">
              <span className="block text-[11px] text-textmut mb-0.5">Sakatlık tipi</span>
              <input
                value={injuryType}
                onChange={(e) => setInjuryType(e.target.value)}
                placeholder="örn. hamstring grade 2"
                className={inputCls}
              />
            </label>
            <label className="block">
              <span className="block text-[11px] text-textmut mb-0.5">Durum</span>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className={inputCls}
              >
                <option value="active">Sakat (active)</option>
                <option value="recovering">İyileşiyor (recovering)</option>
                <option value="cleared">Hazır (cleared)</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-[11px] text-textmut mb-0.5">Sakatlık başlangıcı</span>
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className={inputCls}
              />
            </label>
            <label className="block">
              <span className="block text-[11px] text-textmut mb-0.5">Tahmini dönüş</span>
              <input
                type="date"
                value={expected}
                onChange={(e) => setExpected(e.target.value)}
                className={inputCls}
              />
            </label>
          </div>
          <label className="block">
            <span className="block text-[11px] text-textmut mb-0.5">Not</span>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="opsiyonel"
              className={inputCls}
            />
          </label>
          {err && <div className="text-[12px] text-danger">{err}</div>}
          <button
            type="submit"
            disabled={busy}
            className="w-full mt-1 py-2 rounded bg-accent text-bg font-medium text-[13px] disabled:opacity-50"
          >
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
          <p className="font-mono text-[10px] text-textdim">POST /players/&#123;id&#125;/rehab</p>
        </form>
      </Panel>
    </div>
  );
}
