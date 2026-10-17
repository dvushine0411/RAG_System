# Generation eval — eval_cs256_ov32_h0_k50_n3_s0_gpt-4o-mini_rw_pv1
Dataset `main` (59 items) · judge `gpt-4o-mini`

**Overall score: 0.8832**

| answerable metric | value |
|---|---|
| correctness | 0.9265 |
| groundedness | 0.973 |
| answer_relevance | 0.9755 |
| context_relevance | 0.4444 |
| refusal_correct | 0.9608 |
| score | 0.8766 |

| unanswerable metric | value |
|---|---|
| refusal_correct | 0.875 |
| groundedness | 1.0 |
| score | 0.925 |

| by type | score |
|---|---|
| factual | 0.9085 |
| followup | 0.7768 |
| paraphrase | 0.8764 |
| unanswerable | 0.925 |

Latency avg 1398.5254 ms · prompt tokens avg 1212.1695

## Lowest-scoring answers

- **q047** (followup, 0.25): Và họ đã làm gì dưới bóng đèn? — _The answer correctly refuses to provide information, but the context does contain relevant information about activities under the light._
- **q053** (unanswerable, 0.4): What is the exact number of synapses in a human brain according to recent studies? — _The answer accurately reflects the information provided in the relevant passage._
- **q020** (paraphrase, 0.45): What is the title of the work by Helmstaedter? — _The answer correctly refuses to provide an answer but fails to acknowledge the relevant information present in the context._
- **q026** (paraphrase, 0.5625): Khi Cái Tỉu khóc, phản ứng của chị Dậu là gì? — _The answer provides a partial response but misses the detail of dỗ dành Cái Tỉu from the reference._
- **q045** (followup, 0.65): And what specific technology is reviewed in one of the articles? — _The answer provides a detailed overview of technologies mentioned in the context but does not align with the reference provided._
- **q028** (paraphrase, 0.85): Tôn giáo có thể được coi là một hiện tượng xã hội như thế nào? — _The answer provides a comprehensive overview of how religion is viewed as a social phenomenon, supported by the context._
- **q013** (factual, 0.8875): UNESCO có vai trò gì trong việc phát triển văn hóa và xã hội? — _The answer directly addresses the question and is well-supported by the context passages._
- **q049** (followup, 0.8875): Và điều kiện sống của họ ra sao? — _The answer directly addresses the question about the living conditions of the working class and is well-supported by the context._

_Estimated API cost of this run: $0.0250 · Cohere rerank calls: 0_
