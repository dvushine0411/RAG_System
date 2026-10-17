/**
 * System Role: Main chat area — message history, composer, and stream controls.
 * Inputs: messages/streaming state and send/stop/reset callbacks from useChat.
 * Outputs: Rendered conversation; submits questions on Enter (Shift+Enter = newline).
 */

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { MessageBubble } from "./MessageBubble";
import type { ChatMessage } from "../types";

interface Props {
  messages: ChatMessage[];
  streaming: boolean;
  scopeLabel: string;
  onSend: (text: string) => void;
  onStop: () => void;
  onReset: () => void;
}

export function ChatPanel({ messages, streaming, scopeLabel, onSend, onStop, onReset }: Props) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!draft.trim() || streaming) return;
    onSend(draft);
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <main className="chat">
      <header className="chat-header">
        <div>
          <h1>RAG Assistant</h1>
          <span className="muted">{scopeLabel}</span>
        </div>
        <button className="ghost" onClick={onReset} disabled={messages.length === 0}>
          Cuộc trò chuyện mới
        </button>
      </header>

      <section className="messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <h2>Hỏi về tài liệu của bạn</h2>
            <p>Câu trả lời chỉ dựa trên tài liệu đã tải lên, kèm trích dẫn nguồn [1], [2]…</p>
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <div ref={endRef} />
      </section>

      <form className="composer" onSubmit={submit}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"
          rows={2}
        />
        {streaming ? (
          <button type="button" className="stop" onClick={onStop}>
            Dừng
          </button>
        ) : (
          <button type="submit" disabled={!draft.trim()}>
            Gửi
          </button>
        )}
      </form>
    </main>
  );
}
