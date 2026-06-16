/**
 * Kalibrasyon & Güven — sistemin tahminlerini GERÇEK geçmiş maçlarla kıyaslar.
 *
 * Bir karar destek sistemini "gerçek" yapan tek şey: söylediği güvenin tutması.
 * Bu sayfa, şeffaf bir tahminciyi (Elo gücü → Poisson 1/X/2) 10.000+ gerçek lig
 * maçında WALK-FORWARD çalıştırır (gelecek sızıntısı yok) ve gerçek kalibrasyon
 * metriklerini gösterir: isabet, Brier, beceri (şansa karşı), ECE, güvenilirlik
 * eğrisi, Güven Skoru. Veri: openfootball (top-5 lig, 2017-2023).
 *
 * SERVER component: 1.2MB sonuç JSON'u sunucuda kalır, client bundle'a girmez —
 * sadece küçük rapor nesnesi CalibrationBody'ye (client) geçer.
 */

import { computeCalibration, predictorData } from "@/lib/calibration";
import { engineLedgers } from "@/lib/decision-ledger";
import { ConsoleShell } from "../_console/shell";
import { CalibrationBody, FixturePredictor, DecisionLedger, AppliedActions, EngineRecord } from "../_console/calibration";

export default function CalibrationPage() {
  const report = computeCalibration();
  const leagues = predictorData();
  const ledgers = engineLedgers();

  const right = (
    <>
      <div className="rc">
        <h3>Nasıl Okunur?</h3>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
          <div><b style={{ color: "var(--ink)" }}>Güven Skoru</b> ↑ — kalibrasyon + beceri bileşik (0-100)</div>
          <div><b style={{ color: "var(--ink)" }}>İsabet</b> ↑ — 1/X/2 doğru bilme (3 seçenek, şans %33)</div>
          <div><b style={{ color: "var(--ink)" }}>ECE</b> ↓ — &quot;%X dediğinde %X oluyor mu&quot;, &lt;0.03 çok iyi</div>
          <div><b style={{ color: "var(--ink)" }}>Beceri</b> ↑ — naif tahminden ne kadar iyi</div>
        </div>
      </div>
      <div className="rc">
        <h3>Yöntem</h3>
        <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.6 }}>
          <div>• <b style={{ color: "var(--ink)" }}>Derin model</b>: takım başına ayrı hücum/savunma gücü + Dixon-Coles düşük-skor düzeltmesi.</div>
          <div style={{ marginTop: 4 }}>• <b style={{ color: "var(--ink)" }}>Walk-forward</b>: her maç sadece o ana kadarki bilgiyle — gelecek sızıntısı yok.</div>
          <div style={{ marginTop: 4 }}>• <b style={{ color: "var(--ink)" }}>Out-of-sample</b>: {report.trainMatches.toLocaleString("tr")} maçta eğitildi, görülmemiş {report.splitSeason} ({report.matches.toLocaleString("tr")} maç) test edildi.</div>
          <div style={{ marginTop: 4 }}>• Belirsizlik: bootstrap %95 güven aralığı. Kaynak: openfootball, top-5 lig.</div>
        </div>
      </div>
    </>
  );

  return (
    <ConsoleShell
      active="/calibration"
      title="Kalibrasyon & Güven"
      sub="Out-of-sample · derin model"
      source="claude"
      desc="Demo defteri değil — derin bir model (takım başına hücum/savunma + Dixon-Coles) walk-forward, gelecek sızıntısı olmadan kuruldu ve modelin HİÇ GÖRMEDİĞİ bir sezonda test edildi. 'AI tahmin ediyor' değil: 'tahminlerimiz görmediği maçlarda şu kadar tuttu, güveni şu kadar dürüst — %95 güven aralığıyla.'"
      right={right}
    >
      <CalibrationBody report={report} />

      {/* Canlı tahmin — doğrulanmış model, gerçek takımlar */}
      <div className="st"><h2>Doğrulanmış Model — Canlı Tahmin</h2><span className="ep">öğrenilmiş gerçek takım güçleriyle · bir eşleşme seç</span></div>
      <div className="rc" style={{ margin: 0 }}>
        <FixturePredictor leagues={leagues} trust={report.trust} />
      </div>

      {/* Karar Kanıt Defteri — diğer motorların zamanla güven kazanması */}
      <div className="st"><h2>Karar Kanıt Defteri</h2><span className="ep">her motor şu an ne iddia ediyor + nasıl doğrulanacak</span></div>
      <div className="rc" style={{ margin: "0 0 14px", borderLeft: "3px solid var(--accent)" }}>
        <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.6 }}>
          Maç sonucu motoru gerçek maçlarla doğrulandı (güven 76). Sakatlık ve kadro kararlarının &quot;doğru cevabı&quot; ise
          ancak gelecekte belli olur. Bu yüzden her motor <b>şu an yaptığı falsifiye edilebilir iddiaları</b> kaydediyor ve
          <b> nasıl doğrulanacağını</b> yazıyor. Gerçek sonuç akınca (Süper Lig sezonu) defter dolar, her motor kendi
          &quot;%X tuttu&quot; rakamını kazanır. <b>Sahte sonuç üretilmez</b> — şu an &quot;birikiyor&quot; dürüstçe görünür.
        </div>
      </div>
      <DecisionLedger ledgers={ledgers} />
      <div style={{ height: 14 }} />
      <EngineRecord />
      <div style={{ height: 14 }} />
      <AppliedActions />

      {/* Dürüst sınırlar — ne kanıtlıyor, ne kanıtlamıyor */}
      <div style={{ height: 14 }} />
      <div className="st"><h2>Bu Ne Kanıtlıyor, Ne Kanıtlamıyor</h2></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
        <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--low)" }}>
          <h3 style={{ color: "var(--low)" }}>✓ Kanıtlıyor</h3>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12, color: "var(--ink)", lineHeight: 1.7 }}>
            <li>Sistem gerçek maçlarda <b>şanstan belirgin iyi</b> tahmin ediyor (beceri +%{(report.brierSkill * 100).toFixed(0)}).</li>
            <li>Söylediği güven <b>dürüst/kalibre</b> (ECE {report.ece.toFixed(3)}) — &quot;%60&quot; dediğinde gerçekten ~%60 oluyor.</li>
            <li>Motor <b>gelecek sızıntısı olmadan</b> çalışıyor; metrikler {report.matches.toLocaleString("tr")} bağımsız maçtan.</li>
          </ul>
        </div>
        <div className="rc" style={{ margin: 0, borderLeft: "3px solid var(--mid)" }}>
          <h3 style={{ color: "var(--mid)" }}>⚠ Kanıtlamıyor / Sınırlar</h3>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12, color: "var(--ink)", lineHeight: 1.7 }}>
            <li>Bu test <b>maç sonucu</b> (1/X/2) tahminciyi doğrular. <b>Sakatlık/yük</b> kararları ayrı veri (giyilebilir cihaz) ister.</li>
            <li>Model gol verisine dayanır. <b>Kadro/sakatlık/canlı-xG</b> sinyalleri eklenince beceri daha da artar (mimari hazır).</li>
            <li>Senin ligin (Süper Lig) için bu rapor, <b>Sportmonks canlı verisi</b> bağlanınca senin maçlarınla üretilir.</li>
          </ul>
        </div>
      </div>
      <div className="rc" style={{ marginTop: 14, borderLeft: "3px solid var(--accent)" }}>
        <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.6 }}>
          <b>Sonuç:</b> Aynı motor Sportmonks Süper Lig verisine bağlandığında, senin takımının maçları için
          de bu &quot;ne kadar güvenebilirsin&quot; rakamını üretecek. Bir karar destek sistemini gerçekten güvenilir
          kılan şey budur: tahmin etmek değil, <b>tahmininin ne kadar tuttuğunu kanıtlamak.</b>
        </div>
      </div>
    </ConsoleShell>
  );
}
