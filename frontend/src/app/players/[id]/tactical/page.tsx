"use client";

/**
 * Oyuncu Taktiksel Profil — rol tipolojisi, bölge ısı/dağılım, per-90 metrikler.
 * ConsoleShell çatısında.
 *
 * DEMO_MODE: backend'siz, dolu ve inandırıcı profil. [id] → demoSquad'da aranır
 *   (bulunamazsa ilk oyuncu). Profil pozisyon/yaş/risk'ten deterministik türetilir
 *   (Math.random YOK — tekrarlanabilir). Boş-state / spinner / "veri yok" olmaz.
 * DEMO kapalı: eski canlı-API davranışı (GET /admin/players/{id}/tactical-profile).
 */

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import {
  demoSquad,
  demoMatchups,
  DEMO_CLUB,
  DEMO_OPPONENT,
  type SquadPlayer,
  type Position,
} from "@/lib/demo-data";
import { ConsoleShell } from "../../../_console/shell";
import { RiskDonut, LegendRow } from "../../../_console/viz";

// ───────────────────────── Canlı-API tipleri (DEMO kapalıyken) ─────────────────────────

interface EngineValue {
  value: Record<string, unknown>;
}

interface PlayerTactical {
  player_id: number;
  events_loaded: number;
  meta: {
    team_external_id: number | null;
    minutes_played: number;
    matches_analyzed: number;
  };
  tactical_profile: Record<string, EngineValue | { error: string }>;
  note?: string;
}

function fmt(v: unknown): string {
  if (typeof v === "number") return v.toFixed(2);
  if (v === null || v === undefined) return "—";
  return String(v);
}

function LiveMetricRow({
  label,
  metric,
  primary,
  secondary,
  badge,
}: {
  label: string;
  metric?: EngineValue | { error: string };
  primary: string;
  secondary?: string;
  badge?: string;
}) {
  if (!metric || "error" in metric) {
    return (
      <div className="rc" style={{ margin: 0 }}>
        <h3>{label}</h3>
        <p style={{ color: "var(--dim)", fontSize: 12 }}>—</p>
      </div>
    );
  }
  const v = metric.value;
  return (
    <div className="rc" style={{ margin: 0 }}>
      <h3>{label}</h3>
      <div style={{ fontSize: 24, fontWeight: 800, fontFamily: "JetBrains Mono", marginBottom: 4 }}>{fmt(v[primary])}</div>
      {secondary && (
        <div style={{ fontSize: 11, color: "var(--dim)" }}>
          {secondary}: <span style={{ fontFamily: "JetBrains Mono" }}>{fmt(v[secondary])}</span>
        </div>
      )}
      {badge && v[badge] !== undefined && (
        <span className="pos" style={{ marginTop: 8 }}>{String(v[badge])}</span>
      )}
    </div>
  );
}

// ───────────────────────── DEMO: deterministik taktik profil türetimi ─────────────────────────

const RISK_VAR: Record<string, string> = {
  Kritik: "var(--crit)",
  Yüksek: "var(--high)",
  Orta: "var(--mid)",
  Düşük: "var(--low)",
};

/** Pozisyon detayından okunur rol etiketi + tipoloji açıklaması. */
const ROLE_BY_DETAIL: Record<string, { role: string; typology: string }> = {
  Kaleci: { role: "Oyun Kuran Kaleci", typology: "Ayakla oyun başlatma + ceza sahası hâkimiyeti" },
  Stoper: { role: "Topla Oynayan Stoper", typology: "İlk pasla pres kırma + savunma ikili mücadele" },
  "Sağ Bek": { role: "Hücumcu Sağ Bek", typology: "Üst koridor genişlik + içe kat eden orta" },
  "Sol Bek": { role: "Hücumcu Sol Bek", typology: "Bindirme + derinlik ortası" },
  "Ön Libero": { role: "Ön Libero (Regista)", typology: "Derin tempo + geçiş koruması" },
  "Merkez OS": { role: "Box-to-Box Orta Saha", typology: "Dikey koşu + her iki ceza sahası katkısı" },
  "10 Numara": { role: "Numara 10 (Yaratıcı)", typology: "Yarı-alan yaratıcılık + son pas" },
  "Sol Kanat": { role: "İçe Kat Eden Sol Kanat", typology: "1v1 dripling + içe kat edip bitirme" },
  "Sağ Kanat": { role: "İçe Kat Eden Sağ Kanat", typology: "Hız + dikine geçiş tehdidi" },
  Santrfor: { role: "Komple Santrfor", typology: "Derinlik + hava topu + ceza sahası bitiriciliği" },
};

