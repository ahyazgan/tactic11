"use client";

/**
 * AI Asistan — yardımcı manager (co-pilot) sohbeti.
 *
 * Gerçek kulüp verisiyle çalışır; tool çağrıları (LineupRecommendationAgent,
 * OpponentScoutAgent, PhysicalRiskAgent…) yanıttaki `tool_traces`'ten gösterilir.
 *
 * Backend: POST /assistant/chat  { message, conversation_id }
 *          → { text, conversation_id, tool_traces: [{ name }] }
 */

import * as React from "react";
import { apiFetch } from "@/lib/api";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  tools?: string[];
}

const STARTERS = [
  "Galatasaray maçına nasıl çıkmalıyız?",
  "Rafa Silva'yı dinlendirsek mi?",
  "Sakat oyuncuların dönüş planı",
  "Duran toplarda neden zayıfız?",
];
const CHIPS = [
  "Duran top planı çıkar",
  "Kimler kart riskinde?",
  "Beraberlikte ne yapalım?",
  "Sıradaki rakip brifingi",
];

const AI_AVATAR: React.CSSProperties = {
  background: "linear-gradient(135deg,#3b82f6,#6366f1)",
};

export default function ChatPage() {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [conversationId, setConversationId] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, loading]);

  async function send(text?: string) {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: msg }]);
    setLoading(true);
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
    setMessages([]);
    setConversationId(null);
    setInput("");
  }

  return (
    <div className="flex gap-3 h-[calc(100vh-5rem)]">
      {/* Sohbet geçmişi / başlangıç */}
      <aside className="w-56 shrink-0 bg-surface border border-border rounded-lg p-3 overflow-y-auto hidden md:block">
        <button
          onClick={newChat}
          className="w-full bg-surface2 border border-borderlt rounded-lg py-2.5 text-[13px] font-bold hover:border-accent mb-4"
        >
          + Yeni Sohbet
        </button>
        <div className="text-[10px] font-bold uppercase tracking-wider text-textdim mb-2">
          Başlangıç soruları
        </div>
        {STARTERS.map((s, i) => (
          <button
            key={i}
            onClick={() => send(s)}
            className="block w-full text-left px-3 py-2 rounded-lg text-[12.5px] text-textmut hover:bg-surface2 hover:text-text truncate"
          >
            {s}
          </button>
        ))}
      </aside>

      {/* Sohbet kolonu */}
      <main className="flex-1 flex flex-col min-w-0 bg-surface border border-border rounded-lg overflow-hidden">
        <div ref={scrollRef} className="flex-1 overflow-y-auto py-6">
          <div className="max-w-3xl mx-auto px-6">
            {messages.length === 0 && (
              <div className="text-center text-textmut text-[13px] mt-12">
                <div className="text-3xl mb-2">⚽</div>
                manager2 AI gerçek kulüp verinizle çalışır.
                <br />
                Bir şey sorun ya da soldan başlayın.
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className="mb-6 flex gap-3">
                <div
                  className={`w-7 h-7 rounded-lg shrink-0 flex items-center justify-center font-extrabold text-[12px] text-white ${
                    m.role === "user" ? "bg-brand" : ""
                  }`}
                  style={m.role === "assistant" ? AI_AVATAR : undefined}
                >
                  {m.role === "user" ? "S" : "m2"}
                </div>
                <div className="flex-1 min-w-0 pt-0.5">
                  <div className="text-[11px] font-bold uppercase tracking-wide text-textdim mb-1">
                    {m.role === "user" ? "Teknik Ekip" : "manager2 AI"}
                  </div>
                  {m.tools && m.tools.length > 0 && (
                    <div className="flex flex-col gap-1.5 my-2">
                      {m.tools.map((t, j) => (
                        <div
                          key={j}
                          className="flex items-center gap-2.5 bg-surface2 border border-border rounded-lg px-3 py-1.5 text-[12px]"
                        >
                          <span
                            className="w-2 h-2 rounded-full bg-ok text-ok"
                            style={{ boxShadow: "0 0 7px currentColor" }}
                          />
                          <span className="font-mono font-semibold text-text">{t}</span>
                          <span className="ml-auto font-mono text-[10.5px] text-textdim">çağrıldı</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="text-[14px] leading-relaxed whitespace-pre-wrap text-text">
                    {m.text}
                  </div>
                </div>
              </div>
            ))}

            {loading && (
              <div className="mb-6 flex gap-3">
                <div
                  className="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center font-extrabold text-[12px] text-white"
                  style={AI_AVATAR}
                >
                  m2
                </div>
                <div className="pt-1.5 text-[13px] text-textmut">düşünüyor…</div>
              </div>
            )}
          </div>
        </div>

        {/* Composer */}
        <div className="border-t border-border p-4">
          <div className="max-w-3xl mx-auto">
            <div className="flex gap-2 mb-3 flex-wrap">
              {CHIPS.map((c, i) => (
                <button
                  key={i}
                  onClick={() => setInput(c)}
                  className="bg-surface2 border border-border text-textmut px-3 py-1.5 rounded-full text-[12px] hover:border-accent hover:text-text"
                >
                  {c}
                </button>
              ))}
            </div>
            <div className="flex gap-2.5 items-end bg-surface2 border border-borderlt rounded-xl px-3 py-2.5">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                rows={1}
                placeholder="Takımınız hakkında bir şey sorun…"
                className="flex-1 bg-transparent text-text text-[14px] resize-none outline-none max-h-28 leading-relaxed"
              />
              <button
                onClick={() => send()}
                disabled={loading}
                className="w-9 h-9 rounded-lg bg-brand text-white text-lg shrink-0 flex items-center justify-center disabled:opacity-50"
              >
                ↑
              </button>
            </div>
            <div className="text-center text-[10.5px] text-textdim mt-2.5 font-mono">
              manager2 AI gerçek kulüp verinizle çalışır · yanıtlar audit log&apos;a kaydedilir
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
