"use client";

/**
 * Scout — Oyuncu Benzerliği & Aday Havuzu. ConsoleShell çatısını kullanır.
 * Hedef oyuncu → cosine similarity ile top-N benzer profil + filtreler + izleme listesi.
 *
 * DEMO_MODE açıkken: canlı API'ye dokunmaz, zengin Türkçe scout demosu render eder
 * (FK Demo evreni — hedef Orkun Kökçü #10, transfer adayları + benzerlik tablosu).
 *
 * Backend (DEMO kapalı):
 *   GET    /admin/scout/similar/{player_external_id}
 *   GET    /admin/scout/watchlist
 *   POST   /admin/scout/watchlist
 *   DELETE /admin/scout/watchlist/{id}
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { ConsoleShell } from "../_console/shell";

interface SimMatch {
  player_external_id: number;
  similarity: number; // -1..1 cosine
  total_minutes: number;
}
interface SimResp {
  value: {
    target_player_id: number;
    candidates_considered: number;
    candidates_eligible: number;
    top_matches: SimMatch[];
  };
}
interface WatchEntry {
  id: number;
  player_external_id: number;
  notes: string | null;
}
interface WatchResp {
  entries: WatchEntry[];
}

/* ─────────────────────────────────────────────
   DEMO EVRENİ — bu dosyaya özel inline scout verisi
   (FK Demo · hedef profil: Orkun Kökçü #10, "10 Numara")
───────────────────────────────────────────── */

type DemoPos = "GK" | "DF" | "MF" | "FW";
type DemoTier = "İlk 11" | "Rotasyon" | "Gelecek" | "Kiralık";

interface ScoutCandidate {
  external_id: number;
  name: string;
  pos: DemoPos;
  pos_detail: string;
  age: number;
  club: string;
  league: string;
  value: string;        // piyasa değeri
  minutes: number;      // sezonluk dakika
  goals: number;
  assists: number;
  xg90: number;         // per-90 xG
  xa90: number;         // per-90 xA
  prog90: number;       // per-90 ilerletici aksiyon
  similarity: number;   // 0..1 hedefe benzerlik (cosine)
  tier: DemoTier;
  note: string;
}

/** Hedef oyuncu — kadrodaki 10 numara (yerine alternatif aranıyor). */
const TARGET = {
  external_id: 8,
  name: "Orkun Kökçü",
  shirt: 10,
  pos_detail: "10 Numara",
  age: 30,
  note: "Mevcut 10 numara — 30 yaş, kritik yük riski. Sezon sonu için profil benzeri alternatif aranıyor.",
};

