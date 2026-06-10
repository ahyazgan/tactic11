"use client";

/**
 * Set-piece Routine — duran top rutini önerileri + zone haritası. ConsoleShell çatısında.
 * SetPieceZoneMap görseli korunur.
 *
 * DEMO_MODE: canlı API'ye dokunmaz; Beşiktaş vs Antalyaspor için zengin köşe/serbest
 * vuruş varyasyonları + far-post analizini demo-data evreninden (demoWeaknesses,
 * demoPlan, demoSquad) türetilmiş içerikle gösterir. Boş-state / "opponent_id gerekli"
 * / spinner yoktur. DEMO kapalı: GET /admin/teams/{id}/set-piece-routine.
 */

import * as React from "react";
import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  DEMO_CLUB,
  DEMO_OPPONENT,
  demoSquad,
  demoWeaknesses,
  demoPlan,
} from "@/lib/demo-data";
import { SetPieceZoneMap } from "@/components/charts/SetPieceZoneMap";
import { ConsoleShell } from "../../../_console/shell";

interface Recommendation {
  target_zone: string;
  technique: string;
  rationale: string;
  opponent_weakness_score: number;
  our_strength_score: number;
  routine_score: number;
}
interface RoutineResponse {
  value?: {
    my_team_external_id: number;
    opponent_team_external_id: number;
    set_piece_type: string;
    top_recommendations: Recommendation[];
    avoid_zone: string;
    matches_analyzed: number;
  };
  note?: string;
}

const SET_PIECE_TYPES = ["all", "corner_kick", "free_kick", "set_piece"];
const SP_LABEL: Record<string, string> = {
  all: "Tümü",
  corner_kick: "Köşe vuruşu",
  free_kick: "Serbest vuruş",
  set_piece: "Genel duran top",
};
const ZONE_TR: Record<string, string> = {
  near_post: "Yakın direk",
  central_6yd: "Kale ağzı (6 yd)",
  far_post: "Uzak direk",
  penalty_arc: "Ceza yayı",
  outside_box: "Ceza dışı",
};

// ─────────────────────────────────────────────────────────────────────────
// DEMO EVRENİ — Beşiktaş vs Antalyaspor duran top rutini
// Çekirdek tema demo-data'dan gelir: demoWeaknesses[1] = "Zonal duran top zaafı"
// (far-post örtülemiyor, son 8 maçta 4 gol), demoPlan.set_piece_hint = far-post.
// Aşağıdaki yapı sayfanın canlı-API şekline (Recommendation/RoutineResponse) sadıktır.
// ─────────────────────────────────────────────────────────────────────────

// Kısa isim yardımcıları (demoSquad'dan gerçek oyuncuları çek — uydurma yok).
const byId = (id: number) => demoSquad.find((p) => p.player_id === id);
const tag = (id: number) => {
  const p = byId(id);
  return p ? `${p.player_name} (${p.shirt})` : `#${id}`;
};

// Far-post = ana fırsat (demoWeaknesses zonal zaafı). avoid_zone = near_post (rakip
// yakın direği zonal yığıyor, beklediği yer orası).
const DEMO_AVOID_ZONE = "near_post";

