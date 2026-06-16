"use client";

/**
 * MAÇ MODU / Kenar Ekranı — antrenör-analist için maç-İÇİ glanceable yüzey.
 *
 * Dashboard DEĞİL: tek sütun, dev tip, sadece O AN önemli olan. ZAMAN-GÜDÜMLÜ:
 * oynat/duraklat/sar ile dakika ilerler; skor, kazanma olasılığı ve momentum
 * gerçek zaman-serisinden (LIVE_SERIES + win-prob eğrisi) güncellenir, olaylar
 * zamanı gelince "düşer". Taktik karar kartları = canlı 67' okuması (analist o an
 * ne yapmalı). Gerçekte canlı feed besler; demo'da kayıtlı zaman-serisi oynatılır.
 */

import * as React from "react";
import Link from "next/link";
import { demoLive } from "@/lib/demo-data";
import { demoWinProbCurve, demoWinProbNow, projectWithBoost } from "@/lib/live-win-probability";
import { logAction, removeAction, actionFor, loadActions, type ActionVerb } from "@/lib/action-log";
import { activeFeed } from "@/lib/live-feed";

/** Uygula / Atla — analistin öneriye kararı, kanıt defterine kalıcı düşer. */
function ActionButtons({ id, label, minute, onChange }: { id: string; label: string; minute: number; onChange?: () => void }) {
  const [verb, setVerb] = React.useState<ActionVerb | null>(null);
  React.useEffect(() => { setVerb(actionFor(id)); }, [id]);
  const act = (v: ActionVerb) => { logAction(id, label, minute, v); setVerb(v); onChange?.(); };
  const undo = () => { removeAction(id); setVerb(null); onChange?.(); };

  if (verb) {
    const applied = verb === "applied";
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
        <span style={{ fontSize: 11.5, fontWeight: 800, color: applied ? "var(--low)" : "var(--dim)" }}>
          {applied ? "✓ Uygulandı" : "✕ Atlandı"} <span style={{ color: "var(--dim)", fontWeight: 400 }}>· kanıt defterine düştü</span>
        </span>
        <button onClick={undo} style={{ marginLeft: "auto", background: "none", border: "none", color: "var(--dim)", fontSize: 10.5, cursor: "pointer", textDecoration: "underline" }}>geri al</button>
      </div>
    );
  }
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
      <button onClick={() => act("applied")} style={{ flex: 1, background: "var(--low)", color: "#fff", border: "none", borderRadius: 7, padding: "7px 0", fontSize: 12, fontWeight: 800, cursor: "pointer" }}>Uygula</button>
      <button onClick={() => act("dismissed")} style={{ flex: 1, background: "var(--panel)", color: "var(--muted)", border: "1px solid var(--line)", borderRadius: 7, padding: "7px 0", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>Atla</button>
    </div>
  );
}

const LIVE_END = demoLive.minute;             // verinin bittiği "şu an" (67')
const curve = demoWinProbCurve();
const pct = (x: number) => `%${Math.round(x * 100)}`;

// Planlı değişikliklerin beklenen etkisi (subTiming) — ada göre.
const SUB_IMPACTS = demoLive.subTiming.package.map((name, i) => ({ name, impact: demoLive.subTiming.advices[i]?.impact ?? 0 }));
const PLANNED_BOOST = SUB_IMPACTS.reduce((s, x) => s + x.impact, 0);
// impact = VAEP-tarzı katkı skoru, birebir xG değil → kalan-süre xG'ye sönümlü
// çevrilir (bir değişiklik win-prob'u abartmadan birkaç puan oynatır).
const SUB_XG_FACTOR = 0.4;
const toXg = (impact: number) => impact * SUB_XG_FACTOR;
/** Uygulanan sub'ların toplam beklenen etkisi (kalan sürede ek gol). */
function appliedBoost(): number {
  let b = 0;
  for (const a of loadActions()) {
    if (a.id.startsWith("sub-") && a.verb === "applied") {
      const m = SUB_IMPACTS.find((s) => s.name === a.id.slice(4));
      if (m) b += m.impact;
    }
  }
  return b;
}

