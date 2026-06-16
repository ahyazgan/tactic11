"use client";

/**
 * Test Hesaplayıcı — türetilmiş spor-bilimi metrikleri (interaktif + kaydet).
 *
 * Ham ölçümü gir → metrik + risk bayrağı anında. Üstte oyuncu + tarih seçilir;
 * her kartta "Kaydet" ile sonuç oyuncunun test geçmişine işlenir: türetilmiş
 * değer `value`, ham bileşenler `components` alanına yazılır.
 *
 * Açık tema (ConsoleShell). Hesap TS'de, app/engine/performance_test/compute.py
 * saf fonksiyonlarını BİREBİR yansıtır (eşik sabitleri backend ile aynı).
 * DEMO_MODE: kayıt localStorage'a; backend açıkken POST /physical-tests/.
 */

import * as React from "react";
import Link from "next/link";
import { demoSquad } from "@/lib/demo-data";
import { DEMO_MODE } from "@/lib/demo-mode";
import { apiFetch } from "@/lib/api";
import {
  LS_KEY, PROTO_NAME, PROTO_UNIT, loadDerivedRecords,
  type SavePayload, type SavedRecord,
} from "@/lib/derived-tests";
import { ConsoleShell } from "../../_console/shell";

// ── Eşik sabitleri — backend compute.py ile birebir ─────────────────────────
const RSA_FATIGUE_FLAG_PCT = 7.0;
const COD_DEFICIT_FLAG_S = 1.0;
const ASYMMETRY_WARN_PCT = 10.0;
const ASYMMETRY_HIGH_PCT = 15.0;
const ADDUCTOR_DROP_FLAG_PCT = 10.0;
const CMJ_FATIGUE_DROP_PCT = 10.0;
const RTP_GREEN_LIGHT_PCT = 95.0;
const HQ_RATIO_IDEAL_MIN = 0.6;
const HQ_RATIO_RISK = 0.47;

const r1 = (n: number) => Math.round(n * 10) / 10;
const r2 = (n: number) => Math.round(n * 100) / 100;
const r3 = (n: number) => Math.round(n * 1000) / 1000;

type Flag = "good" | "warn" | "bad" | "neutral";
const FLAG: Record<Flag, { v: string; bg: string }> = {
  good: { v: "var(--low)", bg: "var(--low-bg)" },
  warn: { v: "var(--mid)", bg: "var(--mid-bg)" },
  bad: { v: "var(--crit)", bg: "var(--crit-bg)" },
  neutral: { v: "var(--muted)", bg: "var(--surface2)" },
};

// ── Kaydetme altyapısı (tipler + sözlük @/lib/derived-tests'ten) ────────────
interface SaveCtx {
  player: { player_id: string; player_name: string } | null;
  testDate: string;
  save: (p: SavePayload) => Promise<void>;
  savingKey: string | null;
}
const SaveContext = React.createContext<SaveCtx | null>(null);

const num = (s: string) => (s.trim() === "" ? NaN : Number(s));

// ── Küçük UI yardımcıları ───────────────────────────────────────────────────
function NumIn({ label, value, set, step = "0.01", unit }: {
  label: string; value: string; set: (v: string) => void; step?: string; unit?: string;
}) {
  return (
    <label style={{ display: "block", fontSize: 11.5, color: "var(--dim)", marginBottom: 8 }}>
      {label}{unit ? ` (${unit})` : ""}
      <input
        type="number" inputMode="decimal" step={step} value={value}
        onChange={(e) => set(e.target.value)}
        style={{
          display: "block", width: "100%", marginTop: 3, padding: "7px 9px",
          borderRadius: 8, border: "1px solid var(--line)", background: "var(--panel)",
          color: "var(--ink)", fontFamily: "JetBrains Mono", fontSize: 13, fontWeight: 600,
        }}
      />
    </label>
  );
}

function TxtIn({ label, value, set }: { label: string; value: string; set: (v: string) => void }) {
  return (
    <label style={{ display: "block", fontSize: 11.5, color: "var(--dim)", marginBottom: 8 }}>
      {label}
      <input type="text" value={value} onChange={(e) => set(e.target.value)}
        style={{ display: "block", width: "100%", marginTop: 3, padding: "7px 9px", borderRadius: 8,
          border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)",
          fontFamily: "JetBrains Mono", fontSize: 12.5, fontWeight: 600 }} />
    </label>
  );
}

