"""
rag_engine/ingestion/parsers/html_parser.py
HTML content parser using BeautifulSoup4.
Strips script, style, navigation, and footer elements while extracting semantic body text.
"""

from typing import Any, Dict, List
from bs4 import BeautifulSoup


def parse_html(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parses an HTML document byte stream and returns extracted semantic text.

    Args:
        file_bytes: Raw bytes of the HTML document.

    Returns:
        List of dicts: [{"text": str, "metadata": {"page_title": str}}]
    """
    html_str = file_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html_str, "html.parser")

    # Remove unwanted tags
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()

    page_title = str(soup.title.string).strip() if (soup.title and soup.title.string) else "HTML Document"


    # Extract text with line breaks between blocks
    text = soup.get_text(separator="\n", strip=True)
    if not text:
        return []

    return [{
        "text": text,
        "metadata": {
            "page_title": page_title,
            "source_type": "html"
        }
    }]