// Set-piece tipine göre öneri setleri. routine_score = rakip_zaafı × bizim_güç bileşimi.
const DEMO_RECS: Record<string, Recommendation[]> = {
  corner_kick: [
    {
      target_zone: "far_post",
      technique: "Inswinger → far-post koşusu",
      rationale: `Rakip zonal savunmada ikinci direği örtemiyor (son 8 maçta 4 gol yedi). ${tag(10)} arka direğe gecikmeli koşu yapar; içe kıvrılan top kaleciyi geride bırakır.`,
      opponent_weakness_score: 0.82,
      our_strength_score: 0.71,
      routine_score: 0.88,
    },
    {
      target_zone: "central_6yd",
      technique: "Kısa köşe + cut-back (geri pas)",
      rationale: `İlk savunma çizgisini kısa köşeyle dışarı çek, ardından penaltı noktasına geri orta. ${tag(7)} ceza yayında boşa düşen topu vurmaya hazır bekler.`,
      opponent_weakness_score: 0.64,
      our_strength_score: 0.66,
      routine_score: 0.71,
    },
    {
      target_zone: "penalty_arc",
      technique: "Boşaltma → yay üstü çıkan top",
      rationale: `Ön blok far-post'a koşunca ceza yayı boşalıyor. ${tag(8)} geride durup temizlenen ya da kısa düşen topu ilk vuruşla değerlendirir.`,
      opponent_weakness_score: 0.55,
      our_strength_score: 0.62,
      routine_score: 0.6,
    },
  ],
  free_kick: [
    {
      target_zone: "far_post",
      technique: "Derin yan serbest → arka direk kafa",
      rationale: `Yan kanattan kazanılan serbest vuruşlarda far-post tercih: ${tag(9)} ve ${tag(19)} blok koşusuyla zonal hattı bozar, arka direk savunmasızdır.`,
      opponent_weakness_score: 0.78,
      our_strength_score: 0.64,
      routine_score: 0.82,
    },
    {
      target_zone: "outside_box",
      technique: "Direkt vuruş (yay üstü)",
      rationale: `25-28 m mesafede direkt şans. ${tag(8)} ayağıyla baraj üstünden bükme; rakip kaleci bu bölgeden son 6 maçta 2 gol yedi.`,
      opponent_weakness_score: 0.52,
      our_strength_score: 0.7,
      routine_score: 0.66,
    },
    {
      target_zone: "central_6yd",
      technique: "Sürpriz kısa varyant → erken orta",
      rationale: `Savunma diziliş alırken kısa pasla ritmi boz, açıdan erken ortayla kale ağzını doldur. ${tag(10)} hareketiyle stoperleri çeker.`,
      opponent_weakness_score: 0.49,
      our_strength_score: 0.58,
      routine_score: 0.57,
    },
  ],
};

// "all" / "set_piece" = köşe + serbest birleşik, en yüksek skorlular öne.
DEMO_RECS.all = [...DEMO_RECS.corner_kick, ...DEMO_RECS.free_kick]
  .sort((a, b) => b.routine_score - a.routine_score)
  .slice(0, 4);
DEMO_RECS.set_piece = DEMO_RECS.all;

const DEMO_MATCHES_BY_TYPE: Record<string, number> = {
  all: 12,
  corner_kick: 12,
  free_kick: 9,
  set_piece: 12,
};

function demoRoutine(spType: string): NonNullable<RoutineResponse["value"]> {
  const recs = DEMO_RECS[spType] ?? DEMO_RECS.all;
  return {
    my_team_external_id: 0,
    opponent_team_external_id: 0,
    set_piece_type: spType,
    top_recommendations: recs,
    avoid_zone: DEMO_AVOID_ZONE,
    matches_analyzed: DEMO_MATCHES_BY_TYPE[spType] ?? 12,
  };
}

// Far-post ekibi (demoSquad'dan gerçek oyuncular) — sağ kolonda görev dağılımı.
interface RoutineRole {
  role: string;
  player: string;
  task: string;
}
const DEMO_ROLES: RoutineRole[] = [
  { role: "Kullanan", player: tag(8), task: "Inswinger — arka direğe içe kıvıran top" },
  { role: "Far-post hedef", player: tag(10), task: "Gecikmeli arka direk koşusu, kafa bitiriş" },
  { role: "İkinci dalga", player: tag(9), task: "6 yd boşalan alana ikinci top hücumu" },
  { role: "Yay üstü", player: tag(7), task: "Temizlenen topu ilk vuruşla değerlendirir" },
  { role: "Kontra emniyeti", player: tag(6), task: "Ceza yayı önünde geçişe karşı tutar" },
];

// Köşe varyasyon kataloğu (tablo) — saha-içi anlatım.
interface Variation {
  name: string;
  delivery: string;
  target: string;
  trigger: string;
  xg: number;
}
const DEMO_VARIATIONS: Variation[] = [
  { name: "Far-post inswinger", delivery: "Sağ köşe, içe kıvıran", target: "Uzak direk", trigger: "Zonal hat, arka direk açık", xg: 0.19 },
  { name: "Kısa köşe + cut-back", delivery: "Kısa pas → geri orta", target: "Penaltı noktası", trigger: "Rakip kısa köşeye çıkarsa", xg: 0.16 },
  { name: "Near-post flick", delivery: "Yakın direk, sert düz", target: "Yakın direk → sektirme", trigger: "Yalnızca near boşsa (nadir)", xg: 0.11 },
  { name: "Boşaltma + yay üstü", delivery: "Derin top, yay üstü", target: "Ceza yayı", trigger: "Blok far-post'a koşunca", xg: 0.13 },
];