/** {minute, ...} dizisinde t anına doğrusal interpolasyon. */
function interp(t: number, pts: readonly { minute: number }[], key: string): number {
  const arr = pts as readonly Record<string, number>[];
  if (t <= arr[0].minute) return arr[0][key];
  const last = arr[arr.length - 1];
  if (t >= last.minute) return last[key];
  for (let i = 1; i < arr.length; i++) {
    if (t <= arr[i].minute) {
      const a = arr[i - 1], b = arr[i];
      const f = (t - a.minute) / ((b.minute - a.minute) || 1);
      return a[key] + (b[key] - a[key]) * f;
    }
  }
  return last[key];
}
function scoreAt(t: number): [number, number] {
  let h = 0, a = 0;
  for (const e of demoLive.events) if (e.minute <= t && e.type === "gol") (e.team === "home" ? h++ : a++);
  return [h, a];
}

/** Üst bar — skor, dakika, kazanma olasılığı, momentum oku (t anına göre). */
function LiveHeader({ t, homeBoost }: { t: number; homeBoost: number }) {
  const L = demoLive;
  const [sh, sa] = scoreAt(t);
  const mom = interp(t, L.series, "momentum");
  const live = t >= LIVE_END;
  // Canlı anda uygulanan değişikliklerin kazanma olasılığına yansıması.
  const projected = live && homeBoost > 0 ? projectWithBoost(demoWinProbNow(), toXg(homeBoost)) : null;
  const baseHome = live ? demoWinProbNow().pHome : interp(t, curve, "pHome");
  const arrow = mom > 15 ? "▲" : mom < -15 ? "▼" : "■";
  const momColor = mom > 15 ? "var(--low)" : mom < -15 ? "var(--crit)" : "var(--mid)";
  const momText = mom > 15 ? "momentum bizde" : mom < -15 ? "momentum rakipte" : "momentum dengeli";
  const outcomes = [
    { label: L.home, p: interp(t, curve, "pHome"), c: "var(--accent)" },
    { label: "Berabere", p: interp(t, curve, "pDraw"), c: "var(--dim)" },
    { label: L.away, p: interp(t, curve, "pAway"), c: "var(--high)" },
  ];
  const lead = [...outcomes].sort((a, b) => b.p - a.p)[0];
  return (
    <div className="rc" style={{ margin: 0, textAlign: "center" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14, flexWrap: "wrap" }}>
        <span style={{ fontSize: 16, fontWeight: 800 }}>{L.home}</span>
        <span style={{ fontSize: 30, fontWeight: 900, fontFamily: "JetBrains Mono" }}>{sh}–{sa}</span>
        <span style={{ fontSize: 16, fontWeight: 800 }}>{L.away}</span>
        <span style={{ fontSize: 13, fontWeight: 800, color: "#fff", background: t >= LIVE_END ? "var(--crit)" : "var(--dim)", borderRadius: 5, padding: "3px 9px", fontFamily: "JetBrains Mono" }}>{Math.round(t)}&apos;{t >= LIVE_END ? " CANLI" : ""}</span>
      </div>
      <div style={{ display: "flex", height: 26, borderRadius: 7, overflow: "hidden", border: "1px solid var(--line)", marginTop: 12 }}>
        {outcomes.map((o) => (
          <div key={o.label} style={{ width: `${o.p * 100}%`, background: o.c, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 11, fontWeight: 800, fontFamily: "JetBrains Mono", minWidth: 0, transition: "width .35s ease" }}>
            {o.p > 0.14 ? pct(o.p) : ""}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginTop: 10 }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>En olası: {lead.label} {pct(lead.p)}</span>
        <span style={{ fontSize: 14, fontWeight: 800, color: momColor, fontFamily: "JetBrains Mono", transition: "color .3s" }}>{arrow} {momText}</span>
      </div>
      {projected && (
        <div style={{ marginTop: 10, fontSize: 12, color: "var(--low)", fontWeight: 700, background: "color-mix(in srgb, var(--low) 9%, transparent)", borderRadius: 7, padding: "7px 10px" }}>
          Uygulanan değişiklikle: {L.home} galibiyet{" "}
          <span style={{ fontFamily: "JetBrains Mono" }}>{pct(baseHome)} → {pct(projected.pHome)}</span>{" "}
          <span style={{ color: projected.pHome >= baseHome ? "var(--low)" : "var(--crit)" }}>({projected.pHome >= baseHome ? "+" : ""}{Math.round((projected.pHome - baseHome) * 100)} puan)</span>
        </div>
      )}
    </div>
  );
}

/** Zaman kontrolü — oynat/duraklat + sar. */
function TimeControl({ t, setT, playing, setPlaying }: { t: number; setT: (n: number) => void; playing: boolean; setPlaying: (b: boolean) => void }) {
  return (
    <div className="rc" style={{ margin: 0, display: "flex", alignItems: "center", gap: 12 }}>
      <button
        onClick={() => { if (t >= LIVE_END) setT(0); setPlaying(!playing); }}
        style={{ width: 42, height: 42, borderRadius: "50%", border: "none", background: "var(--accent)", color: "#fff", fontSize: 18, cursor: "pointer", flexShrink: 0 }}
        aria-label={playing ? "Duraklat" : "Oynat"}
      >{playing ? "⏸" : t >= LIVE_END ? "↻" : "▶"}</button>
      <input
        type="range" min={0} max={LIVE_END} value={t}
        onChange={(e) => { setPlaying(false); setT(Number(e.target.value)); }}
        style={{ flex: 1, accentColor: "var(--accent)", cursor: "pointer" }}
        aria-label="Maç dakikası"
      />
      <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 16, width: 42, textAlign: "right" }}>{Math.round(t)}&apos;</span>
    </div>
  );
}

