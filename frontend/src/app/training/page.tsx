"use client";

import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel } from "@/components/ui";

interface League {
  external_id: number;
  name: string;
}

interface Team {
  external_id: number;
  name: string;
}

export default function TrainingIndexPage() {
  const [leagueA, setLeagueA] = React.useState<string>("");
  const [leagueB, setLeagueB] = React.useState<string>("");
  const [teamA, setTeamA] = React.useState<string>("");
  const [teamB, setTeamB] = React.useState<string>("");

  const { data: leagues } = useSWR<League[]>("/leagues", apiFetch);
  const { data: teamsA } = useSWR<Team[]>(
    leagueA ? `/teams/${leagueA}` : null,
    apiFetch,
  );
  const { data: teamsB } = useSWR<Team[]>(
    leagueB ? `/teams/${leagueB}` : null,
    apiFetch,
  );

  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-lg font-semibold text-text">Antrenman Planı</h1>

      <Panel title="Takım + Rakip seç">
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <h3 className="text-[11px] uppercase tracking-wider text-textmut mb-2">
              Bizim takım
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
              Rakip
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
        <div className="mt-3">
          {teamA && teamB && teamA !== teamB ? (
            <Link
              href={`/teams/${teamA}/training-plan?opponent_id=${teamB}`}
              className="inline-block text-[11px] uppercase tracking-wide px-3 py-1 rounded border border-borderlt text-accent hover:bg-surface2"
            >
              Plan oluştur →
            </Link>
          ) : (
            <button
              type="button"
              disabled
              className="inline-block text-[11px] uppercase tracking-wide px-3 py-1 rounded border border-borderlt text-textdim opacity-50 cursor-not-allowed"
            >
              Plan oluştur →
            </button>
          )}
        </div>
      </Panel>
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
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
