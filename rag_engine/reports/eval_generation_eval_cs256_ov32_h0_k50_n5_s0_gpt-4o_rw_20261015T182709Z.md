# Generation eval — eval_cs256_ov32_h0_k50_n5_s0_gpt-4o_rw
Dataset `main` (59 items) · judge `gpt-4o-mini`

**Overall score: 0.8819**

| answerable metric | value |
|---|---|
| correctness | 0.9363 |
| groundedness | 0.9951 |
| answer_relevance | 0.9804 |
| context_relevance | 0.2784 |
| refusal_correct | 0.9804 |
| score | 0.8633 |

| unanswerable metric | value |
|---|---|
| refusal_correct | 1.0 |
| groundedness | 1.0 |
| score | 1.0 |

| by type | score |
|---|---|
| factual | 0.8723 |
| followup | 0.7571 |
| paraphrase | 0.8882 |
| unanswerable | 1.0 |

Latency avg 1347.1017 ms · prompt tokens avg 1680.8305

## Lowest-scoring answers

- **q047** (followup, 0.25): Và họ đã làm gì dưới bóng đèn? — _The answer correctly refuses to provide information, but the context does contain relevant information about activities under the light._
- **q027** (factual, 0.56): Tôn giáo được xem là gì về bản chất? — _The answer accurately reflects the context regarding the nature of religion as a social consciousness that distorts reality._
- **q045** (followup, 0.56): And what specific technology is reviewed in one of the articles? — _The answer correctly identifies technologies mentioned in the context but does not match the reference provided._
- **q026** (paraphrase, 0.8225): Khi Cái Tỉu khóc, phản ứng của chị Dậu là gì? — _The answer accurately describes chị Dậu's actions in response to Cái Tỉu crying, supported by the relevant context._
- **q028** (paraphrase, 0.8775): Tôn giáo có thể được coi là một hiện tượng xã hội như thế nào? — _The answer accurately summarizes the context and aligns with the reference._
- **q002** (paraphrase, 0.88): Which methods are employed for imaging the human brain at a larger scale? — _The answer directly and completely addresses the question using supported claims from the context._
- **q003** (factual, 0.88): Ai đã gặp Chủ tịch Hồ Chí Minh vào năm 1923? — _The answer directly and accurately states the information found in the relevant passage._
- **q004** (paraphrase, 0.88): Người nào đã viết bài về Nguyễn Ái Quốc trong tạp chí Ngọn lửa nhỏ? — _The answer directly and accurately identifies the author of the article about Nguyễn Ái Quốc as stated in the context._

_Estimated API cost of this run: $0.3135 · Cohere rerank calls: 0_