const EV_COLOR: Record<string, string> = {
  gol: "var(--low)", buyuk_firsat: "var(--accent)", sari_kart: "var(--mid)",
  sakatlik: "var(--crit)", degisiklik: "var(--dim)",
};
const EV_LABEL: Record<string, string> = {
  gol: "GOL", buyuk_firsat: "Fırsat", sari_kart: "Sarı kart", sakatlik: "Sakatlık", degisiklik: "Değişiklik",
};

/** Olay akışı — t'ye kadarki olaylar, en yeni üstte ve vurgulu (zamanı gelince düşer). */
function LiveEventFeed({ t }: { t: number }) {
  const shown = demoLive.events.filter((e) => e.minute <= t).sort((a, b) => b.minute - a.minute);
  if (!shown.length) return <div style={{ fontSize: 12, color: "var(--dim)", textAlign: "center", padding: "8px 0" }}>Henüz olay yok — maç başlıyor.</div>;
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>Olay akışı</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {shown.map((e, i) => {
          const fresh = i === 0;
          const col = EV_COLOR[e.type] ?? "var(--dim)";
          return (
            <div key={`${e.minute}-${e.type}`} style={{ display: "flex", gap: 10, alignItems: "flex-start", borderRadius: 8, padding: "9px 11px", background: fresh ? "color-mix(in srgb, var(--accent) 7%, var(--panel))" : "var(--panel)", border: `1px solid ${fresh ? "var(--accent)" : "var(--line)"}`, animation: fresh ? "fadein .4s ease" : undefined }}>
              <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 12, color: col, width: 30, flexShrink: 0 }}>{e.minute}&apos;</span>
              <div style={{ minWidth: 0 }}>
                <span style={{ fontSize: 9.5, fontWeight: 800, color: "#fff", background: col, borderRadius: 3, padding: "1px 5px", marginRight: 6 }}>{EV_LABEL[e.type] ?? e.type}</span>
                <span style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.4 }}>{e.text}</span>
              </div>
            </div>
          );
        })}
      </div>
      <style>{`@keyframes fadein{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}`}</style>
    </div>
  );
}