interface TacticalMetric {
  label: string;
  value: number;
  unit: string;
  pct: number; // 0-100 lig içi yüzdelik dilim (percentile)
  hint: string;
}

interface ZoneCell {
  /** 0=sol/savunma .. dikey 3 dilim x yatay 4 koridor */
  band: number; // 0..3 (defansif -> hücum)
  lane: number; // 0..3 (sol -> sağ)
  heat: number; // 0..100
}

interface TacticalProfile {
  role: string;
  typology: string;
  confidence: number; // 0-100
  secondary: string;
  matchesAnalyzed: number;
  minutes: number;
  metrics: TacticalMetric[];
  zones: ZoneCell[];
  laneShare: { lane: string; share: number }[];
  pressResUnder: number;
  pressResFree: number;
  vaep: number;
  xtAdded: number;
  xa: number;
  progPer90: number;
}

/** Deterministik 0..1 dalga — oyuncuya + tohuma göre tekrarlanabilir. */
function wave(seed: number, k: number): number {
  return Math.sin((seed + k * 2.3) * 1.7) * 0.5 + 0.5; // 0..1
}

/** Pozisyona göre baz koridor ağırlığı (sol..sağ). */
function laneBias(p: SquadPlayer): [number, number, number, number] {
  const d = p.pos_detail;
  if (d.includes("Sol")) return [0.42, 0.28, 0.18, 0.12];
  if (d.includes("Sağ")) return [0.12, 0.18, 0.28, 0.42];
  if (d === "Santrfor" || d === "10 Numara") return [0.18, 0.32, 0.32, 0.18];
  if (d === "Kaleci") return [0.15, 0.35, 0.35, 0.15];
  return [0.22, 0.28, 0.28, 0.22];
}

/** Pozisyona göre baz dikey ağırlık (savunma..hücum band). */
function bandBias(pos: Position): [number, number, number, number] {
  switch (pos) {
    case "GK": return [0.7, 0.22, 0.06, 0.02];
    case "DF": return [0.46, 0.34, 0.15, 0.05];
    case "MF": return [0.18, 0.34, 0.34, 0.14];
    case "FW": return [0.06, 0.18, 0.34, 0.42];
  }
}

