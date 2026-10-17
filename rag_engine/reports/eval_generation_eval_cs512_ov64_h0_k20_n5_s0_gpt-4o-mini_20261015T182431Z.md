# Generation eval — eval_cs512_ov64_h0_k20_n5_s0_gpt-4o-mini
Dataset `main` (59 items) · judge `gpt-4o-mini`

**Overall score: 0.7961**

| answerable metric | value |
|---|---|
| correctness | 0.8214 |
| groundedness | 0.9539 |
| answer_relevance | 0.8873 |
| context_relevance | 0.2784 |
| refusal_correct | 0.8627 |
| score | 0.7758 |

| unanswerable metric | value |
|---|---|
| refusal_correct | 0.875 |
| groundedness | 1.0 |
| score | 0.925 |

| by type | score |
|---|---|
| factual | 0.8074 |
| followup | 0.5329 |
| paraphrase | 0.8216 |
| unanswerable | 0.925 |

Latency avg 1482.7288 ms · prompt tokens avg 2590.3051

## Lowest-scoring answers

- **q019** (factual, 0.25): Who are the authors of the paper on cellular-resolution connectomics? — _The context does not provide the authors' names, but the refusal is appropriate as the answer is not found in the provided passages._
- **q034** (paraphrase, 0.25): Người chủ nuôi chó nghĩ gì về việc nuôi chó so với nuôi người giúp việc? — _The answer correctly refuses to provide an answer as the context does not contain relevant information._
- **q047** (followup, 0.25): Và họ đã làm gì dưới bóng đèn? — _The context does not provide a direct answer to the question, but the reference indicates that there was conversation under the light._
- **q048** (followup, 0.25): Và ai là người đã mang thịt đến? — _The answer correctly refuses to provide information, but the context does not support the refusal as the reference indicates a specific answer._
- **q042** (paraphrase, 0.28): Cảm xúc của bà cụ khi nhận món quà là gì? — _The answer correctly refuses to provide information but fails to acknowledge the relevant context that describes the grandmother's emotions._
- **q035** (factual, 0.2925): Chế độ nào đã bị phê phán trong đoạn văn? — _The answer identifies capitalism as the criticized regime, but the reference indicates that both capitalism and the monarchy were criticized._
- **q029** (factual, 0.4): Who conducted a light-microscopy-based connectomic reconstruction of mammalian brain tissue? — _The answer appropriately refuses to provide information as the context does not contain relevant details._
- **q049** (followup, 0.4): Và điều kiện sống của họ ra sao? — _The answer appropriately refuses to provide information as the context does not contain relevant details about living conditions._

_Estimated API cost of this run: $0.0461 · Cohere rerank calls: 0_