/** ŞİMDİ YAP — tek en acil hamle, dev kart (canlı 67' okuması). */
function NowAction({ onChange }: { onChange?: () => void }) {
  const top = demoLive.subs.find((s) => s.urgency === "kritik") ?? demoLive.subs[0];
  if (!top) return null;
  const window = demoLive.subTiming?.advices?.[0]?.verdict;
  const impact = demoLive.subTiming?.advices?.[0]?.impact;
  return (
    <div style={{ borderRadius: 12, border: "2px solid var(--crit)", background: "color-mix(in srgb, var(--crit) 8%, var(--panel))", padding: "16px 18px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ width: 11, height: 11, borderRadius: "50%", background: "var(--crit)" }} />
        <span style={{ fontSize: 12, fontWeight: 900, letterSpacing: 1, color: "var(--crit)" }}>ŞİMDİ YAP</span>
        {window && <span style={{ marginLeft: "auto", fontSize: 12, fontWeight: 800, fontFamily: "JetBrains Mono", color: "var(--crit)" }}>{window}</span>}
      </div>
      <div style={{ fontSize: 22, fontWeight: 900, lineHeight: 1.15, marginBottom: 6 }}>
        {top.player_out} <span style={{ color: "var(--crit)" }}>→</span> {top.player_in}
      </div>
      <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.5 }}>{top.rationale}</div>
      {impact != null && <div style={{ fontSize: 11.5, fontWeight: 700, color: "var(--low)", marginTop: 6, fontFamily: "JetBrains Mono" }}>beklenen etki +{impact.toFixed(2)} (kalan sürede)</div>}
      <ActionButtons id={`sub-${top.player_out}`} label={`${top.player_out} → ${top.player_in}`} minute={LIVE_END} onChange={onChange} />
    </div>
  );
}

const MAX_SUBS = 5;

/** Değişiklik Yönetimi — hak/pencere bütçesi + planlı değişiklikler (etkiyle).
 *  Uygulanan sub'lar (action-log) bütçeden düşer → gerçek maç-içi kısıt. */
function SubManager({ version }: { version: number }) {
  const baseSubs = demoLive.events.filter((e) => e.type === "degisiklik").length;  // 46' Cengiz→Jota = 1
  const [appliedSubs, setAppliedSubs] = React.useState(0);
  React.useEffect(() => {
    setAppliedSubs(loadActions().filter((a) => a.id.startsWith("sub-") && a.verb === "applied").length);
  }, [version]);
  const used = Math.min(MAX_SUBS, baseSubs + appliedSubs);
  const remaining = MAX_SUBS - used;
  const st = demoLive.subTiming;
  const plan = st.package.map((name, i) => ({ name, ...st.advices[i] }));
  const maxImpact = Math.max(...plan.map((p) => p.impact ?? 0), 0.01);

  return (
    <div className="rc" style={{ margin: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Değişiklik Yönetimi <span className="tiny">5 hak · 3 pencere</span></h3>
        <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 13, color: remaining <= 1 ? "var(--crit)" : "var(--ink)" }}>{used}/{MAX_SUBS} · {remaining} kaldı</span>
      </div>
      {/* hak göstergesi */}
      <div style={{ display: "flex", gap: 5, marginBottom: 12 }}>
        {Array.from({ length: MAX_SUBS }).map((_, i) => (
          <span key={i} style={{ flex: 1, height: 8, borderRadius: 4, background: i < used ? "var(--accent)" : "var(--line)" }} />
        ))}
      </div>
      {/* planlı değişiklik penceresi */}
      <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>Önerilen pencere</div>
      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5, marginBottom: 10 }}>{st.rationale}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        {plan.map((p) => (
          <div key={p.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 12, fontWeight: 700, width: 130, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</span>
            <span style={{ fontFamily: "JetBrains Mono", fontSize: 10.5, color: "var(--dim)", width: 88, flexShrink: 0 }}>{p.verdict}</span>
            <span className="mbar" style={{ flex: 1, margin: 0 }}><i style={{ width: `${((p.impact ?? 0) / maxImpact) * 100}%`, background: "var(--low)" }} /></span>
            <span style={{ fontFamily: "JetBrains Mono", fontSize: 11, fontWeight: 700, color: "var(--low)", width: 38, textAlign: "right" }}>+{(p.impact ?? 0).toFixed(2)}</span>
          </div>
        ))}
      </div>
      {/* Win-prob projeksiyonu — öneriler uygulanırsa */}
      {(() => {
        const now = demoWinProbNow();
        const xgAdd = toXg(PLANNED_BOOST);
        const planned = projectWithBoost(now, xgAdd);
        const delta = Math.round((planned.pHome - now.pHome) * 100);
        return (
          <div style={{ marginTop: 12, borderTop: "1px solid var(--line)", paddingTop: 10, fontSize: 12, lineHeight: 1.5 }}>
            <span style={{ color: "var(--muted)" }}>Önerilen değişiklikler uygulanırsa kazanma: </span>
            <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>{pct(now.pHome)} → {pct(planned.pHome)}</span>{" "}
            <span style={{ color: "var(--low)", fontWeight: 700 }}>(+{delta} puan)</span>
            <span style={{ color: "var(--dim)", fontSize: 10.5 }}> · beklenen ek tehditten (+{xgAdd.toFixed(2)} gol)</span>
          </div>
        );
      })()}
      {remaining <= 2 && <div style={{ fontSize: 11, color: "var(--mid)", marginTop: 10, lineHeight: 1.4 }}>⚠ {remaining} değişiklik hakkın kaldı — pencereyi dikkatli kullan (çift değişiklik tek pencere sayılır).</div>}
    </div>
  );
}

