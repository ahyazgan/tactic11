"use client";

/**
 * AI Asistan — yardımcı manager (co-pilot) sohbeti. ConsoleShell çatısında.
 * Başlangıç soruları sağ kolonda; sohbet + composer ortada (flex-yükseklik).
 * Backend: POST /assistant/chat { message, conversation_id }
 *          → { text, conversation_id, tool_traces: [{ name }] }
 */

import * as React from "react";
import { apiFetch } from "@/lib/api";
import { DEMO_MODE } from "@/lib/demo-mode";
import { demoChatQA } from "@/lib/demo-data";
import { answerQuestion, type AssistantContext } from "@/lib/assistant";
import { engineLabel } from "@/lib/labels";
import { ConsoleShell } from "../_console/shell";

// Motor-güdümlü örnek sorular — canlı motorlardan (risk/kadro/maç/track-record/haftalık) cevaplanır.
const ENGINE_STARTERS = [
  "Orkun Kökçü'nün sakatlık riski ne?",
  "Orkun mu Rıdvan mı daha riskli?",
  "Jota Silva'nın gelişim potansiyeli ne?",
  "En yüksek potansiyelli oyuncular kim?",
  "Antalyaspor'a karşı kimi dinlendireyim?",
  "Antalyaspor maçını kazanır mıyız?",
  "Bu haftanın öncelikleri ne?",
  "Model tahminleri ne kadar tutuyor?",
];

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  tools?: string[];
}

const STARTERS = DEMO_MODE
  ? [...ENGINE_STARTERS, ...demoChatQA.slice(0, 6).map((qa) => qa.question)]
  : [
    "Galatasaray maçına nasıl çıkmalıyız?",
    "Rafa Silva'yı dinlendirsek mi?",
    "Sakat oyuncuların dönüş planı",
    "Duran toplarda neden zayıfız?",
  ];
const CHIPS = DEMO_MODE
  ? ENGINE_STARTERS
  : [
    "Duran top planı çıkar",
    "Kimler kart riskinde?",
    "Beraberlikte ne yapalım?",
    "Sıradaki rakip brifingi",
  ];

// Demo: açılışta dolu örnek diyalog — ilk cevabı CANLI motordan üret (gerçek
// hesaplanan çıktı + gerçek motor izleri), böylece copilot hemen kendini gösterir.
const demoInitialMessages: ChatMessage[] = DEMO_MODE
  ? (() => {
    const q = "Bu hafta en riskli oyuncularım kim?";
    const a = answerQuestion(q);
    return [
      { role: "user", text: q },
      a.matched
        ? { role: "assistant", text: a.text, tools: a.tools }
        : { role: "assistant", text: demoChatQA[0].answer, tools: demoChatQA[0].tools },
    ];
  })()
  : [];

/** Demo: önce CANLI motorlara yönlendir (risk/kadro/maç/gelişim/karşılaştırma/…);
 *  ctx ile takip soruları çözülür. Eşleşmezse demoChatQA'ya, o da yoksa genel cevaba düşer. */
function demoAnswer(msg: string, ctx: AssistantContext): { text: string; tools: string[]; context: AssistantContext } {
  const live = answerQuestion(msg, ctx);
  const nextCtx = live.context ?? ctx;
  if (live.matched) return { text: live.text, tools: live.tools, context: nextCtx };

  const lower = msg.toLocaleLowerCase("tr");
  const hit = demoChatQA.find(
    (qa) => qa.question.toLocaleLowerCase("tr") === lower
      || lower.includes(qa.question.toLocaleLowerCase("tr").slice(0, 12)),
  );
  if (hit) return { text: hit.answer, tools: hit.tools, context: nextCtx };
  return {
    text: "Bunu doğrudan motorlara bağlayamadım. Şunları deneyebilirsin: bir oyuncunun sakatlık riski ya da gelişim potansiyeli, iki oyuncuyu karşılaştırma, sıradaki maç tahmini, kimi dinlendirmem gerektiği, modelin isabet oranı ya da bu haftanın öncelikleri.",
    tools: ["context_engine"],
    context: nextCtx,
  };
}

