"use client";

/**
 * Antrenman Planı (detay) — rakip profili + önerilen drill'ler + hafta briefi.
 * ConsoleShell çatısında. Rota: /teams/[id]/training-plan?opponent_id=<N>.
 *
 * DEMO_MODE açıkken canlı API'ye (GET /admin/teams/{id}/training-plan) hiç dokunmaz;
 * FK Demo'nun "Rakip SK" maçına özel maça-özel planı gösterir: rakip taktik profili,
 * haftalık mikro-döngü yük eğrisi (inline SVG), rakip zaaflarına bağlı önerilen drill'ler
 * ve eşleşme avantajları. URL'deki [id] sadece başlıkta kullanılır (tek demo evreni yeterli).
 * Backend bağlanınca gerçek takım/rakip id'sine göre canlı plana döner.
 */

import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  DEMO_CLUB,
  DEMO_OPPONENT,
  demoNextMatch,
  demoWeaknesses,
  demoMatchups,
} from "@/lib/demo-data";
import { ConsoleShell } from "../../../_console/shell";

interface Drill { name: string; focus: string; rationale: string; duration_min: string }
interface OpponentProfile {
  ppda: number;
  pressing_style: string;
  recovery_style: string;
  archetype: string;
  dominant_channel: string;
}
interface TrainingPlanResponse {
  my_team_external_id?: number;
  opponent_external_id?: number;
  events_loaded?: number;
  matches_analyzed?: number;
  opponent_profile?: OpponentProfile;
  drills?: Drill[];
  ai_brief?: string;
  note?: string;
}

// --------------------------------------------------------------------------- //
// DEMO VERİSİ (yalnızca bu detay sayfasına özel, inline)
// --------------------------------------------------------------------------- //

// Rakip SK taktik profili — Rakip Raporu motorundan türetilmiş özet.
const DEMO_OPP_PROFILE: OpponentProfile = {
  ppda: 9.4,
  pressing_style: "Orta blok · seçici pres",
  recovery_style: "Hızlı geçiş (kontra)",
  archetype: "Reaktif kontra-atak",
  dominant_channel: "Sağ koridor",
};

// Maça özel haftalık mikro-döngü (MG = maç günü). Drill'lerin yerleştiği takvim.
interface MicroDay {
  label: string;       // "MG-4"
  day: string;         // "Çar"
  type: string;        // antrenman türü
  load: number;        // 0-100 planlanan iç yük
  intensity: "Yüksek" | "Orta" | "Düşük" | "Dinlenme";
}
const DEMO_MICRO: MicroDay[] = [
  { label: "MG+1", day: "Pzt", type: "Toparlanma", load: 22, intensity: "Düşük" },
  { label: "MG-5", day: "Sal", type: "İzin", load: 0, intensity: "Dinlenme" },
  { label: "MG-4", day: "Çar", type: "Yüklenme", load: 88, intensity: "Yüksek" },
  { label: "MG-3", day: "Per", type: "Pozisyon", load: 74, intensity: "Yüksek" },
  { label: "MG-2", day: "Cum", type: "Taktik", load: 52, intensity: "Orta" },
  { label: "MG-1", day: "Cmt", type: "Aktivasyon", load: 30, intensity: "Düşük" },
  { label: "MG", day: "Paz", type: "Maç", load: 100, intensity: "Yüksek" },
];

// Rakip zaaflarına bağlı önerilen drill'ler (canlı API drills şekliyle birebir uyumlu).
const DEMO_DRILLS: Drill[] = [
  {
    name: "İzole sağ kanat 1v1 + cut-in",
    focus: "Hücum · sağ koridor",
    rationale: "Rakip sağ bek hücumda yüksek konumlanıyor; arkasındaki koridor maç başına ort. 6 kez açılıyor. Milot Rashica (7) için içeri kat etme ve bitiricilik tekrarları — bu maçın anahtar eşleşmesi.",
    duration_min: "20",
  },
  {
    name: "Köşe — far-post varyasyon provası",
    focus: "Duran top · ikinci direk",
    rationale: "Rakip zonal savunmada far-post'u örtemiyor (son 8 maçta 4 gol yedi). Sabit far-post koşu kalıbı ve blok-perde çalışması.",
    duration_min: "15",
  },
  {
    name: "Geçiş savunması — ön libero senkronu",
    focus: "Savunma · geri pres",
    rationale: "Rakip reaktif kontra-atak arketipi; top kaybı sonrası ilk 6 saniye kritik. Ön libero koruması + ikinci dalga geri pres senkronu çalışıldı.",
    duration_min: "18",
  },
  {
    name: "Pres kırma — kaleci/stoper ilk pas",
    focus: "Top sahipliği · ilk faz",
    rationale: "İlk 15 dk seçici yüksek pres bekleniyor (PPDA 9.4). Kaleci-stoper ilk pasında 3'lü açılma + uzun seçenek tetiği.",
    duration_min: "16",
  },
  {
    name: "Tekrarlı sprint dayanıklılığı (RSA)",
    focus: "Kondisyon · son 15 dk",
    rationale: "Rakip 75. dk sonrası tempo düşürüyor (PPDA +%30). RSA bloğu ile maçın son çeyreğinde fiziksel üstünlük hedeflendi.",
    duration_min: "12",
  },
];

