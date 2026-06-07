"use client";

/**
 * Bildirim Merkezi — kanal yapılandırma durumu + test gönderimi.
 *
 * Backend:
 *   GET  /admin/notifications/status   — kanallar + configured
 *   POST /admin/notifications/test     — test mesajı ({text?})
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel, EndpointTag } from "@/components/ui";

interface Channel {
  name: string;
  configured: boolean;
}
interface StatusResp {
  total_channels: number;
  active_channels: string[];
  channels: Channel[];
}

export default function NotificationsPage() {
  const { data, isLoading, error } = useSWR<StatusResp>(
    "/admin/notifications/status",
    apiFetch,
    { shouldRetryOnError: false },
  );
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<string | null>(null);

  async function sendTest() {
    setBusy(true);
    setResult(null);
    try {
      const res = await apiFetch<Record<string, unknown>>("/admin/notifications/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: "manager2 test bildirimi" }),
      });
      const n = Object.keys(res ?? {}).length;
      setResult(`Test gönderildi — ${n} kanal yanıtladı.`);
    } catch (e) {
      setResult(e instanceof Error ? e.message : "Test başarısız");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Bildirim Merkezi</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Kritik risk, dönüş (RTP), sözleşme ve anomali uyarıları bu kanallardan
            gönderilir. Kanal yapılandırması env ile.
          </p>
        </div>
        <EndpointTag method="GET" path="/admin/notifications/status" />
      </div>

      <Panel
        title="Kanallar"
        actions={
          data && (
            <span className="font-mono text-[11px] text-textmut">
              {data.active_channels.length}/{data.total_channels} aktif
            </span>
          )
        }
      >
        {isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
        {error && <p className="text-[12px] text-textmut">Durum alınamadı ya da yetki yok.</p>}
        {data && (
          <ul className="space-y-1">
            {data.channels.map((c) => (
              <li
                key={c.name}
                className="flex items-center justify-between border-b border-border/40 py-1.5 text-[13px]"
              >
                <span className="text-text font-mono">{c.name}</span>
                {c.configured ? (
                  <span className="inline-flex items-center gap-1.5 text-[12px] text-ok">
                    <span className="w-2 h-2 rounded-full bg-ok" style={{ boxShadow: "0 0 7px currentColor" }} />
                    Yapılandırıldı
                  </span>
                ) : (
                  <span className="text-[12px] text-textdim">Yapılandırılmadı</span>
                )}
              </li>
            ))}
            {data.channels.length === 0 && (
              <li className="text-[12px] text-textmut">Tanımlı kanal yok.</li>
            )}
          </ul>
        )}
      </Panel>

      <Panel title="Test" actions={<EndpointTag method="POST" path="/admin/notifications/test" />}>
        <button
          type="button"
          onClick={sendTest}
          disabled={busy}
          className="px-3 py-2 rounded bg-accent text-bg font-medium text-[13px] disabled:opacity-50"
        >
          {busy ? "Gönderiliyor…" : "Test bildirimi gönder"}
        </button>
        {result && <p className="text-[12px] text-textmut mt-2">{result}</p>}
      </Panel>
    </div>
  );
}
