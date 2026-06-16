"use client";

import { useState } from "react";
import { ConsoleShell } from "../_console/shell";
import { Panel, Pill, StatTile } from "@/components/ui";
import { apiFetch } from "@/lib/api";

interface MatchPlanResult {
  value: {
    our_formation: string;
    opp_formation: string;
    headline: string;
    matchup_vector: Record<string, number>;
    matchup_advice: string[];
    set_piece_top: { name: string; label: string; score: number }[];
    threat_top_lane: string | null;
    threat_advice: string | null;
    plan_lines: string[];
    notes: string[];
  };
}

interface OpportunityWindow {
  type: string;
  minute_open: number;
  confidence: number;
  why: string;
  recommended_action: string;
}

interface OpportunityResult {
  value: {
    snapshot_count: number;
    windows: OpportunityWindow[];
    summary: string;
  };
}

interface Decision {
  type: string;
  priority: string;
  rationale: string;
  recommended_action: string;
  risk_if_ignored: string;
  confidence: number;
}

interface DecisionResult {
  value: {
    minute: number;
    score_state: string;
    decisions: Decision[];
    headline: string;
  };
}

const FORMATIONS = [
  "4-3-3", "4-2-3-1", "4-4-2", "4-4-2-diamond",
  "3-5-2", "3-4-3", "5-3-2", "5-4-1",
];

const STYLES = [
  { id: "", label: "—" },
  { id: "atletico_compact", label: "Atletico Compact" },
  { id: "italian_catenaccio", label: "Italian Catenaccio" },
  { id: "possession", label: "Possession" },
  { id: "gegenpress", label: "Gegenpress" },
];

const VECTOR_LABELS: Record<string, string> = {
  our_xt_expected: "Bizim xT beklentisi",
  opp_xt_expected: "Rakip xT beklentisi",
  our_ppda_advantage: "PPDA üstünlüğü",
  midfield_control: "Orta saha kontrol",
  width_clash: "Geniş çatışma",
  set_piece_clash: "Set-piece çatışma",
  transition_speed: "Geçiş hızı",
  space_behind_lines: "Line arkası boşluk",
};

const PRIORITY_VARIANT: Record<string, "warn" | "win" | "neutral"> = {
  urgent: "warn",
  recommended: "win",
  optional: "neutral",
};

