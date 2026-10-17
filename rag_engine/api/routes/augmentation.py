"""
System Role: FastAPI route handlers exposing prompt assembly, context augmentation, and token budget auditing endpoints.
Inputs: AugmentationRequest JSON payload containing query, candidate chunks, and optional history.
Outputs: AugmentedPromptResponse JSON payload containing formatted messages, XML context, and citation metadata.
Ref: ARCHITECTURE.md §2.2 Phase B step 5, §5.2 Directory Dictionary
"""

import logging
from fastapi import APIRouter, HTTPException, status

from schemas.augmentation import AugmentationRequest, AugmentedPromptResponse
from prompting.augmenter import PromptAugmenter

logger = logging.getLogger("rag_engine.api.augmentation")

router = APIRouter(prefix="/api/v1/augmentation", tags=["Augmentation"])
augmenter_instance = PromptAugmenter()


@router.post(
    "/assemble",
    response_model=AugmentedPromptResponse,
    status_code=status.HTTP_200_OK,
    summary="Assemble grounded prompt, format context with citations, and audit token budget",
)
async def assemble_augmented_prompt(request: AugmentationRequest) -> AugmentedPromptResponse:
    """
    Executes Phase 5 Augmentation & Prompt Engineering:
    1. Generates modular system prompt with strict anti-hallucination and prompt injection guardrails.
    2. Dynamically audits and enforces token budget with chunk-level priority truncation.
    3. Builds structured <context> block with numbered [1], [2] citation markers.
    4. Packages message sequences into standard ChatMessageDTO objects ready for LLM generation.
    """
    try:
        response = augmenter_instance.assemble(request)
        return response
    except Exception as exc:
        logger.error(f"Augmentation pipeline error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prompt augmentation failed: {str(exc)}",
        )
