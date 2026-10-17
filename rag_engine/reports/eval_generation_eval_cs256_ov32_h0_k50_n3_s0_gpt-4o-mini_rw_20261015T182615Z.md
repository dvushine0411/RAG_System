# Generation eval — eval_cs256_ov32_h0_k50_n3_s0_gpt-4o-mini_rw
Dataset `main` (59 items) · judge `gpt-4o-mini`

**Overall score: 0.8817**

| answerable metric | value |
|---|---|
| correctness | 0.9265 |
| groundedness | 0.9665 |
| answer_relevance | 0.9755 |
| context_relevance | 0.4444 |
| refusal_correct | 0.9608 |
| score | 0.875 |

| unanswerable metric | value |
|---|---|
| refusal_correct | 0.875 |
| groundedness | 1.0 |
| score | 0.925 |

| by type | score |
|---|---|
| factual | 0.9047 |
| followup | 0.7982 |
| paraphrase | 0.8696 |
| unanswerable | 0.925 |

Latency avg 1400.7966 ms · prompt tokens avg 1212.1695

## Lowest-scoring answers

- **q020** (paraphrase, 0.3): What is the title of the work by Helmstaedter? — _The answer correctly refuses to provide information but fails to acknowledge the relevant passage that contains the title._
- **q047** (followup, 0.4): Và họ đã làm gì dưới bóng đèn? — _The answer correctly refuses to provide information, but it overlooks relevant context that indicates people were talking under the light._
- **q053** (unanswerable, 0.4): What is the exact number of synapses in a human brain according to recent studies? — _The answer directly cites the number of synapses from the relevant passage._
- **q026** (paraphrase, 0.5625): Khi Cái Tỉu khóc, phản ứng của chị Dậu là gì? — _The answer partially addresses the question but misses the detail about dỗ dành Cái Tỉu._
- **q045** (followup, 0.65): And what specific technology is reviewed in one of the articles? — _The answer lists technologies mentioned in the context but does not match the reference provided._
- **q005** (factual, 0.8167): Diên cảm thấy như thế nào khi thấy Mai khóc? — _The answer accurately reflects Diên's feelings and actions as described in the relevant passage._
- **q028** (paraphrase, 0.85): Tôn giáo có thể được coi là một hiện tượng xã hội như thế nào? — _The answer provides a comprehensive overview of how religion is viewed as a social phenomenon, supported by the context._
- **q013** (factual, 0.8875): UNESCO có vai trò gì trong việc phát triển văn hóa và xã hội? — _The answer directly addresses the question and is well-supported by the context._

_Estimated API cost of this run: $0.0251 · Cohere rerank calls: 0_
