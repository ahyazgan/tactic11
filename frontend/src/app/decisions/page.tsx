"use client";

import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface AgentOutput {
  id: number;
  agent_name: string;
  agent_version: string;
  subject_type: string;
  subject_id: number;
  summary: string;
  updated_at: string;
}

export default function DecisionsPage() {
  const { data, error, isLoading } = useSWR<AgentOutput[]>(
    "/admin/agent-outputs?limit=20",
    apiFetch,
  );

  return (
    <main className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-2">Kararlar</h1>
      <p className="text-muted text-sm mb-6">
        Son agent çıktıları — lineup, sub advice, tactical adjustment, injury load.
      </p>

      {error && <p className="text-bad">Hata: {String(error)}</p>}
      {isLoading && <p className="text-muted">Yükleniyor...</p>}

      {data && data.length === 0 && (
        <p className="text-muted">Henüz agent çıktısı yok. Daily brief job tetiklenmiş mi?</p>
      )}

      {data && data.length > 0 && (
        <div className="space-y-2">
          {data.map((o) => (
            <div key={o.id} className="card flex items-start gap-3">
              <div className="text-xs font-mono text-muted whitespace-nowrap">
                {o.updated_at.slice(0, 16).replace("T", " ")}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs uppercase text-accent">{o.agent_name}</span>
                  <span className="text-xs text-muted">
                    {o.subject_type}:{o.subject_id}
                  </span>
                  <span className="text-xs text-muted">v{o.agent_version}</span>
                </div>
                <div className="text-sm">{o.summary}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
