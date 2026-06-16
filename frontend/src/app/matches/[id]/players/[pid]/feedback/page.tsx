"use client";

/**
 * Oyuncu Maç Feedback — metrikler + alt-optimal pas örnekleri + AI brief.
 * ConsoleShell çatısında. MiniPitch görseli korunur.
 * Backend: GET /admin/matches/{id}/players/{pid}/feedback.
 *
 * DEMO_MODE: canlı API'ye dokunmaz; URL'deki [pid] → demoSquad oyuncusu çözülür
 * (bulunamazsa ilk oyuncu). Oyuncunun kondisyon/risk/mevkisinden deterministik,
 * inandırıcı maç-sonu metrikleri, alt-optimal pas örnekleri, maç içi olayları
 * ve Türkçe AI brief üretilir. Boş-state / spinner gösterilmez.
 */

import { useParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  demoSquad,
  demoLive,
  demoDecisions,
  demoNextMatch,
  DEMO_CLUB,
  DEMO_OPPONENT,
  type SquadPlayer,
} from "@/lib/demo-data";
import { MiniPitch } from "@/components/charts/MiniPitch";
import { ConsoleShell } from "../../../../../_console/shell";
import { LoadingState, EmptyState } from "@/components/ui";

interface SuboptimalPass {
  minute: number;
  start: [number, number];
  actual_end: [number, number];
  best_alternative: { x: number; y: number; delta: number };
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

function opVar(label?: string): string {
  if (label === "clinical") return "var(--low)";
  if (label === "underperforming") return "var(--crit)";
  return "var(--muted)";
}

// --------------------------------------------------------------------------- //
// DEMO — oyuncu maç-sonu feedback'i (deterministik, backend'siz)
// --------------------------------------------------------------------------- //

// Mevkiye göre temel etki katsayıları (xT/xA/prog ağırlıkları farklılaşsın).
const POS_BASE: Record<SquadPlayer["position"], { xt: number; xa: number; vaep: number; prog: number; press: number }> = {
  GK: { xt: 0.04, xa: 0.02, vaep: 0.05, prog: 1.2, press: 0.78 },
  DF: { xt: 0.11, xa: 0.06, vaep: 0.14, prog: 4.1, press: 0.74 },
  MF: { xt: 0.27, xa: 0.21, vaep: 0.33, prog: 6.8, press: 0.69 },
  FW: { xt: 0.34, xa: 0.18, vaep: 0.41, prog: 5.2, press: 0.61 },
};

interface DemoFeedback {
  player: SquadPlayer;
  minutes: number;
  eventsLoaded: number;
  rating: number; // 0-10 maç notu
  metrics: NonNullable<FeedbackResponse["metrics"]>;
  passes: { analyzed: number; meanDelta: number; suboptimalShare: number; top: SuboptimalPass[] };
  involvement: { minute: number; kind: string; text: string; tone: "iyi" | "kotu" | "notr" }[];
  brief: string;
  decisionRefs: typeof demoDecisions;
}

/** Oyuncunun kondisyon/risk/mevki profilinden tekrar-üretilebilir maç metrikleri. */
function buildDemoFeedback(player: SquadPlayer): DemoFeedback {
  const base = POS_BASE[player.position];
  // Kondisyon 0..100 → form çarpanı 0.78..1.18; risk yüksekse press direnci düşer.
  const form = 0.78 + (player.condition / 100) * 0.4;
  const fatiguePenalty = (player.risk_score / 100) * 0.22;

  // Kondisyon kötü olan oyuncu erken alınmış olabilir (kritik → ~62 dk).
  const minutes =
    player.risk_label === "Kritik" ? 62 :
    player.risk_label === "Yüksek" ? 78 :
    player.position === "GK" ? 90 : 90;

  const xt = +(base.xt * form).toFixed(2);
  const xa = +(base.xa * form).toFixed(2);
  const vaep = +(base.vaep * form).toFixed(2);
  const prog = +(base.prog * form).toFixed(1);
  const press = +Math.max(0.32, base.press - fatiguePenalty).toFixed(2);

  // Beklenen-üstü performans: form>1 ise pozitif, riskli & düşük formda negatif.
  const overRaw = (form - 1) * 0.9 - fatiguePenalty * 0.6;
  const over = +overRaw.toFixed(2);
  const overLabel = over > 0.06 ? "clinical" : over < -0.06 ? "underperforming" : "neutral";

  // Maç notu 0-10: forma + beklenen-üstü + mevki katkısı.
  const rating = +Math.min(9.4, Math.max(4.6, 6.2 + (form - 1) * 6 + over * 4)).toFixed(1);

  // Alt-optimal pas örnekleri — deterministik koordinatlar (Math.random YOK).
  const seed = player.player_id;
  const wave = (k: number) => Math.sin((seed + k) * 1.3) * 0.5 + 0.5; // 0..1
  const top: SuboptimalPass[] = [0, 1, 2].map((k) => {
    const minute = 12 + k * 19 + Math.round(wave(k) * 6);
    const sx = 38 + Math.round(wave(k + 1) * 28);
    const sy = 20 + Math.round(wave(k + 2) * 55);
    const ax = sx + 8 + Math.round(wave(k + 3) * 12);
    const ay = sy + (k % 2 === 0 ? 14 : -16);
    const bx = Math.min(92, sx + 18 + Math.round(wave(k + 4) * 16));
    const by = Math.max(8, Math.min(92, sy + (k % 2 === 0 ? -10 : 12)));
    const delta = +(0.12 + wave(k + 5) * 0.21).toFixed(2);
    return {
      minute,
      start: [sx, sy],
      actual_end: [ax, ay],
      best_alternative: { x: bx, y: by, delta },
      completed: wave(k + 6) > 0.32,
    };
  });
  const passesAnalyzed = player.position === "GK" ? 24 : player.position === "DF" ? 58 : 71;
  const suboptimalShare = +Math.min(0.34, 0.12 + fatiguePenalty * 0.8).toFixed(2);
  const meanDelta = +(top.reduce((s, p) => s + p.best_alternative.delta, 0) / top.length).toFixed(2);

  // Maç-içi katılım: önce bu oyuncuyu adıyla anan canlı olayları topla.
  const nameKey = player.player_name.split(" ")[0]; // ilk ad yeterli ayırt edici
  const fromLive = demoLive.events
    .filter((e) => e.text.includes(nameKey) || e.text.includes(player.player_name))
    .map((e) => ({
      minute: e.minute,
      kind:
        e.type === "gol" ? "Gol" :
        e.type === "buyuk_firsat" ? "Büyük Fırsat" :
        e.type === "sari_kart" ? "Sarı Kart" :
        e.type === "kirmizi_kart" ? "Kırmızı Kart" :
        e.type === "sakatlik" ? "Sakatlık" : "Değişiklik",
      text: e.text,
      tone: (e.type === "gol" || e.type === "buyuk_firsat" ? "iyi" : e.type === "sakatlik" || e.type === "kirmizi_kart" || e.type === "sari_kart" ? "kotu" : "notr") as "iyi" | "kotu" | "notr",
    }));

  // Genel maç-akış satırlarıyla zenginleştir (oyuncuya özel olmayan ama bağlamsal).
  const synthetic: DemoFeedback["involvement"] = [
    { minute: 8, kind: "Pas Ağı", text: `İlk çeyrekte ${player.pos_detail.toLowerCase()} hattında topla buluşma sıklığı yüksek; oyuna erken dahil oldu.`, tone: "iyi" },
    { minute: 34, kind: "Pres", text: `Pres altında ${Math.round(press * 100)}% top koruma; ${player.risk_score >= 60 ? "yorgunlukla birlikte ikinci yarı düşüş bekleniyor." : "ikili mücadelelerde dengeli."}`, tone: player.risk_score >= 60 ? "kotu" : "notr" },
    { minute: minutes < 90 ? minutes : 70, kind: minutes < 90 ? "Değişiklik" : "Yük", text: minutes < 90 ? `${minutes}. dakikada oyundan alındı — kondisyon/yük yönetimi gereği planlı rotasyon.` : `Tam 90 dakika sahada; toplam yük beklenen bandın içinde.`, tone: minutes < 90 ? "notr" : "iyi" },
  ];
  const involvement = [...fromLive, ...synthetic].sort((a, b) => a.minute - b.minute);

  // Bu oyuncuyu işaret eden karar kartları.
  const decisionRefs = demoDecisions.filter((d) => d.headline.includes(nameKey) || d.rationale.includes(nameKey));

  // Türkçe AI brief.
  const formTxt = form >= 1.08 ? "üst düzey" : form >= 0.98 ? "iyi" : form >= 0.9 ? "vasat" : "düşük";
  const overTxt = overLabel === "clinical" ? "beklenenin üzerinde (etkili/bitirici)" : overLabel === "underperforming" ? "beklenenin altında" : "beklenen seviyede";
  const brief =
    `${player.player_name} (#${player.shirt}, ${player.pos_detail}) ${DEMO_CLUB} - ${DEMO_OPPONENT} maçında ${minutes} dakika sahadaydı ve ${formTxt} bir performans sergiledi (maç notu ${rating}/10).\n\n` +
    `İleri tehdit üretimi: xT ${xt}/90, xA ${xa}/90, VAEP ${vaep}/90. Topu ileri taşıma (progresif aksiyon) 90 dakikada ${prog}; pres altında top koruma ${Math.round(press * 100)}%. Katkısı ${overTxt}.\n\n` +
    (player.risk_label === "Kritik" || player.risk_label === "Yüksek"
      ? `Dikkat: oyuncu maç-öncesi ${player.risk_label.toLowerCase()} sakatlık riski bandındaydı (kondisyon ${player.condition}). ${minutes < 90 ? "Planlı erken değişiklik isabetli oldu; " : ""}akut/kronik yük takibi ve toparlanma protokolü önerilir.\n\n`
      : `Yük profili sağlıklı (kondisyon ${player.condition}); bir sonraki maça tam hazır görünüyor.\n\n`) +
    `Gelişim alanı: ${top.length} alt-optimal pas tespit edildi (ort. kayıp xT ${meanDelta}). Özellikle yarı-alanda daha dikey/riskli ileri pas tercihleri beklenen gol katkısını artırabilir.`;

  return {
    player,
    minutes,
    eventsLoaded: 1840 + player.player_id * 7,
    rating,
    metrics: {
      xt_per_90: xt,
      xa_per_90: xa,
      vaep_per_90: vaep,
      progressive_per_90: prog,
      press_resistance_under_press: press,
      overperformance_total: over,
      overperformance_label: overLabel,
    },
    passes: { analyzed: passesAnalyzed, meanDelta, suboptimalShare, top },
    involvement,
    brief,
    decisionRefs,
  };
}

function ratingVar(r: number): string {
  if (r >= 7.5) return "var(--low)";
  if (r >= 6.5) return "var(--mid)";
  if (r >= 5.5) return "var(--high)";
  return "var(--crit)";
}
function riskClass(label: string): string {
  if (label === "Kritik") return "risk-crit";
  if (label === "Yüksek") return "risk-high";
  if (label === "Orta") return "risk-mid";
  return "risk-low";
}
function toneVar(tone: "iyi" | "kotu" | "notr"): string {
  return tone === "iyi" ? "var(--low)" : tone === "kotu" ? "var(--crit)" : "var(--dim)";
}
const URGENCY_VAR: Record<string, string> = {
  "kritik": "var(--crit)",
  "yüksek": "var(--high)",
  "orta": "var(--mid)",
  "düşük": "var(--low)",
};

export default function PlayerFeedbackConsolePage() {
  const params = useParams<{ id: string; pid: string }>();
  const matchId = params.id;
  const playerId = params.pid;

  // Demo modunda canlı API'ye hiç dokunma (SWR key null) — dolu mock göster.
  const { data, error, isLoading } = useSWR<FeedbackResponse>(
    DEMO_MODE ? null : `/admin/matches/${matchId}/players/${playerId}/feedback`,
    apiFetch,
    { shouldRetryOnError: false },
  );

  if (DEMO_MODE) {
    const player =
      demoSquad.find((p) => String(p.player_id) === String(playerId)) ?? demoSquad[0];
    return <DemoFeedbackContent fb={buildDemoFeedback(player)} matchId={matchId} />;
  }

  const title = `Oyuncu #${playerId} — Maç #${matchId}`;
  const m = data?.metrics;
  const sub = data?.pass_alternatives_summary;

  const right = (
    <div className="rc">
      <h3>Maç-Sonu Brief</h3>
      {data?.ai_brief ? (
        <div style={{ fontSize: 12.5, color: "var(--ink)", whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{data.ai_brief}</div>
      ) : (
        <div style={{ fontSize: "12px", color: "var(--dim)" }}>Brief yok.</div>
      )}
    </div>
  );

  return (
    <ConsoleShell active="/matches" title={title} sub="Maç feedback" desc={data ? `${data.minutes_played ?? 0} dk · ${data.events_loaded ?? 0} event` : "Oyuncu maç-sonu analizi."} right={right}>
      {error && <div className="pgdesc">Yüklenemedi: {String(error)}</div>}
      {isLoading && <LoadingState />}
      {data?.events_loaded === 0 && <EmptyState title={data.note ?? "Bu maç için event ingest yok."} />}

      {m && (
        <>
          <div className="st" style={{ marginTop: 0 }}><h2>Metrikler</h2></div>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(6,1fr)" }}>
            <div className="kpi"><div className="kl">xT/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.xt_per_90 ?? 0).toFixed(2)}</div></div>
            <div className="kpi"><div className="kl">xA/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.xa_per_90 ?? 0).toFixed(2)}</div></div>
            <div className="kpi"><div className="kl">VAEP/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.vaep_per_90 ?? 0).toFixed(2)}</div></div>
            <div className="kpi"><div className="kl">Prog/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.progressive_per_90 ?? 0).toFixed(2)}</div></div>
            <div className="kpi"><div className="kl">Pres Altı</div><div className="kn" style={{ fontSize: 20 }}>%{Math.round(m.press_resistance_under_press * 100)}</div></div>
            <div className="kpi"><div className="kl">Overperf.</div><div className="kn" style={{ fontSize: 20, color: opVar(m.overperformance_label) }}>{m.overperformance_total > 0 ? "+" : ""}{m.overperformance_total.toFixed(2)}</div><div className="kd">{m.overperformance_label}</div></div>
          </div>
        </>
      )}

      {sub && sub.top_suboptimal.length > 0 && (
        <>
          <div className="st"><h2>Alt-optimal Pas Örnekleri</h2><span className="ep">{sub.passes_analyzed} pas · %{Math.round(sub.suboptimal_share * 100)} alt-optimal</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            {sub.top_suboptimal.map((p, i) => (
              <div className="rc" key={i} style={{ margin: 0 }}>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>{p.minute.toFixed(0)}. dakika{p.completed ? "" : <span style={{ color: "var(--crit)", marginLeft: 8 }}>(başarısız)</span>}</div>
                <MiniPitch start={p.start} actualEnd={p.actual_end} suggestedEnd={[p.best_alternative.x, p.best_alternative.y]} label={`xT Δ +${p.best_alternative.delta.toFixed(2)}`} />
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, fontFamily: "JetBrains Mono", lineHeight: 1.6 }}>
                  <div>Actual: <span style={{ color: "var(--crit)" }}>({p.actual_end[0].toFixed(0)},{p.actual_end[1].toFixed(0)})</span></div>
                  <div>Önerilen: <span style={{ color: "var(--low)" }}>({p.best_alternative.x.toFixed(0)},{p.best_alternative.y.toFixed(0)})</span></div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </ConsoleShell>
  );
}

// --------------------------------------------------------------------------- //
// DEMO içerik
// --------------------------------------------------------------------------- //

function DemoFeedbackContent({ fb, matchId }: { fb: DemoFeedback; matchId: string }) {
  const { player, metrics: m, passes, involvement, brief, decisionRefs } = fb;
  const matchLabel = `${DEMO_CLUB} ${demoLive.score[0]}-${demoLive.score[1]} ${DEMO_OPPONENT}`;
  const title = `${player.player_name} — Maç Feedback`;

  const right = (
    <>
      <div className="rc">
        <h3>Maç-Sonu Brief <span className="tiny">AI</span></h3>
        <div style={{ fontSize: 12.5, color: "var(--ink)", whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{brief}</div>
      </div>

      <div className="rc">
        <h3>Oyuncu <span className="tiny">#{player.shirt}</span></h3>
        <div className="stat"><span style={{ fontSize: 11.5, color: "var(--muted)" }}>Mevki</span><span className="sv">{player.pos_detail}</span></div>
        <div className="stat"><span style={{ fontSize: 11.5, color: "var(--muted)" }}>Yaş</span><span className="sv">{player.age}</span></div>
        <div className="stat"><span style={{ fontSize: 11.5, color: "var(--muted)" }}>Kondisyon</span><span className="sv">{player.condition}</span></div>
        <div className="stat">
          <span style={{ fontSize: 11.5, color: "var(--muted)" }}>Sakatlık Riski</span>
          <span className={`risk ${riskClass(player.risk_label)}`}><span className="rd" />{player.risk_label}</span>
        </div>
      </div>

      {decisionRefs.length > 0 && (
        <div className="rc">
          <h3>İlgili Kararlar <span className="tiny">{decisionRefs.length}</span></h3>
          {decisionRefs.map((d) => {
            const v = URGENCY_VAR[d.urgency] ?? "var(--dim)";
            return (
              <div className="alrt" key={d.minute}>
                <span className="ai" style={{ background: v }} />
                <div className="am"><b>{d.minute}&apos; · {d.decisionType}</b> — {d.headline}
                  <span className="tm">güven %{d.confidence} · {d.urgency}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );

  return (
    <ConsoleShell
      active="/matches"
      title={title}
      sub="Maç feedback"
      desc={`${matchLabel} · ${demoNextMatch.competition} · ${fb.minutes} dk oynadı · ${fb.eventsLoaded.toLocaleString("tr-TR")} event işlendi`}
      right={right}
    >
      {/* KPI şeridi */}
      <div className="kpis" style={{ gridTemplateColumns: "repeat(6,1fr)" }}>
        <div className="kpi">
          <div className="kl">Maç Notu</div>
          <div className="kn" style={{ fontSize: 24, color: ratingVar(fb.rating) }}>{fb.rating.toFixed(1)}</div>
          <div className="kd">10 üzerinden</div>
        </div>
        <div className="kpi"><div className="kl">xT/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.xt_per_90 ?? 0).toFixed(2)}</div><div className="kd">ileri tehdit</div></div>
        <div className="kpi"><div className="kl">xA/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.xa_per_90 ?? 0).toFixed(2)}</div><div className="kd">beklenen asist</div></div>
        <div className="kpi"><div className="kl">VAEP/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.vaep_per_90 ?? 0).toFixed(2)}</div><div className="kd">aksiyon değeri</div></div>
        <div className="kpi"><div className="kl">Prog/90</div><div className="kn" style={{ fontSize: 20 }}>{(m.progressive_per_90 ?? 0).toFixed(1)}</div><div className="kd">ileri taşıma</div></div>
        <div className="kpi">
          <div className="kl">Beklenen-Üstü</div>
          <div className="kn" style={{ fontSize: 20, color: opVar(m.overperformance_label) }}>{m.overperformance_total > 0 ? "+" : ""}{m.overperformance_total.toFixed(2)}</div>
          <div className="kd">{m.overperformance_label === "clinical" ? "etkili" : m.overperformance_label === "underperforming" ? "verimsiz" : "nötr"}</div>
        </div>
      </div>

      {/* Pres altı + alt-optimal pas özeti barları */}
      <div className="st" style={{ marginTop: 4 }}><h2>Performans Profili</h2><span className="ep">model: VAEP + xT</span></div>
      <div className="rc" style={{ margin: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--muted)" }}>
              <span>Pres Altı Top Koruma</span><b style={{ color: "var(--ink)" }}>%{Math.round(m.press_resistance_under_press * 100)}</b>
            </div>
            <div className="mbar"><i style={{ width: `${Math.round(m.press_resistance_under_press * 100)}%`, background: m.press_resistance_under_press >= 0.62 ? "var(--low)" : "var(--mid)" }} /></div>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--muted)" }}>
              <span>Alt-optimal Pas Oranı</span><b style={{ color: "var(--ink)" }}>%{Math.round(passes.suboptimalShare * 100)}</b>
            </div>
            <div className="mbar"><i style={{ width: `${Math.round(passes.suboptimalShare * 100)}%`, background: passes.suboptimalShare > 0.22 ? "var(--high)" : "var(--mid)" }} /></div>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.6 }}>
            <div className="stat"><span style={{ color: "var(--muted)" }}>Analiz edilen pas</span><span className="sv">{passes.analyzed}</span></div>
            <div className="stat"><span style={{ color: "var(--muted)" }}>Ort. kaçırılan xT</span><span className="sv" style={{ color: "var(--high)" }}>{passes.meanDelta.toFixed(2)}</span></div>
            <div className="stat"><span style={{ color: "var(--muted)" }}>Oynadığı dakika</span><span className="sv">{fb.minutes}&apos;</span></div>
          </div>
        </div>
      </div>

      {/* Maç-içi katılım zaman çizelgesi */}
      <div className="st"><h2>Maç-İçi Katılım</h2><span className="ep">{involvement.length} olay</span></div>
      <div className="tbl">
        <table>
          <thead><tr><th className="c">Dk</th><th>Tür</th><th>Açıklama</th></tr></thead>
          <tbody>
            {involvement.map((ev, i) => (
              <tr key={i}>
                <td className="c pnum">{ev.minute}&apos;</td>
                <td><span className="risk" style={{ color: toneVar(ev.tone) }}><span className="rd" style={{ background: toneVar(ev.tone), boxShadow: `0 0 7px ${toneVar(ev.tone)}` }} />{ev.kind}</span></td>
                <td style={{ color: "var(--muted)" }}>{ev.text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Alt-optimal pas örnekleri (MiniPitch) */}
      <div className="st"><h2>Alt-optimal Pas Örnekleri</h2><span className="ep">{passes.analyzed} pas · %{Math.round(passes.suboptimalShare * 100)} alt-optimal</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        {passes.top.map((p, i) => (
          <div className="rc" key={i} style={{ margin: 0 }}>
            <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8, display: "flex", justifyContent: "space-between" }}>
              <span>{p.minute}. dakika</span>
              {p.completed
                ? <span style={{ color: "var(--low)" }}>tamamlandı</span>
                : <span style={{ color: "var(--crit)" }}>başarısız</span>}
            </div>
            <MiniPitch start={p.start} actualEnd={p.actual_end} suggestedEnd={[p.best_alternative.x, p.best_alternative.y]} label={`xT Δ +${p.best_alternative.delta.toFixed(2)}`} />
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, fontFamily: "JetBrains Mono", lineHeight: 1.6 }}>
              <div>Oynanan: <span style={{ color: "var(--crit)" }}>({p.actual_end[0].toFixed(0)},{p.actual_end[1].toFixed(0)})</span></div>
              <div>Önerilen: <span style={{ color: "var(--low)" }}>({p.best_alternative.x.toFixed(0)},{p.best_alternative.y.toFixed(0)})</span> · +{p.best_alternative.delta.toFixed(2)} xT</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ height: 8 }} />
      <div className="pgdesc" style={{ fontSize: 11.5 }}>Demo · Maç #{matchId} · veriler {DEMO_CLUB} demo evreninden türetildi.</div>
    </ConsoleShell>
  );
}
