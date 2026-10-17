/**
 * System Role: Renders one chat message; turns [n] citation markers into interactive badges.
 * Inputs: ChatMessage (content, citations, done metrics, error, streaming flag).
 * Outputs: Message bubble with inline citation badges, source list and usage footer.
 */

import { Fragment, useState } from "react";
import { CitationList } from "./CitationList";
import type { ChatMessage } from "../types";

const CITATION_PATTERN = /\[(\d+)\]/g;

function renderWithCitations(text: string, onHover: (id: number | null) => void) {
  const parts: JSX.Element[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION_PATTERN)) {
    const index = match.index ?? 0;
    if (index > last) parts.push(<Fragment key={`t${last}`}>{text.slice(last, index)}</Fragment>);
    const id = Number(match[1]);
    parts.push(
      <sup
        key={`c${index}`}
        className="cite-badge"
        onMouseEnter={() => onHover(id)}
        onMouseLeave={() => onHover(null)}
      >
        {id}
      </sup>
    );
    last = index + match[0].length;
  }
  if (last < text.length) parts.push(<Fragment key={`t${last}`}>{text.slice(last)}</Fragment>);
  return parts;
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  const isUser = message.role === "user";

  return (
    <div className={`message ${message.role}`}>
      <div className="bubble">
        {isUser ? (
          message.content
        ) : (
          <>
            {message.content ? renderWithCitations(message.content, setActiveCitation) : null}
            {message.streaming && <span className="cursor">▍</span>}
            {!message.streaming && !message.content && !message.error && (
              <span className="muted">(Không có nội dung)</span>
            )}
          </>
        )}
        {message.error && <p className="error">⚠ {message.error}</p>}
      </div>

      {!isUser && (
        <CitationList citations={message.citations} activeId={activeCitation} usedIds={message.done?.used_citation_ids} />
      )}

      {!isUser && message.done?.retrieval_query && (
        <div className="usage">Đã tìm với: “{message.done.retrieval_query}”</div>
      )}

      {!isUser && message.done && (
        <div className="usage">
          {message.done.token_usage.total_tokens} token · {Math.round(message.done.latency_ms)} ms
        </div>
      )}
    </div>
  );
}
