"""
System Role: Prompt Augmenter orchestrator coordinating System Prompt generation, Token Budgeting, Context Assembly, and Message sequencing.
Inputs: AugmentationRequest DTO containing query, candidate chunks, and optional conversation history.
Outputs: AugmentedPromptResponse containing formatted messages ready for LLM generation with citation metadata.
Ref: ARCHITECTURE.md §2.2 Phase B step 5, §5.2 Directory Dictionary
"""

import logging
from typing import List

from prompting.system_prompt import build_system_prompt
from prompting.context_assembler import assemble_context
from prompting.token_budget import TokenBudgetManager
from schemas.augmentation import (
    AugmentationRequest,
    AugmentedPromptResponse,
    ChatMessageDTO,
)

logger = logging.getLogger("rag_engine.prompting.augmenter")


class PromptAugmenter:
    """
    Coordinates the Phase 5 Augmentation pipeline:
    System Prompt -> Token Budget Manager -> Context Assembler -> Structured Chat Messages.
    """

    def assemble(self, request: AugmentationRequest) -> AugmentedPromptResponse:
        """
        Executes end-to-end prompt augmentation:
        1. Generates modular system prompt with strict grounding rules.
        2. Applies TokenBudgetManager to prune history and chunks according to model limits.
        3. Formats accepted chunks into <context> XML blocks with numbered [1], [2] tags.
        4. Packages message sequences into standard ChatMessageDTO objects.
        """
        query_text = request.query.strip()
        logger.info(f"[PromptAugmenter] Assembling prompt for query: '{query_text[:50]}...'")

        # 1. Build System Prompt
        system_prompt = build_system_prompt(custom_role=request.custom_system_role)

        # 2. Allocate Token Budget & Prune Components
        budget_manager = TokenBudgetManager(
            max_context_tokens=request.max_context_tokens,
            reserved_output_tokens=request.reserved_output_tokens,
        )
        accepted_chunks, pruned_history, budget_report = budget_manager.allocate_budget(
            system_prompt=system_prompt,
            query=query_text,
            candidate_chunks=request.chunks,
            conversation_history=request.conversation_history,
        )

        # 3. Assemble Context Block & Citation Catalog
        context_block, citations = assemble_context(chunks=accepted_chunks)

        # 4. Construct Final Message Sequence
        assembled_messages: List[ChatMessageDTO] = []

        # System message (grounding & guardrails)
        assembled_messages.append(ChatMessageDTO(role="system", content=system_prompt))

        # Multi-turn history turns
        for hist_msg in pruned_history:
            assembled_messages.append(hist_msg)

        # Final User message embedding the grounded context block
        final_user_content = (
            f"{context_block}\n\n"
            f"User Question:\n{query_text}"
        )
        assembled_messages.append(ChatMessageDTO(role="user", content=final_user_content))

        logger.info(
            f"[PromptAugmenter] Assembled {len(assembled_messages)} messages with "
            f"{len(citations)} citations. Chunks accepted: {budget_report.chunks_included}/"
            f"{budget_report.chunks_included + budget_report.chunks_truncated}."
        )

        return AugmentedPromptResponse(
            query=query_text,
            system_prompt=system_prompt,
            context_block=context_block,
            assembled_messages=assembled_messages,
            citations=citations,
            budget_report=budget_report,
        )
