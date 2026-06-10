"use client";

/**
 * 3. parti sağlayıcı erişim kapısı — Keşif & Transfer bölümü için.
 *
 * Bu bölüm (Oyuncu Keşif / Skaut Raporları / Transfer) bir TRANSFER/SCOUT veri
 * sağlayıcısına bağlanana kadar KİLİTLİ ve karartılmış gösterilir. Kullanıcı bir
 * sağlayıcı seçip ID + şifre (API anahtarı) girince bölüm açılır.
 *
 * Demo: kimlik bilgisi YALNIZCA cihazda (localStorage) tutulur, sunucuya gitmez;
 * boş olmayan ID+şifre bağlantıyı açar. Backend bağlanınca connect() gerçek
 * sağlayıcı OAuth/anahtar doğrulamasına bağlanır (aynı arayüz).
 *
 * Hiçbir CDN/asset çekmez (self-host kuralı) — ikonlar Tabler font + inline SVG.
 */

import * as React from "react";

export interface Provider { id: string; label: string; kind: string; idLabel: string }

// Gerçek 3. parti transfer & scout platformları.
export const PROVIDERS: Provider[] = [
  { id: "transfermarkt", label: "Transfermarkt",      kind: "piyasa değeri & transfer", idLabel: "Müşteri ID" },
  { id: "wyscout",       label: "Wyscout (Hudl)",     kind: "scout & video",            idLabel: "Hesap ID" },
  { id: "transferroom",  label: "TransferRoom",       kind: "transfer pazarı",          idLabel: "Kulüp ID" },
  { id: "comparisonator",label: "Comparisonator",     kind: "oyuncu karşılaştırma",     idLabel: "Lisans ID" },
  { id: "scisports",     label: "SciSports",          kind: "veri & yetenek",           idLabel: "Hesap ID" },
  { id: "scout7",        label: "Scout7 (Hudl)",      kind: "scout yönetimi",           idLabel: "Kullanıcı ID" },
];

interface Connection { provider: string; providerLabel: string; user: string; at: number }

const keyOf = (scope: string) => `m2.provider.${scope}`;

/** Bir bölümün sağlayıcı bağlantı durumu (localStorage, cihaza özel). */
export function useProviderAccess(scope: string) {
  const [conn, setConn] = React.useState<Connection | null>(null);
  const [ready, setReady] = React.useState(false);

  React.useEffect(() => {
    try {
      const raw = localStorage.getItem(keyOf(scope));
      if (raw) setConn(JSON.parse(raw) as Connection);
    } catch { /* yok say */ }
    setReady(true);
  }, [scope]);

  const connect = React.useCallback((providerId: string, user: string) => {
    const p = PROVIDERS.find((x) => x.id === providerId) ?? PROVIDERS[0];
    const c: Connection = { provider: p.id, providerLabel: p.label, user, at: Date.now() };
    try { localStorage.setItem(keyOf(scope), JSON.stringify(c)); } catch { /* yok say */ }
    setConn(c);
  }, [scope]);

  const disconnect = React.useCallback(() => {
    try { localStorage.removeItem(keyOf(scope)); } catch { /* yok say */ }
    setConn(null);
  }, [scope]);

  return {
    ready,
    connected: !!conn,
    provider: conn?.provider,
    providerLabel: conn?.providerLabel,
    user: conn?.user,
    connect,
    disconnect,
  };
}

// Karartılmış sahte önizleme — "sayfa burada ama kilitli" hissi (gerçek veri sızmaz).
function LockedPreview() {
  const bar = (w: string) => (
    <span style={{ display: "block", height: 10, width: w, borderRadius: 5, background: "var(--line2, #d8dae0)" }} />
  );
  return (
    <div aria-hidden style={{ filter: "blur(3px)", opacity: 0.4, pointerEvents: "none", userSelect: "none" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 10, marginBottom: 16 }}>
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="rc" style={{ margin: 0, display: "grid", gap: 10 }}>
            {bar("60%")}{bar("40%")}{bar("80%")}
          </div>
        ))}
      </div>
      <div className="rc" style={{ margin: 0, display: "grid", gap: 14 }}>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "30px 1fr 80px 80px 60px", gap: 12, alignItems: "center" }}>
            {bar("20px")}{bar("70%")}{bar("100%")}{bar("100%")}{bar("100%")}
          </div>
        ))}
      </div>
    </div>
  );
}

const field: React.CSSProperties = {
  width: "100%", background: "var(--panel)", border: "1px solid var(--line)",
  color: "var(--ink)", fontSize: 13, height: 40, padding: "0 11px",
  borderRadius: 8, fontFamily: "inherit",
};
const fieldLabel: React.CSSProperties = {
  display: "block", fontSize: 10, textTransform: "uppercase", letterSpacing: ".5px",
  color: "var(--muted)", marginBottom: 5,
};

/**
 * Kilitli ekran: karartılmış önizleme + ortada "sağlayıcı bağla" kartı.
 * ConsoleShell'in children'ı olarak kullanılır (sayfa shell'i kendisi sarar).
 */
