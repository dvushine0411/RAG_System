"""
rag_engine/ingestion/parsers/markdown_parser.py
Markdown document parser using markdown-it-py.
Parses markdown text into structural segments preserving header hierarchy.
"""

from typing import Any, Dict, List
import re
from markdown_it import MarkdownIt


def parse_markdown(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parses a Markdown byte stream and splits sections by Markdown headers.

    Args:
        file_bytes: Raw bytes of the Markdown file.

    Returns:
        List of dicts: [{"text": str, "metadata": {"section_title": str, "header_level": int}}]
    """
    try:
        raw_text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw_text = file_bytes.decode("utf-8", errors="replace")

    results: List[Dict[str, Any]] = []
    lines = raw_text.splitlines()

    current_header = "Introduction"
    current_level = 1
    current_lines: List[str] = []

    header_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

    for line in lines:
        match = header_pattern.match(line)
        if match:
            # Flush existing section
            body = "\n".join(current_lines).strip()
            if body:
                results.append({
                    "text": body,
                    "metadata": {
                        "section_title": current_header,
                        "header_level": current_level
                    }
                })
            current_level = len(match.group(1))
            current_header = match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    # Flush remainder
    remainder = "\n".join(current_lines).strip()
    if remainder:
        results.append({
            "text": remainder,
            "metadata": {
                "section_title": current_header,
                "header_level": current_level
            }
        })

    return results
