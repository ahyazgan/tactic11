"use client";

/**
 * Gerçek Veri Taktik Analizi — StatsBomb Open Data maç kütüphanesi.
 * 4 ünlü maç (dropdown): pas ağları + şut haritaları + savunma bloğu + faz
 * metrikleri, hepsi gerçek event verisinden (lib/statsbomb-match). Demo DEĞİL.
 */

import * as React from "react";
import {
  matchList, matchInfo, realPassNetwork, realTeam, realDeepProfile, realScoutSummary, realPlayers,
} from "@/lib/statsbomb-match";
import type { KeyPlayer } from "@/lib/statsbomb-match";
import { ConsoleShell } from "../_console/shell";
import { PassNetworkPitch, ShotMap, DeepTacticalBody, HeatMap, ProgressionMap, XgTimeline, KeyPlayersTable, PlayerDeepDive } from "../_console/pitch-analysis";

const COLORS = ["var(--accent)", "var(--high)"] as const;

export default function TacticalRealPage() {
  const matches = matchList();
  const [mi, setMi] = React.useState(0);
  const [side, setSide] = React.useState<0 | 1>(0);
  const [sel, setSel] = React.useState<{ p: KeyPlayer; ti: 0 | 1 } | null>(null);
  const info = matchInfo(mi);
  const nets = [realPassNetwork(mi, 0), realPassNetwork(mi, 1)];
  const teams = [realTeam(mi, 0), realTeam(mi, 1)];
  const deep = realDeepProfile(mi, side);
  const summary = realScoutSummary(mi);
  const players = [realPlayers(mi, 0), realPlayers(mi, 1)];

  const selectMatch = (idx: number) => { setMi(idx); setSide(0); setSel(null); };

  return (
    <ConsoleShell
      active="/tactical-real"
      title="Gerçek Veri Taktik Analizi"
      sub="StatsBomb Open Data"
      source="claude"
      desc="Demo türetme değil — pas ağları, şut haritaları, savunma bloğu ve faz metrikleri gerçek maç event dosyalarından (her pas/şut/pozisyon) hesaplandı."
    >
      {/* Maç seçici + gerçek veri rozeti */}
      <div className="rc" style={{ margin: "0 0 16px", borderLeft: "3px solid var(--low)", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: 0.5, color: "#fff", background: "var(--low)", borderRadius: 4, padding: "2px 8px" }}>GERÇEK VERİ</span>
        <select
          value={mi}
          onChange={(e) => selectMatch(Number(e.target.value))}
          style={{ background: "var(--panel)", border: "1px solid var(--line)", color: "var(--ink)", fontSize: 13, fontWeight: 700, padding: "7px 10px", borderRadius: 8, fontFamily: "inherit", cursor: "pointer" }}
        >
          {matches.map((m) => <option key={m.idx} value={m.idx}>{m.match} — {m.comp}</option>)}
        </select>
        <span style={{ fontSize: 11.5, color: "var(--muted)", marginLeft: "auto" }}>kaynak: StatsBomb Open Data · match {info.matchId} · ham event → hesaplandı</span>
      </div>

      {/* Scout Özeti — gerçek sayıları okuyup hikâyeyi anlatır (içgörü) */}
      <div className="rc" style={{ margin: "0 0 16px", borderLeft: "3px solid var(--accent)" }}>
        <h3>Scout Özeti <span className="tiny">gerçek veriden otomatik · maçın taktik hikâyesi</span></h3>
        <div style={{ fontSize: 13, color: "var(--ink)", lineHeight: 1.65 }}>
          {summary.map((s, i) => <span key={i}>{s} </span>)}
        </div>
      </div>

      {/* Metrik karşılaştırma */}
      <div className="kpis" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        {teams.map((t, i) => (
          <div className="kpi" key={t.team}>
            <div className="kl">{t.team}</div>
            <div className="kn" style={{ color: COLORS[i] }}>%{t.metrics.possession}</div>
            <div className="kd">topa sahiplik · {t.formation}</div>
          </div>
        ))}
        <div className="kpi"><div className="kl">Şut</div><div className="kn" style={{ fontSize: 22 }}>{teams[0].metrics.shots}–{teams[1].metrics.shots}</div><div className="kd">{teams[0].team.slice(0, 3)}–{teams[1].team.slice(0, 3)}</div></div>
        <div className="kpi"><div className="kl">Üretilen Tehdit (xT)</div><div className="kn" style={{ fontSize: 22 }}>{teams[0].xt}–{teams[1].xt}</div><div className="kd">beklenen tehdit</div></div>
        <div className="kpi"><div className="kl">Toplam xG</div><div className="kn" style={{ fontSize: 22 }}>{teams[0].metrics.xg}–{teams[1].metrics.xg}</div><div className="kd">beklenen gol</div></div>
        <div className="kpi"><div className="kl">Gol</div><div className="kn" style={{ fontSize: 22 }}>{teams[0].metrics.goals}–{teams[1].metrics.goals}</div><div className="kd">gerçek skor</div></div>
      </div>

      {/* Saha üstü derin analiz — gerçek, takım geçişli */}
      <div className="st">
        <h2>Saha Üstü Derin Analiz</h2>
        <div className="seg">
          {teams.map((t, i) => (
            <button key={t.team} className={side === i ? "on" : ""} onClick={() => setSide(i as 0 | 1)}>{t.team}</button>
          ))}
        </div>
      </div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <DeepTacticalBody profile={deep} />
      </div>

      {/* Pas ağları — gerçek */}
      <div className="st"><h2>Pas Ağları</h2><span className="ep">gerçek tamamlanan paslardan</span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: 16 }}>
          {nets.map((n, i) => (
            <div key={n.name}>
              <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6, color: COLORS[i] }}>{n.name} <span style={{ color: "var(--dim)", fontWeight: 400, fontFamily: "JetBrains Mono", fontSize: 11 }}>{n.formation}</span></div>
              <PassNetworkPitch net={n} />
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>{n.insight}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Önemli oyuncular — bireysel teknik katkı (gerçek event'lerden) */}
      <div className="st"><h2>Önemli Oyuncular — Teknik</h2><span className="ep">bir oyuncuya tıkla → derin analiz</span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 20 }}>
          {teams.map((t, i) => (
            <div key={t.team}>
              <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 8, color: COLORS[i] }}>{t.team} <span style={{ color: "var(--dim)", fontWeight: 400, fontSize: 11 }}>{t.formation}</span></div>
              <KeyPlayersTable players={players[i]} color={COLORS[i]} onSelect={(p) => setSel({ p, ti: i as 0 | 1 })} selectedNum={sel?.ti === i ? sel.p.num : undefined} />
            </div>
          ))}
        </div>
        <div style={{ fontSize: 10.5, color: "var(--dim)", marginTop: 10, lineHeight: 1.5 }}>
          Etki = xT üretimi + ilerletme + kilit pas + şut tehdidi + top taşıma + savunma aksiyonu, takım içi göreceli (0-100). Tüm sayılar gerçek maç event'lerinden hesaplandı — demo değil.
        </div>
      </div>

      {/* Oyuncu derin analizi — seçilen oyuncunun ısı + pas haritası + radar */}
      {sel && (
        <>
          <div className="st"><h2>Oyuncu Derin Analizi</h2><span className="ep">{teams[sel.ti].team} · gerçek event'lerden ısı + pas + radar</span></div>
          <div className="rc" style={{ margin: "0 0 14px" }}>
            <PlayerDeepDive player={sel.p} color={COLORS[sel.ti]} />
          </div>
        </>
      )}

      {/* Isı haritaları — saha hâkimiyeti */}
      <div className="st"><h2>Saha Hâkimiyeti — Isı Haritası</h2><span className="ep">gerçek dokunuş yoğunluğu · koyu = yoğun</span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: 16 }}>
          {teams.map((t, i) => (
            <div key={t.team}>
              <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6, color: COLORS[i] }}>{t.team}</div>
              <HeatMap heat={t.heat} color={COLORS[i]} />
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, fontFamily: "JetBrains Mono" }}>üretilen tehdit (xT) {t.xt} · {t.metrics.passes} pas</div>
            </div>
          ))}
        </div>
      </div>

      {/* Pres bölgeleri — savunma aksiyon ısısı */}
      <div className="st"><h2>Pres Bölgeleri</h2><span className="ep">topu nerede kazanıyorlar · savunma aksiyon yoğunluğu</span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: 16 }}>
          {teams.map((t, i) => (
            <div key={t.team}>
              <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6, color: COLORS[i] }}>{t.team}</div>
              <HeatMap heat={t.defHeat} color={COLORS[i]} />
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, fontFamily: "JetBrains Mono" }}>koyu bölge = top kazanımı yoğun · sağ = yüksek pres</div>
            </div>
          ))}
        </div>
      </div>

      {/* Progresyon okları — top yukarı nasıl taşınıyor */}
      <div className="st"><h2>Progresyon — İlerleme Pasları</h2><span className="ep">en tehditli 14 pas · ok kalınlığı = xT katkısı</span></div>
      <div className="rc" style={{ margin: "0 0 14px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: 16 }}>
          {teams.map((t, i) => (
            <div key={t.team}>
              <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6, color: COLORS[i] }}>{t.team}</div>
              <ProgressionMap passes={t.progPasses} color={COLORS[i]} />
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, fontFamily: "JetBrains Mono" }}>topu kaleye taşıyan en değerli paslar (xT)</div>
            </div>
          ))}
        </div>
      </div>

      {/* Şut haritaları — gerçek */}
      <div className="st"><h2>Şut Haritaları</h2><span className="ep">gerçek şut konumları · daire = xG · dolu = gol</span></div>
      <div className="rc" style={{ margin: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: 16 }}>
          {teams.map((t, i) => (
            <div key={t.team}>
              <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6, color: COLORS[i] }}>{t.team}</div>
              <ShotMap shots={t.shots} color={COLORS[i]} />
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, fontFamily: "JetBrains Mono" }}>{t.metrics.shots} şut · xG {t.metrics.xg} · {t.metrics.goals} gol</div>
            </div>
          ))}
        </div>
      </div>

      {/* xG zaman çizgisi — momentum */}
      <div className="st"><h2>xG Zaman Çizgisi</h2><span className="ep">kümülatif xG · maç boyunca momentum · ● gol</span></div>
      <div className="rc" style={{ margin: "14px 0 0" }}>
        <XgTimeline teams={teams.map((t, i) => ({ name: t.team, color: COLORS[i], shots: t.shots }))} />
        <div style={{ display: "flex", justifyContent: "center", gap: 18, fontSize: 11.5, marginTop: 4 }}>
          {teams.map((t, i) => <span key={t.team} style={{ color: COLORS[i] }}>● {t.team} (xG {t.metrics.xg})</span>)}
        </div>
      </div>
    </ConsoleShell>
  );
}
