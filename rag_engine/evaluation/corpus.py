"""
System Role: Indexes an evaluation corpus folder into a dedicated Qdrant collection per chunking configuration
             (never the production `document_chunks`), and exposes helpers to switch / scroll that collection.
Inputs: Folder of supported files (pdf, docx, md, txt, html); ChunkConfig (chunk_size, overlap, context header).
Outputs: Collection `eval_cs<size>_ov<overlap>_h<0|1>` populated through ingestion.indexer.index_document.
"""

import contextlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List

from config import settings
from ingestion.indexer import index_document
from vectordb.collection_manager import ensure_collection_exists
from vectordb.qdrant_client import get_qdrant_client

SUPPORTED = {".pdf", ".docx", ".doc", ".md", ".markdown", ".txt", ".text", ".html", ".htm"}


@dataclass(frozen=True)
class ChunkConfig:
    chunk_size: int
    chunk_overlap: int
    context_header: bool

    @property
    def collection(self) -> str:
        return f"eval_cs{self.chunk_size}_ov{self.chunk_overlap}_h{int(self.context_header)}"

    @classmethod
    def parse(cls, spec: str) -> "ChunkConfig":
        """'512:64:1' -> ChunkConfig(512, 64, True)"""
        size, overlap, header = spec.split(":")
        return cls(int(size), int(overlap), header in ("1", "true", "yes"))


@contextlib.contextmanager
def use_config(cfg: ChunkConfig) -> Iterator[None]:
    """Temporarily point vector_ops / ingestion at the eval collection and header setting (single-process eval)."""
    saved = (settings.qdrant_collection, settings.chunk_context_header_enabled)
    settings.qdrant_collection = cfg.collection
    settings.chunk_context_header_enabled = cfg.context_header
    try:
        yield
    finally:
        settings.qdrant_collection, settings.chunk_context_header_enabled = saved


def document_id_for(path: Path) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"eval-corpus:{path.name}"))


def corpus_files(folder: Path, pattern: str = "*") -> List[Path]:
    return sorted(p for p in folder.rglob(pattern) if p.is_file() and p.suffix.lower() in SUPPORTED)


async def collection_point_count(name: str) -> int:
    client = get_qdrant_client()
    if not await client.collection_exists(name):
        return 0
    return (await client.count(name, exact=True)).count


async def index_corpus(folder: Path, cfg: ChunkConfig, rebuild: bool = False, pattern: str = "*") -> Dict[str, int]:
    client = get_qdrant_client()
    if rebuild and await client.collection_exists(cfg.collection):
        await client.delete_collection(cfg.collection)
    existing = await collection_point_count(cfg.collection)
    if existing and not rebuild:
        print(f"  reuse '{cfg.collection}' ({existing} points)")
        return {"reused": existing}

    stats: Dict[str, int] = {}
    with use_config(cfg):
        await ensure_collection_exists()
        for path in corpus_files(folder, pattern):
            result = await index_document(
                file_bytes=path.read_bytes(),
                filename=path.name,
                document_id=document_id_for(path),
                chunk_size=cfg.chunk_size,
                chunk_overlap=cfg.chunk_overlap,
            )
            stats[path.name] = result.total_chunks
            print(f"  indexed {path.name}: {result.total_chunks} chunks ({result.total_tokens} tokens)")
    return stats


async def scroll_chunks(collection: str) -> List[dict]:
    """All points' payloads (+ id) of a collection."""
    client = get_qdrant_client()
    out, offset = [], None
    while True:
        points, offset = await client.scroll(collection, limit=256, offset=offset, with_payload=True, with_vectors=False)
        out.extend({"id": str(p.id), **(p.payload or {})} for p in points)
        if offset is None:
            return out
