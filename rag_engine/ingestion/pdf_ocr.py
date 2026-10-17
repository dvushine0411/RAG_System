"""
System Role: OCR fallback for scanned PDFs — pages without a usable text layer are rendered to PNG and
             transcribed by an OpenAI vision model (settings.pdf_ocr_model), then merged back into the sections.
Inputs: Raw PDF bytes + sections from pdf_parser; settings.pdf_ocr_* (enabled, model, dpi, concurrency, limits).
Outputs: Sections list where empty pages are replaced by OCR text (metadata.ocr = True), ordered by page.
Cost control: results are cached on disk keyed by SHA-256(page PNG + model) so re-indexing never pays twice;
              `usage_hook` lets callers (evaluation/) account tokens against a budget.
"""

import asyncio
import base64
import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pymupdf

from config import settings

logger = logging.getLogger("rag_engine.ingestion.pdf_ocr")

usage_hook: Optional[Callable[[str, int, int], None]] = None

OCR_PROMPT = (
    "Transcribe ALL readable text on this scanned page exactly as written. Preserve Vietnamese diacritics, "
    "reading order, headings, list markers and paragraph breaks. Do not translate, summarize, explain or add "
    "anything. Omit running headers/footers and bare page numbers. If the page has no text, return nothing."
)


def _clean(text: str) -> str:
    """Vision models sometimes wrap the transcription in a ``` code fence."""
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _cache_path(png: bytes) -> Path:
    digest = hashlib.sha256(png + settings.pdf_ocr_model.encode()).hexdigest()
    return Path(settings.ocr_cache_dir) / f"{digest}.txt"


async def _transcribe(client: Any, png: bytes, page_number: int) -> str:
    cache = _cache_path(png)
    if cache.exists():
        return _clean(cache.read_text(encoding="utf-8"))
    image_url = "data:image/png;base64," + base64.b64encode(png).decode()
    resp = await client.chat.completions.create(
        model=settings.pdf_ocr_model,
        temperature=0.0,
        max_tokens=settings.pdf_ocr_max_output_tokens,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": OCR_PROMPT},
                {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
            ],
        }],
    )
    text = _clean(resp.choices[0].message.content or "")
    if resp.usage:
        logger.info("OCR page %d: %d prompt + %d completion tokens", page_number, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        if usage_hook:
            usage_hook(settings.pdf_ocr_model, resp.usage.prompt_tokens, resp.usage.completion_tokens)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


async def ocr_missing_pages(file_bytes: bytes, sections: List[Dict[str, Any]], page_limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """page_limit: OCR only the first N missing pages (used for cost probing)."""
    if not settings.pdf_ocr_enabled or not settings.openai_api_key:
        return sections

    good = {s["metadata"]["page_number"]: s for s in sections if len(s.get("text", "").strip()) >= settings.pdf_ocr_min_chars}
    with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
        total = doc.page_count
        missing = [i for i in range(total) if (i + 1) not in good]
        if not missing:
            return sections
        if len(missing) > settings.pdf_ocr_max_pages:
            logger.warning("PDF has %d pages without text; OCR limited to the first %d.", len(missing), settings.pdf_ocr_max_pages)
            missing = missing[: settings.pdf_ocr_max_pages]
        if page_limit is not None:
            missing = missing[:page_limit]
        # Render synchronously first (PyMuPDF is not async-safe), then transcribe concurrently
        images = {i: doc.load_page(i).get_pixmap(dpi=settings.pdf_ocr_dpi).tobytes("png") for i in missing}

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    sem = asyncio.Semaphore(settings.pdf_ocr_concurrency)
    logger.info("OCR: %d/%d pages have no text layer — transcribing with %s", len(missing), total, settings.pdf_ocr_model)

    async def one(i: int) -> Optional[Dict[str, Any]]:
        async with sem:
            try:
                text = await _transcribe(client, images[i], i + 1)
            except Exception as exc:
                logger.warning("OCR failed for page %d: %s", i + 1, exc)
                return None
        if len(text) < settings.pdf_ocr_min_chars:
            return None
        return {"text": text, "metadata": {"page_number": i + 1, "total_pages": total, "ocr": True}}

    ocr_sections = [s for s in await asyncio.gather(*(one(i) for i in missing)) if s]
    merged = list(good.values()) + ocr_sections
    merged.sort(key=lambda s: s["metadata"]["page_number"])
    logger.info("OCR added %d pages of text.", len(ocr_sections))
    return merged