function Result({ big, flag, lines }: { big: string; flag: Flag; lines: string[] }) {
  const f = FLAG[flag];
  return (
    <div style={{ marginTop: 4, padding: "10px 12px", borderRadius: 9, background: f.bg, border: `1px solid ${f.v}33` }}>
      <div style={{ fontFamily: "JetBrains Mono", fontSize: 22, fontWeight: 800, color: f.v }}>{big}</div>
      {lines.map((l, i) => (
        <div key={i} style={{ fontSize: 11.5, color: "var(--muted)", marginTop: i === 0 ? 4 : 2, lineHeight: 1.45 }}>{l}</div>
      ))}
    </div>
  );
}

// Kaydet butonu — geçerli sonuç varsa görünür; oyuncu seçili değilse uyarır.
function SaveBtn({ payload, saveKey }: { payload: SavePayload | null; saveKey: string }) {
  const ctx = React.useContext(SaveContext);
  if (!ctx) return null;
  const disabled = payload === null || ctx.player === null || ctx.savingKey !== null;
  const busy = ctx.savingKey === saveKey;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => payload && ctx.save({ ...payload })}
      style={{
        marginTop: 8, width: "100%", padding: "8px", borderRadius: 8, border: 0,
        background: disabled ? "var(--surface2)" : "var(--besiktas)",
        color: disabled ? "var(--dim)" : "#fff", fontWeight: 700, fontSize: 12.5,
        cursor: disabled ? "not-allowed" : "pointer", fontFamily: "inherit",
      }}
      title={ctx.player === null ? "Önce üstten oyuncu seç" : payload === null ? "Geçerli sonuç gir" : ""}
    >
      <i className={`ti ${busy ? "ti-loader-2" : "ti-device-floppy"}`} style={{ marginRight: 6 }} />
      {busy ? "Kaydediliyor…" : ctx.player ? `Kaydet → ${ctx.player.player_name}` : "Kaydet (oyuncu seç)"}
    </button>
  );
}

