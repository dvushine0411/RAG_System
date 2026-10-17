"""
System Role: Package initialization for prompting and augmentation modules.
Inputs: N/A
Outputs: Exported PromptAugmenter, assemble_context, build_system_prompt, and TokenBudgetManager.
Ref: ARCHITECTURE.md §5.2 Directory Dictionary
"""

from prompting.augmenter import PromptAugmenter
from prompting.system_prompt import build_system_prompt
from prompting.context_assembler import assemble_context
from prompting.token_budget import TokenBudgetManager

__all__ = [
    "PromptAugmenter",
    "build_system_prompt",
    "assemble_context",
    "TokenBudgetManager",
]
