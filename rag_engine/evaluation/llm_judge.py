"""
System Role: LLM-as-judge scoring one generated answer on the RAG Triad + correctness + refusal behaviour.
Inputs: Question, retrieved context chunks (as numbered passages), generated answer, reference answer,
        whether the question is answerable; settings.eval_judge_model.
Outputs: JudgeScores — groundedness [0,1], context_relevance [0,1], answer_relevance [0,1],
         correctness [0,1] (None for unanswerable), refused (bool), refusal_correct (bool), rationale.
"""

from dataclasses import asdict, dataclass
from typing import List, Optional

from config import settings
from evaluation.openai_json import chat_json
from schemas.retrieval import ScoredChunkDTO

JUDGE_SYSTEM = """You are a strict evaluator of a retrieval-augmented question answering system. Score objectively.

You receive: the QUESTION, numbered CONTEXT passages that were given to the system, the system's ANSWER and,
when available, a REFERENCE answer written from the source document.

Return JSON with:
- "relevant_passages": list of passage numbers that contain information useful to answer the QUESTION.
- "claims_total": number of factual claims in the ANSWER (0 if it only refuses).
- "claims_supported": how many of those claims are explicitly supported by the CONTEXT (not by world knowledge).
- "answer_relevance": 1-5, how directly and completely the ANSWER addresses the QUESTION (5 = fully, concise, on point;
   for a refusal: 5 if refusing was appropriate given the CONTEXT, 1 if the CONTEXT clearly contained the answer).
- "correctness": 1-5 agreement of the ANSWER with the REFERENCE (5 = same facts, nothing wrong or missing;
   1 = wrong or missing the key fact). Use null when no REFERENCE is given.
- "refused": true if the ANSWER declines to answer / says the information is not in the documents.
- "rationale": one short sentence."""


@dataclass
class JudgeScores:
    groundedness: float
    context_relevance: float
    answer_relevance: float
    correctness: Optional[float]
    refused: bool
    refusal_correct: bool
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def _context_block(chunks: List[ScoredChunkDTO]) -> str:
    if not chunks:
        return "(no passages)"
    return "\n\n".join(f"[{i}] {c.content.strip()[:2500]}" for i, c in enumerate(chunks, start=1))


async def judge(
    question: str,
    chunks: List[ScoredChunkDTO],
    answer: str,
    reference: Optional[str],
    answerable: bool,
) -> JudgeScores:
    user = (
        f"QUESTION:\n{question}\n\nCONTEXT:\n{_context_block(chunks)}\n\nANSWER:\n{answer.strip() or '(empty)'}\n\n"
        f"REFERENCE:\n{reference if reference else '(none — no reference available)'}"
    )
    d = await chat_json(settings.eval_judge_model, JUDGE_SYSTEM, user, temperature=0.0, max_tokens=400)

    refused = bool(d.get("refused", False))
    total = int(d.get("claims_total") or 0)
    supported = min(int(d.get("claims_supported") or 0), total)
    # A pure refusal makes no unsupported claims: it is fully grounded.
    groundedness = 1.0 if total == 0 else supported / total
    relevant = {int(p) for p in d.get("relevant_passages", []) if str(p).isdigit() and 1 <= int(p) <= len(chunks)}
    context_relevance = (len(relevant) / len(chunks)) if chunks else (0.0 if answerable else 1.0)
    correctness = d.get("correctness")
    return JudgeScores(
        groundedness=round(groundedness, 4),
        context_relevance=round(context_relevance, 4),
        answer_relevance=round((float(d.get("answer_relevance") or 1) - 1) / 4, 4),
        correctness=None if (not answerable or correctness is None) else round((float(correctness) - 1) / 4, 4),
        refused=refused,
        refusal_correct=(refused == (not answerable)),
        rationale=str(d.get("rationale", ""))[:300],
    )