const fmtPct = (v: number) => `${Math.round(v * 100)}%`;

// routine_score → tehlike rengi (KPI / rozetler için tutarlı eşik).
function scoreVar(s: number): string {
  return s >= 0.8 ? "var(--low)" : s >= 0.65 ? "var(--mid)" : "var(--high)";
}

export default function SetPieceRoutineConsolePage() {
  // Demo modunda rol kapısı/parametre kapısı yok — direkt zengin içerik.
  if (DEMO_MODE) return <SetPieceRoutineContent />;
  return <SetPieceRoutineLive />;
}

// ─────────────────────────────────────────────────────────────────────────
// DEMO İÇERİĞİ
// ─────────────────────────────────────────────────────────────────────────
function SetPieceRoutineContent() {
  const params = useParams<{ id: string }>();
  const teamId = params.id;
  const [spType, setSpType] = React.useState<string>("all");
  const [selectedZone, setSelectedZone] = React.useState<string | undefined>("far_post");

  const value = demoRoutine(spType);
  const recs = value.top_recommendations;
  const best = recs[0];

  const scoresByZone: Record<string, number> = {};
  recs.forEach((r) => { scoresByZone[r.target_zone] = Math.min(1, r.routine_score); });

  // Far-post zaafı (demo-data demoWeaknesses[1]) sayfanın çekirdek argümanı.
  const farPostWeakness = demoWeaknesses.find((w) => w.title.includes("duran top"));

  const avgScore = recs.reduce((s, r) => s + r.routine_score, 0) / recs.length;
  const avgWeak = recs.reduce((s, r) => s + r.opponent_weakness_score, 0) / recs.length;

  const right = (
    <>
      <div className="rc">
        <h3>Zone Haritası</h3>
        <SetPieceZoneMap
          scoresByZone={scoresByZone}
          avoidZone={value.avoid_zone}
          selectedZone={selectedZone}
          onSelectZone={setSelectedZone}
        />
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>
          Renk = rutin skoru (yeşil ↑). ✕ ({ZONE_TR[value.avoid_zone]}) rakibin zonal yığınak
          yaptığı bölge — burayı bekler, kaçın.
        </div>
      </div>

      <div className="rc">
        <h3>Görev Dağılımı <span className="tiny">far-post rutini</span></h3>
        {DEMO_ROLES.map((r) => (
          <div className="stat" key={r.role} style={{ alignItems: "flex-start" }}>
            <span style={{ fontSize: 11.5, color: "var(--muted)", flex: 1, paddingRight: 8 }}>
              <span className="pos" style={{ marginRight: 6 }}>{r.role}</span>
              <span style={{ display: "block", marginTop: 4, color: "var(--dim)", fontSize: 11, lineHeight: 1.4 }}>{r.task}</span>
            </span>
            <span className="sv" style={{ fontSize: 11.5, whiteSpace: "nowrap", color: "var(--ink)" }}>{r.player}</span>
          </div>
        ))}
      </div>

      <div className="rc">
        <h3>Plan Notu</h3>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.55 }}>
          {demoPlan.set_piece_hint}
        </div>
        <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 8, fontFamily: "JetBrains Mono" }}>
          maç planı senkron · {demoPlan.status.toLowerCase()}
        </div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/teams"
      title="Duran Top Rutini"
      sub={`${DEMO_CLUB} vs ${DEMO_OPPONENT}`}
      desc={`Takım #${teamId} · ${value.matches_analyzed} maç incelendi · rakip zonal far-post zaafı sömürülüyor.`}
      right={right}
    >
      <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        <div className="kpi">
          <div className="kl">Önerilen Bölge</div>
          <div className="kn" style={{ fontSize: 18, color: scoreVar(best.routine_score) }}>{ZONE_TR[best.target_zone]}</div>
          <div className="kd">en yüksek rutin skoru</div>
        </div>
        <div className="kpi">
          <div className="kl">Rutin Skoru</div>
          <div className="kn" style={{ color: scoreVar(best.routine_score) }}>{best.routine_score.toFixed(2)}</div>
          <div className="kd">0–1 · ort. {avgScore.toFixed(2)}</div>
        </div>
        <div className="kpi">
          <div className="kl">Rakip Zaafı</div>
          <div className="kn" style={{ color: "var(--crit)" }}>{fmtPct(avgWeak)}</div>
          <div className="kd">hedef bölgelerde</div>
        </div>
        <div className="kpi">
          <div className="kl">Kaçınılacak</div>
          <div className="kn" style={{ fontSize: 18 }}>{ZONE_TR[value.avoid_zone]}</div>
          <div className="kd">rakip zonal yığınağı</div>
        </div>
      </div>

      {farPostWeakness && (
        <div className="rc" style={{ borderLeft: "3px solid var(--crit)" }}>
          <h3 style={{ marginBottom: 6 }}>
            <span>Ana Fırsat — {farPostWeakness.title}</span>
            <span className="tiny" style={{ color: "var(--crit)" }}>{farPostWeakness.severity}</span>
          </h3>
          <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.55 }}>{farPostWeakness.detail}</div>
        </div>
      )}

      <div className="st" style={{ marginTop: 16 }}>
        <h2>Set-piece Tipi</h2>
        <div className="seg">
          {SET_PIECE_TYPES.map((t) => (
            <button key={t} className={spType === t ? "on" : ""} onClick={() => setSpType(t)}>{SP_LABEL[t] ?? t}</button>
          ))}
        </div>
      </div>

      <div className="st" style={{ marginTop: 4 }}>
        <h2>Top Öneriler</h2>
        <span className="ep">{recs.length} öneri · {SP_LABEL[spType] ?? spType}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {recs.map((r, i) => {
          const isAvoidAdj = r.target_zone === selectedZone;
          return (
            <div
              className="rc"
              key={`${spType}-${i}`}
              style={{ margin: 0, cursor: "pointer", borderColor: isAvoidAdj ? "var(--accent)" : undefined }}
              onClick={() => setSelectedZone(r.target_zone)}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)" }}>
                  {i === 0 && <span style={{ color: "var(--low)", marginRight: 4 }}>★</span>}
                  {ZONE_TR[r.target_zone] ?? r.target_zone}
                </span>
                <span style={{ fontSize: 10, textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: `1px solid ${scoreVar(r.routine_score)}`, color: scoreVar(r.routine_score) }}>
                  skor {r.routine_score.toFixed(2)}
                </span>
              </div>
              <div style={{ fontSize: 12, color: "var(--ink)", marginBottom: 6 }}>
                Teknik: <span style={{ fontWeight: 600 }}>{r.technique}</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{r.rationale}</div>
              <div style={{ marginTop: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "var(--dim)", marginBottom: 3 }}>
                  <span>RAKİP ZAAFI</span><span style={{ color: "var(--crit)", fontWeight: 600 }}>{fmtPct(r.opponent_weakness_score)}</span>
                </div>
                <div className="mbar"><i style={{ width: `${r.opponent_weakness_score * 100}%`, background: "var(--crit)" }} /></div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "var(--dim)", marginBottom: 3 }}>
                  <span>BİZİM GÜCÜMÜZ</span><span style={{ color: "var(--low)", fontWeight: 600 }}>{fmtPct(r.our_strength_score)}</span>
                </div>
                <div className="mbar"><i style={{ width: `${r.our_strength_score * 100}%`, background: "var(--low)" }} /></div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="st"><h2>Köşe Varyasyon Kataloğu</h2><span className="ep">beklenen gol katkısı</span></div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th>Varyasyon</th><th>Gönderim</th><th>Hedef</th><th>Tetik</th><th className="r">xG</th>
          </tr></thead>
          <tbody>
            {DEMO_VARIATIONS.map((v) => (
              <tr key={v.name}>
                <td><span className="nm">{v.name}</span></td>
                <td style={{ color: "var(--muted)" }}>{v.delivery}</td>
                <td style={{ color: "var(--muted)" }}>{v.target}</td>
                <td style={{ color: "var(--dim)", fontSize: 11.5 }}>{v.trigger}</td>
                <td className="r" style={{ color: v.xg >= 0.17 ? "var(--low)" : v.xg >= 0.13 ? "var(--mid)" : "var(--dim)" }}>{v.xg.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// CANLI MOD (DEMO kapalıyken) — orijinal davranış korunur.
// ─────────────────────────────────────────────────────────────────────────
function SetPieceRoutineLive() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const teamId = params.id;
  const opponentId = search.get("opponent_id");
  const [spType, setSpType] = React.useState<string>("all");
  const [selectedZone, setSelectedZone] = React.useState<string | undefined>();

  const url = opponentId ? `/admin/teams/${teamId}/set-piece-routine?opponent_id=${opponentId}&set_piece_type=${spType}` : null;
  const { data, error, isLoading } = useSWR<RoutineResponse>(url, apiFetch, { shouldRetryOnError: false });

  const scoresByZone: Record<string, number> = {};
  data?.value?.top_recommendations.forEach((r) => { scoresByZone[r.target_zone] = Math.min(1, r.routine_score); });

  if (!opponentId) {
    return (
      <ConsoleShell active="/teams" title={`Set-piece — Takım #${teamId}`} sub="Duran top rutini">
        <div className="pgdesc"><code style={{ fontFamily: "JetBrains Mono" }}>?opponent_id=&lt;N&gt;</code> parametresi gerekli.</div>
      </ConsoleShell>
    );
  }

  const right = (
    <div className="rc">
      <h3>Zone Haritası</h3>
      {data?.value ? (
        <>
          <SetPieceZoneMap scoresByZone={scoresByZone} avoidZone={data.value.avoid_zone} selectedZone={selectedZone} onSelectZone={setSelectedZone} />
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>✕ işareti: rakibin saldırgan pattern&apos;i — burayı bekler, defansif yığınak yapar.</div>
        </>
      ) : <div style={{ fontSize: "12px", color: "var(--dim)" }}>Veri bekleniyor…</div>}
    </div>
  );

  return (
    <ConsoleShell
      active="/teams"
      title={`Set-piece — Takım #${teamId}`}
      sub={`vs Rakip #${opponentId}`}
      desc={data?.value ? `${data.value.matches_analyzed} maç incelendi · tip ${data.value.set_piece_type}` : "Rakibe karşı duran top rutini önerileri."}
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Set-piece Tipi</h2>
        <div className="seg">
          {SET_PIECE_TYPES.map((t) => (
            <button key={t} className={spType === t ? "on" : ""} onClick={() => setSpType(t)}>{t}</button>
          ))}
        </div>
      </div>

      {error && <div className="pgdesc">Yüklenemedi: {String(error)}</div>}
      {isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {data?.note && <div className="pgdesc">{data.note}</div>}

      {data?.value && (
        <>
          <div className="st"><h2>Top Öneriler</h2><span className="ep">{data.value.top_recommendations.length} öneri</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {data.value.top_recommendations.map((r, i) => (
              <div className="rc" key={i} style={{ margin: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)" }}>{ZONE_TR[r.target_zone] ?? r.target_zone}</span>
                  <span style={{ fontSize: 10, textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: "1px solid var(--low)", color: "var(--low)" }}>score {r.routine_score.toFixed(2)}</span>
                </div>
                <div style={{ fontSize: 12, color: "var(--ink)", marginBottom: 6 }}>Teknik: <span style={{ fontFamily: "JetBrains Mono" }}>{r.technique}</span></div>
                <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{r.rationale}</div>
                <div style={{ display: "flex", gap: 12, fontSize: 11, color: "var(--dim)", marginTop: 8, fontFamily: "JetBrains Mono" }}>
                  <span>rakip zayıflığı <span style={{ color: "var(--crit)" }}>{(r.opponent_weakness_score * 100).toFixed(0)}%</span></span>
                  <span>bizim güç <span style={{ color: "var(--low)" }}>{(r.our_strength_score * 100).toFixed(0)}%</span></span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
