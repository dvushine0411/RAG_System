"""
System Role: Production LLM client interfacing with OpenAI Chat Completions API with streaming deltas and retry logic.
Inputs: Sequence of ChatMessageDTO instances, optional sampling temperature and token limit.
Outputs: AsyncIterator yielding string token deltas streamed directly from OpenAI.
Ref: ARCHITECTURE.md §2.2 Phase B step 6-7, Phase 6
"""

import logging
from typing import AsyncIterator, List, Optional
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from schemas.augmentation import ChatMessageDTO
from llm.base import BaseLLMProvider

logger = logging.getLogger("rag_engine.llm.openai")


class OpenAILLMProvider(BaseLLMProvider):
    """
    OpenAI Chat Completion provider streaming tokens asynchronously.
    """

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None) -> None:
        model = model_name or settings.llm_model or "gpt-4o"
        super().__init__(model_name=model)
        key = api_key or settings.openai_api_key
        self._client = AsyncOpenAI(api_key=key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _create_stream(
        self,
        formatted_messages: List[dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
    ):
        """Invoke OpenAI chat completions API with stream=True."""
        kwargs: dict[str, object] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        return await self._client.chat.completions.create(**kwargs)  # type: ignore

    async def generate_stream(
        self,
        messages: List[ChatMessageDTO],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Stream token deltas from OpenAI Chat Completions endpoint.
        """
        temp = temperature if temperature is not None else settings.llm_temperature
        formatted_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        try:
            stream = await self._create_stream(
                formatted_messages=formatted_messages,
                temperature=temp,
                max_tokens=max_tokens,
            )
            async for chunk in stream:  # type: ignore
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            logger.error("OpenAI streaming generation error: %s", exc)
            raise exc