function Card({ icon, title, sub, explain, children }: {
  icon: string; title: string; sub: string; explain?: string; children: React.ReactNode;
}) {
  return (
    <div className="rc" style={{ margin: 0 }}>
      <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <i className={`ti ${icon}`} style={{ color: "var(--accent)" }} />{title}
        <span className="tiny" style={{ marginLeft: "auto", fontWeight: 400 }}>{sub}</span>
      </h3>
      {explain && (
        <p style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45, margin: "0 0 10px" }}>{explain}</p>
      )}
      {children}
    </div>
  );
}

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function DeriveCalculatorsPage() {
  const [playerId, setPlayerId] = React.useState<string>("");
  const [testDate, setTestDate] = React.useState<string>(todayISO());
  const [records, setRecords] = React.useState<SavedRecord[]>([]);
  const [savingKey, setSavingKey] = React.useState<string | null>(null);
  const [toast, setToast] = React.useState<string | null>(null);

  // localStorage'tan demo kayıtları yükle (yalnız ilk render).
  React.useEffect(() => {
    if (DEMO_MODE) setRecords(loadDerivedRecords());
  }, []);

  const player = React.useMemo(() => {
    const p = demoSquad.find((s) => String(s.player_id) === playerId);
    return p ? { player_id: String(p.player_id), player_name: p.player_name } : null;
  }, [playerId]);

  const save = React.useCallback(async (p: SavePayload) => {
    if (!player) { setToast("Önce oyuncu seç."); return; }
    setSavingKey(p.protocol + ":" + p.label);
    try {
      const rec: SavedRecord = {
        ...p, id: Date.now(), player_id: player.player_id,
        player_name: player.player_name, test_date: testDate,
      };
      if (DEMO_MODE) {
        const next = [rec, ...records].slice(0, 200);
        setRecords(next);
        window.localStorage.setItem(LS_KEY, JSON.stringify(next));
      } else {
        await apiFetch("/physical-tests/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            player_id: player.player_id, player_name: player.player_name,
            test_date: testDate, protocol: p.protocol, value: p.value,
            components: p.components,
          }),
        });
        setRecords([rec, ...records]);
      }
      setToast(`✓ ${player.player_name} · ${PROTO_NAME[p.protocol] ?? p.protocol} kaydedildi`);
    } catch (e) {
      setToast("Kayıt başarısız: " + (e instanceof Error ? e.message : "hata"));
    } finally {
      setSavingKey(null);
      window.setTimeout(() => setToast(null), 3500);
    }
  }, [player, testDate, records]);

  const playerRecords = records.filter((r) => !player || r.player_id === player.player_id);

  function clearRecords() {
    if (!DEMO_MODE) return;
    const kept = player ? records.filter((r) => r.player_id !== player.player_id) : [];
    setRecords(kept);
    window.localStorage.setItem(LS_KEY, JSON.stringify(kept));
    setToast(player ? `${player.player_name} kayıtları temizlendi` : "Tüm demo kayıtlar temizlendi");
    window.setTimeout(() => setToast(null), 3000);
  }

  const ctx: SaveCtx = { player, testDate, save, savingKey };

  const right = (
    <>
      <div className="rc">
        <h3>Oyuncu & Tarih</h3>
        <label style={{ display: "block", fontSize: 11.5, color: "var(--dim)", marginBottom: 8 }}>
          Oyuncu
          <select value={playerId} onChange={(e) => setPlayerId(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 3, padding: "8px 9px", borderRadius: 8,
              border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)",
              fontSize: 13, fontWeight: 600, fontFamily: "inherit" }}>
            <option value="">— seç —</option>
            {demoSquad.map((p) => (
              <option key={p.player_id} value={String(p.player_id)}>
                {p.shirt}. {p.player_name} · {p.pos_detail}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "block", fontSize: 11.5, color: "var(--dim)" }}>
          Test tarihi
          <input type="date" value={testDate} onChange={(e) => setTestDate(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 3, padding: "7px 9px", borderRadius: 8,
              border: "1px solid var(--line)", background: "var(--panel)", color: "var(--ink)",
              fontSize: 13, fontWeight: 600, fontFamily: "inherit" }} />
        </label>
        {!player && (
          <div style={{ fontSize: 11, color: "var(--high)", marginTop: 8 }}>
            <i className="ti ti-alert-triangle" style={{ marginRight: 4 }} />
            Kaydetmek için oyuncu seç.
          </div>
        )}
      </div>

      <div className="rc">
        <h3>{player ? `${player.player_name} — Kayıtlar` : "Kayıtlar"} <span className="tiny">{playerRecords.length}</span></h3>
        {playerRecords.length === 0 ? (
          <div style={{ fontSize: 12, color: "var(--dim)" }}>Henüz kayıt yok. Bir metrik hesaplayıp “Kaydet”e bas.</div>
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {playerRecords.slice(0, 12).map((r) => (
              <div key={r.id} style={{ padding: "7px 9px", borderRadius: 8, background: "var(--surface2)", fontSize: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <b>{PROTO_NAME[r.protocol] ?? r.protocol}</b>
                  <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>
                    {r.value}{PROTO_UNIT[r.protocol] ? ` ${PROTO_UNIT[r.protocol]}` : ""}
                  </span>
                </div>
                <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 2 }}>{r.test_date} · {r.label}</div>
              </div>
            ))}
          </div>
        )}
        {DEMO_MODE && playerRecords.length > 0 && (
          <button type="button" onClick={clearRecords}
            style={{ marginTop: 10, width: "100%", padding: "7px", borderRadius: 8, border: "1px solid var(--line)",
              background: "var(--panel)", color: "var(--muted)", fontSize: 11.5, cursor: "pointer", fontFamily: "inherit" }}>
            <i className="ti ti-trash" style={{ marginRight: 5 }} />{player ? "Bu oyuncunun kayıtlarını temizle" : "Temizle"}
          </button>
        )}
      </div>
    </>
  );

  return (
    <SaveContext.Provider value={ctx}>
      <ConsoleShell
        active="/physical-tests/derive"
        title="Test Hesaplayıcı"
        sub="türetilmiş metrikler"
        desc="Üstten oyuncu seç; ham ölçümü gir; sonuç anında çıkar ve “Kaydet” ile oyuncunun test geçmişine işlenir (türetilmiş değer + ham bileşenler)."
        right={right}
      >
        {toast && (
          <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 9,
            background: toast.startsWith("✓") ? "var(--low-bg)" : "var(--crit-bg)",
            color: toast.startsWith("✓") ? "var(--low)" : "var(--crit)", fontWeight: 600, fontSize: 13 }}>
            {toast}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))", gap: 14 }}>
          <RSACard />
          <CODCard />
          <RSICard />
          <AsymCard />
          <HQCard />
          <VO2YoyoCard />
          <VO2VIFTCard />
          <AdductorCard />
          <CMJCard />
          <RTPCard />
        </div>

        <div style={{ marginTop: 18 }}>
          <div className="st" style={{ marginTop: 0 }}><h2>Mevkiye Özel Test Paketi</h2><span className="ep">önerilen batarya</span></div>
          <PresetCard />
        </div>

        <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 14, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <i className="ti ti-info-circle" />
          Hesaplar backend <code style={{ fontFamily: "JetBrains Mono" }}>engine/performance_test</code> ile birebir.
          {DEMO_MODE ? " Demo modunda kayıtlar tarayıcıda (localStorage) saklanır." : " Kayıtlar backend’e (POST /physical-tests/) yazılır."}
          <Link href="/physical-tests" style={{ marginLeft: "auto", color: "var(--accent)", textDecoration: "none" }}>← Fiziksel Durum panosu</Link>
        </div>
      </ConsoleShell>
    </SaveContext.Provider>
  );
}