export default function TaktikKomutaPage() {
  // Section 1 — Match Plan
  const [ourForm, setOurForm] = useState("4-3-3");
  const [oppForm, setOppForm] = useState("4-2-3-1");
  const [oppStyle, setOppStyle] = useState("");
  const [aerial, setAerial] = useState(0.75);
  const [plan, setPlan] = useState<MatchPlanResult | null>(null);
  const [planLoading, setPlanLoading] = useState(false);

  // Section 2 — Opportunity
  const [snapshotsJson, setSnapshotsJson] = useState(
    JSON.stringify(
      [
        { minute: 60, opp_distance_covered: 0.85, opp_press_intensity: 0.75 },
        { minute: 75, opp_distance_covered: 0.68, opp_press_intensity: 0.55, opp_yellow_count: 3 },
      ],
      null,
      2,
    ),
  );
  const [opp, setOpp] = useState<OpportunityResult | null>(null);
  const [oppLoading, setOppLoading] = useState(false);

  // Section 3 — Decision
  const [minute, setMinute] = useState(80);
  const [ourScore, setOurScore] = useState(0);
  const [oppScore, setOppScore] = useState(1);
  const [fatigue, setFatigue] = useState(0.75);
  const [subsLeft, setSubsLeft] = useState(2);
  const [yellows, setYellows] = useState(2);
  const [decision, setDecision] = useState<DecisionResult | null>(null);
  const [decLoading, setDecLoading] = useState(false);

  async function runPlan() {
    setPlanLoading(true);
    try {
      const res = await apiFetch<MatchPlanResult>("/admin/tactical/match-plan", {
        method: "POST",
        body: JSON.stringify({
          our_formation: ourForm,
          opp_formation: oppForm,
          opponent_style: oppStyle || undefined,
          set_piece_type: "corner",
          set_piece_side: "long",
          our_attributes: { aerial, set_piece: 0.7, technique: 0.7 },
        }),
      });
      setPlan(res);
    } catch (e) {
      console.error(e);
    } finally {
      setPlanLoading(false);
    }
  }

  async function runOpportunity() {
    setOppLoading(true);
    try {
      const snapshots = JSON.parse(snapshotsJson);
      const res = await apiFetch<OpportunityResult>("/admin/tactical/opportunity-window", {
        method: "POST",
        body: JSON.stringify({ snapshots }),
      });
      setOpp(res);
    } catch (e) {
      console.error(e);
    } finally {
      setOppLoading(false);
    }
  }

  async function runDecision() {
    setDecLoading(true);
    try {
      const res = await apiFetch<DecisionResult>("/admin/tactical/in-match-decision", {
        method: "POST",
        body: JSON.stringify({
          minute,
          our_score: ourScore,
          opp_score: oppScore,
          fatigue_avg: fatigue,
          subs_left: subsLeft,
          yellows_in_starting_xi: yellows,
        }),
      });
      setDecision(res);
    } catch (e) {
      console.error(e);
    } finally {
      setDecLoading(false);
    }
  }

  return (
    <ConsoleShell
      active="/taktik-komuta"
      title="Taktik Komuta"
      desc="Maç planı + canlı fırsat penceresi + TD karar danışmanı — H/I/K/L/M/N motorları tek yerde."
    >
      <div className="space-y-6">

      {/* Section 1 — Match Plan */}
      <Panel title="1. Maç Planı (H+I+K kompozit)">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Bizim formasyon</span>
            <select
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={ourForm}
              onChange={(e) => setOurForm(e.target.value)}
            >
              {FORMATIONS.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Rakip formasyon</span>
            <select
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={oppForm}
              onChange={(e) => setOppForm(e.target.value)}
            >
              {FORMATIONS.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Rakip stili</span>
            <select
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={oppStyle}
              onChange={(e) => setOppStyle(e.target.value)}
            >
              {STYLES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </label>
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Bizim hava topu (0-1)</span>
            <input
              type="number" step={0.05} min={0} max={1}
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={aerial}
              onChange={(e) => setAerial(parseFloat(e.target.value) || 0)}
            />
          </label>
        </div>
        <button
          className="px-3 py-1.5 bg-accent text-white text-sm rounded mb-3"
          onClick={runPlan}
          disabled={planLoading}
        >
          {planLoading ? "Hesaplanıyor…" : "Plan üret"}
        </button>

        {plan && (
          <div className="space-y-3">
            <div className="text-sm font-medium">{plan.value.headline}</div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {Object.entries(plan.value.matchup_vector).map(([k, v]) => (
                <StatTile
                  key={k}
                  label={VECTOR_LABELS[k] || k}
                  value={v.toFixed(2)}
                />
              ))}
            </div>

            {plan.value.matchup_advice.length > 0 && (
              <div>
                <div className="text-xs uppercase text-muted mb-1">Formasyon advice</div>
                <ul className="text-sm space-y-1">
                  {plan.value.matchup_advice.map((a, i) => (
                    <li key={i} className="pl-3 border-l-2 border-accent">{a}</li>
                  ))}
                </ul>
              </div>
            )}

            {plan.value.set_piece_top.length > 0 && (
              <div>
                <div className="text-xs uppercase text-muted mb-1">Set-piece routine (top 2)</div>
                <div className="flex flex-wrap gap-2">
                  {plan.value.set_piece_top.map((p) => (
                    <Pill key={p.name} variant="neutral">
                      {p.label} ({p.score})
                    </Pill>
                  ))}
                </div>
              </div>
            )}

            {plan.value.plan_lines.length > 0 && (
              <div>
                <div className="text-xs uppercase text-muted mb-1">Plan brifingi</div>
                <ol className="text-sm space-y-1 list-decimal pl-5">
                  {plan.value.plan_lines.map((l, i) => <li key={i}>{l}</li>)}
                </ol>
              </div>
            )}
          </div>
        )}
      </Panel>

      {/* Section 2 — Opportunity Window */}
      <Panel title="2. Fırsat Penceresi (canlı snapshot serisi)">
        <label className="flex flex-col text-xs mb-3">
          <span className="text-muted mb-1">Snapshot serisi (JSON)</span>
          <textarea
            rows={6}
            className="bg-bg border border-border rounded px-2 py-1 text-xs font-mono"
            value={snapshotsJson}
            onChange={(e) => setSnapshotsJson(e.target.value)}
          />
        </label>
        <button
          className="px-3 py-1.5 bg-accent text-white text-sm rounded mb-3"
          onClick={runOpportunity}
          disabled={oppLoading}
        >
          {oppLoading ? "Tarama…" : "Pencere tara"}
        </button>

        {opp && (
          <div className="space-y-2">
            <div className="text-sm">{opp.value.summary}</div>
            {opp.value.windows.map((w, i) => (
              <div key={i} className="border border-border rounded p-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs uppercase text-accent">{w.type}</span>
                  <span className="text-xs text-muted">dk {w.minute_open.toFixed(0)}</span>
                  <Pill variant={w.confidence >= 0.75 ? "win" : "warn"}>
                    conf {w.confidence.toFixed(2)}
                  </Pill>
                </div>
                <div className="text-xs text-muted mb-1">{w.why}</div>
                <div className="text-sm">{w.recommended_action}</div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* Section 3 — Decision */}
      <Panel title="3. Karar Danışmanı (anlık maç durumu)">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Dakika</span>
            <input type="number" min={0} max={120}
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={minute} onChange={(e) => setMinute(parseInt(e.target.value) || 0)}
            />
          </label>
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Bizim skor</span>
            <input type="number" min={0}
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={ourScore} onChange={(e) => setOurScore(parseInt(e.target.value) || 0)}
            />
          </label>
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Rakip skor</span>
            <input type="number" min={0}
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={oppScore} onChange={(e) => setOppScore(parseInt(e.target.value) || 0)}
            />
          </label>
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Yorgunluk (0-1)</span>
            <input type="number" step={0.05} min={0} max={1}
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={fatigue} onChange={(e) => setFatigue(parseFloat(e.target.value) || 0)}
            />
          </label>
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">Sub hakkı</span>
            <input type="number" min={0} max={5}
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={subsLeft} onChange={(e) => setSubsLeft(parseInt(e.target.value) || 0)}
            />
          </label>
          <label className="flex flex-col text-xs">
            <span className="text-muted mb-1">XI sarı sayısı</span>
            <input type="number" min={0}
              className="bg-bg border border-border rounded px-2 py-1 text-sm"
              value={yellows} onChange={(e) => setYellows(parseInt(e.target.value) || 0)}
            />
          </label>
        </div>
        <button
          className="px-3 py-1.5 bg-accent text-white text-sm rounded mb-3"
          onClick={runDecision}
          disabled={decLoading}
        >
          {decLoading ? "Karar üretiliyor…" : "Karar üret"}
        </button>

        {decision && (
          <div className="space-y-2">
            <div className="text-sm font-medium">{decision.value.headline}</div>
            {decision.value.decisions.map((d, i) => (
              <div key={i} className="border border-border rounded p-2">
                <div className="flex items-center gap-2 mb-1">
                  <Pill variant={PRIORITY_VARIANT[d.priority] || "neutral"}>
                    {d.priority.toUpperCase()}
                  </Pill>
                  <span className="text-xs uppercase text-accent">{d.type}</span>
                  <span className="text-xs text-muted">conf {d.confidence.toFixed(2)}</span>
                </div>
                <div className="text-xs text-muted mb-1">{d.rationale}</div>
                <div className="text-sm mb-1">{d.recommended_action}</div>
                <div className="text-xs text-bad">Risk: {d.risk_if_ignored}</div>
              </div>
            ))}
            {decision.value.decisions.length === 0 && (
              <div className="text-sm text-muted">
                Şu an alarm yok — mevcut planı uygula, gelişimi izle.
              </div>
            )}
          </div>
        )}
      </Panel>
      </div>
    </ConsoleShell>
  );
}
