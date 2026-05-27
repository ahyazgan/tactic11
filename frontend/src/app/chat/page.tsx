"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  async function send() {
    const msg = input.trim();
    if (!msg) return;
    setInput("");
    setMessages([...messages, { role: "user", text: msg }]);
    setLoading(true);
    try {
      const res = await apiFetch<{
        text: string;
        conversation_id: number;
        tool_traces: { name: string }[];
      }>("/assistant/chat", {
        method: "POST",
        body: JSON.stringify({
          message: msg,
          conversation_id: conversationId,
        }),
      });
      setConversationId(res.conversation_id);
      setMessages((m) => [...m, { role: "assistant", text: res.text }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: `[hata] ${String(e)}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="max-w-3xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">Yardımcı manager (chat)</h1>
      <div className="card min-h-[400px] mb-4 space-y-3 max-h-[60vh] overflow-y-auto">
        {messages.length === 0 && (
          <p className="text-muted text-sm">
            Soru yaz. Örnek: "Galatasaray sıradaki maça nasıl çıkmalı?"
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className="text-sm">
            <span className={m.role === "user" ? "text-accent" : "text-good"}>
              {m.role === "user" ? "Sen" : "Asistan"}:
            </span>{" "}
            <span className="whitespace-pre-wrap">{m.text}</span>
          </div>
        ))}
        {loading && <p className="text-muted text-sm">düşünüyor...</p>}
      </div>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          placeholder="Soru..."
          className="flex-1 bg-bg border border-border rounded px-3 py-2"
        />
        <button
          onClick={send} disabled={loading}
          className="bg-accent text-white font-semibold rounded px-6 disabled:opacity-50"
        >Sor</button>
      </div>
    </main>
  );
}