function buildProfile(p: SquadPlayer): TacticalProfile {
  const meta = ROLE_BY_DETAIL[p.pos_detail] ?? { role: p.pos_detail, typology: "Genel görev" };
  const seed = p.player_id;
  const cond = p.condition; // 0-100
  const fatigue = (100 - cond) / 100; // 0..1 yorgunluk
  // Risk yüksekse hücum çıktısı/yoğunluk biraz düşer (yük yönetimi etkisi).
  const sharp = 0.55 + (cond / 100) * 0.45 - fatigue * 0.1;

  // Pozisyona göre per-90 metrik şablonları + deterministik dalga.
  const mk = (label: string, base: number, spread: number, unit: string, k: number, hint: string): TacticalMetric => {
    const v = base + (wave(seed, k) - 0.5) * spread;
    const pct = Math.round(Math.max(6, Math.min(96, 40 + (wave(seed, k + 5) - 0.5) * 70 + (sharp - 0.75) * 60)));
    return { label, value: Math.round(v * 100) / 100, unit, pct, hint };
  };

  let metrics: TacticalMetric[];
  switch (p.position) {
    case "GK":
      metrics = [
        mk("Pas İsabeti (baskı altında)", 78, 14, "%", 1, "İlk pas çıkışında pres altında doğru pas oranı"),
        mk("Uzun Pas İsabeti", 54, 16, "%", 2, "30m+ pasların yerini bulma oranı"),
        mk("Ceza Sahası Çıkışı /90", 1.8, 1.0, "adet", 3, "Hava topu/orta kesme amaçlı çıkış"),
        mk("Önlenen Gol (PSxG−GA)", 0.21, 0.5, "xG", 4, "Beklenen üzeri kurtarış katkısı"),
        mk("Sweeper Müdahale /90", 1.1, 0.8, "adet", 5, "Savunma arkası alan koruma"),
      ];
      break;
    case "DF":
      metrics = [
        mk("İleri Taşıma /90", 4.6, 2.2, "adet", 1, "Topu ileri sürerek hattı kıran taşımalar"),
        mk("İlerletici Pas /90", 6.2, 2.6, "adet", 2, "Topu 10m+ ileri taşıyan pas"),
        mk("İkili Mücadele Kazanma", 62, 16, "%", 3, "Yer + hava toplam mücadele galibiyeti"),
        mk("Top Kazanımı /90", 7.4, 2.4, "adet", 4, "Müdahale + kesme + top çalma"),
        mk("Pas İsabeti", 86, 10, "%", 5, "Genel pas tamamlama oranı"),
      ];
      break;
    case "MF":
      metrics = [
        mk("xT Katkısı /90", 0.34, 0.22, "xT", 1, "Pas+taşıma ile yaratılan tehdit değeri"),
        mk("İlerletici Pas /90", 8.1, 3.0, "adet", 2, "Hücum yönünde hat kıran pas"),
        mk("Pres Kırma /90", 5.7, 2.4, "adet", 3, "Baskı altında topu koruyup ilerletme"),
        mk("Son 1/3'e Taşıma /90", 3.9, 1.8, "adet", 4, "Topla son bölgeye giriş"),
        mk("Pas İsabeti", 88, 8, "%", 5, "Genel pas tamamlama oranı"),
      ];
      break;
    case "FW":
      metrics = [
        mk("xG /90", 0.46, 0.3, "xG", 1, "90 dakikada beklenen gol"),
        mk("xA /90", 0.28, 0.2, "xA", 2, "Asist beklentisi (yarattığı şut kalitesi)"),
        mk("Topsuz Koşu /90", 9.4, 3.4, "adet", 3, "Derinlik + kanal arkası koşular"),
        mk("1v1 Dripling Başarısı", 58, 18, "%", 4, "İkili geçişte rakibi geçme oranı"),
        mk("Ceza Sahası Dokunuş /90", 5.2, 2.2, "adet", 5, "Rakip ceza sahasında top teması"),
      ];
      break;
  }

  // Bölge ısı haritası (4 band x 4 lane) — pozisyon + koridor + dikey eğilim.
  const lb = laneBias(p);
  const bb = bandBias(p.position);
  const zones: ZoneCell[] = [];
  let zmax = 0;
  for (let band = 0; band < 4; band++) {
    for (let lane = 0; lane < 4; lane++) {
      const base = bb[band] * lb[lane] * 100;
      const noise = (wave(seed, band * 4 + lane + 11) - 0.5) * 18;
      const heat = Math.max(0, base * 9 + noise);
      zmax = Math.max(zmax, heat);
      zones.push({ band, lane, heat });
    }
  }
  // 0-100'e normalize
  zones.forEach((z) => (z.heat = zmax > 0 ? Math.round((z.heat / zmax) * 100) : 0));

  const laneTotals = [0, 0, 0, 0];
  zones.forEach((z) => (laneTotals[z.lane] += z.heat));
  const laneSum = laneTotals.reduce((a, b) => a + b, 0) || 1;
  const laneShare = [
    { lane: "Sol", share: Math.round((laneTotals[0] / laneSum) * 100) },
    { lane: "Sol-İç", share: Math.round((laneTotals[1] / laneSum) * 100) },
    { lane: "Sağ-İç", share: Math.round((laneTotals[2] / laneSum) * 100) },
    { lane: "Sağ", share: Math.round((laneTotals[3] / laneSum) * 100) },
  ];

  const minutes = 1980 + Math.round((wave(seed, 21) - 0.5) * 900); // ~22 maç civarı
  const matchesAnalyzed = Math.max(8, Math.round(minutes / 90));

  return {
    role: meta.role,
    typology: meta.typology,
    confidence: Math.round(72 + (wave(seed, 31) - 0.5) * 36),
    secondary: SECONDARY_BY_DETAIL[p.pos_detail] ?? "—",
    matchesAnalyzed,
    minutes,
    metrics,
    zones,
    laneShare,
    pressResUnder: Math.round(64 + (wave(seed, 41) - 0.5) * 26 + (sharp - 0.75) * 30),
    pressResFree: Math.round(86 + (wave(seed, 42) - 0.5) * 12),
    vaep: Math.round((0.12 + (wave(seed, 43) - 0.5) * 0.22 + (sharp - 0.75) * 0.2) * 1000) / 1000,
    xtAdded: Math.round((0.26 + (wave(seed, 44) - 0.5) * 0.22) * 1000) / 1000,
    xa: Math.round((0.22 + (wave(seed, 45) - 0.5) * 0.2) * 1000) / 1000,
    progPer90: Math.round((6.5 + (wave(seed, 46) - 0.5) * 4.5) * 10) / 10,
  };
}

