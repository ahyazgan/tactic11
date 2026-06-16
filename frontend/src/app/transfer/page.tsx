"use client";

/**
 * Transfer — hedef shortlist (piyasa değeri + uyum skoru) + kendi kadronun
 * sözleşme bitişleri. ConsoleShell, FM26 açık tema. DEMO_MODE inline mock.
 * Backend bağlanınca app/engine/transfer (transfer_value, recruitment_fit,
 * contract_risk) motorlarına bağlanacak — değer € değil performans proxy'sidir.
 */

import * as React from "react";
import { demoSquad } from "@/lib/demo-data";
import { useProviderAccess, ProviderConnect, ProviderConnectedBar } from "@/lib/provider-access";
import { PlayerAvatar } from "@/lib/player-avatar";
import { ConsoleShell } from "../_console/shell";

interface Target {
  player: string; pos: string; age: number; club: string;
  value: number;   // milyon €
  expiry: string;  // sözleşme bitiş
  fit: number;     // uyum skoru 0..100
}

const TARGETS: Target[] = [
  { player: "Mateo Ferreira", pos: "Sol Kanat", age: 19, club: "CA Rosario", value: 8.5, expiry: "2027", fit: 91 },
  { player: "Luka Novak", pos: "Ön Libero", age: 23, club: "NK Maribor", value: 6.0, expiry: "2026", fit: 88 },
  { player: "Kwame Mensah", pos: "Stoper", age: 20, club: "Asante Kotoko", value: 4.2, expiry: "2026", fit: 84 },
  { player: "Diego Sánchez", pos: "Santrfor", age: 21, club: "Dep. Cali", value: 5.5, expiry: "2028", fit: 72 },
  { player: "Tom Bauer", pos: "Sağ Bek", age: 24, club: "SV Wehen", value: 2.8, expiry: "2025", fit: 58 },
];

// Kendi kadronun sözleşme bitişleri (demoSquad'dan deterministik).
const EXP_YEARS = ["2025", "2025", "2026", "2026", "2026", "2027", "2027", "2028"];
const OWN = demoSquad.slice(0, 10).map((p, i) => ({
  shirt: p.shirt, name: p.player_name, pos: p.pos_detail, age: p.age,
  expiry: EXP_YEARS[(p.player_id + i) % EXP_YEARS.length],
  value: Math.round((1.5 + ((p.player_id * 7) % 90) / 10) * 10) / 10,
})).sort((a, b) => a.expiry.localeCompare(b.expiry));

const EXPIRING = OWN.filter((p) => p.expiry <= "2026");
const TOTAL_VALUE = Math.round(TARGETS.reduce((a, t) => a + t.value, 0) * 10) / 10;
const AVG_FIT = Math.round(TARGETS.reduce((a, t) => a + t.fit, 0) / TARGETS.length);
const PRIORITY = TARGETS.filter((t) => t.fit >= 84).length;

function fitColor(v: number): string {
  if (v >= 85) return "var(--low)";
  if (v >= 70) return "var(--mid)";
  return "var(--dim)";
}
function expiryColor(y: string): string {
  if (y <= "2025") return "var(--crit)";
  if (y <= "2026") return "var(--high)";
  return "var(--muted)";
}