export default function ChatConsolePage() {
  const [messages, setMessages] = React.useState<ChatMessage[]>(demoInitialMessages);
  const [input, setInput] = React.useState("");
  const [conversationId, setConversationId] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const ctxRef = React.useRef<AssistantContext>({});   // takip soruları için sohbet bağlamı

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, loading]);

  async function send(text?: string) {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: msg }]);
    setLoading(true);
    // Demo: backend'e gitme, hazır cevabı kısa bir gecikmeyle göster.
    if (DEMO_MODE) {
      const ans = demoAnswer(msg, ctxRef.current);
      ctxRef.current = ans.context;   // bağlamı bir sonraki tura taşı
      window.setTimeout(() => {
        setMessages((m) => [...m, { role: "assistant", text: ans.text, tools: ans.tools }]);
        setLoading(false);
      }, 450);
      return;
    }
    try {
      const res = await apiFetch<{
        text: string;
        conversation_id: number;
        tool_traces: { name: string }[];
      }>("/assistant/chat", {
        method: "POST",
        body: JSON.stringify({ message: msg, conversation_id: conversationId }),
      });
      setConversationId(res.conversation_id);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: res.text, tools: (res.tool_traces ?? []).map((t) => t.name) },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: `[hata] ${e instanceof Error ? e.message : String(e)}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function newChat() {
    setMessages(DEMO_MODE ? demoInitialMessages : []);
    setConversationId(null);
    setInput("");
    ctxRef.current = {};
  }

  const aiAvatar: React.CSSProperties = { background: "var(--accent)" };
  const avatarBase: React.CSSProperties = {
    width: 28, height: 28, borderRadius: 7, flexShrink: 0, display: "flex",
    alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 12, color: "#fff",
  };

  const right = (
    <div className="rc">
      <h3>Sohbet</h3>
      <button
        onClick={newChat}
        style={{ width: "100%", background: "var(--panel3)", border: "1px solid var(--line)", borderRadius: 8, padding: "9px", fontSize: 12.5, fontWeight: 700, color: "var(--ink)", cursor: "pointer", marginBottom: 14, fontFamily: "inherit" }}
      >
        + Yeni Sohbet
      </button>
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1, color: "var(--dim)", marginBottom: 8 }}>Başlangıç soruları</div>
      {STARTERS.map((s, i) => (
        <button
          key={i}
          onClick={() => send(s)}
          style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 10px", borderRadius: 7, fontSize: 12, color: "var(--muted)", background: "transparent", border: 0, cursor: "pointer", marginBottom: 2, fontFamily: "inherit" }}
        >
          {s}
        </button>
      ))}
    </div>
  );

  return (
    <ConsoleShell
      active="/chat"
      title="AI Asistan"
      sub="Co-pilot · gerçek kulüp verisiyle"
      source="claude"
      right={right}
    >
      <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 132px)", border: "1px solid var(--line)", borderRadius: 9, background: "var(--panel)", overflow: "hidden" }}>
        {/* Mesajlar */}
        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
          <div style={{ maxWidth: 720, margin: "0 auto" }}>
            {messages.length === 0 && (
              <div style={{ textAlign: "center", color: "var(--muted)", fontSize: 13, marginTop: 40 }}>
                <div style={{ fontSize: 30, marginBottom: 8 }}>⚽</div>
                tactic11 AI gerçek kulüp verinizle çalışır.<br />Bir şey sorun ya da sağdan başlayın.
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} style={{ marginBottom: 22, display: "flex", gap: 12 }}>
                <div style={{ ...avatarBase, ...(m.role === "assistant" ? aiAvatar : { background: "var(--besiktas)" }) }}>
                  {m.role === "user" ? "S" : "t11"}
                </div>
                <div style={{ flex: 1, minWidth: 0, paddingTop: 2 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--dim)", marginBottom: 4 }}>
                    {m.role === "user" ? "Teknik Ekip" : "tactic11 AI"}
                  </div>
                  {m.tools && m.tools.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6, margin: "8px 0" }}>
                      {m.tools.map((t, j) => (
                        <div key={j} style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "6px 11px", fontSize: 12 }}>
                          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--low)", boxShadow: "0 0 7px var(--low)" }} />
                          <span title={t} style={{ fontWeight: 600, color: "var(--ink)" }}>{engineLabel(t)}</span>
                          <span style={{ marginLeft: "auto", fontFamily: "JetBrains Mono", fontSize: 10.5, color: "var(--dim)" }}>çağrıldı</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div style={{ fontSize: 14, lineHeight: 1.6, whiteSpace: "pre-wrap", color: "var(--ink)" }}>{m.text}</div>
                </div>
              </div>
            ))}
            {loading && (
              <div style={{ marginBottom: 22, display: "flex", gap: 12 }}>
                <div style={{ ...avatarBase, ...aiAvatar }}>t11</div>
                <div style={{ paddingTop: 6, fontSize: 13, color: "var(--muted)" }}>düşünüyor…</div>
              </div>
            )}
          </div>
        </div>

        {/* Composer */}
        <div style={{ borderTop: "1px solid var(--line)", padding: 14, background: "var(--header)" }}>
          <div style={{ maxWidth: 720, margin: "0 auto" }}>
            <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
              {CHIPS.map((c, i) => (
                <button key={i} onClick={() => setInput(c)} style={{ background: "var(--panel2)", border: "1px solid var(--line)", color: "var(--muted)", padding: "5px 12px", borderRadius: 999, fontSize: 12, cursor: "pointer", fontFamily: "inherit" }}>
                  {c}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "flex-end", background: "var(--panel2)", border: "1px solid var(--line2)", borderRadius: 12, padding: "10px 12px" }}>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                rows={1}
                aria-label="Asistana mesaj yaz"
                placeholder="Takımınız hakkında bir şey sorun…"
                style={{ flex: 1, background: "transparent", color: "var(--ink)", fontSize: 14, resize: "none", outline: "none", maxHeight: 110, lineHeight: 1.5, border: 0, fontFamily: "inherit" }}
              />
              <button onClick={() => send()} disabled={loading} style={{ width: 34, height: 34, borderRadius: 8, background: "var(--besiktas)", color: "#fff", fontSize: 17, flexShrink: 0, border: 0, cursor: loading ? "default" : "pointer", opacity: loading ? 0.5 : 1 }}>
                ↑
              </button>
            </div>
            <div style={{ textAlign: "center", fontSize: 10.5, color: "var(--dim)", marginTop: 10, fontFamily: "JetBrains Mono" }}>
              tactic11 AI gerçek kulüp verinizle çalışır · yanıtlar audit log&apos;a kaydedilir
            </div>
          </div>
        </div>
      </div>
    </ConsoleShell>
  );
}
