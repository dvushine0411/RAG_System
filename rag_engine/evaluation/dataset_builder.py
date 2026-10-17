"""
System Role: Generates the evaluation dataset (questions + reference answers + verbatim evidence) from the
             chunks of an indexed eval collection, using an LLM (settings.eval_dataset_model).
Inputs: Eval collection name, target question counts per type, random seed.
Outputs: evaluation/datasets/<name>.json — list of items:
         {id, type: factual|paraphrase|followup|unanswerable, question, history[], reference_answer,
          evidence, document, language}
Quality gates: evidence must appear verbatim in its source chunk (else dropped); items are meant to be
               human-reviewed before optimisation runs.
"""

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from config import settings
from evaluation.corpus import scroll_chunks
from evaluation.evidence import evidence_in_text
from evaluation.openai_json import chat_json

DATASET_DIR = Path(__file__).resolve().parent / "datasets"
MIN_CHUNK_TOKENS = 60

QA_SYSTEM = """You create evaluation data for a retrieval-augmented QA system.
Given ONE passage from a document, write questions a real user could ask whose answer is contained in the passage.
Rules:
- Write in the SAME language as the passage.
- "evidence" MUST be copied VERBATIM from the passage (8-30 consecutive words) and must contain the answer.
- "answer" is a concise, complete reference answer (1-3 sentences) using only the passage.
- "factual": asks directly using the passage's own key terms.
- "paraphrase": same information need but reworded with synonyms, avoiding the passage's exact key phrases.
Return JSON: {"items": [{"type": "factual"|"paraphrase", "question": str, "answer": str, "evidence": str}]}"""

FOLLOWUP_SYSTEM = """You create a 2-turn conversation for evaluating a retrieval-augmented chat assistant.
Given ONE passage, write:
1. "first_question": a question about the passage's main topic.
2. "first_answer": a short answer to it from the passage.
3. "followup": a natural follow-up that depends on the first turn (uses a pronoun or omits the topic, e.g. "And how is it configured?") and asks about a DIFFERENT detail of the same passage.
4. "answer": reference answer to the follow-up, from the passage only.
5. "evidence": VERBATIM 8-30 consecutive words from the passage containing the follow-up's answer.
Write in the SAME language as the passage.
Return JSON: {"first_question": str, "first_answer": str, "followup": str, "answer": str, "evidence": str}"""

UNANSWERABLE_SYSTEM = """You create "unanswerable" questions for evaluating hallucination resistance of a document QA system.
Given short excerpts of every document in the knowledge base, write questions that sound on-topic and plausible
for this knowledge base but whose answers are NOT contained in any excerpt or document (e.g. ask for a specific
number, date, person, or comparison that the documents never mention). Mix the documents' languages.
Return JSON: {"items": [{"question": str, "language": "vi"|"en"}]}"""


def _language(text: str) -> str:
    vi_chars = set("ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ")
    return "vi" if sum(ch in vi_chars for ch in text.lower()) > 3 else "en"


def _pick_chunks(chunks: List[dict], n: int, rng: random.Random) -> List[dict]:
    """Round-robin across documents so every document contributes questions."""
    by_doc: Dict[str, List[dict]] = defaultdict(list)
    for c in chunks:
        if c.get("token_count", 0) >= MIN_CHUNK_TOKENS:
            by_doc[c["filename"]].append(c)
    for lst in by_doc.values():
        rng.shuffle(lst)
    picked: List[dict] = []
    while len(picked) < n and any(by_doc.values()):
        for doc in sorted(by_doc):
            if by_doc[doc] and len(picked) < n:
                picked.append(by_doc[doc].pop())
    return picked


async def build_dataset(collection: str, n_passages: int, n_followup: int, n_unanswerable: int, seed: int, name: str) -> Path:
    rng = random.Random(seed)
    chunks = await scroll_chunks(collection)
    if not chunks:
        raise RuntimeError(f"Collection '{collection}' is empty — run the 'index' command first.")
    model = settings.eval_dataset_model
    items: List[dict] = []
    dropped = 0

    for chunk in _pick_chunks(chunks, n_passages, rng):
        data = await chat_json(model, QA_SYSTEM, f"Document: {chunk['filename']}\nPassage:\n{chunk['content']}", temperature=0.3)
        for q in data.get("items", [])[:2]:
            if not evidence_in_text(q.get("evidence", ""), chunk["content"]):
                dropped += 1
                continue
            items.append({
                "type": q.get("type", "factual"), "question": q["question"], "history": [],
                "reference_answer": q["answer"], "evidence": q["evidence"], "document": chunk["filename"],
                "language": _language(chunk["content"]),
            })

    for chunk in _pick_chunks(chunks, n_followup, random.Random(seed + 1)):
        d = await chat_json(model, FOLLOWUP_SYSTEM, f"Document: {chunk['filename']}\nPassage:\n{chunk['content']}", temperature=0.3)
        if not all(k in d for k in ("first_question", "first_answer", "followup", "answer", "evidence")) or not evidence_in_text(d["evidence"], chunk["content"]):
            dropped += 1
            continue
        items.append({
            "type": "followup", "question": d["followup"],
            "history": [{"role": "user", "content": d["first_question"]}, {"role": "assistant", "content": d["first_answer"]}],
            "reference_answer": d["answer"], "evidence": d["evidence"], "document": chunk["filename"],
            "language": _language(chunk["content"]),
        })

    excerpts: Dict[str, str] = {}
    for c in chunks:
        excerpts.setdefault(c["filename"], "")
        if len(excerpts[c["filename"]]) < 1200:
            excerpts[c["filename"]] += " " + c["content"][:600]
    overview = "\n\n".join(f"## {doc}\n{text.strip()}" for doc, text in excerpts.items())
    d = await chat_json(model, UNANSWERABLE_SYSTEM, f"Write {n_unanswerable} questions.\n\n{overview}", temperature=0.5)
    for q in d.get("items", [])[:n_unanswerable]:
        items.append({
            "type": "unanswerable", "question": q["question"], "history": [], "reference_answer": "",
            "evidence": "", "document": None, "language": q.get("language", _language(q["question"])),
        })

    for i, item in enumerate(items, start=1):
        item["id"] = f"q{i:03d}"
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    path = DATASET_DIR / f"{name}.json"
    path.write_text(json.dumps({"source_collection": collection, "seed": seed, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = defaultdict(int)
    for it in items:
        counts[it["type"]] += 1
    print(f"  dataset '{path.name}': {len(items)} items {dict(counts)} (dropped {dropped} with non-verbatim evidence)")
    return path


def load_dataset(name: str) -> List[dict]:
    return json.loads((DATASET_DIR / f"{name}.json").read_text(encoding="utf-8"))["items"]
