/**
 * System Role: Consumes a Server-Sent Events stream from the RAG Engine and aggregates it into one JSON answer.
 * Inputs: Web ReadableStream<Uint8Array> emitting 'citations' -> 'token'* -> 'done' (or 'error') SSE frames.
 * Outputs: CollectedAnswer { answer, citations, token_usage, finish_reason, latency_ms, used_citation_ids,
 *          retrieval_query }; throws on 'error' frames.
 * Ref: ARCHITECTURE.md §2.3 Full End-to-End RAG Query Chain (non-streaming variant)
 */

import type { CitationMetadata } from "./rag-engine.client.js";

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface CollectedAnswer {
  answer: string;
  citations: CitationMetadata[];
  token_usage: TokenUsage | null;
  finish_reason: string | null;
  latency_ms: number | null;
  used_citation_ids: number[];
  retrieval_query: string | null;
}

export interface SseFrame {
  event: string;
  data: string;
}

/**
 * Splits buffered SSE text into complete frames, returning the unconsumed remainder.
 */
export function parseSseFrames(buffer: string): { frames: SseFrame[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const frames: SseFrame[] = [];

  for (const block of blocks) {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
    }
    if (dataLines.length > 0) frames.push({ event, data: dataLines.join("\n") });
  }
  return { frames, rest };
}

export async function collectSseAnswer(stream: ReadableStream<Uint8Array>): Promise<CollectedAnswer> {
  const result: CollectedAnswer = {
    answer: "",
    citations: [],
    token_usage: null,
    finish_reason: null,
    latency_ms: null,
    used_citation_ids: [],
    retrieval_query: null,
  };

  const decoder = new TextDecoder();
  const reader = stream.getReader();
  let buffer = "";

  const applyFrame = (frame: SseFrame): void => {
    const payload = JSON.parse(frame.data);
    switch (frame.event) {
      case "citations":
        result.citations = payload.citations ?? [];
        break;
      case "token":
        result.answer += payload.delta ?? "";
        break;
      case "done":
        result.token_usage = payload.token_usage ?? null;
        result.finish_reason = payload.finish_reason ?? null;
        result.latency_ms = payload.latency_ms ?? null;
        result.used_citation_ids = payload.used_citation_ids ?? [];
        result.retrieval_query = payload.retrieval_query ?? null;
        break;
      case "error":
        throw new Error(`RAG Engine stream error: ${payload.message ?? frame.data}`);
    }
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { frames, rest } = parseSseFrames(buffer);
    buffer = rest;
    frames.forEach(applyFrame);
  }

  // Flush a trailing frame that was not terminated by a blank line.
  buffer += decoder.decode();
  parseSseFrames(buffer + "\n\n").frames.forEach(applyFrame);

  return result;
}
