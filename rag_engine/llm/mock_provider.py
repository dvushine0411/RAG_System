"""
System Role: Deterministic offline Mock LLM provider streaming grounded responses with citations for CI/CD and offline testing.
Inputs: List of ChatMessageDTO instances, optional temperature and max token ceiling.
Outputs: AsyncIterator yielding token fragments containing citation tags [1], [2] without network requests.
Ref: ARCHITECTURE.md §2.2 Phase B step 6-7, Phase 6
"""

import asyncio
import re
from typing import AsyncIterator, List, Optional
from schemas.augmentation import ChatMessageDTO
from llm.base import BaseLLMProvider


class MockLLMProvider(BaseLLMProvider):
    """
    Offline deterministic LLM mock generating grounded streaming responses with citations.
    """

    def __init__(self, model_name: str = "mock-llm-v1", chunk_delay: float = 0.0) -> None:
        super().__init__(model_name=model_name)
        self.chunk_delay = chunk_delay

    async def generate_stream(
        self,
        messages: List[ChatMessageDTO],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """
        Stream tokens deterministically based on input messages and context citations.
        """
        # Find user message content
        user_content = ""
        context_content = ""
        for msg in messages:
            if msg.role == "user":
                user_content = msg.content
            if "<context>" in msg.content:
                context_content = msg.content

        # Check for citation markers like [1], [2] inside context
        citation_tags = re.findall(r"\[\d+\]", context_content)

        if not context_content or not citation_tags:
            # Ungrounded or empty context fallback
            simulated_response = (
                "Dựa trên tài liệu được cung cấp, tôi không tìm thấy thông tin để trả lời câu hỏi này."
            )
        else:
            # Deterministic grounded response referencing available citations
            tags_str = " ".join(citation_tags[:2])
            simulated_response = (
                f"Theo thông tin từ tài liệu {tags_str}, hệ thống RAG thực hiện tìm kiếm "
                f"ngữ nghĩa chính xác bằng đồ thị HNSW và tái xếp hạng Cross-Encoder. "
                f"Mọi câu trả lời đều được đối chiếu trực tiếp với tài liệu gốc {tags_str}."
            )

        # Tokenize by words and punctuation to simulate realistic streaming deltas
        words = re.findall(r"\S+|\s+", simulated_response)
        for token in words:
            if self.chunk_delay > 0.0:
                await asyncio.sleep(self.chunk_delay)
            yield token
