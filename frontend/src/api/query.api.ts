/**
 * System Role: Client for the streaming RAG query endpoint (POST /api/v1/query/stream).
 * Inputs: QueryRequest, event callbacks, optional AbortSignal.
 * Outputs: Invokes onCitations / onToken / onDone as SSE frames arrive; throws on 'error' frames.
 */

import { apiFetch } from "./http";
import { readSseStream } from "../lib/sse-parser";
import type { Citation, QueryRequest, StreamDone } from "../types";

export interface StreamHandlers {
  onCitations: (citations: Citation[]) => void;
  onToken: (delta: string) => void;
  onDone: (done: StreamDone) => void;
}

export async function streamQuery(
  request: QueryRequest,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const res = await apiFetch("/query/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(request),
    signal,
  });
  if (!res.body) throw new Error("Phản hồi không có nội dung stream.");

  await readSseStream(res.body, (frame) => {
    const payload = JSON.parse(frame.data);
    switch (frame.event) {
      case "citations":
        handlers.onCitations(payload.citations ?? []);
        break;
      case "token":
        handlers.onToken(payload.delta ?? "");
        break;
      case "done":
        handlers.onDone(payload as StreamDone);
        break;
      case "error":
        throw new Error(payload.message ?? "Lỗi khi sinh câu trả lời.");
    }
  });
}