const SECONDARY_BY_DETAIL: Record<string, string> = {
  Kaleci: "—",
  Stoper: "Ön Libero (acil)",
  "Sağ Bek": "Sağ Kanat",
  "Sol Bek": "Sol Kanat",
  "Ön Libero": "Merkez Orta Saha",
  "Merkez OS": "Numara 10",
  "10 Numara": "İkinci Forvet",
  "Sol Kanat": "Numara 10",
  "Sağ Kanat": "İkinci Forvet",
  Santrfor: "Numara 10",
};

function pctVar(pct: number): string {
  return pct >= 75 ? "var(--low)" : pct >= 45 ? "var(--mid)" : "var(--high)";
}

function heatColor(heat: number): string {
  // şeffaf accent → dolu accent (ısı arttıkça koyulaşır)
  const a = 0.06 + (heat / 100) * 0.74;
  return `rgba(92, 53, 212, ${a.toFixed(3)})`;
}

// ───────────────────────── DEMO içerik ─────────────────────────

function DemoTacticalContent({ rawId }: { rawId: string }) {
  const player = demoSquad.find((p) => String(p.player_id) === String(rawId)) ?? demoSquad[0];
  const tp = buildProfile(player);
  const rv = RISK_VAR[player.risk_label] ?? "var(--dim)";

  // Bu oyuncuyu ilgilendiren rakip eşleşmesi (varsa) — demoMatchups'tan.
  const matchup = demoMatchups.find((m) => m.ours.includes(`(${player.shirt})`) || m.ours.includes(player.player_name));

  const POS_LABEL: Record<Position, string> = { GK: "Kaleci", DF: "Defans", MF: "Orta Saha", FW: "Forvet" };

  // Sağ panel: koridor dağılımı (donut) + pres direnci + eşleşme.
  const laneColors = ["var(--accent)", "#7c5ce0", "#a78bfa", "#c4b5fd"];
  const right = (
    <>
      <div className="rc">
        <h3>Koridor Dağılımı <span className="tiny">topla katkı</span></h3>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <RiskDonut
            segments={tp.laneShare.map((l, i) => ({ value: l.share, color: laneColors[i] }))}
            centerLabel={`${Math.max(...tp.laneShare.map((l) => l.share))}%`}
            centerSub="baskın"
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            {tp.laneShare.map((l, i) => (
              <LegendRow key={l.lane} color={laneColors[i]} label={l.lane} value={l.share} />
            ))}
          </div>
        </div>
      </div>

      <div className="rc">
        <h3>Pres Direnci <span className="tiny">pas isabeti</span></h3>
        <div className="stat">
          <span style={{ fontSize: 12, color: "var(--muted)" }}>Baskı altında</span>
          <span className="sv" style={{ color: pctVar(tp.pressResUnder) }}>{tp.pressResUnder}%</span>
        </div>
        <div className="mbar"><i style={{ width: `${tp.pressResUnder}%`, background: pctVar(tp.pressResUnder) }} /></div>
        <div className="stat">
          <span style={{ fontSize: 12, color: "var(--muted)" }}>Baskısız</span>
          <span className="sv">{tp.pressResFree}%</span>
        </div>
        <div className="mbar"><i style={{ width: `${tp.pressResFree}%`, background: "var(--accent)" }} /></div>
        <div style={{ fontSize: 11, color: "var(--dim)", marginTop: 4 }}>
          Fark {tp.pressResFree - tp.pressResUnder} puan — {tp.pressResFree - tp.pressResUnder <= 14 ? "baskıya dirençli" : "baskıda zorlanıyor"}.
        </div>
      </div>

      <div className="rc">
        <h3>Maç Eşleşmesi <span className="tiny">{DEMO_OPPONENT}</span></h3>
        {matchup ? (
          <>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink)" }}>{matchup.ours.split("—")[0].trim()}</div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", margin: "2px 0 8px" }}>vs {matchup.theirs}</div>
            <div className="mbar"><i style={{ width: `${matchup.advantage}%`, background: matchup.advantage >= 60 ? "var(--low)" : matchup.advantage >= 45 ? "var(--mid)" : "var(--high)" }} /></div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
              <span style={{ color: "var(--dim)" }}>avantaj</span>
              <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: matchup.advantage >= 60 ? "var(--low)" : "var(--mid)" }}>%{matchup.advantage}</span>
            </div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8 }}>{matchup.note}</div>
          </>
        ) : (
          <div style={{ fontSize: 12, color: "var(--muted)" }}>
            Bu oyuncu için doğrudan birebir eşleşme öne çıkmıyor; rol içi rotasyon adayı.
          </div>
        )}
        <Link href={`/players/${player.player_id}`} style={{ display: "inline-block", marginTop: 10, fontSize: 11.5, fontWeight: 600, color: "var(--accent)", textDecoration: "none" }}>
          Tam profil →
        </Link>
      </div>
    </>
  );

  // Isı haritası grid'i için band etiketleri (üst=hücum).
  const BAND_LABEL = ["Hücum 1/3", "İleri orta", "Geri orta", "Savunma 1/3"];

  return (
    <ConsoleShell
      active="/squad"
      title={`${player.player_name} — Taktiksel Profil`}
      sub={`#${player.shirt} · ${tp.role}`}
      desc={`${DEMO_CLUB} · son ${tp.matchesAnalyzed} maç · ${tp.minutes} dk · pozisyon dağılımı, per-90 metrikler ve rol tipolojisi.`}
      right={right}
    >
      {/* KPI şeridi */}
      <div className="kpis">
        <div className="kpi">
          <div className="kl">Rol</div>
          <div className="kn" style={{ fontSize: 15, lineHeight: 1.2 }}>{POS_LABEL[player.position]}</div>
          <div className="kd">{tp.role}</div>
        </div>
        <div className="kpi">
          <div className="kl">Rol Güveni</div>
          <div className="kn">{tp.confidence}<span className="pct">%</span></div>
          <div className="kd">ikincil: {tp.secondary}</div>
        </div>
        <div className="kpi">
          <div className="kl">İlerletici Pas /90</div>
          <div className="kn">{tp.progPer90}</div>
          <div className="kd">hat kıran pas</div>
        </div>
        <div className="kpi">
          <div className="kl">xT Katkısı /90</div>
          <div className="kn" style={{ color: "var(--accent)" }}>{tp.xtAdded.toFixed(2)}</div>
          <div className="kd">yaratılan tehdit</div>
        </div>
        <div className="kpi">
          <div className="kl">VAEP /90</div>
          <div className="kn">{tp.vaep.toFixed(2)}</div>
          <div className="kd">pozisyon değeri</div>
        </div>
      </div>

      {/* Rol kartı + kondisyon/risk */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 12, marginBottom: 4 }}>
        <div className="rc" style={{ margin: 0 }}>
          <h3>Rol Tipolojisi <span className="tiny">son {tp.matchesAnalyzed} maç</span></h3>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 19, fontWeight: 800, color: "var(--ink)" }}>{tp.role}</span>
            <span className="pos">{player.pos_detail}</span>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 6 }}>{tp.typology}</div>
          <div style={{ display: "flex", gap: 18, marginTop: 12, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--dim)" }}>xA /90</div>
              <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "JetBrains Mono" }}>{tp.xa.toFixed(2)}</div>
            </div>
            <div>
              <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--dim)" }}>Yaş</div>
              <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "JetBrains Mono" }}>{player.age}</div>
            </div>
            <div>
              <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--dim)" }}>Baskın koridor</div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>{tp.laneShare.reduce((a, b) => (b.share > a.share ? b : a)).lane}</div>
            </div>
          </div>
        </div>

        <div className="rc" style={{ margin: 0 }}>
          <h3>Hazırlık & Risk <span className="tiny">yük durumu</span></h3>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <span style={{ fontSize: 26, fontWeight: 800, fontFamily: "JetBrains Mono" }}>{player.condition}<span style={{ fontSize: 13, color: "var(--dim)" }}>%</span></span>
            <span className="risk" style={{ color: rv }}><span className="rd" style={{ background: rv, boxShadow: `0 0 7px ${rv}` }} />{player.risk_label}</span>
          </div>
          <div className="mbar" style={{ marginTop: 10 }}><i style={{ width: `${player.condition}%`, background: player.condition >= 85 ? "var(--low)" : player.condition >= 72 ? "var(--mid)" : "var(--high)" }} /></div>
          <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 6 }}>
            Risk skoru <b style={{ color: rv, fontFamily: "JetBrains Mono" }}>{player.risk_score}/100</b>.{" "}
            {player.risk_score >= 65
              ? "Yük zirvede — bu profilin yoğun bölge çıktısı maç-içi sınırlanmalı."
              : player.risk_score >= 38
                ? "İzlemede — tam maç yüküne yakın."
                : "Tam maç yüküne hazır."}
          </div>
        </div>
      </div>

      {/* Bölge ısı haritası + per-90 metrikler */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.25fr", gap: 12 }}>
        <div className="rc" style={{ margin: 0 }}>
          <h3>Bölge Isı Haritası <span className="tiny">topla aktivite</span></h3>
          <PitchHeat zones={tp.zones} bandLabels={BAND_LABEL} />
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, fontSize: 11, color: "var(--dim)" }}>
            <span>düşük</span>
            <span style={{ flex: 1, height: 6, borderRadius: 3, background: "linear-gradient(90deg, rgba(92,53,212,.08), rgba(92,53,212,.8))" }} />
            <span>yoğun</span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 8 }}>
            Hücum yönü yukarı. {DEMO_CLUB} soldan sağa oynuyor; ısı topla temas yoğunluğunu gösterir.
          </div>
        </div>

        <div className="rc" style={{ margin: 0 }}>
          <h3>Per-90 Metrikler <span className="tiny">lig içi yüzdelik</span></h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 11, marginTop: 2 }}>
            {tp.metrics.map((m) => (
              <div key={m.label}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--ink)", fontWeight: 500 }} title={m.hint}>{m.label}</span>
                  <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, fontSize: 12.5 }}>
                    {m.value}
                    <span style={{ fontSize: 10, color: "var(--dim)", fontWeight: 400, marginLeft: 3 }}>{m.unit}</span>
                  </span>
                </div>
                <div className="mbar" style={{ margin: "4px 0 0" }}><i style={{ width: `${m.pct}%`, background: pctVar(m.pct) }} /></div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2 }}>
                  <span style={{ fontSize: 10, color: "var(--dim)" }}>{m.hint}</span>
                  <span style={{ fontSize: 10, fontFamily: "JetBrains Mono", color: pctVar(m.pct), fontWeight: 600 }}>%{m.pct} dilim</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <p style={{ fontSize: 11, color: "var(--dim)", marginTop: 14 }}>
        Yüzdelik dilim = oyuncunun lig içindeki pozisyon-grubu sıralaması (yüksek = daha iyi). VAEP = ΔP(skor) − ΔP(gol yeme); xT = pas/taşıma ile yaratılan beklenen tehdit. Demo verisi.
      </p>
    </ConsoleShell>
  );
}

