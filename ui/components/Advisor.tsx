"use client";

import { useEffect, useRef, useState } from "react";
import { api, type ChatReply, type ChatTurn } from "@/lib/api";

type Msg = ChatTurn & { reply?: ChatReply };

const SUGGESTIONS = [
  "How much did I spend on dining last month?",
  "Am I over budget anywhere?",
  "Compare this month with last month",
  "Is my grocery spending going up?",
  "Where should I cut back?",
  "How much have I spent at Starbucks this year?",
];

export default function Advisor() {
  const [messages, setMessages] = useState<Msg[]>([
    { role: "assistant", content: "Hi! Ask me about your spending, budgets, or where you could save. I answer from your BigQuery data only." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Braces matter: newer browsers return a Promise from scrollIntoView, which React would treat as a cleanup.
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const history = messages.slice(1).map(({ role, content }) => ({ role, content })).slice(-6);
    setMessages((m) => [...m, { role: "user", content: q }]);
    setInput("");
    setBusy(true);
    try {
      const reply = await api.chat(q, history);
      setMessages((m) => [...m, { role: "assistant", content: reply.answer, reply }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: `Sorry, something went wrong: ${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card chat">
      <div className="messages">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.content}
            {m.reply && (
              <details className="meta">
                <summary>
                  How I answered: intent <b>{m.reply.intent.intent}</b>
                  {m.reply.intent.category ? ` · ${m.reply.intent.category}` : ""}
                  {m.reply.period ? ` · ${m.reply.period.start} to ${m.reply.period.end}` : ""}
                </summary>
                <pre>{JSON.stringify(m.reply.data, null, 2)}</pre>
              </details>
            )}
          </div>
        ))}
        {busy && <div className="msg assistant muted">Thinking…</div>}
        <div ref={end} />
      </div>
      <div className="suggest">
        {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} disabled={busy}>{s}</button>)}
      </div>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <input type="text" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about your spending…" maxLength={1000} aria-label="Message" />
        <button className="btn primary" disabled={busy || !input.trim()}>Send</button>
      </form>
    </div>
  );
}
