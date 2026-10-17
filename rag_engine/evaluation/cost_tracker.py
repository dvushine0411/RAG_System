"""
System Role: Tracks token usage and estimated USD cost of evaluation API calls; enforces the budget hard stop.
Inputs: (model, prompt_tokens, completion_tokens) per call; settings.eval_pricing_per_million, eval_budget_usd.
Outputs: Running totals per model, summary dict for reports; raises BudgetExceeded once the budget is passed.
"""

from collections import defaultdict
from typing import Dict

from config import settings


class BudgetExceeded(RuntimeError):
    pass


class CostTracker:
    def __init__(self, budget_usd: float | None = None) -> None:
        self.budget = settings.eval_budget_usd if budget_usd is None else budget_usd
        self.tokens: Dict[str, list] = defaultdict(lambda: [0, 0, 0])  # prompt, completion, calls
        self.cohere_calls = 0

    def _price(self, model: str) -> tuple[float, float]:
        for key, (inp, out) in sorted(settings.eval_pricing_per_million.items(), key=lambda kv: -len(kv[0])):
            if model.startswith(key):
                return inp, out
        return settings.eval_pricing_per_million["gpt-4o"]  # unknown model: price conservatively

    def add(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        entry = self.tokens[model]
        entry[0] += prompt_tokens
        entry[1] += completion_tokens
        entry[2] += 1
        if self.total_usd() > self.budget:
            raise BudgetExceeded(f"Estimated OpenAI spend ${self.total_usd():.3f} exceeded budget ${self.budget:.2f}")

    def total_usd(self) -> float:
        total = 0.0
        for model, (p, c, _) in self.tokens.items():
            inp, out = self._price(model)
            total += p / 1e6 * inp + c / 1e6 * out
        return total

    def summary(self) -> dict:
        return {
            "estimated_usd": round(self.total_usd(), 4),
            "budget_usd": self.budget,
            "cohere_rerank_calls": self.cohere_calls,
            "by_model": {m: {"prompt_tokens": p, "completion_tokens": c, "calls": n} for m, (p, c, n) in self.tokens.items()},
        }


TRACKER = CostTracker()