const sevColor = (s: string) => (s === "critical" || s === "kritik" ? "var(--crit)" : s === "warning" || s === "medium" ? "var(--mid)" : "var(--low)");

// Sistem uyarıları — her biri tetikleyen olaya/eşiğe BAĞLI bir tetik-dakikasıyla.
// (Sahte değil: dakika, demoLive olayları/momentum serisinden türetildi.)
//   31' Djaló sarı (event)  · 50' sağ-kanat üstünlük (spatial fırsat)
//   52' Kökçü sakatlık (event) · 57' Rıdvan düello kaybı (matchup, "son 10 dk")
//   58' momentum rakibe döndü (series -38) · 60' hatlar arası açıldı (spatial)
type Sev = "critical" | "warning" | "info";
interface LiveAlert { minute: number; sev: Sev; head: string; body: string }
const LIVE_ALERTS: LiveAlert[] = [
  { minute: 31, sev: "warning", head: "Kart riski — Tiago Djaló (4)", body: "Sarı kartlı. Agresif girişlere dikkat, ikinci sarı riski." },
  { minute: 50, sev: "info", head: "Fırsat — sağ kanat üstünlüğü", body: "Rashica + Murillo sağda sayısal üstün. Geçiş anında bu tarafı kullan." },
  { minute: 52, sev: "critical", head: "Yorgunluk kritik — Orkun Kökçü (10)", body: "Yorgunluk 0.62 + arka adale sinyali. Değişiklik penceresi açılıyor." },
  { minute: 57, sev: "warning", head: "Düello zaafı — sol koridor", body: "Rıdvan Yılmaz (3) son 10 dakikada 4 düellodan 3'ünü kaybetti — yardımcı gönder." },
  { minute: 58, sev: "warning", head: "Momentum rakibe döndü", body: "2 snapshot'tır momentum rakipte (-38). Pres hattını düşür, orta blokta dengele." },
  { minute: 60, sev: "critical", head: "Hatlar arası açıldı (~18m)", body: "Orta blok dağınık — rakip 10 numarası bu boşluğa sızıyor." },
];

const SEV_LABEL: Record<Sev, string> = { critical: "KRİTİK", warning: "UYARI", info: "FIRSAT" };

/** Push uyarı akışı — t'ye kadar tetiklenen sistem uyarıları, en yeni üstte. */
function SystemAlertFeed({ t, onChange }: { t: number; onChange?: () => void }) {
  const fired = LIVE_ALERTS.filter((a) => a.minute <= t).sort((a, b) => b.minute - a.minute);
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>
        Sistem uyarıları <span style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>({fired.length})</span>
      </div>
      {!fired.length
        ? <div style={{ fontSize: 12, color: "var(--dim)", fontStyle: "italic" }}>Henüz uyarı yok — sistem izliyor.</div>
        : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {fired.map((a) => {
              const c = sevColor(a.sev);
              const fresh = a.minute === fired[0].minute;
              return (
                <div key={a.minute} style={{ display: "flex", gap: 11, alignItems: "flex-start", borderRadius: 9, background: fresh ? `color-mix(in srgb, ${c} 8%, var(--panel))` : "var(--panel)", border: `1px solid ${fresh ? c : "var(--line)"}`, borderLeft: `4px solid ${c}`, padding: "11px 13px", animation: fresh ? "fadein .4s ease" : undefined }}>
                  <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 12, color: c, width: 30, flexShrink: 0 }}>{a.minute}&apos;</span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <span style={{ fontSize: 9, fontWeight: 800, color: "#fff", background: c, borderRadius: 3, padding: "1px 5px", marginRight: 6 }}>{SEV_LABEL[a.sev]}</span>
                    <span style={{ fontSize: 14, fontWeight: 800 }}>{a.head}</span>
                    <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.45, marginTop: 3 }}>{a.body}</div>
                    <ActionButtons id={`alert-${a.minute}`} label={a.head} minute={a.minute} onChange={onChange} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
    </div>
  );
}

