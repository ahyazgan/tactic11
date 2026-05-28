"use client";

import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel, Pill, StatTile } from "@/components/ui";
import { MiniPitch } from "@/components/charts/MiniPitch";

interface SuboptimalPass {
  minute: number;
  start: [number, number];
  actual_end: [number, number];
  best_alternative: {
    x: number;
    y: number;
    delta: number;
  };
  completed: boolean;
}

interface FeedbackResponse {
  match_external_id?: number;
  player_external_id?: number;
  minutes_played?: number;
  events_loaded?: number;
  metrics?: {
    xt_per_90: number | null;
    xa_per_90: number | null;
    vaep_per_90: number | null;
    progressive_per_90: number | null;
    press_resistance_under_press: number;
    overperformance_total: number;
    overperformance_label: string;
  };
  pass_alternatives_summary?: {
    passes_analyzed: number;
    mean_best_delta: number;
    suboptimal_share: number;
    top_suboptimal: SuboptimalPass[];
  };
  ai_brief?: string;
  note?: string;
}

function metricColor(label?: string): "win" | "loss" | "neutral" {
  if (label === "clinical") return "win";
  if (label === "underperforming") return "loss";
  return "neutral";
}

export default function PlayerFeedbackPage() {
  const params = useParams<{ id: string; pid: string }>();
  const matchId = params.id;
  const playerId = params.pid;

  const { data, error, isLoading } = useSWR<FeedbackResponse>(
    `/admin/matches/${matchId}/players/${playerId}/feedback`,
    apiFetch,
  );

  if (error) {
    return (
      <div className="max-w-5xl">
        <p className="text-danger text-[13px]">Yüklenemedi: {String(error)}</p>
      </div>
    );
  }
  if (isLoading || !data) {
    return (
      <div className="max-w-5xl">
        <p className="text-textmut text-[13px]">Yükleniyor...</p>
      </div>
    );
  }
  if (data.events_loaded === 0) {
    return (
      <div className="max-w-5xl">
        <h1 className="text-lg font-semibold text-text mb-3">
          Oyuncu #{playerId} — Maç #{matchId} Feedback
        </h1>
        <Panel>
          <p className="text-textmut text-[13px]">
            {data.note ?? "Bu maç için event ingest yok."}
          </p>
        </Panel>
      </div>
    );
  }

  const m = data.metrics;
  const sub = data.pass_alternatives_summary;

  return (
    <div className="max-w-5xl space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-text">
          Oyuncu #{playerId} — Maç #{matchId} Feedback
        </h1>
        <p className="text-[12px] text-textmut">
          {data.minutes_played ?? 0} dk · {data.events_loaded} event
        </p>
      </div>

      {m && (
        <section>
          <h2 className="text-sm font-semibold text-text mb-2">Metrikler</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatTile label="xT/90" value={(m.xt_per_90 ?? 0).toFixed(2)} />
            <StatTile label="xA/90" value={(m.xa_per_90 ?? 0).toFixed(2)} />
            <StatTile label="VAEP/90" value={(m.vaep_per_90 ?? 0).toFixed(2)} />
            <StatTile
              label="Prog/90"
              value={(m.progressive_per_90 ?? 0).toFixed(2)}
            />
            <StatTile
              label="Pres altı"
              value={`%${Math.round(m.press_resistance_under_press * 100)}`}
            />
            <div className="bg-surface border border-border rounded-md p-3">
              <span className="text-[10px] uppercase tracking-wider text-textdim">
                Overperformance
              </span>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-xl font-semibold tabular-nums text-text">
                  {m.overperformance_total > 0 ? "+" : ""}
                  {m.overperformance_total.toFixed(2)}
                </span>
                <Pill variant={metricColor(m.overperformance_label)}>
                  {m.overperformance_label}
                </Pill>
              </div>
            </div>
          </div>
        </section>
      )}

      {sub && sub.top_suboptimal.length > 0 && (
        <section>
          <div className="flex items-baseline justify-between mb-2">
            <h2 className="text-sm font-semibold text-text">
              Alt-optimal Pas Örnekleri
            </h2>
            <span className="text-[11px] text-textmut">
              {sub.passes_analyzed} pas · alt-optimal %
              {Math.round(sub.suboptimal_share * 100)}
            </span>
          </div>
          <div className="grid md:grid-cols-3 gap-3">
            {sub.top_suboptimal.map((p, i) => (
              <Panel key={i}>
                <div className="text-[11px] text-textmut mb-2">
                  {p.minute.toFixed(0)}. dakika
                  {p.completed ? null : (
                    <span className="ml-2 text-loss">(başarısız)</span>
                  )}
                </div>
                <MiniPitch
                  start={p.start}
                  actualEnd={p.actual_end}
                  suggestedEnd={[p.best_alternative.x, p.best_alternative.y]}
                  label={`xT Δ +${p.best_alternative.delta.toFixed(2)}`}
                />
                <div className="text-[11px] text-textmut mt-2 space-y-0.5">
                  <div>
                    Actual:{" "}
                    <span className="font-mono text-loss">
                      ({p.actual_end[0].toFixed(0)},
                      {p.actual_end[1].toFixed(0)})
                    </span>
                  </div>
                  <div>
                    Önerilen:{" "}
                    <span className="font-mono text-win">
                      ({p.best_alternative.x.toFixed(0)},
                      {p.best_alternative.y.toFixed(0)})
                    </span>
                  </div>
                </div>
              </Panel>
            ))}
          </div>
        </section>
      )}

      {data.ai_brief && (
        <section>
          <h2 className="text-sm font-semibold text-text mb-2">
            Maç-sonu Brief
          </h2>
          <Panel>
            <p className="text-[13px] text-text whitespace-pre-wrap leading-[18px]">
              {data.ai_brief}
            </p>
          </Panel>
        </section>
      )}
    </div>
  );
}
