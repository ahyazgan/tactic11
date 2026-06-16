"use client";

/**
 * Taktik Derin Dalış — saha analizi (Biz/Rakip geçişli) + pas ağı yan-yana
 * karşılaştırma. /opponent'taki iki bölümü tek client bileşende toplar.
 */

import * as React from "react";
import { deepProfile, passNetwork } from "@/lib/deep-tactical";
import { DeepTacticalBody, PassNetworkPitch } from "./pitch-analysis";

export function TacticalDeepDive({ usId, themId }: { usId: number; themId: number }) {
  const [side, setSide] = React.useState<"them" | "us">("them");
  const usDeep = deepProfile(usId), themDeep = deepProfile(themId);
  const usNet = passNetwork(usId), themNet = passNetwork(themId);
  const deep = side === "us" ? usDeep : themDeep;

  // Ağ yoğunluğu karşılaştırması (kenar sayısı + toplam ağırlık).
  const density = (n: typeof usNet) => (n ? n.edges.reduce((s, e) => s + e.weight, 0) : 0);
  const usDense = density(usNet), themDense = density(themNet);
  const compare = usNet && themNet
    ? `${usDense > themDense * 1.12 ? `Bizim ağ daha yoğun (kontrol bizde) — onların seyrek/dikine yapısına karşı topu tutup yorabiliriz.` : themDense > usDense * 1.12 ? `Rakip ağı daha yoğun — topa onlar sahip olacak, biz kompakt bekleyip geçişe çıkmalıyız.` : "İki ağ benzer yoğunlukta — top mücadelesi dengeli, detaylar belirleyici."} Hub'lar: biz #${usNet.hubNum} · onlar #${themNet.hubNum}.`
    : "";

  return (
    <>
      {/* Saha analizi — Biz/Rakip geçişli */}
      <div className="st">
        <h2>Saha Üstü Derin Analiz</h2>
        <div className="seg">
          <button className={side === "them" ? "on" : ""} onClick={() => setSide("them")}>Rakip</button>
          <button className={side === "us" ? "on" : ""} onClick={() => setSide("us")}>Biz</button>
        </div>
      </div>
      <div className="rc" style={{ margin: "0 0 12px" }}>
        {deep ? <DeepTacticalBody profile={deep} /> : <div style={{ fontSize: 12, color: "var(--dim)" }}>Profil yok.</div>}
      </div>

      {/* Pas ağı — yan yana karşılaştırma */}
      <div className="st"><h2>Pas Ağı — Karşılaştırma</h2><span className="ep">topla oyun · biz vs rakip</span></div>
      <div className="rc" style={{ margin: "0 0 12px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
          {[{ n: usNet, tag: "Biz", c: "var(--accent)" }, { n: themNet, tag: "Rakip", c: "var(--high)" }].map(({ n, tag, c }) =>
            n ? (
              <div key={tag}>
                <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6, color: c }}>
                  {n.name} <span style={{ color: "var(--dim)", fontWeight: 400, fontFamily: "JetBrains Mono", fontSize: 11 }}>{n.formation}</span>
                </div>
                <PassNetworkPitch net={n} />
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>{n.insight}</div>
              </div>
            ) : null,
          )}
        </div>
        {compare && (
          <div style={{ marginTop: 12, padding: "10px 13px", background: "var(--panel3)", borderRadius: 9, fontSize: 12.5, color: "var(--ink)", lineHeight: 1.6 }}>
            <span style={{ fontWeight: 700, color: "var(--accent)" }}>Okuma → </span>{compare}
          </div>
        )}
      </div>
    </>
  );
}
