"use client";

/**
 * Saha Test Oturumu — kondisyoner için tablet akışı (shell bypass, koyu tema).
 *
 * 4 adım: protokol seç → adım-adım rehber + zamanlayıcı → oyuncu-oyuncu değer
 * girişi → batch kaydet + risk özeti. physical-tests sayfasıyla aynı CSS
 * değişkenleri/tema; tüm class'lar `.ts-root` namespace'i altında.
 *
 * API (Faz 2): GET /physical-tests/protocols, GET /physical-tests/players,
 * POST /physical-tests/batch. DEMO_MODE'da backend'e dokunmaz; demo veriyle
 * çalışır (CDN/backend bağımlılığı yok).
 */

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  demoProtocols, demoPlayerSummaries,
  type ProtocolInfo, type PlayerSummary,
} from "@/lib/demo-data";

type Step = "protocol" | "guide" | "session" | "summary";

interface SessionEntry {
  player_id: string;
  player_name: string;
  value: string;       // input string, kayıtta float'a çevrilir
  notes: string;
  saved: boolean;
}

interface BatchResult {
  created: number;
  failed: number;
  errors: string[];
  risk_alerts: string[];
}

// Protokol key'ine göre saha ekipman listesi (sabit).
const EQUIPMENT: Record<string, string[]> = {
  sprint_10m:      ["Foto-hücre (2 kapı)", "Düz zemin / pist", "Kronometre (yedek)"],
  sprint_30m:      ["Foto-hücre (2 kapı)", "30m düz mesafe", "Başlangıç markörü"],
  yoyo_irl1:       ["Koni (x4)", "20m ölçülü alan", "YoYo ses kaydı / uygulama", "Kronometre"],
  yoyo_irl2:       ["Koni (x4)", "20m ölçülü alan", "YoYo IRL2 ses kaydı", "Kronometre"],
  ttest_agility:   ["Koni (x4)", "T düzeni kurulum", "Kronometre / foto-hücre"],
  rsa:             ["Foto-hücre", "30m mesafe (x6)", "20sn dinlenme zamanlayıcı"],
  cmj:             ["Force plate veya jump mat", "Düz zemin"],
  sj:              ["Force plate veya jump mat", "Squat başlangıç pozisyonu marker"],
  isokinetic_quad: ["İzokinetik dinamometre", "Teknik personel"],
  isokinetic_ham:  ["İzokinetik dinamometre", "Teknik personel"],
  vo2max:          ["Koşu bandı veya 20m alan", "Nabız ölçer (ops)", "Cooper testi için kronometre"],
  gps_total_dist:  ["GPS vest / tracker", "Şarjlı cihaz"],
  gps_hir_dist:    ["GPS vest / tracker", "Şarjlı cihaz"],
  gps_acc_count:   ["GPS vest / tracker", "Şarjlı cihaz"],
  body_fat_pct:    ["Biyoempedans veya skinfold kaliper", "Aynı koşullar (sabah, aç karnına)"],
  custom:          ["Testi başlatmadan önce gerekli ekipmanı hazırlayın"],
};

// Zamanlayıcı gösterilecek protokoller + saniye (0 = serbest/say, >0 = geri sayım).
const TIMER_SECONDS: Record<string, number> = {
  yoyo_irl1: 0, yoyo_irl2: 0, rsa: 20, ttest_agility: 0,
};

function getRating(p: ProtocolInfo, value: number): string {
  if (p.higher_is_better) {
    if (value >= p.norm_elite) return "elit";
    if (value >= p.norm_good) return "iyi";
    if (value >= p.norm_average) return "ortalama";
    return "zayıf";
  }
  if (value <= p.norm_elite) return "elit";
  if (value <= p.norm_good) return "iyi";
  if (value <= p.norm_average) return "ortalama";
  return "zayıf";
}

const RATING_COLOR: Record<string, string> = {
  elit: "var(--low)", iyi: "#a8e063", ortalama: "var(--mid)", zayıf: "var(--high)",
};

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function beep(): void {
  if (typeof window === "undefined") return;
  try {
    const Ctx = window.AudioContext
      ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    osc.connect(gain);
    gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  } catch {
    /* ses çalınamadıysa sessizce geç */
  }
}