// ── Tekrarlı Sprint Yorgunluğu (RSA) ────────────────────────────────────────
function RSACard() {
  const [raw, setRaw] = React.useState("4.30, 4.45, 4.60, 4.80, 5.00, 5.20");
  const times = raw.split(/[,\s]+/).map(Number).filter((n) => !Number.isNaN(n) && n > 0);
  let body: React.ReactNode = <div style={{ fontSize: 11.5, color: "var(--dim)" }}>En az 2 geçerli süre gir.</div>;
  let payload: SavePayload | null = null;
  if (times.length >= 2) {
    const best = Math.min(...times);
    const total = times.reduce((a, b) => a + b, 0);
    const mean = total / times.length;
    const fi = r2(((total / (best * times.length)) - 1) * 100);
    const flagged = fi > RSA_FATIGUE_FLAG_PCT;
    body = <Result big={`FI %${fi}`} flag={flagged ? "bad" : "good"}
      lines={[`${times.length} sprint · en iyi ${r2(best)}sn · toplam ${r2(total)}sn`,
        flagged ? `> %${RSA_FATIGUE_FLAG_PCT} → yetersiz toparlanma` : `≤ %${RSA_FATIGUE_FLAG_PCT} → iyi anaerobik dayanıklılık`]} />;
    payload = { protocol: "rsa", value: r2(mean), label: `FI %${fi} · ${times.length} sprint`,
      components: { sprint_times: times.map(r3), fatigue_index_pct: fi, best: r3(best), insufficient_recovery: flagged } };
  }
  return (
    <Card icon="ti-run" title="Tekrarlı Sprint Yorgunluğu" sub="RSA · Yorgunluk İndeksi"
      explain="Art arda sprintlerde hızın ne kadar düştüğünü ölçer. Yüksek yorgunluk indeksi (FI) = yetersiz toparlanma.">
      <TxtIn label="Sprint süreleri (sn, virgülle)" value={raw} set={setRaw} />
      {body}
      <SaveBtn payload={payload} saveKey="rsa" />
    </Card>
  );
}

// ── Yön Değiştirme Açığı (COD Deficit) ──────────────────────────────────────
function CODCard() {
  const [cod, setCod] = React.useState("3.00");
  const [lin, setLin] = React.useState("1.70");
  const c = num(cod), l = num(lin);
  let body: React.ReactNode = <div style={{ fontSize: 11.5, color: "var(--dim)" }}>Pozitif süre gir.</div>;
  let payload: SavePayload | null = null;
  if (c > 0 && l > 0) {
    const def = r3(c - l);
    const poor = def > COD_DEFICIT_FLAG_S;
    body = <Result big={`${def} sn`} flag={poor ? "bad" : "good"}
      lines={[`505 ${r2(c)}sn − 10m ${r2(l)}sn`,
        poor ? `> ${COD_DEFICIT_FLAG_S}sn → zayıf frenleme/deceleration` : `≤ ${COD_DEFICIT_FLAG_S}sn → iyi yön değiştirme`]} />;
    payload = { protocol: "t505", value: r2(c), label: `COD açığı ${def}sn`,
      components: { linear_10m: r2(l), deficit: def, poor_deceleration: poor } };
  }
  return (
    <Card icon="ti-arrow-back-up" title="Yön Değiştirme Açığı" sub="COD Deficit · 505−10m"
      explain="Düz koşuya kıyasla dönüş/frenlemede kaybedilen süre. Açık büyükse frenleme/deceleration mekaniği zayıf.">
      <NumIn label="505 süresi" value={cod} set={setCod} unit="sn" />
      <NumIn label="10m düz sprint" value={lin} set={setLin} unit="sn" />
      {body}
      <SaveBtn payload={payload} saveKey="cod" />
    </Card>
  );
}

