# Retrieval sweep — eval_cs512_ov64_h0
Dataset `smoke`: 7 answerable + 1 unanswerable questions; candidate pool 50, reranker CohereRerankerProvider.

| config | Hit@N | MRR | nDCG@N | avg chunks | avg ctx tokens | unanswerable→empty |
|---|---|---|---|---|---|---|
| k10_n3_s0.1 | 1.000 | 1.000 | 1.000 | 1.0 | 89.7 | 1.0 |
| k10_n5_s0.1 | 1.000 | 1.000 | 1.000 | 1.0 | 89.7 | 1.0 |
| k20_n3_s0.1 | 1.000 | 1.000 | 1.000 | 1.0 | 89.7 | 1.0 |
| k20_n5_s0.1 | 1.000 | 1.000 | 1.000 | 1.0 | 89.7 | 1.0 |
| k10_n3_s0 | 1.000 | 1.000 | 1.000 | 3.0 | 216.1 | 0.0 |
| k20_n3_s0 | 1.000 | 1.000 | 1.000 | 3.0 | 216.1 | 0.0 |
| k10_n5_s0 | 1.000 | 1.000 | 1.000 | 5.0 | 289.3 | 0.0 |
| k20_n5_s0 | 1.000 | 1.000 | 1.000 | 5.0 | 289.3 | 0.0 |

_Estimated API cost of this run: $0.0000 · Cohere rerank calls: 8_
