"use client";

/**
 * MAÇ-İÇİ KADRO GİRİŞİ — koçun yanındaki kişi için, tablette tek dokunuş.
 *
 * Neden var: takip sistemi sahada 22 ANONİM iz görür; kimin kim olduğunu ve
 * kimin sonradan girdiğini bilmez. Kadro girilmezse "ne zaman değiştir" ve
 * "kimi çıkar" tabloları sessizce devre dışı kalır ve panel boş öneri döndürür.
 * Bu ekran o halkayı kapatır (docs/CANLI-KADRO-GIRISI.md).
 *
 * GET  /admin/teams/{id}/squad             → oyuncu havuzu
 * GET  /admin/matches/{id}/squad-state     → sahadakiler + kullanılmış hak
 * PUT  /admin/matches/{id}/lineup          → ilk 11
 * POST /admin/matches/{id}/substitution    → değişiklik (+ öneriyle uyuşma)
 * POST /admin/matches/{id}/dismissal       → kırmızı kart (hak HARCAMAZ)
 * POST /admin/decisions/{id}/applied       → koçun beyanı (uyuşmadan TÜRETİLMEZ)
 */

import { useMemo, useState } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";

interface SquadPlayer { player_external_id: number; name: string | null; position: string | null; son_mac: string | null }
interface SquadResponse { team_external_id: number; oyuncu: SquadPlayer[] }
interface StateResponse {
  kadro_girildi: boolean; sahada: number[]; sahadaki_sayi: number;
  atilan: number[]; kullanilmis_hak: number;
  mevkiler: Record<string, string>; uyari: string | null;
}
interface Agreement { decision_id: number; minute: number; sira: number; applied: boolean | null }
interface SubResponse { kullanilmis_hak: number; sahada: number[]; oneriyle_uyusma: { aday_listesinde_gecen_oneri: Agreement[] } }

const XI = 11;

const btn = (tone: "ghost" | "primary" | "warn" = "ghost") => ({
  padding: "10px 14px", minHeight: 44, borderRadius: 8, fontSize: 13, fontWeight: 600,
  cursor: "pointer", border: "1px solid var(--line)",
  background: tone === "primary" ? "var(--high)" : tone === "warn" ? "var(--panel2)" : "var(--panel)",
  color: tone === "primary" ? "#fff" : "var(--ink)",
} as const);

/** Oyuncu pulu — parmakla basılacak kadar büyük (tablet). */
function Chip({ p, on, selected, onClick }: {
  p: SquadPlayer; on?: boolean; selected?: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        ...btn(selected ? "primary" : "ghost"),
        display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2,
        opacity: on === false ? 0.45 : 1, textAlign: "left", minWidth: 128,
      }}
    >
      <span style={{ fontSize: 13 }}>{p.name ?? `#${p.player_external_id}`}</span>
      <span style={{ fontSize: 10.5, color: selected ? "#fff" : "var(--dim)" }}>
        {p.position ?? "—"} · {p.player_external_id}
      </span>
    </button>
  );
}

