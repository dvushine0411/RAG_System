# Generation eval — eval_cs256_ov32_h0_k50_n3_s0_gpt-4o-mini_rw_pv2
Dataset `main` (59 items) · judge `gpt-4o-mini`

**Overall score: 0.9111**

| answerable metric | value |
|---|---|
| correctness | 0.9657 |
| groundedness | 0.973 |
| answer_relevance | 0.9951 |
| context_relevance | 0.4444 |
| refusal_correct | 1.0 |
| score | 0.8972 |

| unanswerable metric | value |
|---|---|
| refusal_correct | 1.0 |
| groundedness | 1.0 |
| score | 1.0 |

| by type | score |
|---|---|
| factual | 0.9114 |
| followup | 0.8393 |
| paraphrase | 0.9014 |
| unanswerable | 1.0 |

Latency avg 1371.2881 ms · prompt tokens avg 1301.1695

## Lowest-scoring answers

- **q045** (followup, 0.4625): And what specific technology is reviewed in one of the articles? — _The answer lists technologies mentioned in the context but does not align with the reference provided._
- **q026** (paraphrase, 0.5625): Khi Cái Tỉu khóc, phản ứng của chị Dậu là gì? — _The answer partially addresses the question but misses the detail about dỗ dành Cái Tỉu from the reference._
- **q047** (followup, 0.8125): Và họ đã làm gì dưới bóng đèn? — _The answer correctly identifies that people gathered to talk under the light of the lamp, which is supported by the context._
- **q001** (factual, 0.9): What techniques are used for human-scale brain imaging? — _The answer directly and accurately reflects the information provided in the context._
- **q002** (paraphrase, 0.9): Which methods are employed for imaging the human brain at a larger scale? — _The answer accurately lists the methods for imaging the human brain at a larger scale as supported by the context._
- **q003** (factual, 0.9): Ai đã gặp Chủ tịch Hồ Chí Minh vào năm 1923? — _The answer directly and accurately states the information found in the relevant passage._
- **q004** (paraphrase, 0.9): Người nào đã viết bài về Nguyễn Ái Quốc trong tạp chí Ngọn lửa nhỏ? — _The answer directly identifies the author of the article as Ô-xíp Man-den-xtam, which is fully supported by the context._
- **q005** (factual, 0.9): Diên cảm thấy như thế nào khi thấy Mai khóc? — _The answer accurately reflects the emotions Diên felt and is fully supported by the context._

_Estimated API cost of this run: $0.0254 · Cohere rerank calls: 0_
