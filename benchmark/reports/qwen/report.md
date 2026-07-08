# CQBench report: Qwen

This benchmark measures static-analysis findings and structural non-triviality; it does not establish functional correctness or actual exploitability.

| Language | N | Non-stub | Strict non-trivial | Defect incidence | Vulnerability incidence | High-severity incidence | Clean strict@1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| c | 6889 | 90.8% | 89.4% | 83.3% | 57.9% | 22.8% | 2.8% |
| java | 10103 | 77.3% | 76.5% | 72.9% | 37.7% | 4.9% | 8.2% |
| python | 10354 | 84.7% | 84.2% | 88.4% | 39.3% | 10.2% | 5.6% |

## Structural metrics among strict non-trivial outputs

| Language | Metric | Mean |
|---|---|---:|
| c | nloc_mean | 17.979 |
| c | ccn_mean | 4.266 |
| c | parameter_count_mean | 2.543 |
| c | max_nesting_depth_mean | 1.328 |
| c | distinct_operators_mean | 17.773 |
| c | total_operators_mean | 83.857 |
| c | distinct_operands_mean | 17.938 |
| c | total_operands_mean | 45.299 |
| c | halstead_volume_mean | 684.559 |
| c | halstead_difficulty_mean | 22.252 |
| c | halstead_effort_mean | 18646.087 |
| c | maintainability_index_mean | 54.537 |
| c | target_token_count_mean | 155.367 |
| c | unique_tokens_corpus | 40688 |
| java | nloc_mean | 12.583 |
| java | ccn_mean | 3.218 |
| java | parameter_count_mean | 1.437 |
| java | max_nesting_depth_mean | 1.399 |
| java | distinct_operators_mean | 16.296 |
| java | total_operators_mean | 62.171 |
| java | distinct_operands_mean | 18.081 |
| java | total_operands_mean | 37.710 |
| java | halstead_volume_mean | 531.432 |
| java | halstead_difficulty_mean | 16.357 |
| java | halstead_effort_mean | 11422.899 |
| java | maintainability_index_mean | 59.305 |
| java | target_token_count_mean | 161.736 |
| java | unique_tokens_corpus | 39529 |
| python | nloc_mean | 10.552 |
| python | ccn_mean | 3.277 |
| python | parameter_count_mean | 2.767 |
| python | max_nesting_depth_mean | 1.232 |
| python | distinct_operators_mean | 13.591 |
| python | total_operators_mean | 47.828 |
| python | distinct_operands_mean | 20.516 |
| python | total_operands_mean | 47.772 |
| python | halstead_volume_mean | 514.402 |
| python | halstead_difficulty_mean | 15.188 |
| python | halstead_effort_mean | 10887.976 |
| python | maintainability_index_mean | 62.009 |
| python | target_token_count_mean | 115.597 |
| python | unique_tokens_corpus | 52074 |
