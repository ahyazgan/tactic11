"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { apiFetch, apiFetchResponse, ApiError, login, setTokens } from "@/lib/api";
import { useCurrentUser } from "@/lib/auth";
import { ConsoleShell } from "../_console/shell";
import { ReviewFollowUps } from "./follow-ups";
import styles from "./reports.module.css";

type Category = "attack" | "defence" | "transition" | "set_piece" | "player";
interface Finding {
  id: string; start: number; end: number; category: Category; title: string;
  observation: string; action: string; player: string; next_check: string;
}
interface Document {
  club: string; opponent: string; match_date: string | null; scope: "selected_segments" | "full_match";
  summary: string; strengths: string; training_focus: string[]; findings: Finding[];
}
interface Report {
  id: string; title: string; video_id: string; version: number; document: Document;
  reviewed_at: string | null; reviewed_by: string | null;
}
interface Video { id: string; filename: string; duration_seconds: number; size_bytes: number }
interface ExportJob { id: string; state: "queued" | "running" | "done" | "failed"; error?: string; report_version: number }
interface Draft { report: Report; dirty: boolean; finding: Finding | null; editingId: string | null }
const categories: Record<Category, string> = {
  attack: "Hücum", defence: "Savunma", transition: "Geçiş", set_piece: "Duran top", player: "Oyuncu gelişimi",
};
const freshFinding = (): Finding => ({
  id: crypto.randomUUID(), start: 0, end: 10, category: "attack", title: "", observation: "", action: "", player: "", next_check: "",
});
const clock = (seconds: number) => {
  const ticks = Math.round(seconds * 10);
  return `${Math.floor(ticks / 600).toString().padStart(2, "0")}:${Math.floor(ticks % 600 / 10).toString().padStart(2, "0")}${ticks % 10 ? `.${ticks % 10}` : ""}`;
};

function readDraft(key: string): Draft | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw || raw.length > 200_000) return null;
    const draft = JSON.parse(raw), report = draft.report, doc = report?.document;
    const strings = (value: Record<string, unknown>, keys: string[]) => keys.every(k => typeof value?.[k] === "string");
    const uuid = (value: unknown) => typeof value === "string" && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
    const validFinding = (value: Finding) => value && uuid(value.id) && Number.isFinite(value.start) && Number.isFinite(value.end)
      && Object.keys(categories).includes(value.category) && strings(value as unknown as Record<string, unknown>, ["title", "observation", "action", "player", "next_check"]);
    if (!uuid(report?.id) || !uuid(report?.video_id) || typeof report.title !== "string" || !Number.isInteger(report.version)
      || !strings(doc, ["club", "opponent", "summary", "strengths"]) || !["selected_segments", "full_match"].includes(doc.scope)
      || (doc.match_date !== null && typeof doc.match_date !== "string")
      || !Array.isArray(doc.training_focus) || !doc.training_focus.every((item: unknown) => typeof item === "string")
      || !Array.isArray(doc.findings) || !doc.findings.every(validFinding)
      || typeof draft.dirty !== "boolean" || (draft.finding !== null && !validFinding(draft.finding))
      || (draft.editingId !== null && !uuid(draft.editingId))) return null;
    return draft as Draft;
  } catch { return null; }
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) return "Oturum açılamadı veya süresi doldu. Giriş bilgilerinizi kontrol edip yeniden deneyin. Bu sekmedeki notlarınız korunur.";
  if (error instanceof ApiError && error.detail) return error.detail;
  const message = error instanceof Error ? error.message : "İşlem tamamlanamadı.";
  const json = message.indexOf("{");
  if (json >= 0) {
    try {
      const body = JSON.parse(message.slice(json));
      if (typeof body.detail === "string") return body.detail;
    } catch { /* Keep the original bounded API error. */ }
  }
  return message;
}

