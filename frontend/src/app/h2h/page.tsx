"use client";

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import {
  ExplainButton,
  ExplainPanel,
  Panel,
  StatTile,
} from "@/components/ui";

interface League {
  external_id: number;
  name: string;
}

interface Team {
  external_id: number;
  name: string;
}

interface H2HResult {
  value?: {
    team_a_external_id: number;
    team_b_external_id: number;
    matches_played: number;
    team_a_wins: number;
    draws: number;
    team_b_wins: number;
    team_a_goals: number;
    team_b_goals: number;
  };
  commentary?: string;
  audit?: Record<string, unknown> | null;
}

export default function H2HPage() {
  const [leagueA, setLeagueA] = React.useState<string>("");
  const [leagueB, setLeagueB] = React.useState<string>("");
  const [teamA, setTeamA] = React.useState<string>("");
  const [teamB, setTeamB] = React.useState<string>("");
  const [shouldFetch, setShouldFetch] = React.useState(false);
  const [explainOpen, setExplainOpen] = React.useState(false);

  const { data: leagues } = useSWR<League[]>("/leagues", apiFetch);
  const { data: teamsA } = useSWR<Team[]>(
    leagueA ? `/teams/${leagueA}` : null,
    apiFetch,
  );
  const { data: teamsB } = useSWR<Team[]>(
    leagueB ? `/teams/${leagueB}` : null,
    apiFetch,
  );

  const { data: h2h, error, isLoading } = useSWR<H2HResult>(
    shouldFetch && teamA && teamB ? `/teams/${teamA}/vs/${teamB}` : null,
    apiFetch,
  );

  const teamAName = teamsA?.find((t) => String(t.external_id) === teamA)?.name;
  const teamBName = teamsB?.find((t) => String(t.external_id) === teamB)?.name;

  return (
    <div className="max-w-6xl">
      <h1 className="text-lg font-semibold text-text mb-3">
        Head-to-Head Karşılaştırma
      </h1>

      <Panel title="Takım seç" className="mb-4">
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <h3 className="text-[11px] uppercase tracking-wider text-textmut mb-2">
              Takım A
            </h3>
            <div className="grid grid-cols-2 gap-2">
              <Select
                value={leagueA}
                onChange={(v) => {
                  setLeagueA(v);
                  setTeamA("");
                }}
                options={leagues?.map((l) => ({
                  value: String(l.external_id),
                  label: l.name,
                })) ?? []}
                placeholder="Lig"
              />
              <Select
                value={teamA}
                onChange={setTeamA}
                options={teamsA?.map((t) => ({
                  value: String(t.external_id),
                  label: t.name,
                })) ?? []}
                placeholder="Takım"
                disabled={!leagueA}
              />
            </div>
          </div>
          <div>
            <h3 className="text-[11px] uppercase tracking-wider text-textmut mb-2">
              Takım B
            </h3>
            <div className="grid grid-cols-2 gap-2">
              <Select
                value={leagueB}
                onChange={(v) => {
                  setLeagueB(v);
                  setTeamB("");
                }}
                options={leagues?.map((l) => ({
                  value: String(l.external_id),
                  label: l.name,
                })) ?? []}
                placeholder="Lig"
              />
              <Select
                value={teamB}
                onChange={setTeamB}
                options={teamsB?.map((t) => ({
                  value: String(t.external_id),
                  label: t.name,
                })) ?? []}
                placeholder="Takım"
                disabled={!leagueB}
              />
            </div>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShouldFetch(true)}
            disabled={!teamA || !teamB || teamA === teamB}
            className="text-[11px] uppercase tracking-wide px-3 py-1 rounded border border-borderlt text-accent hover:bg-surface2 disabled:opacity-50"
          >
            Karşılaştır
          </button>
          {shouldFetch && h2h && (
            <ExplainButton onClick={() => setExplainOpen(true)} />
          )}
        </div>
      </Panel>

      {isLoading && shouldFetch && (
        <p className="text-textmut text-[13px]">Yükleniyor...</p>
      )}
      {error && (
        <p className="text-danger text-[13px]">
          Yüklenemedi: {String(error)}
        </p>
      )}
      {h2h?.value && (
        <Panel title={`${teamAName ?? "Takım A"} vs ${teamBName ?? "Takım B"}`}>
          <div className="grid grid-cols-3 gap-3 mb-3">
            <StatTile
              label={teamAName ?? "A"}
              value={h2h.value.team_a_wins}
              delta={`${h2h.value.team_a_goals} gol`}
            />
            <StatTile
              label="Beraberlik"
              value={h2h.value.draws}
            />
            <StatTile
              label={teamBName ?? "B"}
              value={h2h.value.team_b_wins}
              delta={`${h2h.value.team_b_goals} gol`}
            />
          </div>
          <div className="text-[12px] text-textmut">
            Toplam {h2h.value.matches_played} maç oynandı.
          </div>
        </Panel>
      )}

      <ExplainPanel
        open={explainOpen}
        onClose={() => setExplainOpen(false)}
        fetchExplain={() =>
          apiFetch<H2HResult>(`/teams/${teamA}/vs/${teamB}?explain=true`)
        }
        title="H2H Açıklama"
      />
    </div>
  );
}

function Select({
  value, onChange, options, placeholder, disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder: string;
  disabled?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className="bg-surface2 border border-border text-text text-[12px] px-2 py-1 rounded h-7 disabled:opacity-50"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}