export default function TestSessionPage() {
  const [step, setStep] = React.useState<Step>("protocol");
  const [selectedProtocol, setSelectedProtocol] = React.useState<ProtocolInfo | null>(null);
  const [entries, setEntries] = React.useState<SessionEntry[]>([]);
  const [activeIndex, setActiveIndex] = React.useState(0);
  const [batchResult, setBatchResult] = React.useState<BatchResult | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [saveError, setSaveError] = React.useState<string | null>(null);

  // Yeni (kadro dışı) oyuncu ekleme
  const [newPid, setNewPid] = React.useState("");
  const [newName, setNewName] = React.useState("");

  // Zamanlayıcı
  const [timerRunning, setTimerRunning] = React.useState(false);
  const [timerSeconds, setTimerSeconds] = React.useState(0);

  const inputRef = React.useRef<HTMLInputElement>(null);

  // ── Veri kaynakları (DEMO_MODE → statik; canlı → SWR) ──
  const protocolsSwr = useSWR<ProtocolInfo[]>(
    DEMO_MODE ? null : "/physical-tests/protocols", apiFetch);
  const protocols: ProtocolInfo[] = DEMO_MODE ? demoProtocols : (protocolsSwr.data ?? []);
  const protocolsLoading = DEMO_MODE ? false : (protocolsSwr.isLoading && !protocolsSwr.data);
  const protocolsError = DEMO_MODE ? null : protocolsSwr.error;

  const playersSwr = useSWR<PlayerSummary[]>(
    DEMO_MODE ? null : "/physical-tests/players", apiFetch);
  const players: PlayerSummary[] = DEMO_MODE ? demoPlayerSummaries : (playersSwr.data ?? []);

  // Kadroyu entries'e çevir (bir kez, oturum boşken).
  React.useEffect(() => {
    if (players.length > 0 && entries.length === 0) {
      setEntries(players.map((p) => ({
        player_id: p.player_id, player_name: p.player_name,
        value: "", notes: "", saved: false,
      })));
    }
  }, [players, entries.length]);

  // Aktif oyuncu değişince değer input'una odaklan.
  React.useEffect(() => {
    if (step === "session") {
      const t = setTimeout(() => inputRef.current?.focus(), 100);
      return () => clearTimeout(t);
    }
  }, [activeIndex, step]);

  // Zamanlayıcı tik.
  const timerInitial = selectedProtocol ? (TIMER_SECONDS[selectedProtocol.key] ?? 0) : 0;
  const isCountdown = timerInitial > 0;
  React.useEffect(() => {
    if (!timerRunning) return;
    const id = setInterval(() => {
      setTimerSeconds((s) => {
        const next = isCountdown ? s - 1 : s + 1;
        if (isCountdown && next <= 0) {
          beep();
          setTimerRunning(false);
          return 0;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [timerRunning, isCountdown]);

  function resetTimer() {
    setTimerRunning(false);
    setTimerSeconds(isCountdown ? timerInitial : 0);
  }

  // ── Akış aksiyonları ──
  function pickProtocol(p: ProtocolInfo) {
    setSelectedProtocol(p);
    setTimerRunning(false);
    setTimerSeconds(TIMER_SECONDS[p.key] > 0 ? TIMER_SECONDS[p.key] : 0);
    setStep("guide");
  }

  function setActiveValue(value: string) {
    setEntries((prev) => prev.map((e, i) => (i === activeIndex ? { ...e, value } : e)));
  }
  function setActiveNotes(notes: string) {
    setEntries((prev) => prev.map((e, i) => (i === activeIndex ? { ...e, notes } : e)));
  }

  function goNext() {
    if (activeIndex >= entries.length - 1) {
      setStep("summary");
      return;
    }
    setActiveIndex(activeIndex + 1);
  }
  function saveAndNext() {
    const e = entries[activeIndex];
    if (!e || e.value.trim() === "") return;
    setEntries((prev) => prev.map((x, i) => (i === activeIndex ? { ...x, saved: true } : x)));
    goNext();
  }

  function addPlayer() {
    const pid = newPid.trim();
    const name = newName.trim();
    if (!pid || !name) return;
    if (entries.some((e) => e.player_id === pid)) return;
    setEntries((prev) => [...prev, { player_id: pid, player_name: name, value: "", notes: "", saved: false }]);
    setNewPid("");
    setNewName("");
  }

  async function save() {
    if (!selectedProtocol) return;
    const items = entries
      .filter((e) => e.saved && e.value.trim() !== "")
      .map((e) => ({
        player_id: e.player_id,
        player_name: e.player_name,
        value: parseFloat(e.value),
        notes: e.notes || undefined,
      }));
    if (items.length === 0) {
      setSaveError("Kaydedilecek sonuç yok.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      let result: BatchResult;
      if (DEMO_MODE) {
        const alerts = items
          .filter((it) => players.find((p) => p.player_id === it.player_id)?.risk_label === "Kritik")
          .map((it) => `${it.player_name} — Kritik risk`);
        result = { created: items.length, failed: 0, errors: [], risk_alerts: alerts };
      } else {
        result = (await apiFetch("/physical-tests/batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            protocol: selectedProtocol.key,
            test_date: new Date().toISOString().slice(0, 10),
            items,
          }),
        })) as BatchResult;
      }
      setBatchResult(result);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Kayıt başarısız.");
    } finally {
      setSaving(false);
    }
  }

  function resetSession() {
    setStep("protocol");
    setSelectedProtocol(null);
    setEntries(players.map((p) => ({
      player_id: p.player_id, player_name: p.player_name, value: "", notes: "", saved: false,
    })));
    setActiveIndex(0);
    setBatchResult(null);
    setSaveError(null);
    resetTimer();
  }

  const today = new Date().toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long" });
  const completed = entries.filter((e) => e.saved && e.value.trim() !== "").length;
  const active = entries[activeIndex] ?? null;
  const activeRating = selectedProtocol && active && active.value.trim() !== "" && !Number.isNaN(parseFloat(active.value))
    ? getRating(selectedProtocol, parseFloat(active.value))
    : null;

  return (
    <div className="ts-root">
      {/* ─────────── TOPBAR ─────────── */}
      <header className="ts-top">
        <div className="ts-left">
          {step === "protocol" && (
            <Link href="/physical-tests" className="ts-back" title="Panele dön">←</Link>
          )}
          {step !== "protocol" && (
            <button
              type="button"
              className="ts-back"
              title="Geri"
              onClick={() => setStep(step === "summary" ? "session" : step === "session" ? "guide" : "protocol")}
            >
              ←
            </button>
          )}
          <div className="ts-mark">m2</div>
          <div className="ts-title">
            Test Oturumu
            {selectedProtocol && <span> · {selectedProtocol.name}</span>}
          </div>
        </div>
        <div className="ts-right">
          {step === "session" && (
            <div className="ts-progresswrap" title={`${completed}/${entries.length} tamamlandı`}>
              <span className="ts-progresslbl">{completed}/{entries.length}</span>
              <span className="ts-progressbar">
                <i style={{ width: `${entries.length ? (completed / entries.length) * 100 : 0}%` }} />
              </span>
            </div>
          )}
          <span className="ts-date">{today}</span>
        </div>
      </header>

      {/* ─────────── ADIM 1 — PROTOKOL ─────────── */}
      {step === "protocol" && (
        <main className="ts-stage">
          <div className="ts-hero">
            <h1>Hangi testi uygulayacaksınız?</h1>
            <p>Protokol seçin — adım adım rehber gösterilecek</p>
          </div>

          {protocolsError && (
            <div className="ts-error">
              Protokoller yüklenemedi.
              <button type="button" onClick={() => protocolsSwr.mutate()}>Yenile</button>
            </div>
          )}

          <div className="ts-grid">
            {protocolsLoading
              ? [0, 1, 2].map((i) => <div key={i} className="ts-card ts-skel" />)
              : protocols.map((p) => (
                <button key={p.key} type="button" className="ts-card" onClick={() => pickProtocol(p)}>
                  <div className="ts-card-head">
                    <span className="ts-card-name">{p.name}</span>
                    <span className="ts-unit">{p.unit}</span>
                  </div>
                  <p className="ts-card-desc">{p.description}</p>
                  <div className="ts-norms">
                    {([["Elit", p.norm_elite, "var(--low)"], ["İyi", p.norm_good, "#a8e063"], ["Ortalama", p.norm_average, "var(--mid)"]] as [string, number, string][]).map(([lbl, v, c]) => (
                      <div key={lbl} className="ts-norm">
                        <span className="ts-norm-lbl" style={{ color: c }}>{lbl}</span>
                        <span className="ts-norm-val">{v}</span>
                      </div>
                    ))}
                  </div>
                </button>
              ))}
          </div>
        </main>
      )}

      {/* ─────────── ADIM 2 — REHBER ─────────── */}
      {step === "guide" && selectedProtocol && (
        <main className="ts-stage ts-guide">
          <div className="ts-guide-main">
            <div className="ts-eyebrow">Uygulama Talimatı</div>
            <p className="ts-instruction">{selectedProtocol.description}</p>

            <div className="ts-eyebrow" style={{ marginTop: 26 }}>Gerekli Ekipman</div>
            <ul className="ts-equip">
              {(EQUIPMENT[selectedProtocol.key] ?? EQUIPMENT.custom).map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>

            {selectedProtocol.key in TIMER_SECONDS && (
              <div className="ts-timer">
                <div className="ts-eyebrow">{isCountdown ? "Geri Sayım (dinlenme)" : "Kronometre"}</div>
                <div className="ts-timer-num" style={{ color: timerRunning ? "var(--low)" : "var(--ink)" }}>
                  {fmtTime(timerSeconds)}
                </div>
                <div className="ts-timer-btns">
                  <button type="button" onClick={() => setTimerRunning((v) => !v)}>
                    {timerRunning ? "Duraklat" : "Başlat"}
                  </button>
                  <button type="button" onClick={resetTimer} className="ghost">Sıfırla</button>
                </div>
              </div>
            )}
          </div>

          <aside className="ts-guide-side">
            <div className="ts-eyebrow">Norm Eşikleri</div>
            <div className="ts-normtable">
              {([["Elit", selectedProtocol.norm_elite, "var(--low)"], ["İyi", selectedProtocol.norm_good, "#a8e063"], ["Ortalama", selectedProtocol.norm_average, "var(--mid)"]] as [string, number, string][]).map(([lbl, v, c]) => (
                <div key={lbl} className="ts-ntrow">
                  <span style={{ color: c, fontWeight: 700 }}>{lbl}</span>
                  <span className="mono">{v} {selectedProtocol.unit}</span>
                </div>
              ))}
              <div className="ts-ntrow">
                <span style={{ color: "var(--high)", fontWeight: 700 }}>Zayıf</span>
                <span className="mono">
                  {selectedProtocol.higher_is_better ? "<" : ">"} {selectedProtocol.norm_average} {selectedProtocol.unit}
                </span>
              </div>
            </div>
            <div className="ts-dir">
              {selectedProtocol.higher_is_better ? "↑ Yüksek değer iyi" : "↓ Düşük değer iyi"}
            </div>
          </aside>

          <button type="button" className="ts-cta" onClick={() => setStep("session")}>
            Hazır — Oturumu Başlat
          </button>
        </main>
      )}

      {/* ─────────── ADIM 3 — OTURUM ─────────── */}
      {step === "session" && selectedProtocol && (
        <main className="ts-session">
          <aside className="ts-roster">
            <div className="ts-add">
              <input placeholder="ID" value={newPid} onChange={(e) => setNewPid(e.target.value)} />
              <input placeholder="Ad" value={newName} onChange={(e) => setNewName(e.target.value)} />
              <button type="button" onClick={addPlayer}>+</button>
            </div>
            <div className="ts-rlist">
              {entries.map((e, i) => {
                const isActive = i === activeIndex;
                const cls = `ts-rrow${isActive ? " active" : ""}${e.saved ? " done" : ""}`;
                return (
                  <button key={e.player_id} type="button" className={cls} onClick={() => setActiveIndex(i)}>
                    <span className="ts-rnum">{i + 1}</span>
                    <span className="ts-rname">{e.player_name}</span>
                    <span className="ts-rstat">
                      {e.saved
                        ? <span style={{ color: "var(--low)" }}>✓ {e.value} {selectedProtocol.unit}</span>
                        : isActive
                          ? <span style={{ color: "var(--besiktas)" }}>● Aktif</span>
                          : <span style={{ color: "var(--dim)" }}>Bekliyor</span>}
                    </span>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="ts-active">
            {active ? (
              <>
                <div className="ts-anum">Oyuncu {activeIndex + 1} / {entries.length}</div>
                <h2 className="ts-aname">{active.player_name}</h2>
                <div className="ts-ameta">#{active.player_id}</div>

                <div className="ts-valuebox">
                  <input
                    ref={inputRef}
                    type="number"
                    step="0.01"
                    inputMode="decimal"
                    placeholder="0.00"
                    value={active.value}
                    onChange={(e) => setActiveValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") { e.preventDefault(); saveAndNext(); }
                      else if (e.key === "Escape") { e.preventDefault(); goNext(); }
                    }}
                  />
                  <div className="ts-vunit">{selectedProtocol.unit}</div>
                  {activeRating && (
                    <span className="ts-rating" style={{ background: RATING_COLOR[activeRating], color: activeRating === "ortalama" ? "#1a1500" : "#06140a" }}>
                      {activeRating}
                    </span>
                  )}
                </div>

                <input
                  className="ts-notes"
                  placeholder="Not ekle… (opsiyonel)"
                  value={active.notes}
                  onChange={(e) => setActiveNotes(e.target.value)}
                />

                <div className="ts-actions">
                  <button type="button" className="ghost" onClick={goNext}>Atla →</button>
                  <button type="button" className="primary" onClick={saveAndNext} disabled={active.value.trim() === ""}>
                    Kaydet ve İleri →
                  </button>
                </div>
                <div className="ts-hint">Enter: kaydet ve ileri · Esc: atla</div>
              </>
            ) : (
              <div className="ts-empty">Kadro yükleniyor…</div>
            )}
          </section>
        </main>
      )}

      {/* ─────────── ADIM 4 — ÖZET ─────────── */}
      {step === "summary" && selectedProtocol && (
        <main className="ts-stage">
          <SummaryView
            protocol={selectedProtocol}
            entries={entries}
            saving={saving}
            saveError={saveError}
            batchResult={batchResult}
            onSave={save}
            onReset={resetSession}
          />
        </main>
      )}

      <style dangerouslySetInnerHTML={{ __html: CSS }} />
    </div>
  );
}

function SummaryView({
  protocol, entries, saving, saveError, batchResult, onSave, onReset,
}: {
  protocol: ProtocolInfo;
  entries: SessionEntry[];
  saving: boolean;
  saveError: string | null;
  batchResult: BatchResult | null;
  onSave: () => void;
  onReset: () => void;
}) {
  const done = entries.filter((e) => e.saved && e.value.trim() !== "");
  const skipped = entries.filter((e) => !e.saved || e.value.trim() === "");
  const vals = done.map((e) => parseFloat(e.value)).filter((v) => !Number.isNaN(v));
  const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
  const best = vals.length ? (protocol.higher_is_better ? Math.max(...vals) : Math.min(...vals)) : 0;
  const worst = vals.length ? (protocol.higher_is_better ? Math.min(...vals) : Math.max(...vals)) : 0;
  const u = protocol.unit;

  return (
    <div className="ts-summary">
      <h1 className="ts-sumttl">Oturum Özeti</h1>
      <div className="ts-sumsub">{protocol.name}</div>

      <div className="ts-stats">
        <div className="ts-stat"><span className="k">Toplam</span><span className="v">{entries.length}</span></div>
        <div className="ts-stat"><span className="k">Tamamlanan</span><span className="v" style={{ color: "var(--low)" }}>{done.length}</span></div>
        <div className="ts-stat"><span className="k">Atlanan</span><span className="v" style={{ color: "var(--dim)" }}>{skipped.length}</span></div>
        <div className="ts-stat"><span className="k">Ortalama</span><span className="v mono">{vals.length ? `${avg.toFixed(2)} ${u}` : "—"}</span></div>
        <div className="ts-stat"><span className="k">En iyi</span><span className="v mono">{vals.length ? `${best.toFixed(2)} ${u}` : "—"}</span></div>
        <div className="ts-stat"><span className="k">En kötü</span><span className="v mono">{vals.length ? `${worst.toFixed(2)} ${u}` : "—"}</span></div>
      </div>

      {done.length > 0 && (
        <div className="ts-sumtable">
          {done.map((e) => {
            const r = getRating(protocol, parseFloat(e.value));
            return (
              <div key={e.player_id} className="ts-sumrow">
                <span className="ts-sumname">{e.player_name}</span>
                <span className="ts-sumval mono">{e.value} {u}</span>
                <span className="ts-sumrating" style={{ color: RATING_COLOR[r] }}>{r}</span>
              </div>
            );
          })}
        </div>
      )}

      {skipped.length > 0 && (
        <div className="ts-skipped">Atlanan: {skipped.map((e) => e.player_name).join(", ")}</div>
      )}

      {!batchResult && (
        <>
          {saveError && <div className="ts-error" style={{ marginBottom: 12 }}>{saveError}</div>}
          <button type="button" className="ts-cta" onClick={onSave} disabled={saving || done.length === 0}>
            {saving ? "Kaydediliyor…" : `Kaydet (${done.length} sonuç)`}
          </button>
        </>
      )}

      {batchResult && (
        <div className="ts-result">
          <div className="ts-result-ok">✓ {batchResult.created} sonuç kaydedildi</div>
          {batchResult.risk_alerts.length > 0 ? (
            <div className="ts-alerts">
              <div className="ts-alerts-ttl">Risk Uyarıları</div>
              {batchResult.risk_alerts.map((a, i) => <div key={i} className="ts-alert">⚠ {a}</div>)}
            </div>
          ) : (
            <div className="ts-noalert">✓ Kritik riske düşen oyuncu yok</div>
          )}
          {batchResult.errors.length > 0 && (
            <div className="ts-alerts">
              <div className="ts-alerts-ttl">Hatalar ({batchResult.failed})</div>
              {batchResult.errors.map((a, i) => <div key={i} className="ts-alert">{a}</div>)}
            </div>
          )}
          <div className="ts-result-actions">
            <button type="button" className="ts-cta" onClick={onReset}>Yeni Oturum Başlat</button>
            <Link href="/physical-tests" className="ts-link">Panel'e Dön</Link>
          </div>
        </div>
      )}
    </div>
  );
}

const CSS = `
.ts-root{
  --bg:#0a0a0c; --panel:#131318; --panel2:#1a1a21; --line:#26262f;
  --ink:#f4f4f6; --muted:#8a8a96; --dim:#5a5a66; --accent:#ffffff;
  --low:#3ddc84; --mid:#ffd23f; --high:#ff8c42; --crit:#ff4d4d; --besiktas:#e30613;
  background:var(--bg); color:var(--ink);
  font-family:'Archivo','Segoe UI',system-ui,sans-serif;
  min-height:100vh; margin:0;
  background-image:
    radial-gradient(circle at 15% 8%, rgba(255,255,255,0.03), transparent 42%),
    radial-gradient(circle at 85% 92%, rgba(227,6,19,0.06), transparent 46%);
}
.ts-root *{margin:0;padding:0;box-sizing:border-box}
.ts-root .mono{font-family:'JetBrains Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums}
.ts-root button{font-family:inherit}

/* TOPBAR */
.ts-root .ts-top{
  display:flex;align-items:center;justify-content:space-between;
  padding:16px 30px;border-bottom:1px solid var(--line);
  background:rgba(10,10,12,0.85);backdrop-filter:blur(12px);
  position:sticky;top:0;z-index:30;
}
.ts-root .ts-left{display:flex;align-items:center;gap:13px}
.ts-root .ts-back{
  width:34px;height:34px;border-radius:9px;border:1px solid var(--line);
  background:var(--panel2);color:var(--muted);font-size:17px;font-weight:700;
  display:flex;align-items:center;justify-content:center;cursor:pointer;
  text-decoration:none;transition:all .15s;
}
.ts-root .ts-back:hover{color:var(--ink);border-color:var(--muted)}
.ts-root .ts-mark{
  width:38px;height:38px;border-radius:9px;
  background:linear-gradient(135deg,#fff,#bdbdc7);color:#0a0a0c;
  display:flex;align-items:center;justify-content:center;font-weight:900;font-size:18px;letter-spacing:-1px;
}
.ts-root .ts-title{font-size:16px;font-weight:800;letter-spacing:-0.3px}
.ts-root .ts-title span{color:var(--dim);font-weight:500}
.ts-root .ts-right{display:flex;align-items:center;gap:18px}
.ts-root .ts-date{font-size:13px;color:var(--dim);text-transform:capitalize}
.ts-root .ts-progresswrap{display:flex;align-items:center;gap:10px}
.ts-root .ts-progresslbl{font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:700;color:var(--muted)}
.ts-root .ts-progressbar{display:block;width:120px;height:6px;border-radius:3px;background:var(--panel2);overflow:hidden}
.ts-root .ts-progressbar i{display:block;height:100%;background:var(--besiktas);border-radius:3px;transition:width .3s}

/* STAGE */
.ts-root .ts-stage{max-width:1100px;margin:0 auto;padding:38px 30px 60px}
.ts-root .ts-hero{text-align:center;margin-bottom:34px}
.ts-root .ts-hero h1{font-size:34px;font-weight:900;letter-spacing:-1px;margin-bottom:8px}
.ts-root .ts-hero p{font-size:15px;color:var(--muted)}
.ts-root .ts-error{
  background:rgba(255,77,77,0.08);border:1px solid var(--crit);color:#ff9d9d;
  border-radius:11px;padding:14px 18px;margin-bottom:18px;font-size:14px;
  display:flex;align-items:center;gap:14px;
}
.ts-root .ts-error button{
  margin-left:auto;background:var(--crit);color:#fff;border:0;padding:7px 14px;
  border-radius:8px;font-weight:700;cursor:pointer;font-size:13px;
}

/* PROTOKOL GRID */
.ts-root .ts-grid{display:grid;grid-template-columns:1fr;gap:16px}
.ts-root .ts-card{
  background:var(--panel);border:1px solid var(--line);border-radius:16px;
  padding:22px;text-align:left;cursor:pointer;color:var(--ink);
  transition:transform .14s,border-color .14s,box-shadow .14s;display:block;
}
.ts-root .ts-card:hover{transform:translateY(-2px);border-color:var(--besiktas);box-shadow:0 10px 30px rgba(0,0,0,.35)}
.ts-root .ts-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:10px}
.ts-root .ts-card-name{font-size:18px;font-weight:800;letter-spacing:-0.3px;line-height:1.25}
.ts-root .ts-unit{
  flex-shrink:0;background:var(--panel2);border:1px solid var(--line);color:var(--muted);
  font-family:'JetBrains Mono',monospace;font-size:12px;padding:3px 9px;border-radius:7px;
}
.ts-root .ts-card-desc{
  color:var(--muted);font-size:13.5px;line-height:1.55;margin-bottom:16px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:42px;
}
.ts-root .ts-norms{display:flex;gap:10px;border-top:1px solid var(--line);padding-top:13px}
.ts-root .ts-norm{flex:1;display:flex;flex-direction:column;gap:3px}
.ts-root .ts-norm-lbl{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px}
.ts-root .ts-norm-val{font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:700}
.ts-root .ts-skel{height:182px;animation:ts-pulse 1.4s ease infinite}
@keyframes ts-pulse{0%,100%{opacity:1}50%{opacity:.45}}

/* REHBER */
.ts-root .ts-guide{display:grid;grid-template-columns:1fr 320px;gap:22px;align-items:start}
.ts-root .ts-eyebrow{
  text-transform:uppercase;letter-spacing:2px;font-size:11px;color:var(--dim);
  font-weight:700;margin-bottom:12px;
}
.ts-root .ts-instruction{font-size:16px;line-height:1.7;color:var(--ink)}
.ts-root .ts-equip{list-style:none}
.ts-root .ts-equip li{
  position:relative;padding:9px 0 9px 24px;font-size:14px;
  border-bottom:1px solid rgba(38,38,47,0.5);
}
.ts-root .ts-equip li:last-child{border:0}
.ts-root .ts-equip li::before{content:'→';position:absolute;left:0;color:var(--besiktas);font-weight:800}
.ts-root .ts-timer{
  margin-top:26px;background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:20px;text-align:center;
}
.ts-root .ts-timer-num{font-family:'JetBrains Mono',monospace;font-size:64px;font-weight:700;line-height:1;margin-bottom:16px}
.ts-root .ts-timer-btns{display:flex;gap:10px;justify-content:center}
.ts-root .ts-timer-btns button{
  background:var(--ink);color:#0a0a0c;border:0;padding:11px 22px;border-radius:10px;
  font-weight:800;font-size:14px;cursor:pointer;
}
.ts-root .ts-timer-btns button.ghost{background:var(--panel2);color:var(--ink);border:1px solid var(--line)}
.ts-root .ts-guide-side{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}
.ts-root .ts-normtable{display:flex;flex-direction:column;gap:2px}
.ts-root .ts-ntrow{
  display:flex;align-items:center;justify-content:space-between;
  padding:11px 0;border-bottom:1px solid rgba(38,38,47,0.5);font-size:14px;
}
.ts-root .ts-ntrow:last-child{border:0}
.ts-root .ts-ntrow .mono{font-family:'JetBrains Mono',monospace;color:var(--muted)}
.ts-root .ts-dir{
  margin-top:12px;padding-top:14px;border-top:1px solid var(--line);
  font-size:13px;color:var(--muted);font-weight:600;
}
.ts-root .ts-cta{
  grid-column:1/-1;width:100%;margin-top:8px;
  background:var(--besiktas);color:#fff;border:0;padding:18px;border-radius:13px;
  font-size:16px;font-weight:800;letter-spacing:0.3px;cursor:pointer;
  transition:filter .15s,transform .1s;
}
.ts-root .ts-cta:hover{filter:brightness(1.1)}
.ts-root .ts-cta:active{transform:translateY(1px)}
.ts-root .ts-cta:disabled{opacity:.45;cursor:default;filter:none}

/* OTURUM */
.ts-root .ts-session{display:grid;grid-template-columns:320px 1fr;gap:0;min-height:calc(100vh - 67px)}
.ts-root .ts-roster{border-right:1px solid var(--line);background:var(--panel);overflow-y:auto;max-height:calc(100vh - 67px)}
.ts-root .ts-add{display:flex;gap:6px;padding:14px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--panel);z-index:2}
.ts-root .ts-add input{
  min-width:0;flex:1;background:var(--panel2);border:1px solid var(--line);color:var(--ink);
  padding:9px 10px;border-radius:8px;font-size:13px;outline:none;
}
.ts-root .ts-add input:first-child{max-width:64px}
.ts-root .ts-add button{
  flex-shrink:0;background:var(--ink);color:#0a0a0c;border:0;width:38px;border-radius:8px;
  font-size:18px;font-weight:800;cursor:pointer;
}
.ts-root .ts-rrow{
  width:100%;display:flex;align-items:center;gap:11px;padding:13px 16px;cursor:pointer;
  border:0;border-left:3px solid transparent;border-bottom:1px solid rgba(38,38,47,0.4);
  background:transparent;color:var(--ink);text-align:left;transition:background .12s;
}
.ts-root .ts-rrow:hover{background:var(--panel2)}
.ts-root .ts-rrow.active{background:var(--panel2);border-left-color:var(--besiktas)}
.ts-root .ts-rrow.done{opacity:.75}
.ts-root .ts-rnum{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--dim);width:22px;font-weight:700;flex-shrink:0}
.ts-root .ts-rname{flex:1;font-size:14px;font-weight:600}
.ts-root .ts-rstat{font-size:12px;font-family:'JetBrains Mono',monospace}

.ts-root .ts-active{padding:46px 50px;display:flex;flex-direction:column}
.ts-root .ts-anum{text-transform:uppercase;letter-spacing:2px;font-size:11px;color:var(--dim);font-weight:700;margin-bottom:10px}
.ts-root .ts-aname{font-size:42px;font-weight:900;letter-spacing:-1.2px;line-height:1}
.ts-root .ts-ameta{color:var(--muted);font-size:14px;margin-top:6px;margin-bottom:30px;font-family:'JetBrains Mono',monospace}
.ts-root .ts-valuebox{position:relative;border-bottom:2px solid var(--line);padding-bottom:10px;margin-bottom:18px;max-width:420px}
.ts-root .ts-valuebox input{
  width:100%;background:transparent;border:0;outline:none;color:var(--ink);
  font-family:'JetBrains Mono',monospace;font-size:60px;font-weight:700;letter-spacing:-2px;
}
.ts-root .ts-valuebox input::-webkit-outer-spin-button,
.ts-root .ts-valuebox input::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}
.ts-root .ts-vunit{position:absolute;right:0;bottom:18px;font-size:20px;color:var(--dim);font-family:'JetBrains Mono',monospace}
.ts-root .ts-rating{
  position:absolute;right:0;top:6px;padding:5px 13px;border-radius:8px;
  font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.6px;
}
.ts-root .ts-notes{
  max-width:420px;background:var(--panel);border:1px solid var(--line);color:var(--ink);
  padding:11px 14px;border-radius:10px;font-size:14px;outline:none;margin-bottom:26px;
}
.ts-root .ts-actions{display:flex;gap:12px;max-width:420px}
.ts-root .ts-actions button{padding:15px 22px;border-radius:11px;font-size:15px;font-weight:800;cursor:pointer;border:0}
.ts-root .ts-actions .ghost{background:var(--panel2);color:var(--muted);border:1px solid var(--line)}
.ts-root .ts-actions .primary{flex:1;background:var(--besiktas);color:#fff}
.ts-root .ts-actions .primary:disabled{opacity:.4;cursor:default}
.ts-root .ts-hint{margin-top:14px;font-size:12px;color:var(--dim)}
.ts-root .ts-empty{color:var(--dim);font-size:15px;padding:60px 0;text-align:center}

/* ÖZET */
.ts-root .ts-summary{max-width:680px;margin:0 auto}
.ts-root .ts-sumttl{font-size:30px;font-weight:900;letter-spacing:-0.8px}
.ts-root .ts-sumsub{color:var(--muted);font-size:14px;margin:4px 0 24px}
.ts-root .ts-stats{
  display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px;
}
.ts-root .ts-stat{
  background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;
  display:flex;flex-direction:column;gap:6px;
}
.ts-root .ts-stat .k{font-size:11px;text-transform:uppercase;letter-spacing:0.8px;color:var(--dim);font-weight:700}
.ts-root .ts-stat .v{font-size:22px;font-weight:800}
.ts-root .ts-sumtable{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;margin-bottom:18px}
.ts-root .ts-sumrow{display:grid;grid-template-columns:1fr auto 90px;gap:14px;align-items:center;padding:13px 18px;border-bottom:1px solid rgba(38,38,47,0.5)}
.ts-root .ts-sumrow:last-child{border:0}
.ts-root .ts-sumname{font-weight:600;font-size:14px}
.ts-root .ts-sumval{font-family:'JetBrains Mono',monospace;font-weight:700;text-align:right;font-size:14px}
.ts-root .ts-sumrating{text-transform:uppercase;font-size:12px;font-weight:800;letter-spacing:0.5px;text-align:right}
.ts-root .ts-skipped{color:var(--dim);font-size:13px;margin-bottom:20px}
.ts-root .ts-result-ok{font-size:18px;font-weight:800;color:var(--low);margin-bottom:16px}
.ts-root .ts-alerts{background:rgba(255,77,77,0.08);border:1px solid var(--crit);border-radius:12px;padding:14px 18px;margin-bottom:16px}
.ts-root .ts-alerts-ttl{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#ff9d9d;font-weight:700;margin-bottom:8px}
.ts-root .ts-alert{font-size:14px;color:#ffc9c9;padding:3px 0}
.ts-root .ts-noalert{color:var(--low);font-size:14px;margin-bottom:16px}
.ts-root .ts-result-actions{display:flex;align-items:center;gap:16px;margin-top:8px}
.ts-root .ts-result-actions .ts-cta{flex:1;margin:0}
.ts-root .ts-link{color:var(--muted);text-decoration:none;font-size:14px;font-weight:600;white-space:nowrap}
.ts-root .ts-link:hover{color:var(--ink)}

/* RESPONSIVE */
@media (min-width:768px){
  .ts-root .ts-grid{grid-template-columns:repeat(2,1fr)}
}
@media (min-width:1024px){
  .ts-root .ts-grid{grid-template-columns:repeat(3,1fr)}
}
@media (max-width:900px){
  .ts-root .ts-guide{grid-template-columns:1fr}
}
@media (max-width:767px){
  .ts-root .ts-top{padding:13px 16px}
  .ts-root .ts-date{display:none}
  .ts-root .ts-stage{padding:24px 16px 50px}
  .ts-root .ts-hero h1{font-size:26px}
  .ts-root .ts-session{display:block}
  .ts-root .ts-roster{border-right:0;border-bottom:1px solid var(--line);max-height:none}
  .ts-root .ts-rlist{display:flex;overflow-x:auto;gap:0}
  .ts-root .ts-rrow{flex-direction:column;align-items:flex-start;min-width:150px;border-left:0;border-bottom:0;border-right:1px solid rgba(38,38,47,0.4)}
  .ts-root .ts-rrow.active{border-left:0;border-top:3px solid var(--besiktas)}
  .ts-root .ts-active{padding:28px 18px}
  .ts-root .ts-aname{font-size:32px}
  .ts-root .ts-valuebox input{font-size:46px}
  .ts-root .ts-stats{grid-template-columns:repeat(2,1fr)}
}
@media (min-width:1280px){
  .ts-root .ts-session{grid-template-columns:380px 1fr}
}
`;
