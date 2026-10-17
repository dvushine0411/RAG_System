"""
rag_engine/ingestion/parsers/pdf_parser.py
PDF document text and metadata parser using PyMuPDF (fitz).
Extracts text page-by-page to retain page numbering in chunk metadata.
"""

from typing import Any, Dict, List
import pymupdf


def parse_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parses a PDF byte stream and returns a list of page records.

    Args:
        file_bytes: Raw bytes of the PDF file.

    Returns:
        List of dicts: [{"text": str, "metadata": {"page_number": int, "total_pages": int}}]
    """
    results: List[Dict[str, Any]] = []

    with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:

        total_pages = doc.page_count
        for page_index in range(total_pages):
            page = doc.load_page(page_index)
            raw_text = page.get_text("text")
            text = raw_text.strip() if isinstance(raw_text, str) else str(raw_text).strip()
            if text:


                results.append({
                    "text": text,
                    "metadata": {
                        "page_number": page_index + 1,
                        "total_pages": total_pages,
                    }
                })

    return results