async function download(path: string, filename: string) {
  const response = await apiFetchResponse(path);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

async function downloadDelivery(reportId: string, jobId: string) {
  const result = await apiFetch<{ path: string }>(`/match-reports/${reportId}/exports/${jobId}/download-link`, { method: "POST" });
  const link = document.createElement("a");
  link.href = `/api${result.path}`;
  link.download = "";
  link.referrerPolicy = "no-referrer";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export default function MatchReportsPage() {
  const { user, isLoading: authLoading, mutate: refreshUser } = useCurrentUser();
  const canEdit = !!user && ["admin", "analyst", "coach"].includes(user.role);
  const { data: reports, error: reportsError, mutate: refreshReports } = useSWR<Report[]>(user ? ["/match-reports", user.tenant_id] : null, ([path]: [string, string]) => apiFetch(path));
  const { data: videos, error: videosError, mutate: refreshVideos } = useSWR<Video[]>(user ? ["/match-reports/videos", user.tenant_id] : null, ([path]: [string, string]) => apiFetch(path));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [dirty, setDirty] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [videoId, setVideoId] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [saveConflict, setSaveConflict] = useState(false);
  const [notice, setNotice] = useState("");
  const [playback, setPlayback] = useState("");
  const [playbackRevision, setPlaybackRevision] = useState(0);
  const [finding, setFinding] = useState<Finding | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [draftOwner, setDraftOwner] = useState<string | null>(null);
  const account = user ? `${user.tenant_id}:${user.email}` : null;
  const activeVideo = videos?.find(v => v.id === report?.video_id);
  const { data: exports, mutate: refreshExports } = useSWR<ExportJob[]>(report ? `/match-reports/${report.id}/exports` : null,
    apiFetch, { refreshInterval: (jobs) => jobs?.some(j => j.state === "queued" || j.state === "running") ? 2000 : 0 });
  const activeExport = exports?.find(j => j.state === "queued" || j.state === "running");

  useEffect(() => {
    // Expiry hides the workspace, but retains this tab's draft for the same
    // account. A different account must never inherit those observations.
    if (!account || draftOwner === account) return;
    const draft = readDraft(`manager2_review_draft:${account}`);
    setReport(draft?.report ?? null); setDirty(draft?.dirty ?? false); setFinding(draft?.finding ?? null);
    setEditingId(draft?.editingId ?? null); setConfirmed(false); setVideoId(""); setDraftOwner(account); setSaveConflict(false);
    if (draft) setNotice("Bu sekmedeki taslak geri yüklendi. Sunucudaki kayıt değiştiyse kaydetme sırasında haber verilir.");
  }, [account, draftOwner]);

  useEffect(() => {
    if (!account || draftOwner !== account) return;
    const key = `manager2_review_draft:${account}`;
    try {
      if (report && (dirty || finding)) sessionStorage.setItem(key, JSON.stringify({ report, dirty, finding, editingId }));
      else sessionStorage.removeItem(key);
    } catch { /* Private/limited browser storage: in-memory draft and explicit save still work. */ }
  }, [account, draftOwner, report, dirty, finding, editingId]);

  useEffect(() => {
    if (!dirty && !finding) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, finding]);

  useEffect(() => {
    let cancelled = false;
    setPlayback(""); setCurrentTime(0);
    if (report) {
      apiFetch<{ path: string }>(`/match-reports/videos/${report.video_id}/playback`, { method: "POST" })
        .then(result => { if (!cancelled) setPlayback(`/api${result.path}`); })
        .catch(e => { if (!cancelled) setError(errorMessage(e)); });
    }
    return () => { cancelled = true; };
  }, [report?.video_id, playbackRevision]); // eslint-disable-line react-hooks/exhaustive-deps

  const operation = async (name: string, action: () => Promise<void>) => {
    setBusy(name); setError(""); setNotice("");
    try { await action(); } catch (e) {
      setError(errorMessage(e));
      if (name === "Kaydediliyor" && e instanceof ApiError && e.status === 409) setSaveConflict(true);
    } finally { setBusy(""); }
  };
  const openReport = (next: Report) => {
    if (dirty || finding) { setError("Başka bir rapora geçmeden önce pozisyonu rapora ekleyip değişiklikleri kaydedin."); return; }
    setReport(structuredClone(next)); setConfirmed(false); setFinding(null); setEditingId(null); setError(""); setNotice("");
    setSaveConflict(false);
    setPlaybackRevision(value => value + 1);
  };
  const changeDocument = (patch: Partial<Document>) => {
    if (!report) return;
    setReport({ ...report, document: { ...report.document, ...patch } }); setDirty(true); setConfirmed(false);
  };
  const changeFinding = (patch: Partial<Finding>) => finding && setFinding({ ...finding, ...patch });
  const seek = (time: number) => { if (videoRef.current) videoRef.current.currentTime = time; };

  const addFinding = () => {
    if (!report || !finding) return;
    if (!finding.title.trim() || !finding.observation.trim() || !finding.action.trim()) {
      setError("Pozisyon başlığı, gözlem ve çalışma önerisini doldurun."); return;
    }
    if (!Number.isFinite(finding.start) || !Number.isFinite(finding.end) || finding.start < 0
      || finding.end - finding.start < 0.5 || finding.end - finding.start > 120
      || (activeVideo && finding.end > activeVideo.duration_seconds)) {
      setError("Video içinde 0,5–120 saniyelik geçerli bir aralık seçin."); return;
    }
    const next = editingId ? report.document.findings.map(f => f.id === editingId ? finding : f)
      : [...report.document.findings, finding];
    if (next.length > 12) { setError("Bir rapora en fazla 12 pozisyon ekleyebilirsiniz."); return; }
    changeDocument({ findings: next }); setFinding(null); setEditingId(null); setError("");
  };

  return <ConsoleShell active="/match-reports" title="Klipli Maç Raporu" sub="İncele · doğrula · teslim et"
    desc="Maç görüntüsünü, gözlemlerinizi ve antrenman önerilerini aynı raporda birleştirin.">
    <div className={styles.workspace} data-review-workspace>
      {!user ? <section className={styles.card}>
        <h2>{authLoading ? "Oturum kontrol ediliyor…" : "Kulübünüzün raporlarına giriş yapın"}</h2>
        <p>Bu alan gerçek videolar ve kaydedilmiş raporlarla çalışır.</p>
        {(dirty || finding) && <p>Kaydetmediğiniz notlar bu sekmede korunuyor. Aynı hesapla giriş yaparak devam edin; sekmeyi kapatmayın.</p>}
        {!authLoading && <form className={styles.stack} onSubmit={e => { e.preventDefault(); void operation("Giriş yapılıyor", async () => {
          const tokens = await login(email, password, tenantSlug || undefined);
          setTokens(tokens.access_token, tokens.refresh_token); setPassword(""); await refreshUser();
        }); }}>
          <label>E-posta<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label>
          <label>Şifre<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
          <label>Kulüp kodu (varsa)<input autoComplete="organization" value={tenantSlug} onChange={e => setTenantSlug(e.target.value)} /></label>
          <button disabled={!!busy}>Giriş yap</button>
          {error && <p role="alert" className={styles.error}>{error}</p>}
        </form>}
      </section> : <>
        {(error || reportsError || videosError) && <div role="alert" className={styles.error}>{error || errorMessage(reportsError || videosError)}</div>}
        {saveConflict && report && draftOwner === account && canEdit && <section className={styles.card}>
          <p>Başka oturumdaki kaydın üzerine yazılmadı. Buradaki notları ayrı bir taslak olarak kaydedebilirsiniz.</p>
          <button disabled={!!busy || !!finding} onClick={() => void operation("Taslak kopyalanıyor", async () => {
            const copy = await apiFetch<Report>("/match-reports", { method: "POST", body: JSON.stringify({
              video_id: report.video_id, title: `${report.title.slice(0, 170)} (kopya)`, document: report.document,
            }) });
            setReport(copy); setDirty(false); setConfirmed(false); setSaveConflict(false); await refreshReports();
            setNotice("Notlarınız ayrı bir taslağa kaydedildi. Teslim için bu raporu inceleyip onaylayın.");
          })}>Notlarımı ayrı rapora kaydet</button>
        </section>}
        {notice && <div role="status" className={styles.notice}>{notice}</div>}
        {reports && <ReviewFollowUps key={account} reports={reports} busy={!!busy} onOpen={id => {
          const source = reports.find(item => item.id === id);
          if (source) openReport(source);
        }} />}
        <div className={styles.columns}>
          <aside className={styles.card}>
            <h2>Raporlar</h2>
            {reports?.length === 0 && <p>Henüz rapor yok. Bir MP4 video yükleyerek başlayın.</p>}
            <div className={styles.reportList}>{reports?.map(r => <button key={r.id} onClick={() => openReport(r)}
              aria-pressed={report?.id === r.id} disabled={!!busy} className={styles.reportChoice}>
              <strong>{r.title}</strong><small>{r.reviewed_at ? "İncelendi" : "Taslak"} · v{r.version}</small>
            </button>)}</div>
            {canEdit && <form onSubmit={e => { e.preventDefault(); if (dirty || finding) { setError("Önce pozisyonu rapora ekleyip açık raporu kaydedin."); return; }
              void operation("Rapor oluşturuluyor", async () => {
                const created = await apiFetch<Report>("/match-reports", { method: "POST", body: JSON.stringify({ video_id: videoId, title }) });
                setReport(created); setFinding(null); setConfirmed(false); setTitle(""); await refreshReports();
              }); }} className={styles.stack}>
              <h3>Yeni rapor</h3>
              <label>MP4 video yükle<input type="file" accept="video/mp4,.mp4" disabled={!!busy}
                onChange={e => { const file = e.target.files?.[0]; if (!file) return;
                  void operation("Video yükleniyor ve kontrol ediliyor", async () => {
                    const form = new FormData(); form.append("file", file);
                    const uploaded = await apiFetch<Video>("/match-reports/videos", { method: "POST", body: form });
                    await refreshVideos(); setVideoId(uploaded.id); setNotice("Video kaydedildi. Rapor başlığı girerek devam edin.");
                  }); e.target.value = "";
                }} /></label>
              <small>H.264 (8 bit) MP4 · En fazla 3 saat. Varsayılan yükleme sınırı 2 GB.</small>
              <label>Kaynak video<select required value={videoId} onChange={e => setVideoId(e.target.value)}>
                <option value="">Video seçin</option>{videos?.map(v => <option key={v.id} value={v.id}>{v.filename} · {clock(v.duration_seconds)}</option>)}
              </select></label>
              <label>Rapor başlığı<input required maxLength={180} value={title} onChange={e => setTitle(e.target.value)} placeholder="U17 · Haftalık maç değerlendirmesi" /></label>
              <button type="submit" disabled={!!busy || !videoId}>Rapor oluştur</button>
            </form>}
          </aside>
          {!report || draftOwner !== account ? <section className={styles.card}><h2>Görüntüden uygulanabilir öneriye</h2>
            <p>Bir rapor seçin veya kulübünüzün videosuyla yeni bir rapor oluşturun.</p>
            <ol><li>Videodan kritik pozisyonları seçin.</li><li>Gözlemi ve çalışma önerisini yazın.</li><li>İnceleyip onaylayın; PDF ve klipleri indirin.</li></ol>
          </section> : <div className={styles.stack}>
            <section className={styles.card}>
              <div className={styles.toolbar}><div><h2>{report.title}</h2><small>
                {dirty ? "Kaydedilmemiş değişiklikler" : report.reviewed_at ? "İncelendi · teslim edilebilir" : "Taslak · inceleme bekliyor"} · v{report.version}
              </small></div>{canEdit && <button disabled={!!busy || !dirty || !!finding} onClick={() => void operation("Kaydediliyor", async () => {
                const saved = await apiFetch<Report>(`/match-reports/${report.id}`, { method: "PUT", body: JSON.stringify({ version: report.version, title: report.title, document: report.document }) });
                setReport(saved); setDirty(false); setConfirmed(false); setSaveConflict(false); await refreshReports(); setNotice("Rapor kaydedildi. Teslim için son sürümü inceleyip onaylayın.");
              })}>Değişiklikleri kaydet</button>}</div>
              <fieldset disabled={!canEdit || !!busy} className={styles.stack}>
                <label>Başlık<input value={report.title} maxLength={180} onChange={e => { setReport({ ...report, title: e.target.value }); setDirty(true); setConfirmed(false); }} /></label>
                <div className={styles.row}><label>Kulüp<input maxLength={120} value={report.document.club} onChange={e => changeDocument({ club: e.target.value })} /></label>
                  <label>Rakip<input maxLength={120} value={report.document.opponent} onChange={e => changeDocument({ opponent: e.target.value })} /></label>
                  <label>Maç tarihi<input type="date" value={report.document.match_date ?? ""} onChange={e => changeDocument({ match_date: e.target.value || null })} /></label></div>
                <label>İnceleme kapsamı<select value={report.document.scope} onChange={e => changeDocument({ scope: e.target.value as Document["scope"] })}>
                  <option value="selected_segments">Seçilmiş bölümleri inceledim</option><option value="full_match">Maçın tamamını inceledim</option>
                </select></label>
              </fieldset>
            </section>
            <section className={styles.card}>
              <h2>Video ve pozisyonlar</h2>
              {playback ? <video ref={videoRef} controls preload="metadata" src={playback} className={styles.video}
                onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime ?? 0)}
                onError={() => setError("Video oynatılamadı. Kaynak MP4 dosyasını veya oturumunuzu kontrol edin.")} /> : <p>Video hazırlanıyor…</p>}
              <div className={styles.toolbar}><small>{activeVideo?.filename} · Kaynak zamanı {clock(currentTime)}</small>
                <button className={styles.secondary} disabled={!!busy} onClick={() => { setError(""); setPlaybackRevision(value => value + 1); }}>Videoyu yeniden bağla</button>
                {canEdit && !finding && <button disabled={!!busy || report.document.findings.length >= 12} onClick={() => {
                  const start = Math.floor(currentTime); setFinding({ ...freshFinding(), start, end: Math.min(start + 10, activeVideo?.duration_seconds ?? start + 10) }); setEditingId(null);
                }}>Pozisyon ekle</button>}</div>
              <p className={styles.muted}>Zamanlar videonun başlangıcına göredir. Oyuncu adı ve yorumları görüntüden doğrulayın.</p>
              {finding && <fieldset className={styles.findingForm} disabled={!!busy || !canEdit}>
                <legend>{editingId ? "Pozisyonu düzenle" : "Yeni pozisyon"}</legend>
                <div className={styles.row}>
                  <div className={styles.stack}><label>Başlangıç (saniye)<input type="number" min={0} step="0.1" value={finding.start} onChange={e => changeFinding({ start: Number(e.target.value) })} /></label><button type="button" onClick={() => changeFinding({ start: Math.round(currentTime * 10) / 10 })}>Başlangıcı buradan al</button></div>
                  <div className={styles.stack}><label>Bitiş (saniye)<input type="number" min={0.5} step="0.1" value={finding.end} onChange={e => changeFinding({ end: Number(e.target.value) })} /></label><button type="button" onClick={() => changeFinding({ end: Math.round(currentTime * 10) / 10 })}>Bitişi buradan al</button></div>
                </div>
                <label>Pozisyon başlığı<input maxLength={140} value={finding.title} onChange={e => changeFinding({ title: e.target.value })} /></label>
                <div className={styles.row}><label>Konu<select value={finding.category} onChange={e => changeFinding({ category: e.target.value as Category })}>{Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
                  <label>Oyuncu (isteğe bağlı)<input maxLength={120} value={finding.player} onChange={e => changeFinding({ player: e.target.value })} /></label></div>
                <label>Gözlem<textarea aria-label="Gözlem" maxLength={1500} value={finding.observation} onChange={e => changeFinding({ observation: e.target.value })} placeholder="Görüntüde ne oluyor?" /></label>
                <label>Çalışma önerisi<textarea aria-label="Çalışma önerisi" maxLength={1000} value={finding.action} onChange={e => changeFinding({ action: e.target.value })} /></label>
                <label>Sonraki maçta neye bakacağız?<textarea aria-label="Sonraki maçta neye bakacağız?" maxLength={700} value={finding.next_check} onChange={e => changeFinding({ next_check: e.target.value })} /></label>
                <div className={styles.toolbar}><button onClick={addFinding}>{editingId ? "Pozisyonu güncelle" : "Rapora ekle"}</button>
                  <button className={styles.secondary} onClick={() => { setFinding(null); setEditingId(null); }}>Vazgeç</button></div>
              </fieldset>}
              {report.document.findings.map((f, i) => <article key={f.id} className={styles.finding}>
                <div className={styles.toolbar}><h3>{i + 1}. {f.title}</h3><button className={styles.secondary} onClick={() => seek(f.start)}>{clock(f.start)}–{clock(f.end)} · Görüntüye git</button></div>
                <small>{categories[f.category]}{f.player ? ` · ${f.player}` : ""}</small><p>{f.observation}</p><p><strong>Çalışma:</strong> {f.action}</p>
                {f.next_check && <p><strong>Sonraki kontrol:</strong> {f.next_check}</p>}
                {canEdit && <div className={styles.toolbar}><button disabled={!!busy || !!finding} className={styles.secondary} onClick={() => { setFinding({ ...f }); setEditingId(f.id); seek(f.start); }}>Düzenle</button>
                  <button disabled={!!busy || !!finding} className={styles.secondary} onClick={() => changeDocument({ findings: report.document.findings.filter(item => item.id !== f.id) })}>Pozisyonu kaldır</button></div>}
              </article>)}
            </section>
            <section className={styles.card}><h2>Koç özeti</h2><fieldset disabled={!canEdit || !!busy} className={styles.stack}>
              <label>Maç değerlendirmesi<textarea aria-label="Maç değerlendirmesi" rows={4} maxLength={3000} value={report.document.summary} onChange={e => changeDocument({ summary: e.target.value })} /></label>
              <label>İyi yapılanlar<textarea aria-label="İyi yapılanlar" maxLength={1500} value={report.document.strengths} onChange={e => changeDocument({ strengths: e.target.value })} /></label>
              {[0, 1, 2].map(i => <label key={i}>Antrenman odağı {i + 1}<input maxLength={700} value={report.document.training_focus[i] ?? ""} onChange={e => {
                const focus = [...report.document.training_focus]; while (focus.length < 3) focus.push(""); focus[i] = e.target.value; changeDocument({ training_focus: focus });
              }} /></label>)}
            </fieldset></section>
            <section className={styles.card}><h2>İnceleme ve teslim</h2>
              {canEdit && !report.reviewed_at && <><label className={styles.checkbox}><input type="checkbox" checked={confirmed} disabled={dirty || !!finding || !!busy} onChange={e => setConfirmed(e.target.checked)} />Videodaki pozisyonları, oyuncu adlarını ve yorumları kontrol ettim.</label>
                <button disabled={dirty || !!finding || !!busy || !confirmed || !!report.reviewed_at} onClick={() => void operation("Onay kaydediliyor", async () => {
                  const approved = await apiFetch<Report>(`/match-reports/${report.id}/approve`, { method: "POST", body: JSON.stringify({ version: report.version }) });
                  setReport(approved); await refreshReports(); setNotice("İnceleme kaydedildi. Teslim paketini hazırlayabilirsiniz.");
                })}>İncelemeyi onayla</button></>}
              <p className={styles.muted}>{dirty ? "Onay ve teslim için önce değişiklikleri kaydedin." : report.reviewed_at ? `Son inceleme: ${new Date(report.reviewed_at).toLocaleString("tr-TR")}` : "PDF ve klip paketi, inceleme onayından sonra açılır."}</p>
              <div className={styles.toolbar}><button disabled={dirty || !!finding || !!busy || !report.reviewed_at} onClick={() => void operation("PDF hazırlanıyor", () => download(`/match-reports/${report.id}/pdf`, "mac-raporu.pdf"))}>PDF indir</button>
                {canEdit && <button disabled={dirty || !!finding || !!busy || !report.reviewed_at || !!activeExport} onClick={() => void operation("Paket sıraya alınıyor", async () => {
                  await apiFetch(`/match-reports/${report.id}/exports`, { method: "POST", body: JSON.stringify({ version: report.version }) }); await refreshExports();
                })}>Klipli teslim paketi hazırla</button>}</div>
              <p className={styles.muted}>Paket; PDF, oynatılabilir MP4 klipler ve çevrimdışı rapor sayfası içerir. ZIP dosyasını çıkarıp index.html dosyasını açın.</p>
              {exports?.map(job => <div key={job.id} className={styles.export}><span>Rapor v{job.report_version} · {{ queued: "Sırada", running: "Klipler hazırlanıyor", done: "Paket hazır", failed: "Hazırlanamadı" }[job.state]}</span>
                {job.error && <p role="alert">{job.error}</p>}{job.state === "done" && <button disabled={!!busy} onClick={() => void operation("İndirme başlatılıyor", () => downloadDelivery(report.id, job.id))}>ZIP indir</button>}
              </div>)}
            </section>
          </div>}
        </div>
        {busy && <div role="status" className={styles.progress}>{busy}…</div>}
      </>}
    </div>
  </ConsoleShell>;
}
