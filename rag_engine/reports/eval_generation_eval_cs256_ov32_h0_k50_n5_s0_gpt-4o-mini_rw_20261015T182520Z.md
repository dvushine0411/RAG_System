# Generation eval — eval_cs256_ov32_h0_k50_n5_s0_gpt-4o-mini_rw
Dataset `main` (59 items) · judge `gpt-4o-mini`

**Overall score: 0.8614**

| answerable metric | value |
|---|---|
| correctness | 0.935 |
| groundedness | 0.9641 |
| answer_relevance | 0.9608 |
| context_relevance | 0.3294 |
| refusal_correct | 0.9608 |
| score | 0.8515 |

| unanswerable metric | value |
|---|---|
| refusal_correct | 0.875 |
| groundedness | 1.0 |
| score | 0.925 |

| by type | score |
|---|---|
| factual | 0.8471 |
| followup | 0.715 |
| paraphrase | 0.8992 |
| unanswerable | 0.925 |

Latency avg 1413.8814 ms · prompt tokens avg 1680.8305

## Lowest-scoring answers

- **q007** (factual, 0.235): Ai là người đọc sổ điền cho các ông kia? — _The answer incorrectly identifies the reader of the sổ điền, which is actually the thư ký according to the reference._
- **q047** (followup, 0.25): Và họ đã làm gì dưới bóng đèn? — _The answer correctly refuses to provide information, but the context does contain relevant information about activities under the light._
- **q053** (unanswerable, 0.4): What is the exact number of synapses in a human brain according to recent studies? — _The answer directly cites the number of synapses from the relevant passage._
- **q049** (followup, 0.585): Và điều kiện sống của họ ra sao? — _The answer provides some relevant information but ultimately refuses to give a detailed response about living conditions, which are partially addressed in the context._
- **q045** (followup, 0.59): And what specific technology is reviewed in one of the articles? — _The answer accurately lists and describes the technologies reviewed in the context passages._
- **q027** (factual, 0.765): Tôn giáo được xem là gì về bản chất? — _The answer accurately reflects the nature of religion as described in the context but does not mention its negative aspect as stated in the reference._
- **q041** (factual, 0.7925): Bà cụ cảm thấy như thế nào khi nhận gói bạc? — _The answer accurately reflects the emotion of the old woman as described in the relevant passage, but it omits the detail of her feeling 'run run'._
- **q005** (factual, 0.8267): Diên cảm thấy như thế nào khi thấy Mai khóc? — _The answer accurately reflects Diên's feelings and actions when he sees Mai crying, supported by the context._

_Estimated API cost of this run: $0.0324 · Cohere rerank calls: 0_
