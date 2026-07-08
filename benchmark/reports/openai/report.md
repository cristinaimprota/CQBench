# CQBench report: OpenAI

This benchmark measures static-analysis findings and structural non-triviality; it does not establish functional correctness or actual exploitability.

| Language | N | Non-stub | Strict non-trivial | Defect incidence | Vulnerability incidence | High-severity incidence | Clean strict@1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| c | 6889 | 98.9% | 98.8% | 75.9% | 57.8% | 15.3% | 6.7% |
| java | 10103 | 15.3% | 15.1% | 85.6% | 44.8% | 14.8% | 1.3% |
| python | 10354 | 5.0% | 4.9% | 72.6% | 51.3% | 12.5% | 0.4% |

## Structural metrics among strict non-trivial outputs

| Language | Metric | Mean |
|---|---|---:|
| c | nloc_mean | 19.114 |
| c | ccn_mean | 6.350 |
| c | parameter_count_mean | 2.638 |
| c | max_nesting_depth_mean | 1.194 |
| c | distinct_operators_mean | 20.220 |
| c | total_operators_mean | 100.312 |
| c | distinct_operands_mean | 19.503 |
| c | total_operands_mean | 52.786 |
| c | halstead_volume_mean | 832.315 |
| c | halstead_difficulty_mean | 27.264 |
| c | halstead_effort_mean | 27660.859 |
| c | maintainability_index_mean | 52.658 |
| c | target_token_count_mean | 159.697 |
| c | unique_tokens_corpus | 36866 |
| java | nloc_mean | 12.297 |
| java | ccn_mean | 3.038 |
| java | parameter_count_mean | 1.472 |
| java | max_nesting_depth_mean | 1.238 |
| java | distinct_operators_mean | 16.045 |
| java | total_operators_mean | 58.714 |
| java | distinct_operands_mean | 17.454 |
| java | total_operands_mean | 34.756 |
| java | halstead_volume_mean | 496.586 |
| java | halstead_difficulty_mean | 15.599 |
| java | halstead_effort_mean | 10735.458 |
| java | maintainability_index_mean | 59.932 |
| java | target_token_count_mean | 141.649 |
| java | unique_tokens_corpus | 42179 |
| python | nloc_mean | 9.738 |
| python | ccn_mean | 3.067 |
| python | parameter_count_mean | 2.220 |
| python | max_nesting_depth_mean | 1.191 |
| python | distinct_operators_mean | 13.047 |
| python | total_operators_mean | 46.128 |
| python | distinct_operands_mean | 18.256 |
| python | total_operands_mean | 42.314 |
| python | halstead_volume_mean | 468.770 |
| python | halstead_difficulty_mean | 14.393 |
| python | halstead_effort_mean | 11164.909 |
| python | maintainability_index_mean | 63.172 |
| python | target_token_count_mean | 102.652 |
| python | unique_tokens_corpus | 46282 |
