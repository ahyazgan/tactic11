"use client";

import { useState } from "react";
import styles from "./reports.module.css";

interface FollowUpReport {
  id: string;
  title: string;
  version: number;
  reviewed_at: string | null;
  document: { findings: { id: string; title: string; player: string; action: string; next_check: string }[] };
}

export function ReviewFollowUps({ reports, onOpen, busy }: {
  reports: FollowUpReport[];
  onOpen: (reportId: string) => void;
  busy: boolean;
}) {
  const [query, setQuery] = useState("");
  const [visible, setVisible] = useState(8);
  const notes = reports.filter(report => !!report.reviewed_at).flatMap(report =>
    report.document.findings.filter(finding => finding.next_check.trim()).map(finding => ({ report, finding })));
  const needle = query.trim().toLocaleLowerCase("tr-TR");
  const matching = notes.filter(({ report, finding }) =>
    [report.title, finding.title, finding.player, finding.next_check].join(" ").toLocaleLowerCase("tr-TR").includes(needle));

  return <details className={`${styles.card} ${styles.followUps}`}>
    <summary>Önceki raporlardan gelişim takibi · {notes.length} not</summary>
    <p>En güncel 100 raporda kaydedilen onaylı takip notları. Bir sonraki maçta gözlemleyeceğiniz davranışı ve kaynak raporunu buradan bulun.</p>
    {notes.length === 0 ? <p>Henüz onaylı takip notu yok. Pozisyondaki “Sonraki maçta neye bakacağız?” alanını doldurup raporu onaylayın.</p> : <>
      <label>Oyuncu veya takip konusu ara<input type="search" value={query} maxLength={200}
        placeholder="Oyuncu adı, alan paylaşımı, geçiş…"
        onChange={event => { setQuery(event.target.value); setVisible(8); }} /></label>
      <p className={styles.muted}>{matching.length} takip notu bulundu. Aynı adlı oyuncuların hangi rapora ait olduğunu kontrol edin.</p>
      <div className={styles.followUpList}>{matching.slice(0, visible).map(({ report, finding }) =>
        <article className={styles.followUpItem} key={`${report.id}:${finding.id}`} aria-label={`${finding.player || "Takım"}: ${finding.title}`}>
          <h3>{finding.player || "Takım gözlemi"} · {finding.title}</h3>
          <p><strong>Sonraki kontrol:</strong> {finding.next_check}</p>
          <p><strong>Önceki çalışma:</strong> {finding.action}</p>
          <small>{report.title} · v{report.version} · {new Date(report.reviewed_at!).toLocaleDateString("tr-TR")}</small>
          <button type="button" className={styles.secondary} disabled={busy} onClick={() => onOpen(report.id)}>Kaynak raporu aç</button>
        </article>)}</div>
      {matching.length > visible && <button type="button" className={styles.secondary}
        onClick={() => setVisible(value => value + 8)}>Diğer takip notlarını göster</button>}
    </>}
  </details>;
}
