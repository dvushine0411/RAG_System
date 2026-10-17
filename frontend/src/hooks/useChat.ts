/**
 * System Role: React state hook driving the chat conversation and token streaming.
 * Inputs: User question text and the selected document ids (retrieval filter).
 * Outputs: messages (with live-streamed assistant content, citations, usage), send/stop/reset actions.
 */

import { useCallback, useRef, useState } from "react";
import { streamQuery } from "../api/query.api";
import { appConfig } from "../config";
import type { ChatMessage, HistoryMessage } from "../types";

let nextId = 0;
const newId = () => `msg-${Date.now()}-${nextId++}`;

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const patch = (id: string, update: (m: ChatMessage) => ChatMessage) =>
    setMessages((all) => all.map((m) => (m.id === id ? update(m) : m)));

  const send = useCallback(
    async (query: string, documentIds: string[]) => {
      const text = query.trim();
      if (!text || streaming) return;

      const history: HistoryMessage[] = messages
        .filter((m) => !m.error && m.content)
        .slice(-appConfig.historyTurns * 2)
        .map((m) => ({ role: m.role, content: m.content }));

      const userMsg: ChatMessage = { id: newId(), role: "user", content: text, citations: [] };
      const assistantId = newId();
      setMessages((all) => [
        ...all,
        userMsg,
        { id: assistantId, role: "assistant", content: "", citations: [], streaming: true },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);

      try {
        await streamQuery(
          {
            query: text,
            conversation_history: history.length > 0 ? history : undefined,
            filter: documentIds.length > 0 ? { document_ids: documentIds } : undefined,
          },
          {
            onCitations: (citations) => patch(assistantId, (m) => ({ ...m, citations })),
            onToken: (delta) => patch(assistantId, (m) => ({ ...m, content: m.content + delta })),
            onDone: (done) => patch(assistantId, (m) => ({ ...m, done })),
          },
          controller.signal
        );
      } catch (err) {
        const aborted = controller.signal.aborted;
        patch(assistantId, (m) => ({
          ...m,
          error: aborted ? undefined : err instanceof Error ? err.message : String(err),
          content: aborted && !m.content ? "(Đã dừng)" : m.content,
        }));
      } finally {
        patch(assistantId, (m) => ({ ...m, streaming: false }));
        abortRef.current = null;
        setStreaming(false);
      }
    },
    [messages, streaming]
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
  }, []);

  return { messages, streaming, send, stop, reset };
}