// ── Sıçrama Reaktif Gücü (Drop Jump RSI) ────────────────────────────────────
function RSICard() {
  const [fl, setFl] = React.useState("0.52");
  const [ct, setCt] = React.useState("0.25");
  const f = num(fl), c = num(ct);
  let body: React.ReactNode = <div style={{ fontSize: 11.5, color: "var(--dim)" }}>Temas süresi pozitif olmalı.</div>;
  let payload: SavePayload | null = null;
  if (c > 0 && f >= 0) {
    const rsi = r3(f / c);
    const flag: Flag = rsi >= 2.5 ? "good" : rsi >= 1.5 ? "warn" : "bad";
    body = <Result big={`RSI ${rsi}`} flag={flag}
      lines={[`uçuş ${r2(f)}s / temas ${r2(c)}s`,
        rsi >= 2.5 ? "elit reaktif kuvvet" : rsi >= 1.5 ? "orta — geliştirilebilir" : "düşük reaktif kuvvet"]} />;
    payload = { protocol: "drop_jump_rsi", value: rsi, label: `RSI ${rsi}`,
      components: { flight_time_s: r3(f), contact_time_s: r3(c) } };
  }
  return (
    <Card icon="ti-arrows-up" title="Sıçrama Reaktif Gücü" sub="Drop Jump · RSI"
      explain="Yere değme süresine göre patlayıcı sıçrama gücü (RSI). Yüksek RSI = daha reaktif ve elastik bacak.">
      <NumIn label="Havada kalma süresi" value={fl} set={setFl} unit="sn" />
      <NumIn label="Yere temas süresi" value={ct} set={setCt} unit="sn" />
      {body}
      <SaveBtn payload={payload} saveKey="rsi" />
    </Card>
  );
}

// ── Bacak Denge / Asimetri (Triple Hop) ─────────────────────────────────────
function AsymCard() {
  const [lf, setLf] = React.useState("600");
  const [rt, setRt] = React.useState("510");
  const l = num(lf), r = num(rt);
  let body: React.ReactNode = <div style={{ fontSize: 11.5, color: "var(--dim)" }}>İki bacak ölçümü gir.</div>;
  let payload: SavePayload | null = null;
  if (l >= 0 && r >= 0 && Math.max(l, r) > 0) {
    const hi = Math.max(l, r);
    const asym = r2((Math.abs(l - r) / hi) * 100);
    const flag: Flag = asym > ASYMMETRY_HIGH_PCT ? "bad" : asym > ASYMMETRY_WARN_PCT ? "warn" : "good";
    const side = Math.abs(l - r) < 1e-9 ? "denge" : l > r ? "sol" : "sağ";
    const fl = flag === "bad" ? "kırmızı" : flag === "warn" ? "sarı" : "yeşil";
    body = <Result big={`%${asym}`} flag={flag}
      lines={[`güçlü taraf: ${side} · ${fl} bayrak`,
        asym > ASYMMETRY_HIGH_PCT ? `> %${ASYMMETRY_HIGH_PCT} → müdahale (yeniden-sakatlanma riski)`
          : asym > ASYMMETRY_WARN_PCT ? `> %${ASYMMETRY_WARN_PCT} → izle` : "denge kabul aralığında"]} />;
    payload = { protocol: "triple_hop", value: r1(hi), label: `asimetri %${asym} (${fl})`,
      components: { left: r1(l), right: r1(r), asymmetry_pct: asym, stronger_side: side, flag: fl } };
  }
  return (
    <Card icon="ti-scale" title="Bacak Denge / Asimetri" sub="Triple Hop sol-sağ"
      explain="Sağ ve sol bacak arasındaki güç farkı. %10 üstü fark sarı, %15 üstü kırmızı — yeniden-sakatlanma riski.">
      <NumIn label="Sol bacak" value={lf} set={setLf} step="1" unit="cm" />
      <NumIn label="Sağ bacak" value={rt} set={setRt} step="1" unit="cm" />
      {body}
      <SaveBtn payload={payload} saveKey="asym" />
    </Card>
  );
}