const DEMO_AI_BRIEF =
  `Bu hafta planın merkezi: rakibin SAĞ KORİDOR zaafını sömürmek. ${DEMO_OPPONENT} orta blokta seçici pres yapıyor ` +
  `(PPDA 9.4) ve top kazanınca hızlı kontraya çıkıyor — yani bizim geçiş savunmamız ve ilk-pas pres kırma kalitemiz ` +
  `belirleyici olacak.\n\n` +
  `Yük planı tapering mantığında: tepe MG-4'te (yüklenme), sonra maça doğru kademeli düşüş. MG-2 taktik gününde ` +
  `sağ kanat 1v1 ve far-post duran top senaryolarına ağırlık veriyoruz.\n\n` +
  `Risk: Orkun Kökçü (10) şüpheli — MG-4/3 bireysel program, MG-1 sabah testine göre karar. Junior Olaitan (14) taze ` +
  `tutuluyor. Milot Rashica (7) sağ kanatta tam yükle hazır; maçın anahtar eşleşmesi onun tarafında.`;

const intensityColor: Record<string, string> = {
  "Yüksek": "var(--high)",
  "Orta": "var(--mid)",
  "Düşük": "var(--low)",
  "Dinlenme": "var(--dim)",
};

const sevMeta: Record<string, { v: string; bg: string }> = {
  "yüksek": { v: "var(--crit)", bg: "var(--crit-bg)" },
  "orta": { v: "var(--mid)", bg: "var(--mid-bg)" },
  "düşük": { v: "var(--low)", bg: "var(--low-bg)" },
};

const PEAK_LOAD = Math.max(...DEMO_MICRO.map((d) => d.load));
const SESSIONS = DEMO_MICRO.filter((d) => d.load > 0 && d.type !== "Maç").length;
const TOTAL_DRILL_MIN = DEMO_DRILLS.reduce((a, d) => a + Number(d.duration_min), 0);

/** Haftalık yük eğrisi — saf inline SVG. */
function LoadCurve({ days }: { days: MicroDay[] }) {
  const W = 560, H = 138, padX = 26, padY = 16;
  const n = days.length;
  const innerW = W - padX * 2;
  const innerH = H - padY * 2;
  const x = (i: number) => padX + (innerW * i) / (n - 1);
  const y = (v: number) => padY + innerH - (innerH * v) / 100;
  const pts = days.map((d, i) => `${x(i)},${y(d.load)}`).join(" ");
  const area = `${padX},${padY + innerH} ${pts} ${padX + innerW},${padY + innerH}`;

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }} preserveAspectRatio="none">
      {[0, 25, 50, 75, 100].map((g) => (
        <line key={g} x1={padX} x2={padX + innerW} y1={y(g)} y2={y(g)} stroke="var(--line)" strokeWidth={1} strokeDasharray={g === 0 ? "0" : "3 4"} />
      ))}
      <polygon points={area} fill="var(--accent)" opacity={0.08} />
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      {days.map((d, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(d.load)} r={d.type === "Maç" ? 5 : 3.5} fill={intensityColor[d.intensity]} stroke="var(--white)" strokeWidth={1.5} />
          <text x={x(i)} y={H - 3} textAnchor="middle" fill="var(--dim)" style={{ fontSize: 9.5 }}>{d.label}</text>
        </g>
      ))}
    </svg>
  );
}

