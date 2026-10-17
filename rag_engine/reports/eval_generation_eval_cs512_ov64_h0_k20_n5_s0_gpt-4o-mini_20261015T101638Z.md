# Generation eval — eval_cs512_ov64_h0_k20_n5_s0_gpt-4o-mini
Dataset `smoke` (8 items) · judge `gpt-4o-mini`

**Overall score: 0.8988**

| answerable metric | value |
|---|---|
| correctness | 1.0 |
| groundedness | 1.0 |
| answer_relevance | 1.0 |
| context_relevance | 0.2286 |
| refusal_correct | 1.0 |
| score | 0.8843 |

| unanswerable metric | value |
|---|---|
| refusal_correct | 1.0 |
| groundedness | 1.0 |
| score | 1.0 |

| by type | score |
|---|---|
| factual | 0.88 |
| followup | 0.91 |
| paraphrase | 0.88 |
| unanswerable | 1.0 |

Latency avg 1348.375 ms · prompt tokens avg 901.5

## Lowest-scoring answers

- **q001** (factual, 0.88): What serves as the single entry point for all frontend and external service requests? — _The answer directly quotes the relevant passage and accurately reflects the information in the reference._
- **q002** (paraphrase, 0.88): Which component acts as the main access point for requests from the frontend and external services? — _The answer accurately identifies the Fastify API Gateway as the main access point, directly supported by the context._
- **q003** (factual, 0.88): What is the chunk size used in the chunking strategy? — _The answer directly states the chunk size and is fully supported by the relevant context._
- **q004** (paraphrase, 0.88): How many tokens are included in each segment created by the recursive character splitting? — _The answer directly and accurately reflects the information provided in the relevant context._
- **q005** (factual, 0.88): What must all engineering teams adhere to? — _The answer directly and completely addresses the question with supported claims from the context._
- **q006** (paraphrase, 0.88): What is required for a pull request before it can be merged? — _The answer directly and accurately reflects the requirement stated in the context._
- **q007** (followup, 0.91): And what does it do before forwarding files to the ML service? — _The answer accurately summarizes the actions taken by the Fastify API Gateway before forwarding files to the ML service, supported by the context._
- **q008** (unanswerable, 1.0): What is the exact number of tokens required for optimal performance in the ingestion pipeline? — _The answer appropriately refuses to provide information not present in the context._

_Estimated API cost of this run: $0.0024 · Cohere rerank calls: 0_
