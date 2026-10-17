"""
System Role: Token Budget Manager dynamically auditing and truncating prompt components to respect model context windows.
Inputs: System prompt string, user query, conversation history messages, candidate chunks, and token limits.
Outputs: Selected chunks, pruned history messages, and a comprehensive TokenBudgetReport.
Ref: ARCHITECTURE.md §2.2 Phase B step 5, §5.2 Directory Dictionary
"""

import logging
from typing import List, Optional, Tuple

from config import settings
from ingestion.chunking import count_tokens
from schemas.augmentation import ChatMessageDTO, TokenBudgetReport
from schemas.retrieval import ScoredChunkDTO

logger = logging.getLogger("rag_engine.prompting.budget")


class TokenBudgetManager:
    """
    Manages token allocation across System Prompt, Query, History, and Context chunks.
    Applies Chunk-Level Priority Truncation based on relevance scores.
    """

    def __init__(
        self,
        max_context_tokens: Optional[int] = None,
        reserved_output_tokens: Optional[int] = None,
    ):
        self.max_context_tokens = (
            max_context_tokens
            if max_context_tokens is not None
            else settings.max_context_tokens
        )
        self.reserved_output_tokens = (
            reserved_output_tokens
            if reserved_output_tokens is not None
            else settings.reserved_output_tokens
        )

    def allocate_budget(
        self,
        system_prompt: str,
        query: str,
        candidate_chunks: List[ScoredChunkDTO],
        conversation_history: Optional[List[ChatMessageDTO]] = None,
    ) -> Tuple[List[ScoredChunkDTO], List[ChatMessageDTO], TokenBudgetReport]:
        """
        Calculates token consumption and prunes context chunks to fit within the available budget.

        Strategy:
        1. Fixed reservation: System Prompt + Query are guaranteed 100% full allocation.
        2. Generation reservation: Reserved tokens set aside for LLM response generation.
        3. History pruning: Prioritizes recent conversation turns (up to 20% of net budget).
        4. Context Chunk Truncation: Fills remaining budget with candidate chunks in descending score order.
        """
        # 1. Calculate essential fixed tokens
        system_tokens = count_tokens(system_prompt)
        query_tokens = count_tokens(query)

        net_budget = max(0, self.max_context_tokens - self.reserved_output_tokens)
        remaining_budget = max(0, net_budget - (system_tokens + query_tokens))

        # 2. Prune conversation history (most recent turns first)
        selected_history: List[ChatMessageDTO] = []
        history_tokens = 0

        if conversation_history:
            # Allocate up to 25% of remaining budget to history
            max_history_budget = int(remaining_budget * 0.25)
            temp_history: List[ChatMessageDTO] = []
            curr_hist_tokens = 0

            # Iterate backwards (most recent to oldest)
            for msg in reversed(conversation_history):
                msg_tokens = count_tokens(msg.content)
                if curr_hist_tokens + msg_tokens <= max_history_budget:
                    temp_history.append(msg)
                    curr_hist_tokens += msg_tokens
                else:
                    break

            selected_history = list(reversed(temp_history))
            history_tokens = curr_hist_tokens
            remaining_budget -= history_tokens

        # 3. Chunk-Level Priority Truncation
        accepted_chunks: List[ScoredChunkDTO] = []
        context_tokens = 0
        truncated_count = 0

        # Sort candidate chunks strictly descending by final relevance score
        sorted_chunks = sorted(candidate_chunks, key=lambda c: c.final_score, reverse=True)

        for chunk in sorted_chunks:
            # Estimate chunk tokens including citation wrapper overhead (~25 tokens)
            chunk_token_est = count_tokens(chunk.content) + 25

            if context_tokens + chunk_token_est <= remaining_budget:
                accepted_chunks.append(chunk)
                context_tokens += chunk_token_est
            else:
                truncated_count += 1

        total_prompt_tokens = system_tokens + query_tokens + history_tokens + context_tokens

        logger.info(
            f"[TokenBudgetManager] Budget allocation: System={system_tokens}, Query={query_tokens}, "
            f"History={history_tokens}, Context={context_tokens} (Chunks: {len(accepted_chunks)}/{len(candidate_chunks)}). "
            f"Total input={total_prompt_tokens} / Net budget={net_budget}."
        )

        budget_report = TokenBudgetReport(
            system_tokens=system_tokens,
            query_tokens=query_tokens,
            history_tokens=history_tokens,
            context_tokens=context_tokens,
            total_prompt_tokens=total_prompt_tokens,
            max_context_tokens=self.max_context_tokens,
            reserved_output_tokens=self.reserved_output_tokens,
            chunks_included=len(accepted_chunks),
            chunks_truncated=truncated_count,
        )

        return accepted_chunks, selected_history, budget_report