// ── Arka-Ön Bacak Dengesi (H:Q) ─────────────────────────────────────────────
function HQCard() {
  const [h, setH] = React.useState("1.50");
  const [q, setQ] = React.useState("2.80");
  const hv = num(h), qv = num(q);
  let body: React.ReactNode = <div style={{ fontSize: 11.5, color: "var(--dim)" }}>Quadriceps pozitif olmalı.</div>;
  let payload: SavePayload | null = null;
  if (qv > 0 && hv >= 0) {
    const ratio = r3(hv / qv);
    const band = ratio >= HQ_RATIO_IDEAL_MIN ? "ideal" : ratio >= HQ_RATIO_RISK ? "sınırda" : "yüksek risk";
    const flag: Flag = ratio >= HQ_RATIO_IDEAL_MIN ? "good" : ratio >= HQ_RATIO_RISK ? "warn" : "bad";
    body = <Result big={`H:Q ${ratio}`} flag={flag}
      lines={[`hamstring ${r2(hv)} / quadriceps ${r2(qv)} · ${band}`,
        ratio < HQ_RATIO_RISK ? `< ${HQ_RATIO_RISK} → yüksek hamstring riski` : `hedef ≥ ${HQ_RATIO_IDEAL_MIN}`]} />;
    payload = { protocol: "isokinetic_ham", value: r2(hv), label: `H:Q ${ratio} (${band})`,
      components: { quadriceps: r2(qv), hq_ratio: ratio, band } };
  }
  return (
    <Card icon="ti-activity-heartbeat" title="Arka-Ön Bacak Dengesi" sub="H:Q · hamstring/quadriceps"
      explain="Arka bacak (hamstring) kuvvetinin ön bacağa (quadriceps) oranı = H:Q. Düşük oran hamstring sakatlık riskini artırır; hedeflenen denge ≥ 0.6.">
      <NumIn label="İzokinetik hamstring" value={h} set={setH} unit="Nm/kg" />
      <NumIn label="İzokinetik quadriceps" value={q} set={setQ} unit="Nm/kg" />
      {body}
      <SaveBtn payload={payload} saveKey="hq" />
    </Card>
  );
}

// ── Dayanıklılık (VO2max) — Yo-Yo IR1 / Bangsbo ─────────────────────────────
function VO2YoyoCard() {
  const [d, setD] = React.useState("2000");
  const dv = num(d);
  let body: React.ReactNode = <div style={{ fontSize: 11.5, color: "var(--dim)" }}>Mesafe (m) gir.</div>;
  let payload: SavePayload | null = null;
  if (dv >= 0) {
    const vo2 = r1(dv * 0.0084 + 36.4);
    const flag: Flag = vo2 >= 60 ? "good" : vo2 >= 52 ? "warn" : "bad";
    body = <Result big={`${vo2}`} flag={flag} lines={["ml/kg/dk · Bangsbo (2008)",
      vo2 >= 60 ? "elit aerobik kapasite" : vo2 >= 52 ? "iyi" : "geliştirilmeli"]} />;
    payload = { protocol: "vo2max", value: vo2, label: `VO2max ${vo2} (Yo-Yo)`,
      components: { yoyo_ir1_distance_m: dv, source: "yoyo_ir1_bangsbo" } };
  }
  return (
    <Card icon="ti-lungs" title="Dayanıklılık (VO2max) — Yo-Yo" sub="Yo-Yo IR1 · Bangsbo"
      explain="Aralıklı koşu testinden tahmini maksimal oksijen kapasitesi (VO2max). Yüksek değer = daha iyi aerobik dayanıklılık.">
      <NumIn label="Yo-Yo IR1 toplam mesafe" value={d} set={setD} step="20" unit="m" />
      {body}
      <SaveBtn payload={payload} saveKey="vo2yoyo" />
    </Card>
  );
}

// ── Dayanıklılık (VO2max) — 30-15 IFT / Buchheit ────────────────────────────
function VO2VIFTCard() {
  const [v, setV] = React.useState("20.0");
  const [a, setA] = React.useState("24");
  const [w, setW] = React.useState("75");
  const [female, setFemale] = React.useState(false);
  const vv = num(v), av = num(a), wv = num(w);
  let body: React.ReactNode = <div style={{ fontSize: 11.5, color: "var(--dim)" }}>VIFT, yaş, kilo gir.</div>;
  let payload: SavePayload | null = null;
  if (vv > 0 && av > 0 && wv > 0) {
    const g = female ? 2 : 1;
    const vo2 = r1(28.3 - 2.15 * g - 0.741 * av - 0.0357 * wv + 0.0586 * av * vv + 1.03 * vv);
    const flag: Flag = vo2 >= 60 ? "good" : vo2 >= 52 ? "warn" : "bad";
    body = <Result big={`${vo2}`} flag={flag} lines={["ml/kg/dk · Buchheit (2008)", `VIFT ${r1(vv)} km/sa`]} />;
    payload = { protocol: "ift_30_15", value: r1(vv), label: `VIFT ${r1(vv)} · VO2max ${vo2}`,
      components: { age: av, weight_kg: wv, female, vo2max_est: vo2 } };
  }
  return (
    <Card icon="ti-lungs" title="Dayanıklılık (VO2max) — 30-15 IFT" sub="VIFT · Buchheit"
      explain="Son tamamlanan kademenin hızından (VIFT) tahmini VO2max ve aralıklı dayanıklılık. Antrenman hız bölgelerini belirler.">
      <NumIn label="VIFT (son kademe hızı)" value={v} set={setV} step="0.5" unit="km/sa" />
      <div style={{ display: "flex", gap: 8 }}>
        <div style={{ flex: 1 }}><NumIn label="Yaş" value={a} set={setA} step="1" /></div>
        <div style={{ flex: 1 }}><NumIn label="Kilo" value={w} set={setW} step="1" unit="kg" /></div>
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--dim)", marginBottom: 8 }}>
        <input type="checkbox" checked={female} onChange={(e) => setFemale(e.target.checked)} /> Kadın
      </label>
      {body}
      <SaveBtn payload={payload} saveKey="vo2vift" />
    </Card>
  );
}