/** Aday havuzu — hedefe per-90 profil yakınlığına göre sıralı (16 oyuncu). */
const CANDIDATES: ScoutCandidate[] = [
  { external_id: 201, name: "Junior Olaitan",   pos: "MF", pos_detail: "10 Numara",   age: 23, club: "FK Demo",        league: "Süper Lig",   value: "€4.2M",  minutes: 1180, goals: 6,  assists: 9,  xg90: 0.28, xa90: 0.34, prog90: 7.1, similarity: 0.93, tier: "Rotasyon", note: "Kadro içi — hazır alternatif. Yaratıcılık ve pres kırma kalitesi yüksek." },
  { external_id: 202, name: "Emir Kaplan",    pos: "MF", pos_detail: "Ön Libero",   age: 21, club: "Genç Yıldız FK", league: "Süper Lig",   value: "€6.8M",  minutes: 2340, goals: 4,  assists: 11, xg90: 0.21, xa90: 0.41, prog90: 8.4, similarity: 0.91, tier: "Gelecek",  note: "Yarı-alan ustası. Yaşına göre olgun karar verme; gelişim eğrisi dik." },
  { external_id: 203, name: "Deniz Aktaş",    pos: "MF", pos_detail: "Merkez OS",   age: 25, club: "Liman SK",       league: "Süper Lig",   value: "€5.1M",  minutes: 2610, goals: 7,  assists: 8,  xg90: 0.31, xa90: 0.29, prog90: 6.7, similarity: 0.88, tier: "İlk 11",   note: "Gol katkısı dengeli; ceza sahasına geç giriş timing'i çok iyi." },
  { external_id: 204, name: "Mateo Rincón",   pos: "MF", pos_detail: "10 Numara",   age: 24, club: "Atlético Vega",  league: "La Liga 2",   value: "€8.5M",  minutes: 2480, goals: 9,  assists: 7,  xg90: 0.36, xa90: 0.27, prog90: 7.9, similarity: 0.86, tier: "İlk 11",   note: "Yabancı bonservis. Bitiricilik üst düzey ama uyum süresi gerekebilir." },
  { external_id: 205, name: "Kaan Erdoğan",   pos: "MF", pos_detail: "Merkez OS",   age: 27, club: "Dağ FK",         league: "Süper Lig",   value: "€3.9M",  minutes: 2890, goals: 5,  assists: 10, xg90: 0.19, xa90: 0.38, prog90: 9.2, similarity: 0.84, tier: "İlk 11",   note: "İlerletici pas hacmi lig lideri seviyesinde; düşük gol tehdidi." },
  { external_id: 206, name: "Yiğit Sönmez",   pos: "MF", pos_detail: "10 Numara",   age: 20, club: "Akademi U21",    league: "PAF Ligi",    value: "€1.5M",  minutes: 1640, goals: 8,  assists: 6,  xg90: 0.33, xa90: 0.25, prog90: 6.1, similarity: 0.82, tier: "Gelecek",  note: "Akademi çıkışı; ucuz seçenek. Fiziksel olgunlaşması bekleniyor." },
  { external_id: 207, name: "Luka Petrović",  pos: "MF", pos_detail: "Ön Libero",   age: 26, club: "HNK Jadran",     league: "1. HNL",      value: "€7.2M",  minutes: 2720, goals: 3,  assists: 9,  xg90: 0.15, xa90: 0.33, prog90: 8.8, similarity: 0.80, tier: "İlk 11",   note: "Derin oyun kurucu; tempo değiştirme yeteneği. Defansif katkı bonus." },
  { external_id: 208, name: "Onurcan Bilge",  pos: "FW", pos_detail: "Sol Kanat",   age: 22, club: "Sahil GK",       league: "Süper Lig",   value: "€4.6M",  minutes: 2010, goals: 11, assists: 5,  xg90: 0.42, xa90: 0.22, prog90: 7.4, similarity: 0.78, tier: "Rotasyon", note: "Kanattan içeri kat eden tip; sol ayak tehdidi. Daha çok gol odaklı." },
  { external_id: 209, name: "Tomáš Novák",    pos: "MF", pos_detail: "10 Numara",   age: 28, club: "SK Brno",        league: "Chance Liga", value: "€5.8M",  minutes: 2550, goals: 6,  assists: 8,  xg90: 0.27, xa90: 0.30, prog90: 7.0, similarity: 0.77, tier: "İlk 11",   note: "Deneyimli; lider profil. Yaş eğrisi düşüşe yakın, kısa sözleşme mantıklı." },
  { external_id: 210, name: "Bora Şimşek",    pos: "MF", pos_detail: "Merkez OS",   age: 24, club: "Ova SK",         league: "Süper Lig",   value: "€3.2M",  minutes: 2380, goals: 4,  assists: 7,  xg90: 0.18, xa90: 0.28, prog90: 6.9, similarity: 0.75, tier: "Rotasyon", note: "Ekonomik; çift yönlü orta saha. Yaratıcılıkta tavan sınırlı." },
  { external_id: 211, name: "Renato Alvez",   pos: "FW", pos_detail: "Sol Kanat",   age: 23, club: "CD Marítimo",    league: "Liga 3",      value: "€6.1M",  minutes: 2190, goals: 10, assists: 8,  xg90: 0.38, xa90: 0.31, prog90: 8.0, similarity: 0.73, tier: "Gelecek",  note: "Yüksek tavan; dripling + gol. Scout izleme önerisi: 3 maç daha." },
  { external_id: 212, name: "Hakan Uğurlu",   pos: "MF", pos_detail: "Ön Libero",   age: 29, club: "Kale FK",        league: "Süper Lig",   value: "€2.4M",  minutes: 2960, goals: 2,  assists: 6,  xg90: 0.11, xa90: 0.24, prog90: 9.6, similarity: 0.71, tier: "İlk 11",   note: "Pas metronomu; düşük maliyet. Hücum tehdidi zayıf, kurgu güçlü." },
  { external_id: 213, name: "Doruk Yalçın",   pos: "MF", pos_detail: "10 Numara",   age: 19, club: "Akademi U19",    league: "PAF Ligi",    value: "€0.9M",  minutes: 980,  goals: 5,  assists: 4,  xg90: 0.30, xa90: 0.26, prog90: 5.8, similarity: 0.69, tier: "Gelecek",  note: "Çok genç; uzun vadeli yatırım. Kiralıkla pişmesi öneriliyor." },
  { external_id: 214, name: "Stefan Marković", pos: "FW", pos_detail: "Santrfor",  age: 25, club: "FK Partizan B",  league: "Prva Liga",   value: "€7.9M",  minutes: 2440, goals: 14, assists: 4,  xg90: 0.51, xa90: 0.18, prog90: 5.2, similarity: 0.66, tier: "İlk 11",   note: "Net santrfor profili; hedefe pozisyon olarak uzak ama gol açlığını kapatır." },
  { external_id: 215, name: "Cenk Aytaç",     pos: "MF", pos_detail: "Merkez OS",   age: 26, club: "Tepe SK",        league: "1. Lig",      value: "€2.1M",  minutes: 3010, goals: 3,  assists: 9,  xg90: 0.16, xa90: 0.32, prog90: 7.3, similarity: 0.64, tier: "Rotasyon", note: "Alt ligden çıkış adayı; istikrarlı asist üretimi. Sıçrama riski var." },
  { external_id: 216, name: "Iker Mendoza",   pos: "MF", pos_detail: "10 Numara",   age: 31, club: "Real Costa",     league: "La Liga 2",   value: "€1.8M",  minutes: 2280, goals: 7,  assists: 10, xg90: 0.29, xa90: 0.36, prog90: 7.6, similarity: 0.61, tier: "Kiralık",  note: "Deneyim transferi; sözleşme sonu fırsat. Yaş nedeniyle kısa vadeli." },
];

