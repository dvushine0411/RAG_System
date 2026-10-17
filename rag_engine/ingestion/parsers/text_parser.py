"""
rag_engine/ingestion/parsers/text_parser.py
Plain text parser with multi-encoding fallback support.
"""

from typing import Any, Dict, List


def parse_text(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parses a plain text file bytes stream.

    Args:
        file_bytes: Raw bytes of the text file.

    Returns:
        List of dicts: [{"text": str, "metadata": {"source_type": "text"}}]
    """
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    decoded_text = ""

    for enc in encodings:
        try:
            decoded_text = file_bytes.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if not decoded_text:
        decoded_text = file_bytes.decode("utf-8", errors="replace")

    clean_text = decoded_text.strip()
    if not clean_text:
        return []

    return [{
        "text": clean_text,
        "metadata": {"source_type": "text"}
    }]
