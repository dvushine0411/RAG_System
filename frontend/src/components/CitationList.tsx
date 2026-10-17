/**
 * System Role: Renders the source list for an assistant answer, matching [n] markers to provenance.
 * Inputs: citations array, the currently highlighted citation id, and (after streaming) the ids actually cited.
 * Outputs: Ordered list of cited sources (title, page/section, relevance score); unused retrieved sources are
 *          collapsed behind a toggle so they do not look like evidence.
 */

import { useState } from "react";
import type { Citation } from "../types";

interface Props {
  citations: Citation[];
  activeId: number | null;
  usedIds?: number[];
}

export function CitationList({ citations, activeId, usedIds }: Props) {
  const [showUnused, setShowUnused] = useState(false);
  if (citations.length === 0) return null;

  // Before the answer finishes (or if it cites nothing) show everything that was retrieved.
  const used = usedIds && usedIds.length > 0 ? citations.filter((c) => usedIds.includes(c.citation_id)) : citations;
  const unused = citations.filter((c) => !used.includes(c));
  const visible = showUnused ? citations : used;

  return (
    <>
    <ol className="citations">
      {visible.map((c) => (
        <li
          key={c.citation_id}
          id={`cite-${c.chunk_id}`}
          className={activeId === c.citation_id ? "active" : undefined}
        >
          <span className="cite-num">[{c.citation_id}]</span>
          <span className="cite-title">{c.title || c.document_id}</span>
          {c.page_number != null && <span className="cite-meta">tr. {c.page_number}</span>}
          {c.section_title && <span className="cite-meta">§ {c.section_title}</span>}
          <span className="cite-score">{c.score.toFixed(2)}</span>
        </li>
      ))}
    </ol>
    {unused.length > 0 && (
      <button className="ghost cite-toggle" onClick={() => setShowUnused((v) => !v)}>
        {showUnused ? "Ẩn nguồn không được trích dẫn" : `+${unused.length} nguồn đã tìm nhưng không dùng`}
      </button>
    )}
    </>
  );
}
