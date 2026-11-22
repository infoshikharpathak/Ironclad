# Policy retrieval: four setups

text-embedding-3-small; 74 child chunks, 53 parent sections; top 3. Thresholds tuned on dev (25 questions) only, then applied to held-out (20). 3752 embedding tokens, $7.5e-05. 2026-11-22T13:17:31Z.

| Setup | Params | Set | Recall@1 | Recall@3 | MRR@3 | Answerable empty | Unanswerable empty | Misses @3 |
|---|---|---|---|---|---|---|---|---|
| vector | min_score 0.43 | dev | 0.80 | 0.85 | 0.88 | 0.00 | 1.00 | q14, q19, q20 |
| vector | min_score 0.43 | heldout | 0.80 | 0.80 | 0.83 | 0.07 | 0.80 | h08, h11, h14 |
| keyword | min_rank 0.2 | dev | 0.35 | 0.60 | 0.47 | 0.05 | 0.40 | q09, q11, q12, q13, q16, q18, q19, q20 |
| keyword | min_rank 0.2 | heldout | 0.47 | 0.53 | 0.52 | 0.00 | 0.20 | h06, h07, h11, h12, h13, h14, h15 |
| hybrid | vector_gate 0.43, keyword_gate 0.7, rrf_k 5, keyword_weight 0.25, keyword_fuse_min 0.0 | dev | 0.80 | 0.90 | 0.90 | 0.00 | 1.00 | q19, q20 |
| hybrid | vector_gate 0.43, keyword_gate 0.7, rrf_k 5, keyword_weight 0.25, keyword_fuse_min 0.0 | heldout | 0.80 | 0.80 | 0.86 | 0.07 | 0.80 | h11, h14, h15 |
| hybrid_parent | vector_gate 0.43, keyword_gate 0.7, rrf_k 5, keyword_weight 0.25, keyword_fuse_min 0.0 | dev | 0.80 | 0.90 | 0.90 | 0.00 | 1.00 | q19, q20 |
| hybrid_parent | vector_gate 0.43, keyword_gate 0.7, rrf_k 5, keyword_weight 0.25, keyword_fuse_min 0.0 | heldout | 0.80 | 0.87 | 0.87 | 0.07 | 0.80 | h11, h14 |
