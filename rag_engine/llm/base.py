"""
System Role: Abstract Base Class defining standard interface for LLM generation providers.
Inputs: Formatted sequence of ChatMessageDTO instances, optional sampling temperature and token ceiling.
Outputs: Asynchronous token generator yielding string chunks for real-time streaming.
Ref: ARCHITECTURE.md §2.2 Phase B step 6, Phase 6
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional
from schemas.augmentation import ChatMessageDTO


class BaseLLMProvider(ABC):
    """
    Abstract interface that all LLM provider clients (OpenAI, Gemini, Anthropic, Mock) must implement.
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[ChatMessageDTO],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Asynchronously stream generated text tokens.

        Args:
            messages: Chronological sequence of chat messages (System, User, Assistant).
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens allowed in the completion.

        Yields:
            str: Next token or text delta.
        """
        yield ""  # Abstract placeholder

    async def generate(
        self,
        messages: List[ChatMessageDTO],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Non-streaming helper accumulating all tokens into a single text response.

        Args:
            messages: Chronological sequence of chat messages.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens allowed.

        Returns:
            str: Full generated completion text.
        """
        tokens: List[str] = []
        async for token in self.generate_stream(messages, temperature=temperature, max_tokens=max_tokens):
            tokens.append(token)
        return "".join(tokens)