export default function TrainingPlanConsolePage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const teamId = params.id;
  const opponentId = search.get("opponent_id");

  // DEMO_MODE açıkken canlı API'ye hiç dokunma (boş-state / spinner olmaz).
  const { data, error, isLoading } = useSWR<TrainingPlanResponse>(
    DEMO_MODE || !opponentId ? null : `/admin/teams/${teamId}/training-plan?opponent_id=${opponentId}`,
    apiFetch,
    { shouldRetryOnError: false },
  );

  // Demo: dolu plan; canlı: API yanıtı.
  const op: OpponentProfile | undefined = DEMO_MODE ? DEMO_OPP_PROFILE : data?.opponent_profile;
  const drills: Drill[] = DEMO_MODE ? DEMO_DRILLS : (data?.drills ?? []);
  const aiBrief = DEMO_MODE ? DEMO_AI_BRIEF : data?.ai_brief;

  const right = (
    <>
      <div className="rc">
        <h3>Sıradaki Maç <span className="tiny">{DEMO_MODE ? demoNextMatch.competition : ""}</span></h3>
        <div className="nm-vs"><span className="t">{DEMO_MODE ? demoNextMatch.home : DEMO_CLUB}</span><span className="x">vs</span><span className="t away">{DEMO_MODE ? demoNextMatch.away : DEMO_OPPONENT}</span></div>
        <div className="nm-when">{DEMO_MODE ? `${demoNextMatch.date} · ${demoNextMatch.kickoff} · ev sahibi` : "—"}</div>
        <div className="stat"><span>Hazırlık fazı</span><span className="sv" style={{ color: "var(--mid)" }}>MG-2 · Taktik</span></div>
        <div className="stat"><span>Önerilen drill</span><span className="sv">{drills.length} adet</span></div>
        <div className="stat"><span>Toplam drill süresi</span><span className="sv">{TOTAL_DRILL_MIN}&apos;</span></div>
      </div>

      <div className="rc">
        <h3>Hafta Briefi</h3>
        {aiBrief ? (
          <div style={{ fontSize: 12, color: "var(--muted)", whiteSpace: "pre-wrap", lineHeight: 1.55 }}>{aiBrief}</div>
        ) : <div style={{ fontSize: "12px", color: "var(--dim)" }}>Brief yok.</div>}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/training"
      title={DEMO_MODE ? `Antrenman — ${DEMO_CLUB}` : `Antrenman — Takım #${teamId}`}
      sub={DEMO_MODE ? `vs ${DEMO_OPPONENT}` : `vs Rakip #${opponentId ?? "?"}`}
      desc={DEMO_MODE
        ? `${DEMO_OPPONENT} maçına özel haftalık plan: rakip taktik profili, yük eğrisi ve zaaflara bağlı önerilen drill'ler.`
        : (data?.matches_analyzed != null ? `${data.matches_analyzed} rakip maç · ${data.events_loaded ?? 0} event` : "Rakibe özel haftalık antrenman planı.")}
      right={right}
    >
      {!DEMO_MODE && !opponentId && (
        <div className="pgdesc"><code style={{ fontFamily: "JetBrains Mono" }}>?opponent_id=&lt;N&gt;</code> parametresi gerekli (Antrenman ekranından gel).</div>
      )}
      {!DEMO_MODE && error && <div className="pgdesc">Yüklenemedi: {String(error)}</div>}
      {!DEMO_MODE && isLoading && <div className="pgdesc">Yükleniyor…</div>}
      {!DEMO_MODE && data && (data.events_loaded ?? 0) === 0 && <div className="pgdesc">{data.note ?? "Veri yok."}</div>}

      {op && (
        <>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(5,1fr)" }}>
            <div className="kpi"><div className="kl">Önerilen Drill</div><div className="kn">{drills.length}</div><div className="kd">rakibe özel</div></div>
            <div className="kpi"><div className="kl">Saha Seansı</div><div className="kn">{SESSIONS}</div><div className="kd">7 günlük döngü</div></div>
            <div className="kpi"><div className="kl">Zirve Yük</div><div className="kn" style={{ color: "var(--high)" }}>{PEAK_LOAD}<span className="pct">%</span></div><div className="kd">MG-4 yüklenme</div></div>
            <div className="kpi"><div className="kl">Rakip PPDA</div><div className="kn" style={{ fontSize: 22 }}>{op.ppda.toFixed(1)}</div><div className="kd">seçici pres</div></div>
            <div className="kpi"><div className="kl">Hedef Kanal</div><div className="kn" style={{ fontSize: 14 }}>{op.dominant_channel}</div><div className="kd">zaaf koridoru</div></div>
          </div>

          <div className="st" style={{ marginTop: 0 }}><h2>Rakip Profili</h2><span className="ep">{DEMO_OPPONENT}</span></div>
          <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
            <div className="kpi"><div className="kl">Arketip</div><div className="kn" style={{ fontSize: 14 }}>{op.archetype}</div></div>
            <div className="kpi"><div className="kl">Pres Tarzı</div><div className="kn" style={{ fontSize: 14 }}>{op.pressing_style}</div></div>
            <div className="kpi"><div className="kl">Kazanım</div><div className="kn" style={{ fontSize: 14 }}>{op.recovery_style}</div></div>
            <div className="kpi"><div className="kl">Baskın Kanal</div><div className="kn" style={{ fontSize: 14 }}>{op.dominant_channel}</div></div>
          </div>
        </>
      )}

      {DEMO_MODE && (
        <>
          <div className="st"><h2>Haftalık Yük Eğrisi</h2><span className="ep">planlanan iç yük · tapering</span></div>
          <div className="rc" style={{ margin: "0 0 16px" }}>
            <LoadCurve days={DEMO_MICRO} />
            <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
              {(["Yüksek", "Orta", "Düşük"] as const).map((lbl) => (
                <span key={lbl} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)" }}>
                  <span style={{ width: 9, height: 9, borderRadius: 3, background: intensityColor[lbl] }} /> {lbl} yoğunluk
                </span>
              ))}
              <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--dim)" }}>Tepe MG-4, maça doğru kademeli düşüş.</span>
            </div>
          </div>
        </>
      )}

      {drills.length > 0 && (
        <>
          <div className="st"><h2>Önerilen Drill&apos;ler</h2><span className="ep">{drills.length} drill · {TOTAL_DRILL_MIN}&apos;</span></div>
          <div className="tbl">
            <table>
              <thead><tr><th>Drill</th><th>Odak</th><th className="c">Süre</th><th>Gerekçe</th></tr></thead>
              <tbody>
                {drills.map((d) => (
                  <tr key={d.name}>
                    <td><span className="nm">{d.name}</span></td>
                    <td style={{ color: "var(--muted)" }}>{d.focus}</td>
                    <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{d.duration_min}&apos;</td>
                    <td style={{ color: "var(--muted)", fontSize: 11.5, lineHeight: 1.45 }}>{d.rationale}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {DEMO_MODE && (
        <>
          <div className="st"><h2>Maça Özel Antrenman Odakları</h2><span className="ep">{DEMO_OPPONENT} zaaflarına göre</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 16 }}>
            {demoWeaknesses.map((w, i) => {
              const m = sevMeta[w.severity] ?? sevMeta["orta"];
              return (
                <div className="rc" key={i} style={{ margin: 0, borderTop: `2px solid ${m.v}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                    <b style={{ fontSize: 12.5 }}>{w.title}</b>
                    <span style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: 0.5, color: m.v }}>{w.severity}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{w.detail}</div>
                </div>
              );
            })}
          </div>

          <div className="st"><h2>Anahtar Eşleşmeler</h2><span className="ep">drill önceliklerini yönlendirir</span></div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th>Bizim</th><th>Rakip</th><th className="c">Avantaj</th><th>Not</th>
              </tr></thead>
              <tbody>
                {demoMatchups.map((mu) => {
                  const adv = mu.advantage;
                  const av = adv >= 65 ? "var(--low)" : adv >= 50 ? "var(--mid)" : "var(--high)";
                  return (
                    <tr key={mu.ours}>
                      <td><span className="nm">{mu.ours}</span></td>
                      <td style={{ color: "var(--muted)" }}>{mu.theirs}</td>
                      <td className="c">
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, justifyContent: "center" }}>
                          <span className="cond"><i style={{ width: `${adv}%`, background: av }} /></span>
                          <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: av, minWidth: 30 }}>%{adv}</span>
                        </span>
                      </td>
                      <td style={{ color: "var(--dim)", fontSize: 11.5 }}>{mu.note}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}
