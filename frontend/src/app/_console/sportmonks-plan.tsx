"use client";

/**
 * Sportmonks Bağlantı Planı — matchday motorunu gerçek veriye bağlama haritası
 * (görünür). Her özellik → kaynak + durum (hazır/add-on/türetilir/premium) + 3 faz.
 * Veri: lib/sportmonks-matchday.
 */

import * as React from "react";
import { MATCHDAY_DATA_MAP, matchdaySummary, STATUS_LABEL, STATUS_COLOR, type SmStatus, type MatchdayDataItem } from "@/lib/sportmonks-matchday";

const SCREENS = ["Maç Öncesi", "Maç Modu", "Devre Arası", "Değerlendirme"] as const;

export function SportmonksPlanBody() {
  const sum = matchdaySummary();
  const byScreen = (s: string) => MATCHDAY_DATA_MAP.filter((i) => i.screen === s);

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Özet sayım */}
      <div className="kpis" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))" }}>
        {(Object.keys(sum) as SmStatus[]).map((st) => (
          <div className="kpi" key={st} style={{ borderTop: `3px solid ${STATUS_COLOR[st]}` }}>
            <div className="kl">{STATUS_LABEL[st]}</div>
            <div className="kn" style={{ color: STATUS_COLOR[st] }}>{sum[st]}</div>
            <div className="kd">{MATCHDAY_DATA_MAP.length} özellikten</div>
          </div>
        ))}
      </div>

      {/* Açıklama */}
      <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--accent)" }}>
        <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.6 }}>
          Matchday motorunun her parçası bir Sportmonks kaynağına eşlendi. <b style={{ color: "var(--low)" }}>Hazır</b> = temel
          aboneliğle çalışır (bazıları zaten bağlı). <b style={{ color: "var(--mid)" }}>Add-on</b> = belirli paket (xG/Predictions/
          Livescores) gerekir. <b style={{ color: "var(--accent)" }}>Türetilir</b> = gerçek agregat statten hesaplarız. <b style={{ color: "var(--high)" }}>Premium</b> =
          Sportmonks&apos;ta yok, mekânsal/event-koordinat feed&apos;i (Tier 2) ister → projeksiyon kalır, dürüstçe işaretli. <b>Motor ve UI değişmez</b> — sadece veri kaynağı.
        </div>
      </div>

      {/* Ekran-ekran harita */}
      {SCREENS.map((screen) => (
        <div key={screen}>
          <div style={{ fontSize: 11, color: "var(--dim)", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 7 }}>{screen}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {byScreen(screen).map((i: MatchdayDataItem, k) => {
              const c = STATUS_COLOR[i.status];
              return (
                <div key={k} style={{ display: "flex", gap: 11, alignItems: "flex-start", borderRadius: 9, background: "var(--panel)", border: "1px solid var(--line)", borderLeft: `4px solid ${c}`, padding: "10px 13px" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 800 }}>{i.feature}</div>
                    <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45, marginTop: 2 }}>{i.note}</div>
                    <div style={{ fontSize: 10.5, color: "var(--dim)", fontFamily: "JetBrains Mono", marginTop: 3 }}>↳ {i.smSource}</div>
                  </div>
                  <span style={{ fontSize: 9.5, fontWeight: 800, color: "#fff", background: c, borderRadius: 4, padding: "2px 7px", whiteSpace: "nowrap", flexShrink: 0 }}>{STATUS_LABEL[i.status]}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* 3 fazlı geçiş */}
      <div className="rc" style={{ margin: 0 }}>
        <h3 style={{ margin: "0 0 8px" }}>3 Fazlı Geçiş Planı</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[
            { n: "Faz 1", c: "var(--low)", t: "Temel gerçek (kısmen bağlı)", d: "/sm/schedule + /sm/squad + standings → Maç Öncesi'nde fikstür/form/kadro gerçek. Kalibrasyon backtest'i Süper Lig'de çalıştırılır → senin liginde kendi güven rakamı." },
            { n: "Faz 2", c: "var(--mid)", t: "Add-on'lar (xG + Predictions + Livescores)", d: "Canlı skor/olay/xG + tahmin. Maç Modu canlı feed'e bağlanır (live-feed.ts providerFeed implemente edilir, UI değişmez). Win-prob/momentum/bütçe/devre-arası stat gerçek; reconcile + motor sicili gerçek olaylarla dolar." },
            { n: "Faz 3", c: "var(--high)", t: "Derinlik (+ opsiyonel Tier 2)", d: "Rakip zaafları/DNA/dangerman agregat statten gerçek girdiyle. Mekânsal sinyaller (rakip canlı okuma, pas ağı, pres bölgesi) projeksiyon kalır → bunlar için Wyscout/Opta event feed'i ayrı karar." },
          ].map((p) => (
            <div key={p.n} style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: "#fff", background: p.c, borderRadius: 5, padding: "3px 9px", flexShrink: 0, fontFamily: "JetBrains Mono" }}>{p.n}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 800 }}>{p.t}</div>
                <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5, marginTop: 2 }}>{p.d}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 10, lineHeight: 1.5, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
          Mimari hazır: adapter dikişi <b>live-feed.ts</b> (LiveFeedSource) + <b>sportmonks.ts</b> (/sm/*) + <b>sportmonks-matchday.ts</b> (eşleme + stub&apos;lar). Abonelik gelince stub&apos;lar gerçek çağrılarla doldurulur; motorlar değişmeden gerçeğe geçer.
        </div>
      </div>
    </div>
  );
}