export default function TransferPage() {
  const access = useProviderAccess("transfer");

  // Kilitli: bölüm bir 3. parti transfer sağlayıcısına bağlanana dek karartılır.
  if (!access.connected) {
    return (
      <ConsoleShell
        active="/transfer"
        title="Transfer"
        sub="Bağlantı gerekli"
        desc="Transfer pazarı ve piyasa değeri verileri için bir 3. parti sağlayıcıya bağlan."
        right={<div className="rc"><h3>Neden bağlantı?</h3><div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55 }}>Piyasa değeri, sözleşme ve shortlist verileri bir transfer veri sağlayıcısından gelir. Sağlayıcını seçip ID + şifreni girince bölüm açılır.</div></div>}
      >
        <ProviderConnect kind="transfer" onConnect={access.connect} />
      </ConsoleShell>
    );
  }

  const right = (
    <>
      <div className="rc">
        <h3>Bütçe</h3>
        <div className="nm-vs" style={{ justifyContent: "space-between" }}>
          <div><div style={{ fontSize: 22, fontWeight: 800 }}>€15M</div><div style={{ fontSize: 11, color: "var(--dim)" }}>transfer bütçesi</div></div>
          <div style={{ textAlign: "right" }}><div style={{ fontSize: 22, fontWeight: 800, color: "var(--low)" }}>€6.5M</div><div style={{ fontSize: 11, color: "var(--dim)" }}>kalan</div></div>
        </div>
        <div className="mbar" style={{ marginTop: 6 }}><i style={{ width: "57%", background: "var(--accent)" }} /></div>
        <div style={{ fontSize: 11, color: "var(--muted)" }}>€8.5M tahsis (öncelikli hedefler)</div>
      </div>
      <div className="rc">
        <h3>Öncelikli Hedefler <span className="tiny">uyum ≥ 84</span></h3>
        {TARGETS.filter((t) => t.fit >= 84).map((t) => (
          <div className="alrt" key={t.player}>
            <span className="ai" style={{ background: fitColor(t.fit) }} />
            <div className="am"><b>{t.player}</b>
              <span className="tm">{t.pos} · €{t.value}M · uyum {t.fit}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="rc">
        <h3>Not</h3>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55 }}>
          Uyum skoru taktik profil + yaş + mevki ihtiyacından türetilir. Piyasa değeri performans proxy'sidir (gerçek piyasa verisi entegre edilince güncellenir).
        </div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/transfer"
      title="Transfer"
      sub="Shortlist · sözleşme · uyum"
      desc="Transfer hedefleri (piyasa değeri + uyum skoru) ve kendi kadronun sözleşme bitiş riski."
      right={right}
    >
      <ProviderConnectedBar providerLabel={access.providerLabel} user={access.user} onDisconnect={access.disconnect} />
      <div className="kpis">
        <div className="kpi"><div className="kl">Sözleşmesi Biten</div><div className="kn" style={{ color: "var(--high)" }}>{EXPIRING.length}</div><div className="kd">≤ 2026 · kendi kadro</div></div>
        <div className="kpi"><div className="kl">Hedef Oyuncu</div><div className="kn">{TARGETS.length}</div><div className="kd">shortlist</div></div>
        <div className="kpi"><div className="kl">Toplam Değer</div><div className="kn">€{TOTAL_VALUE}<span className="pct">M</span></div><div className="kd">hedeflerin</div></div>
        <div className="kpi"><div className="kl">Ort. Uyum</div><div className="kn" style={{ color: fitColor(AVG_FIT) }}>{AVG_FIT}</div><div className="kd">100 üzerinden</div></div>
        <div className="kpi"><div className="kl">Öncelikli</div><div className="kn" style={{ color: "var(--low)" }}>{PRIORITY}</div><div className="kd">uyum ≥ 84</div></div>
      </div>

      <div className="st" style={{ marginTop: 0 }}><h2>Transfer Hedefleri</h2><span className="ep">uyum skoruna göre</span></div>
      <div className="tbl" style={{ marginBottom: 16 }}>
        <table>
          <thead><tr>
            <th>Oyuncu</th><th>Mevki</th><th className="c">Yaş</th><th>Kulüp</th>
            <th className="r">Piyasa Değeri</th><th className="c">Sözleşme</th><th style={{ width: 160 }}>Uyum Skoru</th>
          </tr></thead>
          <tbody>
            {[...TARGETS].sort((a, b) => b.fit - a.fit).map((t) => {
              const c = fitColor(t.fit);
              return (
                <tr key={t.player}>
                  <td><span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}><PlayerAvatar name={t.player} size={22} /><span className="nm">{t.player}</span></span></td>
                  <td style={{ color: "var(--muted)" }}>{t.pos}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{t.age}</td>
                  <td style={{ color: "var(--muted)" }}>{t.club}</td>
                  <td className="r" style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>€{t.value}M</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: expiryColor(t.expiry) }}>{t.expiry}</td>
                  <td>
                    <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="cond" style={{ flex: 1 }}><i style={{ width: `${t.fit}%`, background: c }} /></span>
                      <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: c, minWidth: 24 }}>{t.fit}</span>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="st"><h2>Kendi Kadro — Sözleşme Bitişleri</h2><span className="ep">{EXPIRING.length} oyuncu ≤ 2026</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th><th>Oyuncu</th><th>Mevki</th><th className="c">Yaş</th>
            <th className="r">Değer (proxy)</th><th className="c">Bitiş</th><th className="c">Aksiyon</th>
          </tr></thead>
          <tbody>
            {OWN.map((p) => {
              const c = expiryColor(p.expiry);
              const action = p.expiry <= "2025" ? "Acil görüşme" : p.expiry <= "2026" ? "Uzatma planla" : "İzle";
              return (
                <tr key={p.shirt}>
                  <td className="pnum c">{p.shirt}</td>
                  <td><span className="nm">{p.name}</span></td>
                  <td style={{ color: "var(--muted)" }}>{p.pos}</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{p.age}</td>
                  <td className="r" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>€{p.value}M</td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: c }}>{p.expiry}</td>
                  <td className="c" style={{ fontSize: 11.5, color: c }}>{action}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
