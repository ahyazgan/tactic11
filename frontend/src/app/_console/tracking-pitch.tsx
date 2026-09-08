"use client";

/**
 * Saha overlay — bir tracking frame'ini (StatsBomb 360 / ileride video)
 * gerçek sahada gösterir: oyuncular, top, aktör, pas seçenekleri (açık/kapalı
 * hat), kamera görüş alanı; altta baskı / alan kontrolü / topa sahip olma /
 * görünen iz sayısı / faz.
 *
 * Tüm sayılar `lib/tracking-geometry` kestirimidir; başlıkta "~" ile işaretli.
 */

import * as React from "react";
import {
  actorOf,
  closestPressureM,
  passOptions,
  phaseLabel,
  possessionShare,
  screenedLaneCount,
  sourceTR,
  spaceControl,
  visibleTracks,
  type PassOption,
  type TrackingFrame,
} from "@/lib/tracking-geometry";
import { PH, PW, PitchLines, ppx, ppy } from "./pitch-analysis";

const US = "var(--accent)";
const THEM = "var(--high)";
const OPEN = "#d9b44a";
const SCREENED = "#d45f5f";

function shortId(p: { player_external_id: number; identity_estimated: boolean; name?: string | null }): string {
  if (p.name) return p.name;
  return (p.identity_estimated ? "~" : "#") + String(p.player_external_id).slice(-3);
}

function fmtM(v: number | null | undefined): string {
  return v == null ? "—" : `~${v.toFixed(1)} m`;
}

function fmtPct(p: number): string {
  if (p >= 0.95) return ">95%";
  return `~${Math.round(p * 100)}%`;
}

function Stat({ label, value, sub, accent }: { label: string; value: React.ReactNode; sub?: string; accent?: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: accent ?? "var(--ink)", fontFamily: "JetBrains Mono, monospace", lineHeight: 1.2, marginTop: 2 }}>{value}</div>
      {sub && <div style={{ fontSize: 9.5, color: "var(--dim)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function PassOptionRow({ opt, rank }: { opt: PassOption; rank: number }) {
  const color = opt.screened ? SCREENED : OPEN;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "18px 1fr auto", gap: 8, alignItems: "center", padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
      <span style={{ fontSize: 10, color: "var(--dim)", fontFamily: "JetBrains Mono, monospace" }}>{String(rank).padStart(2, "0")}</span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink)" }}>{shortId(opt.player)}</div>
        <div style={{ fontSize: 10, color: "var(--muted)" }}>
          ~{Math.round(opt.distM)} m · {opt.screened ? "hat kapalı" : "hat açık"}
          {opt.nearestDefM != null && ` · en yakın rakip ${opt.nearestDefM.toFixed(1)} m`}
        </div>
      </div>
      <span style={{ fontSize: 14, fontWeight: 700, color, fontFamily: "JetBrains Mono, monospace" }}>{fmtPct(opt.prob)}</span>
    </div>
  );
}

export interface TrackingOverlayCardProps {
  frame: TrackingFrame | null;
  /** Topa sahip olma payı için pencere (son ~3 dk kareleri). */
  recent?: TrackingFrame[];
  ourTeamId: number;
  minute: number;
}

