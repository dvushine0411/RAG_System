"""
System Role: Production LLM client interfacing with Google Gemini API with token streaming.
Inputs: Sequence of ChatMessageDTO instances, optional sampling temperature and token limit.
Outputs: AsyncIterator yielding string token deltas streamed directly from Gemini.
Ref: ARCHITECTURE.md §2.2 Phase B step 6-7, Phase 6
"""

import logging
from typing import AsyncIterator, List, Optional
from config import settings
from schemas.augmentation import ChatMessageDTO
from llm.base import BaseLLMProvider

logger = logging.getLogger("rag_engine.llm.gemini")


class GeminiLLMProvider(BaseLLMProvider):
    """
    Google Gemini provider streaming tokens asynchronously using Google GenAI SDK.
    """

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None) -> None:
        model = model_name or "gemini-1.5-pro"
        super().__init__(model_name=model)
        self.api_key = api_key or settings.google_api_key

    async def generate_stream(
        self,
        messages: List[ChatMessageDTO],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Stream tokens from Google Gemini API.
        """
        try:
            from google import genai  # type: ignore # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise RuntimeError(
                "google-genai SDK is not installed. Please install google-genai or select another provider."
            ) from exc

        client = genai.Client(api_key=self.api_key)

        # Build contents from messages
        prompt_parts: List[str] = []
        for msg in messages:
            prompt_parts.append(f"[{msg.role.upper()}]:\n{msg.content}\n")
        full_prompt = "\n".join(prompt_parts)

        try:
            response = client.models.generate_content_stream(
                model=self.model_name,
                contents=full_prompt,
            )
            for chunk in response:
                if hasattr(chunk, "text") and chunk.text:
                    yield chunk.text
        except Exception as exc:
            logger.error("Gemini streaming error: %s", exc)
            raise exc