/** Toast — son ~3 dakikada düşen uyarı, ekrana "push" gibi gelir. */
function AlertToast({ t }: { t: number }) {
  const recent = LIVE_ALERTS.filter((a) => a.minute <= t && a.minute > t - 3).sort((a, b) => (b.sev === "critical" ? 1 : 0) - (a.sev === "critical" ? 1 : 0) || b.minute - a.minute)[0];
  if (!recent) return null;
  const c = sevColor(recent.sev);
  return (
    <div key={recent.minute} style={{ display: "flex", alignItems: "center", gap: 10, borderRadius: 10, background: c, color: "#fff", padding: "10px 14px", animation: "drop .45s cubic-bezier(.2,.8,.3,1)" }}>
      <span style={{ fontSize: 16 }}>🔔</span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.8, opacity: 0.85 }}>{SEV_LABEL[recent.sev]} · {recent.minute}&apos; · YENİ</div>
        <div style={{ fontSize: 13.5, fontWeight: 800, lineHeight: 1.2 }}>{recent.head}</div>
      </div>
      <style>{`@keyframes drop{from{opacity:0;transform:translateY(-14px)}to{opacity:1;transform:none}}`}</style>
    </div>
  );
}

const TRIG_LABEL: Record<string, string> = { press_height: "Pres hattı", channel_shift: "Koridor kaydır", block_height: "Blok yüksekliği" };
const TRIG_ICON: Record<string, string> = { press_height: "⬇️", channel_shift: "↔️", block_height: "📏" };