// ── Maç Sonrası Kasık Kuvveti (MD+1 Adductor) ───────────────────────────────
function AdductorCard() {
  const [cur, setCur] = React.useState("340");
  const [prev, setPrev] = React.useState("400");
  const c = num(cur), p = num(prev);
  let body: React.ReactNode = <div style={{ fontSize: 11.5, color: "var(--dim)" }}>Önceki ölçüm pozitif olmalı.</div>;
  let payload: SavePayload | null = null;
  if (p > 0 && c >= 0) {
    const drop = r2(((p - c) / p) * 100);
    const flagged = drop > ADDUCTOR_DROP_FLAG_PCT;
    body = <Result big={drop >= 0 ? `−%${drop}` : `+%${Math.abs(drop)}`} flag={flagged ? "bad" : "good"}
      lines={[`${r1(p)}N → ${r1(c)}N`,
        flagged ? `> %${ADDUCTOR_DROP_FLAG_PCT} düşüş → kasık/pubis riski` : "düşüş eşik altında"]} />;
    payload = { protocol: "adductor_squeeze", value: r1(c), label: `%${drop} düşüş`,
      components: { previous: r1(p), drop_pct: drop, flagged } };
  }
  return (
    <Card icon="ti-stethoscope" title="Maç Sonrası Kasık Kuvveti" sub="MD+1 Adductor Squeeze"
      explain="Maç ertesi (MD+1) kasık (adduktor) sıkıştırma kuvvetindeki düşüş. %10 üstü düşüş kasık/pubis sakatlık göstergesidir.">
      <NumIn label="Güncel squeeze" value={cur} set={setCur} step="5" unit="N" />
      <NumIn label="Önceki ölçüm" value={prev} set={setPrev} step="5" unit="N" />
      {body}
      <SaveBtn payload={payload} saveKey="adductor" />
    </Card>
  );
}

// ── Maç Sonrası Sıçrama Yorgunluğu (MD+1 CMJ) ───────────────────────────────
function CMJCard() {
  const [cur, setCur] = React.useState("34");
  const [base, setBase] = React.useState("40, 41, 39");
  const c = num(cur);
  const baseVals = base.split(/[,\s]+/).map(Number).filter((n) => !Number.isNaN(n) && n > 0);
  let body: React.ReactNode = <div style={{ fontSize: 11.5, color: "var(--dim)" }}>Baseline değerleri gir.</div>;
  let payload: SavePayload | null = null;
  if (c >= 0 && baseVals.length >= 1) {
    const mean = baseVals.reduce((a, b) => a + b, 0) / baseVals.length;
    const drop = r2(((mean - c) / mean) * 100);
    const flagged = drop > CMJ_FATIGUE_DROP_PCT;
    body = <Result big={drop >= 0 ? `−%${drop}` : `+%${Math.abs(drop)}`} flag={flagged ? "bad" : "good"}
      lines={[`baseline ort. ${r1(mean)}cm → güncel ${r1(c)}cm`,
        flagged ? `> %${CMJ_FATIGUE_DROP_PCT} → nöromusküler yorgunluk` : "toparlanmış"]} />;
    payload = { protocol: "cmj", value: r1(c), label: `MD+1 %${drop} düşüş`,
      components: { baseline_values: baseVals.map(r1), baseline_mean: r1(mean), drop_pct: drop, flagged } };
  }
  return (
    <Card icon="ti-bolt" title="Maç Sonrası Sıçrama Yorgunluğu" sub="MD+1 CMJ · nöromusküler"
      explain="Maç ertesi (MD+1) dikey sıçrama yüksekliğindeki düşüş. %10 üstü düşüş nöromüsküler yorgunluğu gösterir.">
      <NumIn label="Güncel CMJ" value={cur} set={setCur} step="0.5" unit="cm" />
      <TxtIn label="Baseline CMJ (virgülle)" value={base} set={setBase} />
      {body}
      <SaveBtn payload={payload} saveKey="cmj" />
    </Card>
  );
}