export function TrackingOverlayCard({ frame, recent = [], ourTeamId, minute }: TrackingOverlayCardProps) {
  if (!frame) {
    return (
      <div className="rc" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <h3 style={{ margin: 0 }}>Saha Overlay</h3>
          <span style={{ fontSize: 10, color: "var(--muted)" }}>StatsBomb 360 · freeze-frame</span>
        </div>
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>
          Bu maç/dakika için pozisyon karesi yok. 360 verisi olan maçlar için
          <code style={{ margin: "0 4px" }}>scripts.ingest_statsbomb_360</code> ile yüklenir.
        </div>
      </div>
    );
  }

  const actor = actorOf(frame);
  const options = passOptions(frame, 3);
  const pressure = closestPressureM(frame);
  const space = spaceControl(frame, ourTeamId);
  const poss = possessionShare(recent.length ? recent : [frame], ourTeamId);
  const tracks = visibleTracks(frame);
  const phase = phaseLabel(frame, ourTeamId);
  const actorIsOurs = actor?.team_external_id === ourTeamId;
  const lag = Math.max(0, minute - frame.minute);

  return (
    <div className="rc" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Saha Overlay <span style={{ fontWeight: 400, color: "var(--muted)", fontSize: 11 }}>· {phase}</span></h3>
        <span style={{ fontSize: 10, color: "var(--muted)" }}>
          {sourceTR(frame.source)} · kare {frame.minute.toFixed(1)}&apos;
          {lag > 0.5 && ` (${lag.toFixed(1)} dk önce)`} · ~ tahmini kimlik
        </span>
      </div>

      <div className="tracking-overlay-grid" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 230px", gap: 14, marginTop: 10 }}>
        <svg viewBox={`0 0 ${PW} ${PH}`} width="100%" style={{ display: "block", borderRadius: 10, background: "color-mix(in srgb, var(--low) 9%, var(--panel))" }}>
          <PitchLines />
          {frame.visible_area && frame.visible_area.length >= 3 && (
            <polygon
              points={frame.visible_area.map(([x, y]) => `${ppx(x)},${ppy(y)}`).join(" ")}
              fill="color-mix(in srgb, var(--accent) 7%, transparent)"
              stroke="var(--line2)" strokeDasharray="3 3" strokeWidth={0.8}
            />
          )}
          <text x={PW - 8} y={PH - 10} fontSize={8.5} fill="var(--dim)" textAnchor="end">aktör takımı hücum yönü →</text>

          {actor && options.map((o, i) => {
            const color = o.screened ? SCREENED : OPEN;
            // Etiket hattın alıcıya yakın %62'sinde; sıraya göre hafif kaydırılır ki
            // kümelenmiş alıcılarda üst üste binmesin.
            const t = 0.62;
            const mx = ppx(actor.x) + (ppx(o.player.x) - ppx(actor.x)) * t;
            const my = ppy(actor.y) + (ppy(o.player.y) - ppy(actor.y)) * t + (i - 1) * 9;
            return (
              <g key={o.player.player_external_id}>
                <line x1={ppx(actor.x)} y1={ppy(actor.y)} x2={ppx(o.player.x)} y2={ppy(o.player.y)}
                  stroke={color} strokeWidth={1.6} strokeDasharray={o.screened ? "4 3" : undefined} opacity={0.9} />
                <rect x={mx - 26} y={my - 8} width={52} height={14} rx={3} fill="var(--panel)" stroke={color} strokeWidth={0.8} />
                <text x={mx} y={my + 2.5} fontSize={8} fill={color} textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontWeight={700}>
                  {fmtPct(o.prob)} · {Math.round(o.distM)}m
                </text>
              </g>
            );
          })}

          {frame.players.map((p) => {
            const ours = p.team_external_id === ourTeamId;
            const color = ours ? US : THEM;
            const r = p.is_actor ? 7 : 5.5;
            return (
              <g key={`${p.player_external_id}-${p.x}-${p.y}`}>
                {p.is_actor && <circle cx={ppx(p.x)} cy={ppy(p.y)} r={r + 4} fill="none" stroke={color} strokeWidth={1.2} opacity={0.6} />}
                {p.is_keeper
                  ? <rect x={ppx(p.x) - r} y={ppy(p.y) - r} width={2 * r} height={2 * r} rx={2} fill="var(--panel)" stroke={color} strokeWidth={2} />
                  : <circle cx={ppx(p.x)} cy={ppy(p.y)} r={r} fill={p.is_actor ? color : "var(--panel)"} stroke={color} strokeWidth={p.identity_estimated ? 1.6 : 2.2} strokeDasharray={p.identity_estimated ? "2 1.5" : undefined} />}
                <text x={ppx(p.x)} y={ppy(p.y) - r - 3} fontSize={7.5} fill={p.is_actor ? color : "var(--dim)"} textAnchor="middle" fontWeight={p.is_actor ? 700 : 400}>
                  {p.is_keeper ? "GK" : shortId(p)}
                </text>
              </g>
            );
          })}

          {frame.ball && (
            <circle cx={ppx(frame.ball.x)} cy={ppy(frame.ball.y)} r={3} fill="#fff" stroke="#222" strokeWidth={1} />
          )}
        </svg>

        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", fontWeight: 700 }}>Pas seçenekleri</div>
          <div style={{ fontSize: 12.5, fontWeight: 700, color: "var(--ink)", marginTop: 2 }}>
            {actor ? `${actorIsOurs ? "Bizim" : "Rakip"} aktör ${shortId(actor)}` : "Aktör yok"}
          </div>
          <div style={{ fontSize: 10, color: "var(--dim)", marginBottom: 4 }}>Kısa pas tamamlanma modeli</div>
          {options.length === 0 && <div style={{ fontSize: 11, color: "var(--muted)" }}>Görünür takım arkadaşı yok.</div>}
          {options.map((o, i) => <PassOptionRow key={o.player.player_external_id} opt={o} rank={i + 1} />)}
          <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>
            {screenedLaneCount(options)} kapalı hat · en yakın rakip {fmtM(pressure)}
            <br />
            <span style={{ color: "var(--dim)" }}>*Geometrik hat kontrolü, garanti değil</span>
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 10, fontSize: 10, color: "var(--muted)" }}>
            <span><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 4, background: US, marginRight: 4 }} />Biz</span>
            <span><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 4, background: THEM, marginRight: 4 }} />Rakip</span>
            <span><span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 4, background: "#fff", border: "1px solid #222", marginRight: 4 }} />Top</span>
          </div>
        </div>
      </div>

      <div className="tracking-overlay-stats" style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 12, marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--line)" }}>
        <Stat
          label="Kontrollü topa sahip olma"
          value={poss ? <><span style={{ color: US }}>{poss.ours}%</span><span style={{ color: "var(--dim)", fontSize: 12 }}> / </span><span style={{ color: THEM }}>{poss.theirs}%</span></> : "—"}
          sub={poss ? `${poss.frames} event karesi · ölü top hariç` : "pencere boş"}
        />
        <Stat
          label="Yerel alan kontrolü"
          value={space ? `${space.pct}%` : "—"}
          sub="en yakın oyuncu bölgesi · yalnız görünür sarmal"
          accent={US}
        />
        <Stat
          label="En yakın baskı"
          value={fmtM(pressure)}
          sub="aktör–rakip mesafesi · kestirim"
          accent={pressure != null && pressure < 3 ? "var(--crit)" : undefined}
        />
        <Stat
          label="Görünen izler"
          value={tracks}
          sub="kamera görüş alanındaki oyuncu"
        />
        <Stat
          label="Oyun fazı"
          value={<span style={{ fontSize: 14 }}>{phase}</span>}
          sub={frame.event_uuid ? `event ${frame.event_uuid.slice(0, 8)}` : "event anı"}
        />
      </div>
      <style>{`
        @media (max-width: 760px) {
          .tracking-overlay-grid { grid-template-columns: 1fr !important; }
          .tracking-overlay-stats { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
        }
      `}</style>
    </div>
  );
}
