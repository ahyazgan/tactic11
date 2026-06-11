"use client";

/**
 * Bildirimler — kanal yapılandırma durumu + test gönderimi. ConsoleShell çatısında.
 * Backend:
 *   GET  /admin/notifications/status
 *   POST /admin/notifications/test
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { DemoLiveBanner } from "@/lib/demo-live-banner";
import { ConsoleShell } from "../_console/shell";

interface Channel {
  name: string;
  configured: boolean;
}
interface StatusResp {
  total_channels: number;
  active_channels: string[];
  channels: Channel[];
}

// Demo örnek durumu — env'de kanal yapılandırılmamışken sayfa boş kalmasın.
// Canlı status kanal listeliyorsa daima o gösterilir.
const DEMO_STATUS: StatusResp = {
  total_channels: 4,
  active_channels: ["telegram", "email"],
  channels: [
    { name: "telegram", configured: true },
    { name: "email (SMTP)", configured: true },
    { name: "whatsapp (Twilio)", configured: false },
    { name: "sms", configured: false },
  ],
};

export default function NotificationsConsolePage() {
  const { data: liveData, isLoading, error } = useSWR<StatusResp>(
    "/admin/notifications/status",
    apiFetch,
    { shouldRetryOnError: false },
  );
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<string | null>(null);

  // Demo modunda kanal yapılandırması yoksa örnek durum göster.
  const useDemo = DEMO_MODE && (!liveData || (liveData.channels?.length ?? 0) === 0);
  const data = useDemo ? DEMO_STATUS : liveData;

  async function sendTest() {
    setBusy(true);
    setResult(null);
    if (useDemo) {
      // Örnek-veri modunda gerçek gönderim yapılmaz; dürüstçe simülasyon de.
      setTimeout(() => {
        setResult("Demo simülasyonu: 2 kanala örnek bildirim gönderildi (gerçek gönderim için SMTP/Telegram env ayarları gerekir).");
        setBusy(false);
      }, 500);
      return;
    }
    try {
      const res = await apiFetch<Record<string, unknown>>("/admin/notifications/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: "tactic11 test bildirimi" }),
      });
      const n = Object.keys(res ?? {}).length;
      setResult(`Test gönderildi — ${n} kanal yanıtladı.`);
    } catch (e) {
      setResult(e instanceof Error ? e.message : "Test başarısız");
    } finally {
      setBusy(false);
    }
  }

  const channels = data?.channels ?? [];
  const active = data?.active_channels.length ?? 0;

  const right = (
    <div className="rc">
      <h3>Test Gönderimi</h3>
      <div style={{ fontSize: "12px", color: "var(--muted)", marginBottom: 12, lineHeight: 1.5 }}>
        Yapılandırılmış kanallara örnek bir bildirim gönderir.
      </div>
      <button
        type="button"
        onClick={sendTest}
        disabled={busy}
        style={{ width: "100%", padding: "9px", borderRadius: 7, background: "var(--besiktas)", color: "#fff", fontWeight: 600, fontSize: 12.5, border: 0, cursor: busy ? "default" : "pointer", opacity: busy ? 0.5 : 1, fontFamily: "inherit" }}
      >
        {busy ? "Gönderiliyor…" : "Test bildirimi gönder"}
      </button>
      {result && <div style={{ fontSize: "11.5px", color: "var(--muted)", marginTop: 10 }}>{result}</div>}
    </div>
  );

  return (
    <ConsoleShell
      active="/notifications"
      title="Bildirimler"
      sub="Uyarı kanalları"
      desc="Kritik risk, dönüş (RTP), sözleşme ve anomali uyarıları bu kanallardan gönderilir. Kanal yapılandırması env ile."
      right={right}
    >
      <DemoLiveBanner />
      <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
        <div className="kpi"><div className="kl">Kanal</div><div className="kn">{data?.total_channels ?? 0}</div><div className="kd">tanımlı</div></div>
        <div className="kpi"><div className="kl">Aktif</div><div className="kn" style={{ color: active ? "var(--low)" : "var(--high)" }}>{active}</div><div className="kd">yapılandırıldı</div></div>
        <div className="kpi"><div className="kl">Pasif</div><div className="kn" style={{ color: "var(--dim)" }}>{(data?.total_channels ?? 0) - active}</div><div className="kd">eksik konfig</div></div>
      </div>

      <div className="st"><h2>Kanallar</h2><span className="ep">{useDemo ? "örnek veri (env'de kanal yapılandırılmadı)" : "GET /admin/notifications/status"}</span></div>
      {isLoading && !useDemo && <div className="pgdesc">Yükleniyor…</div>}
      {error && !useDemo && <div className="pgdesc">Durum alınamadı ya da yetki yok.</div>}
      <div className="tbl">
        <table>
          <thead><tr><th>Kanal</th><th className="r">Durum</th></tr></thead>
          <tbody>
            {channels.length === 0 && (
              <tr><td colSpan={2} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                Tanımlı kanal yok.
              </td></tr>
            )}
            {channels.map((c) => {
              const v = c.configured ? "var(--low)" : "var(--dim)";
              return (
                <tr key={c.name}>
                  <td><span className="nm" style={{ fontFamily: "JetBrains Mono" }}>{c.name}</span></td>
                  <td className="r"><span className="risk" style={{ color: v }}><span className="rd" style={{ background: v, boxShadow: c.configured ? `0 0 7px ${v}` : "none" }} />{c.configured ? "Yapılandırıldı" : "Yapılandırılmadı"}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