// ── Sahaya Dönüş Hazırlığı (Return-to-Play) — anlık değerlendirme, kaydedilmez ─
function RTPCard() {
  const [cur, setCur] = React.useState("92");
  const [base, setBase] = React.useState("100");
  const [hib, setHib] = React.useState(true);
  const c = num(cur), b = num(base);
  let body: React.ReactNode = <div style={{ fontSize: 11.5, color: "var(--dim)" }}>Pozitif değerler gir.</div>;
  if (c > 0 && b > 0) {
    const pct = r1((hib ? c / b : b / c) * 100);
    const cleared = pct >= RTP_GREEN_LIGHT_PCT;
    body = <Result big={`%${pct}`} flag={cleared ? "good" : "bad"}
      lines={[`baseline'ın %${pct}'i · ${cleared ? "🟢 yeşil ışık" : "🔴 kırmızı ışık"}`,
        cleared ? "sahaya çıkabilir" : `< %${RTP_GREEN_LIGHT_PCT} → sahaya çıkmasın`]} />;
  }
  return (
    <Card icon="ti-traffic-lights" title="Sahaya Dönüş Hazırlığı" sub="Return-to-Play"
      explain="Sakatlık sonrası performansın sağlıklı dönemdeki seviyeye (baseline) oranı. ≥%95 yeşil ışık = sahaya hazır.">
      <NumIn label="Dönüş mikro-test sonucu" value={cur} set={setCur} step="0.1" />
      <NumIn label="Sakatlık-öncesi baseline" value={base} set={setBase} step="0.1" />
      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--dim)", marginBottom: 8 }}>
        <input type="checkbox" checked={hib} onChange={(e) => setHib(e.target.checked)} /> Yüksek değer iyi (sprint süresi ise işareti kaldır)
      </label>
      {body}
      <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 8 }}>
        <i className="ti ti-info-circle" style={{ marginRight: 4 }} />Anlık karar — tek metrik kaydı yerine ilgili teste kaydedilir.
      </div>
    </Card>
  );
}

// ── Mevkiye özel test paketi ────────────────────────────────────────────────
const PRESETS: Record<string, string[]> = {
  kaleci: ["cmj", "sj", "drop_jump_rsi", "sprint_5m", "t505", "adductor_squeeze"],
  stoper: ["cmj", "sprint_10m", "t505", "yoyo_irl1", "isokinetic_ham", "adductor_squeeze"],
  bek: ["sprint_10m", "sprint_30m", "ift_30_15", "illinois", "rsa", "triple_hop"],
  kanat: ["sprint_10m", "sprint_30m", "ift_30_15", "arrowhead", "rsa", "triple_hop"],
  orta_saha: ["yoyo_irl1", "ift_30_15", "vo2max", "sprint_30m", "ttest_agility", "cmj"],
  forvet: ["sprint_5m", "sprint_10m", "cmj", "drop_jump_rsi", "t505", "adductor_squeeze"],
};
const POS_LABEL: Record<string, string> = {
  kaleci: "Kaleci", stoper: "Stoper", bek: "Bek", kanat: "Kanat",
  orta_saha: "Orta Saha", forvet: "Forvet",
};

function PresetCard() {
  const [pos, setPos] = React.useState("kaleci");
  const keys = PRESETS[pos] ?? [];
  return (
    <div className="rc" style={{ margin: 0 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {Object.keys(PRESETS).map((k) => (
          <button key={k} type="button" onClick={() => setPos(k)}
            style={{
              padding: "6px 12px", borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: "pointer",
              fontFamily: "inherit", border: pos === k ? 0 : "1px solid var(--line)",
              background: pos === k ? "var(--besiktas)" : "var(--panel)",
              color: pos === k ? "#fff" : "var(--ink)",
            }}>
            {POS_LABEL[k]}
          </button>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
        {keys.map((k) => (
          <div key={k} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 8, background: "var(--surface2)", fontSize: 12.5 }}>
            <i className="ti ti-circle-check" style={{ color: "var(--low)" }} />
            {PROTO_NAME[k] ?? k}
          </div>
        ))}
      </div>
      <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 10 }}>
        {POS_LABEL[pos]} için önerilen default test bataryası ({keys.length} protokol). Bilinmeyen mevki → genel batarya.
      </div>
    </div>
  );
}
