"""
System Role: Production LLM client interfacing with Anthropic Claude API with token streaming.
Inputs: Sequence of ChatMessageDTO instances, optional sampling temperature and token limit.
Outputs: AsyncIterator yielding string token deltas streamed directly from Anthropic Claude.
Ref: ARCHITECTURE.md §2.2 Phase B step 6-7, Phase 6
"""

import logging
from typing import AsyncIterator, List, Optional
from config import settings
from schemas.augmentation import ChatMessageDTO
from llm.base import BaseLLMProvider

logger = logging.getLogger("rag_engine.llm.anthropic")


class AnthropicLLMProvider(BaseLLMProvider):
    """
    Anthropic Claude provider streaming tokens asynchronously.
    """

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None) -> None:
        model = model_name or "claude-3-5-sonnet-20241022"
        super().__init__(model_name=model)
        self.api_key = api_key or settings.anthropic_api_key

    async def generate_stream(
        self,
        messages: List[ChatMessageDTO],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Stream tokens from Anthropic Messages streaming API.
        """
        try:
            from anthropic import AsyncAnthropic  # type: ignore # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK is not installed. Please install anthropic or select another provider."
            ) from exc

        client = AsyncAnthropic(api_key=self.api_key)

        # Separate system message from conversation turns (Anthropic API requirement)
        system_text = ""
        chat_turns: List[dict[str, str]] = []
        for msg in messages:
            if msg.role == "system":
                system_text += f"{msg.content}\n"
            else:
                chat_turns.append({"role": msg.role, "content": msg.content})

        temp = temperature if temperature is not None else settings.llm_temperature
        token_limit = max_tokens or settings.reserved_output_tokens

        try:
            async with client.messages.stream(
                model=self.model_name,
                system=system_text.strip() or None,
                messages=chat_turns,
                temperature=temp,
                max_tokens=token_limit,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            logger.error("Anthropic streaming error: %s", exc)
            raise exc