export function SquadEntry({ matchId, teamId, minute }: {
  matchId: number; teamId: number; minute: number;
}) {
  const { data: squad } = useSWR<SquadResponse>(
    `/admin/teams/${teamId}/squad`, apiFetch, { revalidateOnFocus: false },
  );
  const stateKey = `/admin/matches/${matchId}/squad-state?team_external_id=${teamId}&minute=${minute}`;
  const { data: state, mutate } = useSWR<StateResponse>(stateKey, apiFetch, { revalidateOnFocus: false });

  const [picked, setPicked] = useState<number[]>([]);
  const [off, setOff] = useState<number | null>(null);
  const [on, setOn] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [redMode, setRedMode] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, setPending] = useState<Agreement[]>([]);

  const pool = squad?.oyuncu ?? [];
  const byId = useMemo(() => new Map(pool.map((p) => [p.player_external_id, p])), [pool]);
  const onPitch = state?.sahada ?? [];
  const bench = useMemo(
    () => pool.filter((p) => !onPitch.includes(p.player_external_id)),
    [pool, onPitch],
  );
  const entered = state?.kadro_girildi ?? false;

  const call = async (url: string, body: unknown, method: "PUT" | "POST") => {
    setBusy(true); setMsg(null);
    try {
      const r = await apiFetch(url, { method, body: JSON.stringify(body) });
      await mutate();
      return r;
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "istek başarısız");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const saveLineup = async () => {
    if (picked.length !== XI) return;
    const r = await call(`/admin/matches/${matchId}/lineup`, {
      team_external_id: teamId, minute,
      starters: picked.map((id) => ({
        player_external_id: id, position: byId.get(id)?.position ?? null,
      })),
    }, "PUT");
    if (r) { setPicked([]); setMsg("ilk 11 kaydedildi"); }
  };

  const saveSub = async () => {
    if (off == null || on == null) return;
    const r = (await call(`/admin/matches/${matchId}/substitution`, {
      team_external_id: teamId, minute, player_off: off, player_on: on,
    }, "POST")) as SubResponse | null;
    if (!r) return;
    setOff(null); setOn(null);
    const matched = r.oneriyle_uyusma?.aday_listesinde_gecen_oneri ?? [];
    setPending(matched.filter((m) => m.applied == null));
    setMsg(`değişiklik kaydedildi · kullanılan hak ${r.kullanilmis_hak}`);
  };

  const saveRed = async () => {
    if (off == null) return;
    const r = await call(`/admin/matches/${matchId}/dismissal`, {
      team_external_id: teamId, minute, player_external_id: off,
    }, "POST");
    if (!r) return;
    setOff(null); setRedMode(false);
    setMsg(`kırmızı kart kaydedildi · sahada 10 · kullanılan hak değişmedi`);
  };

  const mark = async (decisionId: number, applied: boolean) => {
    await apiFetch(`/admin/decisions/${decisionId}/applied`, {
      method: "POST", body: JSON.stringify({ applied }),
    });
    setPending((p) => p.filter((x) => x.decision_id !== decisionId));
  };

  return (
    <section style={{ display: "grid", gap: 12 }}>
      <header style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>Kadro girişi</h3>
        <span style={{ fontSize: 12, color: "var(--dim)" }}>
          {minute.toFixed(0)}. dakika · sahada {onPitch.length} · kullanılan hak{" "}
          {state?.kullanilmis_hak ?? 0}
          {state?.atilan?.length ? ` · ${state.atilan.length} kırmızı kart` : ""}
        </span>
      </header>

      {state?.uyari && (
        <p style={{
          margin: 0, padding: 10, borderRadius: 8, fontSize: 12.5, lineHeight: 1.45,
          background: "var(--panel2)", border: "1px solid var(--line)", color: "var(--ink)",
        }}>
          ⚠ {state.uyari}
        </p>
      )}

      {!entered ? (
        <div style={{ display: "grid", gap: 8 }}>
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--dim)" }}>
            İlk 11&apos;i seç ({picked.length}/{XI})
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {pool.map((p) => (
              <Chip
                key={p.player_external_id}
                p={p}
                selected={picked.includes(p.player_external_id)}
                onClick={() => setPicked((cur) =>
                  cur.includes(p.player_external_id)
                    ? cur.filter((x) => x !== p.player_external_id)
                    : cur.length < XI ? [...cur, p.player_external_id] : cur)}
              />
            ))}
          </div>
          <button
            onClick={saveLineup}
            disabled={picked.length !== XI || busy}
            style={{ ...btn("primary"), opacity: picked.length === XI && !busy ? 1 : 0.5 }}
          >
            İlk 11&apos;i kaydet
          </button>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--dim)" }}>Çıkan</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {onPitch.map((id) => {
              const p = byId.get(id) ?? { player_external_id: id, name: null, position: state?.mevkiler?.[String(id)] ?? null, son_mac: null };
              return <Chip key={id} p={p} selected={off === id} onClick={() => setOff(off === id ? null : id)} />;
            })}
          </div>
          {!redMode && (
            <p style={{ margin: 0, fontSize: 12.5, color: "var(--dim)" }}>Giren</p>
          )}
          <div style={{ display: redMode ? "none" : "flex", flexWrap: "wrap", gap: 8 }}>
            {bench.map((p) => (
              <Chip key={p.player_external_id} p={p} selected={on === p.player_external_id}
                    onClick={() => setOn(on === p.player_external_id ? null : p.player_external_id)} />
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              onClick={saveSub}
              disabled={off == null || on == null || busy || redMode}
              style={{ ...btn("primary"),
                opacity: off != null && on != null && !busy && !redMode ? 1 : 0.5 }}
            >
              Değişikliği kaydet
            </button>
            {/*
              Kırmızı kart DEĞİŞİKLİK HAKKI HARCAMAZ — ayrı bir yol olmasının
              sebebi bu. Kaydedilmezse atılan oyuncu sahada görünmeye devam eder
              ve motor onu "çıkar" diye önerebilir.
            */}
            {!redMode ? (
              <button onClick={() => { setRedMode(true); setOn(null); }} style={btn("warn")}>
                Kırmızı kart
              </button>
            ) : (
              <>
                <button
                  onClick={saveRed}
                  disabled={off == null || busy}
                  style={{ ...btn("warn"), opacity: off != null && !busy ? 1 : 0.5 }}
                >
                  {off != null ? `${off} numaralı oyuncuyu at` : "Çıkan oyuncuyu seç"}
                </button>
                <button onClick={() => setRedMode(false)} style={btn()}>Vazgeç</button>
              </>
            )}
          </div>
        </div>
      )}

      {/*
        Öneriyle uyuşma GÖZLEMdir; "uygulandı" işareti KOÇUN beyanıdır ve
        uyuşmadan türetilmez. Bu soru sorulmazsa karnenin Karşı-olgu boyutu
        ölçülemez kalır; otomatik doldurulursa sahte ölçülebilir olur.
      */}
      {pending.map((a) => (
        <div key={a.decision_id} style={{
          display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
          padding: 10, borderRadius: 8, background: "var(--panel2)", border: "1px solid var(--line)",
        }}>
          <span style={{ fontSize: 12.5 }}>
            Bu oyuncu {a.minute.toFixed(0)}. dakikadaki önerinin {a.sira}. sırasındaydı —
            değişikliği bu öneri yüzünden mi yaptın?
          </span>
          <button style={btn("primary")} onClick={() => mark(a.decision_id, true)}>Evet</button>
          <button style={btn("warn")} onClick={() => mark(a.decision_id, false)}>Hayır</button>
        </div>
      ))}

      {msg && <p style={{ margin: 0, fontSize: 12, color: "var(--dim)" }}>{msg}</p>}
    </section>
  );
}