/** Inline SVG saha + ısı grid'i (4 band x 4 lane). Hücum yönü yukarı. */
function PitchHeat({ zones, bandLabels }: { zones: ZoneCell[]; bandLabels: string[] }) {
  const W = 260;
  const H = 360;
  const cellW = W / 4;
  const cellH = H / 4;
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block", borderRadius: 10, background: "var(--surface2)" }}>
      {/* ısı hücreleri */}
      {zones.map((z) => (
        <rect
          key={`${z.band}-${z.lane}`}
          x={z.lane * cellW}
          y={z.band * cellH}
          width={cellW}
          height={cellH}
          fill={heatColor(z.heat)}
        />
      ))}
      {/* saha çizgileri */}
      <g stroke="var(--border2)" strokeWidth={1.2} fill="none">
        <rect x={4} y={4} width={W - 8} height={H - 8} rx={6} />
        <line x1={4} y1={H / 2} x2={W - 4} y2={H / 2} />
        <circle cx={W / 2} cy={H / 2} r={34} />
        <circle cx={W / 2} cy={H / 2} r={2} fill="var(--border2)" />
        {/* ceza sahaları */}
        <rect x={W / 2 - 56} y={4} width={112} height={52} />
        <rect x={W / 2 - 56} y={H - 56} width={112} height={52} />
        <rect x={W / 2 - 26} y={4} width={52} height={20} />
        <rect x={W / 2 - 26} y={H - 24} width={52} height={20} />
      </g>
      {/* band etiketleri */}
      {bandLabels.map((b, i) => (
        <text key={b} x={8} y={i * cellH + 14} fill="var(--dim)" style={{ fontSize: 9, letterSpacing: 0.3 }}>
          {b}
        </text>
      ))}
      {/* en yoğun hücreye yüzde */}
      {zones
        .filter((z) => z.heat >= 60)
        .map((z) => (
          <text
            key={`t-${z.band}-${z.lane}`}
            x={z.lane * cellW + cellW / 2}
            y={z.band * cellH + cellH / 2 + 4}
            textAnchor="middle"
            fill="#fff"
            style={{ fontSize: 11, fontWeight: 700, fontFamily: "JetBrains Mono" }}
          >
            {z.heat}
          </text>
        ))}
    </svg>
  );
}