/* Filtre tipleri */
type PosFilter = "all" | "MF" | "FW";
type TierFilter = "all" | "İlk 11" | "Rotasyon" | "Gelecek";

const POS_LABEL: Record<DemoPos, string> = { GK: "Kaleci", DF: "Defans", MF: "Orta Saha", FW: "Forvet" };

const TIER_VAR: Record<DemoTier, string> = {
  "İlk 11": "var(--low)",
  "Rotasyon": "var(--mid)",
  "Gelecek": "var(--accent)",
  "Kiralık": "var(--dim)",
};

function simColor(sim: number): string {
  if (sim >= 0.85) return "var(--low)";
  if (sim >= 0.7) return "var(--mid)";
  return "var(--high)";
}

const inputStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 10px",
  borderRadius: "7px",
  width: "130px",
  fontFamily: "inherit",
};

/* ═══════════════════════════════════════════════
   DEMO SAYFA
═══════════════════════════════════════════════ */
function ScoutDemo() {
  const [pos, setPos] = React.useState<PosFilter>("all");
  const [tier, setTier] = React.useState<TierFilter>("all");
  const [maxAge, setMaxAge] = React.useState<number>(35);
  const [watched, setWatched] = React.useState<Set<number>>(
    () => new Set([201, 202, 211]), // başlangıçta birkaç oyuncu izleniyor
  );

  function toggleWatch(id: number) {
    setWatched((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const shown = CANDIDATES.filter((c) => {
    if (pos !== "all" && c.pos !== pos) return false;
    if (tier !== "all" && c.tier !== tier) return false;
    if (c.age > maxAge) return false;
    return true;
  });

  // KPI'lar (tüm havuz üzerinden)
  const poolSize = CANDIDATES.length;
  const topSim = Math.round(CANDIDATES[0].similarity * 100);
  const avgAge = Math.round(CANDIDATES.reduce((a, c) => a + c.age, 0) / poolSize);
  const u23 = CANDIDATES.filter((c) => c.age <= 23).length;
  const watchCount = watched.size;

  // İzleme listesindeki adaylar
  const watchList = CANDIDATES.filter((c) => watched.has(c.external_id));

  // En yüksek benzerlik 3 aday (sağ kolon kısa liste)
  const topThree = [...CANDIDATES].sort((a, b) => b.similarity - a.similarity).slice(0, 3);

  // En yüksek similarity (görsel bar normalizasyonu için)
  const maxSim = Math.max(...CANDIDATES.map((c) => c.similarity));

  const right = (
    <>
      <div className="rc">
        <h3>Hedef Profil <span className="tiny">#{TARGET.shirt}</span></h3>
        <div className="nm-vs" style={{ justifyContent: "flex-start", gap: 10, margin: "2px 0 6px" }}>
          <span className="t" style={{ fontSize: 16 }}>{TARGET.name}</span>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
          <span className="pos">{TARGET.pos_detail}</span>
          <span className="pos">{TARGET.age} yaş</span>
          <span className="pos" style={{ color: "var(--crit)" }}>kritik yük</span>
        </div>
        <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>{TARGET.note}</div>
      </div>

      <div className="rc">
        <h3>En Yüksek Eşleşme <span className="tiny">cosine</span></h3>
        {topThree.map((c) => (
          <div className="stat" key={c.external_id}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, color: "var(--ink)" }}>{c.name}</div>
              <div style={{ fontSize: 10.5, color: "var(--dim)" }}>{c.club} · {c.pos_detail}</div>
            </div>
            <span className="sv" style={{ color: simColor(c.similarity) }}>%{Math.round(c.similarity * 100)}</span>
          </div>
        ))}
      </div>

      <div className="rc">
        <h3>İzleme Listesi <span className="tiny">{watchList.length}</span></h3>
        {watchList.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--dim)" }}>Liste boş. Tablodan oyuncu ekle.</div>
        )}
        {watchList.map((c) => (
          <div className="alrt" key={c.external_id}>
            <span className="ai" style={{ background: TIER_VAR[c.tier] }} />
            <div className="am" style={{ flex: 1, minWidth: 0 }}>
              <b>{c.name}</b>
              <span className="tm">{c.club} · {c.value} · %{Math.round(c.similarity * 100)} benzer</span>
            </div>
            <button
              type="button"
              onClick={() => toggleWatch(c.external_id)}
              title="İzleme listesinden çıkar"
              style={{ background: "transparent", border: "1px solid var(--line)", color: "var(--crit)", fontSize: 10, padding: "2px 7px", borderRadius: 5, cursor: "pointer" }}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/scout"
      title="Scout — Benzerlik"
      sub="Aday havuzu ve profil eşleştirme"
      desc="Per-90 stat vektörü + cosine similarity ile hedef oyuncuya en yakın transfer adayları. Filtreyle pozisyon, kademe ve yaşa göre daralt."
      right={right}
    >
      <div className="kpis">
        <div className="kpi"><div className="kl">Aday Havuzu</div><div className="kn">{poolSize}</div><div className="kd">taranan profil</div></div>
        <div className="kpi"><div className="kl">En Yüksek</div><div className="kn" style={{ color: "var(--low)" }}>{topSim}<span className="pct">%</span></div><div className="kd">{CANDIDATES[0].name}</div></div>
        <div className="kpi"><div className="kl">Ort. Yaş</div><div className="kn">{avgAge}</div><div className="kd">{u23} oyuncu ≤23</div></div>
        <div className="kpi"><div className="kl">İzlemede</div><div className="kn" style={{ color: "var(--accent)" }}>{watchCount}</div><div className="kd">aktif takip</div></div>
        <div className="kpi"><div className="kl">Hedef</div><div className="kn" style={{ fontSize: 18 }}>#{TARGET.shirt}</div><div className="kd">{TARGET.name}</div></div>
      </div>

      <div className="st" style={{ marginTop: 8 }}>
        <h2>Filtreler</h2>
        <span className="ep">{shown.length}/{poolSize} aday</span>
      </div>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center", marginBottom: 4 }}>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--dim)", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 5 }}>Pozisyon</div>
          <div className="seg">
            <button className={pos === "all" ? "on" : ""} onClick={() => setPos("all")}>Tümü</button>
            <button className={pos === "MF" ? "on" : ""} onClick={() => setPos("MF")}>Orta Saha</button>
            <button className={pos === "FW" ? "on" : ""} onClick={() => setPos("FW")}>Forvet</button>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--dim)", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 5 }}>Kademe</div>
          <div className="seg">
            <button className={tier === "all" ? "on" : ""} onClick={() => setTier("all")}>Tümü</button>
            <button className={tier === "İlk 11" ? "on" : ""} onClick={() => setTier("İlk 11")}>İlk 11</button>
            <button className={tier === "Rotasyon" ? "on" : ""} onClick={() => setTier("Rotasyon")}>Rotasyon</button>
            <button className={tier === "Gelecek" ? "on" : ""} onClick={() => setTier("Gelecek")}>Gelecek</button>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--dim)", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 5 }}>Maks. Yaş: {maxAge}</div>
          <input
            type="range"
            min={19}
            max={35}
            value={maxAge}
            onChange={(e) => setMaxAge(Number(e.target.value))}
            style={{ width: 160, accentColor: "var(--accent)", cursor: "pointer", verticalAlign: "middle" }}
          />
        </div>
      </div>

      <div className="st">
        <h2>Benzer Oyuncular</h2>
        <span className="ep">hedef #{TARGET.external_id} · per-90 cosine</span>
      </div>
      <div className="tbl">
        <table>
          <thead><tr>
            <th className="c">#</th>
            <th>Oyuncu</th>
            <th>Kulüp / Lig</th>
            <th className="c">Yaş</th>
            <th className="r">xG90</th>
            <th className="r">xA90</th>
            <th className="r">Değer</th>
            <th style={{ width: 150 }}>Benzerlik</th>
            <th className="c">İzle</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--dim)", padding: 18 }}>
                Bu filtrede aday yok. Filtreyi gevşet.
              </td></tr>
            )}
            {shown.map((c, i) => {
              const sc = simColor(c.similarity);
              const isW = watched.has(c.external_id);
              return (
                <tr key={c.external_id}>
                  <td className="pnum c">{i + 1}</td>
                  <td>
                    <span className="nm">{c.name}</span>{" "}
                    <span className="pos" style={{ marginLeft: 4, color: TIER_VAR[c.tier] }}>{c.tier}</span>
                    <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 2 }}>{c.pos_detail} · {POS_LABEL[c.pos]} · {c.goals}G {c.assists}A</div>
                  </td>
                  <td>
                    <span style={{ fontWeight: 500, color: "var(--muted)" }}>{c.club}</span>
                    <div style={{ fontSize: 10.5, color: "var(--dim)" }}>{c.league}</div>
                  </td>
                  <td className="c" style={{ fontFamily: "JetBrains Mono", color: c.age <= 23 ? "var(--low)" : "var(--muted)" }}>{c.age}</td>
                  <td className="r" style={{ color: "var(--muted)" }}>{c.xg90.toFixed(2)}</td>
                  <td className="r" style={{ color: "var(--muted)" }}>{c.xa90.toFixed(2)}</td>
                  <td className="r" style={{ fontFamily: "JetBrains Mono", color: "var(--ink)" }}>{c.value}</td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="mbar" style={{ flex: 1, margin: 0 }}>
                        <i style={{ width: `${(c.similarity / maxSim) * 100}%`, background: sc }} />
                      </span>
                      <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: sc, minWidth: 36, textAlign: "right" }}>%{Math.round(c.similarity * 100)}</span>
                    </div>
                  </td>
                  <td className="c">
                    {isW ? (
                      <span style={{ fontSize: 10, color: "var(--low)", textTransform: "uppercase" }}>✓ listede</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => toggleWatch(c.external_id)}
                        style={{ fontSize: 10, textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: "1px solid var(--line)", color: "var(--ink)", background: "var(--panel3)", cursor: "pointer" }}
                      >
                        + izle
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="st">
        <h2>Scout Notları</h2>
        <span className="ep">öne çıkan adaylar</span>
      </div>
      <div className="tbl" style={{ padding: "6px 0" }}>
        {shown.slice(0, 4).map((c) => (
          <div className="stat" key={c.external_id} style={{ padding: "9px 14px", alignItems: "flex-start" }}>
            <div style={{ minWidth: 0, paddingRight: 12 }}>
              <div style={{ fontWeight: 600, color: "var(--ink)", marginBottom: 2 }}>
                {c.name} <span style={{ fontSize: 10.5, color: "var(--dim)", fontWeight: 400 }}>· {c.club}</span>
              </div>
              <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 }}>{c.note}</div>
            </div>
            <span className="sv" style={{ color: simColor(c.similarity), whiteSpace: "nowrap" }}>%{Math.round(c.similarity * 100)}</span>
          </div>
        ))}
      </div>
    </ConsoleShell>
  );
}

