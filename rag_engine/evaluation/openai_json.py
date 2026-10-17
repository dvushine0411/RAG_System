"""
System Role: Minimal OpenAI chat helper returning parsed JSON (response_format=json_object) with cost tracking.
Inputs: model, system/user prompts, temperature; settings.openai_api_key.
Outputs: Parsed dict; usage recorded in cost_tracker.TRACKER. Retries transient errors with exponential backoff.
"""

import json

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from evaluation.cost_tracker import TRACKER

_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for evaluation (dataset generation / LLM judge).")
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=20), reraise=True)
async def chat_json(model: str, system: str, user: str, temperature: float = 0.0, max_tokens: int = 1200) -> dict:
    resp = await client().chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    if resp.usage:
        TRACKER.add(model, resp.usage.prompt_tokens, resp.usage.completion_tokens)
    return json.loads(resp.choices[0].message.content or "{}")
