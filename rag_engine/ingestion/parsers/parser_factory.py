"""
rag_engine/ingestion/parsers/parser_factory.py
Factory module routing document parsing requests to the appropriate parser.
"""

from typing import Any, Callable, Dict, List
import os

from ingestion.parsers.pdf_parser import parse_pdf
from ingestion.parsers.docx_parser import parse_docx
from ingestion.parsers.markdown_parser import parse_markdown
from ingestion.parsers.text_parser import parse_text
from ingestion.parsers.html_parser import parse_html


_PARSER_MAP: Dict[str, Callable[[bytes], List[Dict[str, Any]]]] = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "doc": parse_docx,
    "md": parse_markdown,
    "markdown": parse_markdown,
    "txt": parse_text,
    "text": parse_text,
    "html": parse_html,
    "htm": parse_html,
}


def get_parser(filename: str, source_type: str = "") -> Callable[[bytes], List[Dict[str, Any]]]:
    """
    Selects the appropriate parser based on source_type or filename extension.

    Args:
        filename: Name of the uploaded file.
        source_type: Optional explicit source format string.

    Returns:
        Parser callable accepting raw bytes and returning list of section dicts.

    Raises:
        ValueError: If file format is unsupported.
    """
    # 1. Check explicit source_type
    normalized_type = source_type.lower().strip()
    if normalized_type in _PARSER_MAP:
        return _PARSER_MAP[normalized_type]

    # 2. Derive from file extension
    _, ext = os.path.splitext(filename)
    clean_ext = ext.lstrip(".").lower()

    if clean_ext in _PARSER_MAP:
        return _PARSER_MAP[clean_ext]

    raise ValueError(
        f"Unsupported document format: '{ext or source_type}'. "
        f"Supported formats: {list(_PARSER_MAP.keys())}"
    )
