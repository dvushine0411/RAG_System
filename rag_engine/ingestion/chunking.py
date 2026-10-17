"""
rag_engine/ingestion/chunking.py
Document chunking engine implementing Strategy 1 (Recursive Character Splitting)
with token-based boundaries and metadata preservation.
Ref: optimize_document_chunking SKILL.md & ARCHITECTURE.md §2.2
"""

from typing import Any, Dict, List, Optional
import logging

try:
    import tiktoken  # type: ignore
    _ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:
    _ENCODER = None


from langchain_text_splitters import RecursiveCharacterTextSplitter
from schemas.ingestion import ChunkDTO

logger = logging.getLogger("rag_engine.chunker")


def count_tokens(text: str) -> int:
    """
    Counts tokens accurately using tiktoken cl100k_base.
    Falls back to whitespace heuristic if tiktoken is unavailable.
    """
    if _ENCODER:
        return len(_ENCODER.encode(text))
    # Heuristic fallback: ~1.3 tokens per word
    return max(1, int(len(text.split()) * 1.3))


class DocumentChunker:
    """
    Recursive Character Text Splitter tuned for enterprise RAG.
    Preserves document page numbers, section headers, and hierarchical breadcrumbs.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        separators: Optional[List[str]] = None
    ):
        """
        Args:
            chunk_size: Target token count per chunk (default: 512).
            chunk_overlap: Number of overlapping tokens between adjacent chunks (default: 64, ~12.5%).
            separators: Hierarchy of split delimiters.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", "? ", "! ", " ", ""]

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=count_tokens,
            separators=self.separators,
        )

    def chunk_sections(
        self,
        sections: List[Dict[str, Any]],
        document_id: Optional[str] = None
    ) -> List[ChunkDTO]:
        """
        Chunks a list of parsed sections while retaining each section's metadata.

        Args:
            sections: List of [{"text": str, "metadata": dict}] from parsers.
            document_id: Optional UUID of the parent document.

        Returns:
            List of ChunkDTO objects ready for embedding and vector storage.
        """
        chunks: List[ChunkDTO] = []
        global_index = 0

        for section in sections:
            section_text = section.get("text", "").strip()
            if not section_text:
                continue

            section_meta = section.get("metadata", {})
            split_texts = self._splitter.split_text(section_text)

            for text_segment in split_texts:
                clean_segment = text_segment.strip()
                if not clean_segment:
                    continue

                token_cnt = count_tokens(clean_segment)
                chunk_meta: Dict[str, Any] = {
                    **section_meta,
                    "document_id": document_id,
                }

                chunks.append(
                    ChunkDTO(
                        chunk_index=global_index,
                        content=clean_segment,
                        token_count=token_cnt,
                        metadata=chunk_meta,
                    )
                )
                global_index += 1

        logger.info(
            f"Chunked document {document_id or 'unknown'}: "
            f"{len(sections)} sections -> {len(chunks)} chunks"
        )
        return chunks