/** Canlı taktik ayarlar — değişiklik DIŞI hamleler (pres/koridor), Uygula/Atla'lı. */
function TacticalAdjustments({ onChange }: { onChange?: () => void }) {
  const trigs = demoLive.tacticalTriggers;
  if (!trigs.length) return null;
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>Canlı taktik ayarlar <span style={{ textTransform: "none", color: "var(--muted)" }}>· değişiklik dışı</span></div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {trigs.map((tr, i) => (
          <div key={i} style={{ borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: "4px solid var(--mid)", padding: "11px 13px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 15 }}>{TRIG_ICON[tr.type] ?? "⚙️"}</span>
              <span style={{ fontSize: 13, fontWeight: 800 }}>{TRIG_LABEL[tr.type] ?? tr.type}</span>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.45, marginTop: 4 }}>{tr.recommendation}</div>
            <ActionButtons id={`tac-${tr.type}`} label={`${TRIG_LABEL[tr.type] ?? tr.type}: ${tr.recommendation.slice(0, 40)}…`} minute={LIVE_END} onChange={onChange} />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Rakip canlı okuma — rakip şu an ne yapıyor (şekil/boşluk/üstünlük/sıcak oyuncu). */
function OpponentLiveRead() {
  const sp = demoLive.spatial, mu = demoLive.matchup;
  const cells = [
    { label: "Rakip şekli", value: sp.shape_state ?? "—", color: "var(--high)" },
    { label: "Hatlar arası", value: `${sp.gap_between_lines ?? "—"} m`, color: (sp.gap_between_lines ?? 0) > 15 ? "var(--crit)" : "var(--ink)" },
    { label: "Saha üstünlüğü", value: sp.superiority_flank ?? "—", color: /biz/.test(sp.superiority_flank ?? "") ? "var(--low)" : "var(--high)" },
    { label: "Sıcak rakip", value: mu.hot_opponent ? `#${mu.hot_opponent}` : "—", color: "var(--crit)" },
    { label: "Zorlanan bizimki", value: mu.struggling_defender ? `#${mu.struggling_defender}` : "—", color: "var(--mid)" },
  ];
  return (
    <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--high)" }}>
      <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 8 }}>Rakip canlı okuma <span style={{ textTransform: "none", color: "var(--muted)" }}>· şu an ne yapıyorlar</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: 10 }}>
        {cells.map((c) => (
          <div key={c.label}>
            <div style={{ fontSize: 10, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.3 }}>{c.label}</div>
            <div style={{ fontSize: 14, fontWeight: 800, color: c.color, fontFamily: "JetBrains Mono", marginTop: 2 }}>{c.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MatchModeBody() {
  const L = demoLive;
  const [t, setT] = React.useState(LIVE_END);
  const [playing, setPlaying] = React.useState(false);
  const [actionsVersion, setActionsVersion] = React.useState(0);
  const bump = () => setActionsVersion((v) => v + 1);
  const [boost, setBoost] = React.useState(0);
  React.useEffect(() => { setBoost(appliedBoost()); }, [actionsVersion]);

  React.useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setT((cur) => { if (cur >= LIVE_END) { setPlaying(false); return cur; } return cur + 1; });
    }, 280);
    return () => clearInterval(id);
  }, [playing]);

  const live = t >= LIVE_END;

  return (
    <div style={{ maxWidth: 560, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
      <AlertToast t={t} />
      {t >= 45 && (
        <Link href="/halftime-mode" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: 10, borderRadius: 10, border: "1.5px solid var(--accent)", background: "color-mix(in srgb, var(--accent) 8%, var(--panel))", padding: "11px 14px" }}>
          <span style={{ fontSize: 18 }}>⏸</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: "var(--ink)" }}>Devre arası — soyunma odası okuması hazır</div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>2. yarıya öncelikli hamleler + plan</div>
          </div>
          <span style={{ fontSize: 12, fontWeight: 800, color: "var(--accent)" }}>Devre Arası Modu →</span>
        </Link>
      )}
      <LiveHeader t={t} homeBoost={boost} />
      <TimeControl t={t} setT={setT} playing={playing} setPlaying={setPlaying} />
      <SystemAlertFeed t={t} onChange={bump} />
      <LiveEventFeed t={t} />

      {/* Canlı taktik okuması — 67' anlık karar katmanı */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
        <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
        <span style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: 0.8, color: live ? "var(--crit)" : "var(--dim)" }}>CANLI OKUMA · {LIVE_END}&apos;</span>
        <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
      </div>
      {!live && <div style={{ fontSize: 11, color: "var(--dim)", textAlign: "center", marginTop: -6 }}>Yukarıda geçmişi izliyorsun — aşağısı şu anki ({LIVE_END}&apos;) karar okuması.</div>}

      <NowAction onChange={bump} />
      <SubManager version={actionsVersion} />
      <TacticalAdjustments onChange={bump} />
      <OpponentLiveRead />

      <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--accent)" }}>
        <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 4 }}>Skor durumu · duruş ({L.closing.score_state})</div>
        <div style={{ fontSize: 13.5, color: "var(--ink)", lineHeight: 1.55 }}>{L.closing.closing_recipe}</div>
      </div>

      {/* Maç sonu → değerlendirme + veri kaynağı (seam) */}
      {live && (
        <Link href="/match-review" style={{ textDecoration: "none", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 10, border: "1.5px solid var(--accent)", background: "color-mix(in srgb, var(--accent) 8%, var(--panel))", padding: "11px 14px" }}>
          <span style={{ fontSize: 16 }}>📋</span>
          <span style={{ fontSize: 13, fontWeight: 800, color: "var(--ink)" }}>Maç sonu — uyarılar gerçekten oldu mu? Maç Değerlendirmesi →</span>
        </Link>
      )}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, fontSize: 11, color: "var(--dim)" }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: activeFeed().isLive ? "var(--crit)" : "var(--dim)" }} />
        <span>Veri kaynağı: <b style={{ color: "var(--muted)" }}>{activeFeed().label}</b>{activeFeed().latencyMs != null ? ` · ${activeFeed().latencyMs}ms gecikme` : ""} — production'da gerçek feed aynı arayüzü besler, UI değişmez.</span>
      </div>
      <div style={{ fontSize: 11, color: "var(--dim)", textAlign: "center", lineHeight: 1.5 }}>
        Kenar ekranı · analist için. Sistem sahayı görmez — sayısal sinyalleri hatırlatır, kararı sen verirsin.
      </div>
    </div>
  );
}
