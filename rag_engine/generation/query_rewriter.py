"""
System Role: Conversational query rewriter — condenses a follow-up question plus chat history into a
             standalone search query used ONLY for retrieval (the LLM still answers the original question).
Inputs: User query, conversation history (ChatMessageDTO list), settings.query_rewrite_* options.
Outputs: Standalone query string; falls back to the original query on any error or when history is empty.
Why: follow-ups like "And how is it handled?" carry no searchable topic on their own.
"""

import logging
from typing import List, Optional

from config import settings
from llm.factory import get_llm_provider
from llm.mock_provider import MockLLMProvider
from schemas.augmentation import ChatMessageDTO

logger = logging.getLogger("rag_engine.generation.query_rewriter")

REWRITE_INSTRUCTIONS = (
    "You rewrite the user's latest message into a standalone search query for a document retrieval system.\n"
    "- Resolve pronouns and implicit references using the conversation.\n"
    "- Keep every specific term, name, number and acronym.\n"
    "- Use the same language as the latest message.\n"
    "- If the message is already standalone, return it unchanged.\n"
    "- Output ONLY the rewritten query, without quotes or explanations."
)


async def rewrite_query(
    query: str,
    history: Optional[List[ChatMessageDTO]],
    model: Optional[str] = None,
) -> str:
    turns = [m for m in (history or []) if m.role in ("user", "assistant") and m.content.strip()]
    if not turns:
        return query

    recent = turns[-settings.query_rewrite_history_turns :]
    transcript = "\n".join(f"{m.role.upper()}: {m.content.strip()[:1500]}" for m in recent)
    messages = [
        ChatMessageDTO(role="system", content=REWRITE_INSTRUCTIONS),
        ChatMessageDTO(role="user", content=f"Conversation:\n{transcript}\n\nLatest message: {query}\n\nStandalone query:"),
    ]

    try:
        provider = get_llm_provider(model_name=model or settings.query_rewrite_model or None)
        if isinstance(provider, MockLLMProvider):
            return query  # mock output is canned text, never a usable query
        parts = [d async for d in provider.generate_stream(messages=messages, temperature=0.0, max_tokens=settings.query_rewrite_max_tokens)]
        rewritten = "".join(parts).strip().strip('"').strip()
        if not rewritten:
            return query
        logger.info("Rewrote follow-up %r -> %r", query[:80], rewritten[:120])
        return rewritten
    except Exception as exc:
        logger.warning("Query rewrite failed (%s); using original query.", exc)
        return query
