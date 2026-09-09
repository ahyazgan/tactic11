"use client";

/**
 * Kimlik eşleme — video takibindeki sentetik takipleri (30000+id) gerçek oyuncuya bağla.
 * GET /tracking/matches/{id}/tracks → liste; PUT /tracking/matches/{id}/identities → kaydet.
 * Kaydedince overlay'de isim/forma görünür (identity_estimated=false).
 */

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface Identity { track_player_external_id: number; player_name: string; player_external_id: number | null; jersey_number: number | null; team_external_id: number | null; is_keeper: boolean }
interface Track {
  player_external_id: number; team_external_id: number | null; frames: number; first_minute: number; last_minute: number;
  actor_frames: number; mean_speed_mps: number | null; mean_x: number; mean_y: number; identity: Identity | null;
}
interface TracksResponse { home_team_external_id: number | null; away_team_external_id: number | null; frames: number; tracks: Track[]; total: number }

interface Draft { name: string; jersey: string; keeper: boolean }

const inputStyle = {
  padding: 4, background: "var(--panel2)", color: "var(--ink)", border: "1px solid var(--line)", borderRadius: 4, fontSize: 11.5,
} as const;

export function TrackIdentityPanel({ matchId, ourTeamId, onSaved }: { matchId: number | null; ourTeamId: number; onSaved: () => void }) {
  const key = matchId != null ? `/tracking/matches/${matchId}/tracks` : null;
  const { data, mutate } = useSWR<TracksResponse>(key, apiFetch, { revalidateOnFocus: false, shouldRetryOnError: false });
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [showAll, setShowAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    const d: Record<number, Draft> = {};
    for (const t of data.tracks) {
      d[t.player_external_id] = {
        name: t.identity?.player_name ?? "",
        jersey: t.identity?.jersey_number != null ? String(t.identity.jersey_number) : "",
        keeper: t.identity?.is_keeper ?? false,
      };
    }
    setDrafts(d);
  }, [data]);

  const tracks = useMemo(() => {
    const all = data?.tracks ?? [];
    const minFrames = Math.max(3, Math.round((data?.frames ?? 0) * 0.2));
    return showAll ? all : all.filter((t) => t.frames >= minFrames || t.identity);
  }, [data, showAll]);

  const dirty = useMemo(() => tracks.filter((t) => {
    const d = drafts[t.player_external_id];
    if (!d) return false;
    const cur = t.identity;
    return d.name.trim() !== (cur?.player_name ?? "") || (d.jersey || "") !== (cur?.jersey_number != null ? String(cur.jersey_number) : "") || d.keeper !== (cur?.is_keeper ?? false);
  }), [tracks, drafts]);

  const save = async () => {
    if (!matchId) return;
    setSaving(true); setMsg(null);
    try {
      const identities = dirty
        .filter((t) => drafts[t.player_external_id].name.trim())
        .map((t) => ({
          track_player_external_id: t.player_external_id,
          player_name: drafts[t.player_external_id].name.trim(),
          jersey_number: drafts[t.player_external_id].jersey ? parseInt(drafts[t.player_external_id].jersey) : null,
          is_keeper: drafts[t.player_external_id].keeper,
          team_external_id: t.team_external_id,
        }));
      const cleared = dirty.filter((t) => !drafts[t.player_external_id].name.trim() && t.identity);
      if (identities.length) {
        await apiFetch(`/tracking/matches/${matchId}/identities`, { method: "PUT", body: JSON.stringify({ identities }) });
      }
      for (const t of cleared) {
        await apiFetch(`/tracking/matches/${matchId}/identities/${t.player_external_id}`, { method: "DELETE" });
      }
      await mutate();
      onSaved();
      setMsg(`${identities.length} eşleme kaydedildi${cleared.length ? `, ${cleared.length} silindi` : ""}.`);
    } catch (e) {
      setMsg(`Hata: ${String(e).slice(0, 160)}`);
    } finally {
      setSaving(false);
    }
  };

  if (!matchId || !data) return null;
  const sideOf = (team: number | null) => (team == null ? "—" : team === ourTeamId ? "Biz" : "Rakip");
  const mapped = (data.tracks ?? []).filter((t) => t.identity).length;

  return (
    <div className="rc" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Kimlik eşleme <span style={{ fontWeight: 400, color: "var(--muted)", fontSize: 11 }}>· takip → oyuncu</span></h3>
        <span style={{ fontSize: 10, color: "var(--muted)" }}>{mapped}/{data.total} takip eşlendi · {data.frames} kare</span>
      </div>
      <div style={{ overflowX: "auto", marginTop: 8 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5, minWidth: 640 }}>
          <thead>
            <tr style={{ color: "var(--muted)", textAlign: "left", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
              <th style={{ padding: "4px 6px" }}>Takip</th><th>Taraf</th><th>Kare</th><th>Aralık</th><th>Ort. hız</th><th>Topla</th><th>Konum</th><th>Oyuncu adı</th><th>Forma</th><th>GK</th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((t) => {
              const d = drafts[t.player_external_id] ?? { name: "", jersey: "", keeper: false };
              const isDirty = dirty.includes(t);
              return (
                <tr key={t.player_external_id} style={{ borderTop: "1px solid var(--line)", background: isDirty ? "color-mix(in srgb, var(--accent) 6%, transparent)" : undefined }}>
                  <td style={{ padding: "4px 6px", fontFamily: "JetBrains Mono, monospace" }}>~{String(t.player_external_id).slice(-3)}</td>
                  <td style={{ color: t.team_external_id === ourTeamId ? "var(--accent)" : "var(--high)", fontWeight: 700 }}>{sideOf(t.team_external_id)}</td>
                  <td>{t.frames}</td>
                  <td style={{ color: "var(--muted)" }}>{t.first_minute.toFixed(1)}–{t.last_minute.toFixed(1)}&apos;</td>
                  <td>{t.mean_speed_mps != null ? `${Math.round(t.mean_speed_mps * 3.6)} km/h` : "—"}</td>
                  <td>{t.actor_frames}</td>
                  <td style={{ color: "var(--muted)" }}>{t.mean_x < 33 ? "geri" : t.mean_x < 66 ? "orta" : "ileri"} · {t.mean_y < 33 ? "üst" : t.mean_y < 66 ? "merkez" : "alt"}</td>
                  <td><input value={d.name} placeholder="ad" onChange={(e) => setDrafts((s) => ({ ...s, [t.player_external_id]: { ...d, name: e.target.value } }))} style={{ ...inputStyle, width: 130 }} /></td>
                  <td><input value={d.jersey} placeholder="#" inputMode="numeric" onChange={(e) => setDrafts((s) => ({ ...s, [t.player_external_id]: { ...d, jersey: e.target.value.replace(/\D/g, "").slice(0, 2) } }))} style={{ ...inputStyle, width: 38 }} /></td>
                  <td><input type="checkbox" checked={d.keeper} onChange={(e) => setDrafts((s) => ({ ...s, [t.player_external_id]: { ...d, keeper: e.target.checked } }))} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={save} disabled={saving || dirty.length === 0}
          style={{ padding: "7px 12px", background: dirty.length ? "var(--accent)" : "var(--panel2)", color: dirty.length ? "#fff" : "var(--muted)", border: "1px solid var(--line)", borderRadius: 4, cursor: "pointer", fontSize: 12, fontWeight: 700 }}>
          {saving ? "Kaydediliyor…" : `Kaydet (${dirty.length})`}
        </button>
        <button type="button" onClick={() => setShowAll((v) => !v)} style={{ background: "none", border: "none", color: "var(--muted)", fontSize: 11, cursor: "pointer" }}>
          {showAll ? "kısa takipleri gizle" : `tüm takipleri göster (${data.total})`}
        </button>
        {msg && <span style={{ fontSize: 11, color: msg.startsWith("Hata") ? "var(--crit)" : "var(--low)" }}>{msg}</span>}
        <span style={{ fontSize: 10, color: "var(--dim)", marginLeft: "auto" }}>Adı boşaltıp kaydetmek eşlemeyi siler. Kısa takipler aynı oyuncunun parçası olabilir.</span>
      </div>
    </div>
  );
}
