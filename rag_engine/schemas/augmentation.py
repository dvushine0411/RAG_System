"""
System Role: Pydantic schemas defining chat messages, citation metadata, token budget auditing, and augmented prompt DTOs.
Inputs: Retrieved chunk candidates, user query, conversation history, and optional token budget overrides.
Outputs: Strongly-typed validation models enforcing structured prompt assembly and citation tracking.
Ref: ARCHITECTURE.md §2.2 Phase B step 5, §5.2 Directory Dictionary
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from schemas.retrieval import ScoredChunkDTO


class ChatMessageDTO(BaseModel):
    """
    Standard chat message representation compatible with OpenAI, Anthropic, and Gemini SDKs.
    """
    role: str = Field(..., description="Message role: 'system', 'user', or 'assistant'")
    content: str = Field(..., min_length=1, description="Message text content")


class CitationMetadata(BaseModel):
    """
    Citation mapping tying in-text citation markers ([1], [2]) directly to source chunk provenance.
    """
    citation_id: int = Field(..., description="1-indexed numeric citation reference (e.g. 1 for [1])")
    chunk_id: str = Field(..., description="Qdrant point UUID of the referenced chunk")
    document_id: str = Field(..., description="UUID of the parent document")
    title: Optional[str] = Field(default=None, description="Document title or filename")
    source_type: str = Field(default="unknown", description="Source format ('pdf', 'docx', etc.)")
    page_number: Optional[int] = Field(default=None, description="Page number if applicable")
    section_title: Optional[str] = Field(default=None, description="Section heading if applicable")
    score: float = Field(..., description="Relevance / rerank score of the chunk")


class TokenBudgetReport(BaseModel):
    """
    Detailed audit log tracking token consumption across all prompt components.
    """
    system_tokens: int = Field(..., description="Tokens allocated to System Prompt and guardrails")
    query_tokens: int = Field(..., description="Tokens consumed by user query")
    history_tokens: int = Field(..., description="Tokens consumed by multi-turn conversation history")
    context_tokens: int = Field(..., description="Tokens consumed by assembled context chunks")
    total_prompt_tokens: int = Field(..., description="Total input tokens across all prompt components")
    max_context_tokens: int = Field(..., description="Configured ceiling for total context window")
    reserved_output_tokens: int = Field(..., description="Tokens reserved for LLM response generation")
    chunks_included: int = Field(..., description="Count of chunks successfully fitted into budget")
    chunks_truncated: int = Field(..., description="Count of chunks truncated or dropped due to budget limit")


class AugmentationRequest(BaseModel):
    """
    Payload for assembling an augmented prompt from retrieved chunks and user query.
    """
    query: str = Field(..., min_length=1, description="User search query or prompt")
    chunks: List[ScoredChunkDTO] = Field(default_factory=list, description="Candidate chunks from retrieval pipeline")
    conversation_history: Optional[List[ChatMessageDTO]] = Field(
        default=None,
        description="Prior conversation turns for multi-turn grounding"
    )
    custom_system_role: Optional[str] = Field(
        default=None,
        description="Optional domain persona or role override for system instructions"
    )
    max_context_tokens: Optional[int] = Field(
        default=None,
        ge=512,
        le=128000,
        description="Override for max context token limit (defaults to settings.max_context_tokens)"
    )
    reserved_output_tokens: Optional[int] = Field(
        default=None,
        ge=128,
        le=8192,
        description="Override for tokens reserved for generation (defaults to settings.reserved_output_tokens)"
    )


class AugmentedPromptResponse(BaseModel):
    """
    Final assembled prompt package ready for streaming LLM generation in Phase 6.
    """
    query: str = Field(..., description="Original user query")
    system_prompt: str = Field(..., description="Complete system prompt with anti-hallucination guardrails")
    context_block: str = Field(..., description="Structured XML/Markdown context with [1], [2] citation tags")
    assembled_messages: List[ChatMessageDTO] = Field(
        ...,
        description="Complete list of formatted messages ready for LLM API invocation"
    )
    citations: List[CitationMetadata] = Field(
        default_factory=list,
        description="Complete provenance citation catalog for client citation rendering"
    )
    budget_report: TokenBudgetReport = Field(..., description="Token usage audit report")
