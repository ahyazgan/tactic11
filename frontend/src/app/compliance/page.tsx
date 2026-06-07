"use client";

/**
 * Erişim Denetimi (KVKK) — özel nitelikli kişisel veriye kim, ne zaman, neye
 * erişti + şüpheli toplu-erişim anomalileri. Uyumluluk/denetim arayüzü.
 *
 * Backend:
 *   GET /admin/compliance/access-log?subject_id=&days=   — erişim kayıtları
 *   GET /admin/compliance/audit?days=                    — anomali tespiti
 */

import * as React from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { Panel, EndpointTag } from "@/components/ui";

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
  if (v.includes("özel") || v.includes("special")) return "text-danger";
  if (v.includes("kişisel") || v.includes("personal")) return "text-high";
  return "text-textmut";
}

const inputCls = "bg-surface2 border border-border text-text text-[13px] px-2 py-1.5 rounded";
const DAYS = [7, 30, 90];

export default function CompliancePage() {
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
  const entries = log.data?.entries ?? [];
  const anomalies = audit.data?.anomalies ?? [];

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-text">Erişim Denetimi · KVKK</h1>
          <p className="text-[12px] text-textmut mt-0.5">
            Özel nitelikli kişisel veriye (sağlık/performans) kim, ne zaman, neye
            erişti. Toplu-erişim anomalileri işaretlenir.
          </p>
        </div>
        <EndpointTag method="GET" path="/admin/compliance/access-log" />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSubjectQ(subject.trim());
          }}
          className="flex items-center gap-2"
        >
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value.replace(/[^0-9]/g, ""))}
            inputMode="numeric"
            placeholder="Özne ID (oyuncu) — opsiyonel"
            className={`${inputCls} h-8 w-56`}
          />
          <button type="submit" className="text-[11px] uppercase px-2 py-1.5 rounded border border-borderlt text-textmut hover:text-text">
            Filtrele
          </button>
        </form>
        <div className="flex items-center gap-1 ml-2">
          {DAYS.map((d) => (
            <button key={d} type="button" onClick={() => setDays(d)} className={`text-[11px] px-2 py-1.5 rounded border ${days === d ? "border-accent text-accent" : "border-borderlt text-textmut hover:text-text"}`}>
              {d}g
            </button>
          ))}
        </div>
      </div>

      {anomalies.length > 0 && (
        <Panel title={`⚠ Şüpheli Toplu Erişim (${anomalies.length})`}>
          <ul className="text-[12px] space-y-1">
            {anomalies.map((a, i) => (
              <li key={i} className="flex items-center gap-3 text-danger">
                <span className="font-mono">{a.user_id ?? "(atıfsız)"}</span>
                {a.distinct_subjects !== undefined && (
                  <span className="font-mono text-textmut">{a.distinct_subjects} özneye erişim</span>
                )}
                {a.data_category && <span className="text-textmut">· {a.data_category}</span>}
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel
        title={`Erişim Kayıtları (${log.data?.total ?? 0})`}
        actions={<EndpointTag method="GET" path="/admin/compliance/audit" />}
      >
        {log.isLoading && <p className="text-[12px] text-textmut">Yükleniyor…</p>}
        {log.error && <p className="text-[12px] text-textmut">Kayıt alınamadı ya da yetki yok (admin).</p>}
        {log.data && entries.length === 0 && (
          <p className="text-[12px] text-textmut">Bu aralıkta erişim kaydı yok.</p>
        )}
        {entries.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-textmut text-left border-b border-border uppercase text-[10.5px]">
                  <th className="py-1 pr-2">Zaman</th>
                  <th className="py-1 pr-2">Kullanıcı</th>
                  <th className="py-1 pr-2">Özne</th>
                  <th className="py-1 pr-2">Kategori</th>
                  <th className="py-1 pr-2">Hassasiyet</th>
                  <th className="py-1 pr-2">Eylem</th>
                  <th className="py-1">Uç</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="py-1 pr-2 font-mono text-textmut whitespace-nowrap">
                      {e.at ? e.at.slice(0, 19).replace("T", " ") : "—"}
                    </td>
                    <td className="py-1 pr-2 font-mono">{e.user_id ?? "—"}</td>
                    <td className="py-1 pr-2 font-mono text-textmut">
                      {e.subject_type}#{e.subject_id}
                    </td>
                    <td className="py-1 pr-2">{e.data_category}</td>
                    <td className={`py-1 pr-2 font-semibold ${sensColor(e.sensitivity)}`}>
                      {e.sensitivity}
                    </td>
                    <td className="py-1 pr-2 font-mono text-textmut">{e.action}</td>
                    <td className="py-1 font-mono text-textdim">{e.endpoint}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