// ───────────────────────── Canlı içerik (DEMO kapalıyken) ─────────────────────────

function LiveTacticalContent() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const playerId = params.id;
  const lastN = search.get("last_n") ?? "10";
  const { data, error, isLoading } = useSWR<PlayerTactical>(
    `/admin/players/${playerId}/tactical-profile?last_n=${lastN}`,
    apiFetch,
    { shouldRetryOnError: false },
  );

  const note =
    error
      ? `Yüklenemedi: ${String(error)}`
      : isLoading || !data
        ? "Yükleniyor…"
        : data.events_loaded === 0
          ? "Bu oyuncu için events tablosunda kayıt yok."
          : null;

  const tp = data?.tactical_profile;

  return (
    <ConsoleShell
      active="/squad"
      title={`Oyuncu #${playerId} — Taktiksel Profil`}
      sub="per-90 metrikler"
      desc={
        data
          ? `Son ${data.meta.matches_analyzed} maç · ${data.meta.minutes_played} dk · takım #${data.meta.team_external_id ?? "—"}`
          : "Yaratıcı katkı, top atağı ve pres metrikleri."
      }
    >
      {note && (
        <div className="rc" style={{ margin: 0 }}>
          <div style={{ fontSize: 12.5, color: error ? "var(--crit)" : "var(--muted)" }}>{note}</div>
        </div>
      )}

      {tp && (
        <>
          <div className="st"><h2>Yaratıcı Katkı</h2></div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
            <LiveMetricRow label="Player xT" metric={tp.player_xt} primary="player_xt_added" secondary="contributions" />
            <LiveMetricRow label="Player xA" metric={tp.player_xa} primary="xa_total" secondary="key_passes" />
            <LiveMetricRow label="Overperformance" metric={tp.overperformance} primary="total_overperformance" secondary="goals" badge="label" />
          </div>

          <div className="st"><h2>Top Atağı</h2></div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
            <LiveMetricRow label="İlerletici Pas" metric={tp.progressive_passes} primary="progressive_per_90" secondary="progressive_share" />
            <LiveMetricRow label="Son 1/3'e Taşıma" metric={tp.carries_into_final_third} primary="per_90" secondary="deep_to_final_third" />
            <LiveMetricRow label="Topsuz Koşu" metric={tp.off_ball_runs} primary="forward_runs_per_90" secondary="runs_per_possession" />
          </div>

          <div className="st"><h2>Pres & Tehdit</h2></div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 12 }}>
            <LiveMetricRow label="Press Resistance" metric={tp.press_resistance} primary="completion_rate_under_press" secondary="completion_rate_unpressed" />
            <LiveMetricRow label="VAEP (Possession Value)" metric={tp.vaep} primary="vaep_per_90" secondary="vaep_value" badge="model_version" />
          </div>

          <p style={{ fontSize: 11, color: "var(--dim)", marginTop: 14 }}>
            VAEP = ΔP(score) − ΔP(concede). Şu an heuristic baseline; v2 ML.
          </p>
        </>
      )}
    </ConsoleShell>
  );
}

// ───────────────────────── Sayfa kökü ─────────────────────────

export default function PlayerTacticalPage() {
  const params = useParams<{ id: string }>();
  // Demo modunda backend'e hiç dokunma — id'yi demoSquad'da çöz, dolu profil göster.
  if (DEMO_MODE) return <DemoTacticalContent rawId={String(params?.id ?? "")} />;
  return <LiveTacticalContent />;
}