export function ProviderConnect({
  onConnect,
  kind = "transfer",
}: {
  onConnect: (providerId: string, user: string) => void;
  kind?: "transfer" | "scout";
}) {
  const [provider, setProvider] = React.useState(PROVIDERS[0].id);
  const [user, setUser] = React.useState("");
  const [secret, setSecret] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);
  const meta = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0];

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!provider || !user.trim() || !secret.trim()) {
      setErr("Sağlayıcı, ID ve şifre/anahtar zorunludur.");
      return;
    }
    setErr(null);
    onConnect(provider, user.trim());
  };

  const intro = kind === "scout"
    ? "Oyuncu keşfi ve skaut verileri bir 3. parti scout sağlayıcısına bağlanınca açılır."
    : "Transfer pazarı ve piyasa değeri verileri bir 3. parti transfer sağlayıcısına bağlanınca açılır.";

  return (
    <div style={{ position: "relative", minHeight: 520 }}>
      <LockedPreview />
      {/* karartma örtüsü */}
      <div style={{
        position: "absolute", inset: 0,
        background: "linear-gradient(180deg, rgba(10,12,16,0.55), rgba(10,12,16,0.78))",
        backdropFilter: "blur(2px)", borderRadius: 12,
      }} />
      {/* bağlan kartı */}
      <div style={{ position: "absolute", inset: 0, display: "flex", justifyContent: "center", alignItems: "flex-start", padding: "44px 16px" }}>
        <form onSubmit={submit} style={{
          width: "100%", maxWidth: 440, background: "var(--white)",
          border: "1px solid var(--border)", borderRadius: 14,
          boxShadow: "0 18px 50px -16px rgba(0,0,0,0.5)", padding: 22,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <span style={{
              width: 34, height: 34, borderRadius: 9, flexShrink: 0,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              background: "var(--accent-lt)", color: "var(--accent)",
            }}>
              <i className="ti ti-lock" style={{ fontSize: 18 }} />
            </span>
            <div>
              <div style={{ fontSize: 15, fontWeight: 800, color: "var(--ink)" }}>Sağlayıcı bağlantısı gerekli</div>
              <div style={{ fontSize: 11.5, color: "var(--dim)" }}>Keşif & Transfer · 3. parti veri</div>
            </div>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5, margin: "8px 0 16px" }}>{intro}</div>

          <label style={{ display: "block", marginBottom: 12 }}>
            <span style={fieldLabel}>Sağlayıcı</span>
            <select value={provider} onChange={(e) => setProvider(e.target.value)} style={field}>
              {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label} — {p.kind}</option>)}
            </select>
          </label>

          <label style={{ display: "block", marginBottom: 12 }}>
            <span style={fieldLabel}>{meta.idLabel}</span>
            <input value={user} onChange={(e) => setUser(e.target.value)} placeholder={`${meta.label} ${meta.idLabel.toLowerCase()}`} style={field} autoComplete="username" />
          </label>

          <label style={{ display: "block", marginBottom: 6 }}>
            <span style={fieldLabel}>API anahtarı / Şifre</span>
            <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="••••••••" style={field} autoComplete="current-password" />
          </label>

          {err && <div style={{ fontSize: 12, color: "var(--crit)", marginTop: 8 }}>{err}</div>}

          <button type="submit" style={{
            width: "100%", marginTop: 14, height: 42, borderRadius: 9, border: 0,
            background: "var(--besiktas, var(--accent))", color: "#fff", fontWeight: 700,
            fontSize: 13.5, cursor: "pointer", fontFamily: "inherit",
            display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8,
          }}>
            <i className="ti ti-plug-connected" style={{ fontSize: 16 }} />Bağlan ve kilidi aç
          </button>

          <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 12, lineHeight: 1.5, display: "flex", gap: 6 }}>
            <i className="ti ti-shield-lock" style={{ fontSize: 13, flexShrink: 0, marginTop: 1 }} />
            Kimlik bilgileri yalnızca bu cihazda saklanır, sunucuya gönderilmez (demo). Test için herhangi bir ID + şifre yeterli.
          </div>
        </form>
      </div>
    </div>
  );
}

/** Bağlıyken içeriğin üstünde gösterilen ince durum çubuğu (+ bağlantıyı kes). */
export function ProviderConnectedBar({
  providerLabel, user, onDisconnect,
}: {
  providerLabel?: string; user?: string; onDisconnect: () => void;
}) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10, marginBottom: 14,
      padding: "8px 13px", borderRadius: 10,
      border: "1px solid var(--low)", background: "var(--low-bg)",
    }}>
      <i className="ti ti-plug-connected" style={{ fontSize: 16, color: "var(--low)", flexShrink: 0 }} />
      <span style={{ fontSize: 12.5, color: "var(--ink)" }}>
        <b>{providerLabel ?? "Sağlayıcı"}</b> bağlı — veriler bu sağlayıcıdan geliyor{user ? <span style={{ color: "var(--dim)" }}> · {user}</span> : null}
      </span>
      <button type="button" onClick={onDisconnect} style={{
        marginLeft: "auto", fontSize: 11.5, fontWeight: 600, cursor: "pointer",
        background: "transparent", border: "1px solid var(--line)", color: "var(--muted)",
        borderRadius: 7, padding: "4px 10px", fontFamily: "inherit",
      }}>
        Bağlantıyı kes
      </button>
    </div>
  );
}