/* ═══════════════════════════════════════════════
   CANLI SAYFA (DEMO kapalı) — orijinal API davranışı
═══════════════════════════════════════════════ */
function ScoutLive() {
  const [query, setQuery] = React.useState("");
  const [search, setSearch] = React.useState("");

  const sim = useSWR<SimResp>(
    query ? `/admin/scout/similar/${query}` : null,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const watch = useSWR<WatchResp>("/admin/scout/watchlist", apiFetch, {
    shouldRetryOnError: false,
  });

  const matches = sim.data?.value.top_matches ?? [];
  const entries = watch.data?.entries ?? [];
  const watched = new Set(entries.map((e) => e.player_external_id));

  async function addWatch(pid: number) {
    try {
      await apiFetch("/admin/scout/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_external_id: pid, notes: `Scout: ${query} ile benzer` }),
      });
      watch.mutate();
    } catch {
      /* sessizce yut */
    }
  }

  async function removeWatch(pid: number) {
    try {
      await apiFetch(`/admin/scout/watchlist/${pid}`, { method: "DELETE" });
      watch.mutate();
    } catch {
      /* sessizce yut */
    }
  }

  const right = (
    <div className="rc">
      <h3>İzleme Listesi <span className="tiny">{entries.length}</span></h3>
      {entries.length === 0 && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Liste boş. Soldan oyuncu ekle.</div>}
      {entries.map((e) => (
        <div className="alrt" key={e.id}>
          <span className="ai" style={{ background: "var(--low)" }} />
          <div className="am" style={{ flex: 1 }}>
            <b style={{ fontFamily: "JetBrains Mono" }}>#{e.player_external_id}</b>
            <span className="tm">{e.notes ?? "—"}</span>
          </div>
          <button
            type="button"
            onClick={() => removeWatch(e.player_external_id)}
            title="İzleme listesinden çıkar"
            style={{ background: "transparent", border: "1px solid var(--line)", color: "var(--crit)", fontSize: "10px", padding: "2px 7px", borderRadius: 5, cursor: "pointer" }}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );

  return (
    <ConsoleShell
      active="/scout"
      title="Scout — Benzerlik"
      sub="Oyuncu profil eşleştirme"
      desc="Per-90 stat vektörü + cosine similarity ile hedef oyuncuya en yakın profiller. Aday havuzu mevcut kadrodur."
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Hedef Oyuncu</h2>
        <form onSubmit={(e) => { e.preventDefault(); setQuery(search.trim()); }} style={{ display: "flex", gap: 6 }}>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Oyuncu ID" inputMode="numeric" style={inputStyle} />
          <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Analiz et</button>
        </form>
      </div>

      {!query && <div className="pgdesc">Benzerlik analizi için bir hedef oyuncu ID gir.</div>}
      {query && sim.isLoading && <div className="pgdesc">Hesaplanıyor…</div>}
      {query && sim.error && <div className="pgdesc">Bu oyuncu için maç verisi yok ya da aday havuzu yetersiz.</div>}
      {sim.data && matches.length === 0 && !sim.isLoading && <div className="pgdesc">Yeterli benzer aday bulunamadı.</div>}

      {sim.data && matches.length > 0 && (
        <>
          <div className="st">
            <h2>Benzer Oyuncular</h2>
            <span className="ep">hedef #{sim.data.value.target_player_id} · {sim.data.value.candidates_eligible}/{sim.data.value.candidates_considered} aday</span>
          </div>
          <div className="tbl">
            <table>
              <thead><tr>
                <th className="c">#</th><th>Oyuncu</th><th className="r">Benzerlik</th><th className="r">Dakika</th><th className="c">İzle</th>
              </tr></thead>
              <tbody>
                {matches.map((m, i) => (
                  <tr key={m.player_external_id}>
                    <td className="pnum c">{i + 1}</td>
                    <td><span className="nm" style={{ fontFamily: "JetBrains Mono" }}>#{m.player_external_id}</span></td>
                    <td className="r" style={{ color: simColor(m.similarity) }}>{(m.similarity * 100).toFixed(1)}%</td>
                    <td className="r" style={{ color: "var(--muted)" }}>{m.total_minutes}</td>
                    <td className="c">
                      {watched.has(m.player_external_id) ? (
                        <span style={{ fontSize: "10px", color: "var(--low)", textTransform: "uppercase" }}>✓ listede</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => addWatch(m.player_external_id)}
                          style={{ fontSize: "10px", textTransform: "uppercase", padding: "2px 8px", borderRadius: 5, border: "1px solid var(--line)", color: "var(--ink)", background: "var(--panel3)", cursor: "pointer" }}
                        >
                          + izle
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </ConsoleShell>
  );
}

export default function ScoutConsolePage() {
  return DEMO_MODE ? <ScoutDemo /> : <ScoutLive />;
}
