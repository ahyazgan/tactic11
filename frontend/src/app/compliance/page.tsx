"use client";

/**
 * Erişim Denetimi (KVKK) — özel nitelikli veriye kim/ne zaman/neye erişti +
 * şüpheli toplu-erişim anomalileri. ConsoleShell çatısında.
 * Backend:
 *   GET /admin/compliance/access-log?subject_id=&days=
 *   GET /admin/compliance/audit?days=
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { ConsoleShell } from "../_console/shell";
import { LoadingState, ErrorState } from "@/components/ui";

interface LogEntry {
  user_id: string | null;
  subject_type: string;
  subject_id: number;
  data_category: string;
  sensitivity: string;
  action: string;
  endpoint: string;
  at: string | null;
}
interface LogResp {
  total: number;
  entries: LogEntry[];
}
interface Anomaly {
  user_id: string | null;
  distinct_subjects?: number;
  data_category?: string;
}
interface AuditResp {
  anomalies: Anomaly[];
}

function sensColor(s: string): string {
  const v = s.toLowerCase();
  if (v.includes("özel") || v.includes("special")) return "var(--crit)";
  if (v.includes("kişisel") || v.includes("personal")) return "var(--high)";
  return "var(--muted)";
}

const DAYS = [7, 30, 90];

// ── Demo örnek verisi ─────────────────────────────────────────────────────────
// Backend'te erişim kaydı yokken sayfa boş kalmasın: KVKK panosunun nasıl
// göründüğünü anlatan gerçekçi kayıtlar (hekim sağlık notuna, analist fiziksel
// teste erişiyor). Canlı kayıt varsa daima o gösterilir.
const DEMO_LOG: LogEntry[] = [
  { user_id: "dr.kaya", subject_type: "player", subject_id: 7, data_category: "saglik_notu", sensitivity: "özel nitelikli", action: "read", endpoint: "/players/7/medical", at: "2026-06-08T09:14:02" },
  { user_id: "dr.kaya", subject_type: "player", subject_id: 11, data_category: "sakatlik_gecmisi", sensitivity: "özel nitelikli", action: "read", endpoint: "/players/11/medical", at: "2026-06-08T09:11:40" },
  { user_id: "analist.demir", subject_type: "player", subject_id: 7, data_category: "fiziksel_test", sensitivity: "kişisel", action: "read", endpoint: "/physical-tests/7", at: "2026-06-07T17:32:18" },
  { user_id: "analist.demir", subject_type: "player", subject_id: 14, data_category: "fiziksel_test", sensitivity: "kişisel", action: "read", endpoint: "/physical-tests/14", at: "2026-06-07T17:30:05" },
  { user_id: "kondisyoner.arslan", subject_type: "player", subject_id: 3, data_category: "gps_yuku", sensitivity: "kişisel", action: "write", endpoint: "/physical-tests/load-entries", at: "2026-06-07T11:02:51" },
  { user_id: "dr.kaya", subject_type: "player", subject_id: 19, data_category: "saglik_notu", sensitivity: "özel nitelikli", action: "write", endpoint: "/players/19/medical", at: "2026-06-06T15:48:33" },
  { user_id: "analist.demir", subject_type: "player", subject_id: 21, data_category: "performans_raporu", sensitivity: "kişisel", action: "read", endpoint: "/players/21/season-stats", at: "2026-06-06T10:21:07" },
  { user_id: "td.ozkan", subject_type: "player", subject_id: 7, data_category: "performans_raporu", sensitivity: "kişisel", action: "read", endpoint: "/players/7/season-stats", at: "2026-06-05T19:05:44" },
];
const DEMO_ANOMALIES: Anomaly[] = [
  { user_id: "analist.demir", distinct_subjects: 14, data_category: "fiziksel_test" },
];

const inputStyle: React.CSSProperties = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  color: "var(--ink)",
  fontSize: "12.5px",
  padding: "6px 10px",
  borderRadius: "7px",
  width: "200px",
  fontFamily: "inherit",
};

export default function ComplianceConsolePage() {
  const [subject, setSubject] = React.useState("");
  const [subjectQ, setSubjectQ] = React.useState("");
  const [days, setDays] = React.useState(30);

  const log = useSWR<LogResp>(
    `/admin/compliance/access-log?days=${days}${subjectQ ? `&subject_id=${subjectQ}` : ""}`,
    apiFetch,
    { shouldRetryOnError: false },
  );
  const audit = useSWR<AuditResp>(`/admin/compliance/audit?days=${days}`, apiFetch, {
    shouldRetryOnError: false,
  });
  // Demo modunda canlı kayıt yoksa örnek pano (boş tablo yerine). Özne filtresi
  // örnek veride de çalışır.
  const useDemo = DEMO_MODE && (!log.data || log.data.total === 0);
  const demoEntries = subjectQ
    ? DEMO_LOG.filter((e) => String(e.subject_id) === subjectQ)
    : DEMO_LOG;
  const entries = useDemo ? demoEntries : (log.data?.entries ?? []);
  const anomalies = useDemo ? DEMO_ANOMALIES : (audit.data?.anomalies ?? []);
  const totalCount = useDemo ? demoEntries.length : (log.data?.total ?? 0);

  const right = (
    <div className="rc">
      <h3>Şüpheli Toplu Erişim <span className="tiny">{anomalies.length}</span></h3>
      {anomalies.length === 0 && <div style={{ fontSize: "12px", color: "var(--dim)" }}>Anomali tespit edilmedi.</div>}
      {anomalies.map((a, i) => (
        <div className="alrt" key={i}>
          <span className="ai" style={{ background: "var(--crit)" }} />
          <div className="am"><b style={{ fontFamily: "JetBrains Mono" }}>{a.user_id ?? "(atıfsız)"}</b>
            <span className="tm">
              {a.distinct_subjects !== undefined ? `${a.distinct_subjects} özneye erişim` : ""}
              {a.data_category ? ` · ${a.data_category}` : ""}
            </span>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <ConsoleShell
      active="/compliance"
      title="Erişim Denetimi"
      sub="KVKK · denetim"
      desc="Özel nitelikli kişisel veriye (sağlık/performans) kim, ne zaman, neye erişti. Toplu-erişim anomalileri işaretlenir."
      navBadge={anomalies.length}
      right={right}
    >
      <div className="st" style={{ marginTop: 0 }}>
        <h2>Filtre</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <form onSubmit={(e) => { e.preventDefault(); setSubjectQ(subject.trim()); }} style={{ display: "flex", gap: 6 }}>
            <input value={subject} onChange={(e) => setSubject(e.target.value.replace(/[^0-9]/g, ""))} inputMode="numeric" placeholder="Özne ID (ops.)" style={inputStyle} />
            <button type="submit" style={{ ...inputStyle, width: "auto", cursor: "pointer", color: "var(--muted)" }}>Filtrele</button>
          </form>
          <div className="seg">
            {DAYS.map((d) => (
              <button key={d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>{d}g</button>
            ))}
          </div>
        </div>
      </div>

      <div className="kpis" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
        <div className="kpi"><div className="kl">Erişim Kaydı</div><div className="kn">{totalCount}</div><div className="kd">son {days} gün</div></div>
        <div className="kpi"><div className="kl">Anomali</div><div className="kn" style={{ color: anomalies.length ? "var(--crit)" : "var(--low)" }}>{anomalies.length}</div><div className="kd">toplu erişim</div></div>
        <div className="kpi"><div className="kl">Dönem</div><div className="kn">{days}<span className="pct">g</span></div><div className="kd">seçili aralık</div></div>
      </div>

      <div className="st"><h2>Erişim Kayıtları</h2><span className="ep">{useDemo ? "örnek veri (backend'te kayıt yok)" : "GET /admin/compliance/access-log"}</span></div>
      {log.isLoading && !useDemo && <LoadingState />}
      {log.error && !useDemo && <ErrorState title="Kayıt alınamadı ya da yetki yok (admin)." />}
      <div className="tbl">
        <table>
          <thead><tr>
            <th>Zaman</th><th>Kullanıcı</th><th>Özne</th><th>Kategori</th>
            <th className="c">Hassasiyet</th><th className="c">Eylem</th><th>Uç</th>
          </tr></thead>
          <tbody>
            {entries.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--dim)", padding: "18px" }}>
                {log.data ? "Bu aralıkta erişim kaydı yok." : "Veri yok (backend bağlı değilse boş gelir)."}
              </td></tr>
            )}
            {entries.map((e, i) => (
              <tr key={i}>
                <td style={{ fontFamily: "JetBrains Mono", color: "var(--muted)", fontSize: 11, whiteSpace: "nowrap" }}>{e.at ? e.at.slice(0, 19).replace("T", " ") : "—"}</td>
                <td style={{ fontFamily: "JetBrains Mono" }}>{e.user_id ?? "—"}</td>
                <td style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{e.subject_type}#{e.subject_id}</td>
                <td>{e.data_category}</td>
                <td className="c" style={{ color: sensColor(e.sensitivity), fontWeight: 700 }}>{e.sensitivity}</td>
                <td className="c" style={{ fontFamily: "JetBrains Mono", color: "var(--muted)" }}>{e.action}</td>
                <td style={{ fontFamily: "JetBrains Mono", color: "var(--dim)", fontSize: 11 }}>{e.endpoint}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ConsoleShell>
  );
}
