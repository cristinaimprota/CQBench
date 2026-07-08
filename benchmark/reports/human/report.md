# CQBench report: Human

This benchmark measures static-analysis findings and structural non-triviality; it does not establish functional correctness or actual exploitability.

| Language | N | Non-stub | Strict non-trivial | Defect incidence | Vulnerability incidence | High-severity incidence | Clean strict@1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| c | 6889 | 100.0% | 100.0% | 70.8% | 40.4% | 15.0% | 17.1% |
| java | 10103 | 100.0% | 100.0% | 59.1% | 12.4% | 1.9% | 38.5% |
| python | 10354 | 100.0% | 100.0% | 57.2% | 15.4% | 2.3% | 37.2% |

## Structural metrics among strict non-trivial outputs

| Language | Metric | Mean |
|---|---|---:|
| c | nloc_mean | 28.066 |
| c | ccn_mean | 6.680 |
| c | parameter_count_mean | 2.636 |
| c | max_nesting_depth_mean | 1.323 |
| c | distinct_operators_mean | 19.448 |
| c | total_operators_mean | 125.585 |
| c | distinct_operands_mean | 25.218 |
| c | total_operands_mean | 71.311 |
| c | halstead_volume_mean | 1134.084 |
| c | halstead_difficulty_mean | 26.756 |
| c | halstead_effort_mean | 42638.889 |
| c | maintainability_index_mean | 49.808 |
| c | target_token_count_mean | 203.417 |
| c | unique_tokens_corpus | 68342 |
| java | nloc_mean | 16.262 |
| java | ccn_mean | 3.894 |
| java | parameter_count_mean | 1.502 |
| java | max_nesting_depth_mean | 1.344 |
| java | distinct_operators_mean | 17.162 |
| java | total_operators_mean | 78.745 |
| java | distinct_operands_mean | 21.205 |
| java | total_operands_mean | 45.930 |
| java | halstead_volume_mean | 700.030 |
| java | halstead_difficulty_mean | 17.544 |
| java | halstead_effort_mean | 18820.901 |
| java | maintainability_index_mean | 57.253 |
| java | target_token_count_mean | 136.108 |
| java | unique_tokens_corpus | 65375 |
| python | nloc_mean | 14.310 |
| python | ccn_mean | 4.079 |
| python | parameter_count_mean | 3.152 |
| python | max_nesting_depth_mean | 1.317 |
| python | distinct_operators_mean | 14.693 |
| python | total_operators_mean | 65.838 |
| python | distinct_operands_mean | 24.422 |
| python | total_operands_mean | 59.287 |
| python | halstead_volume_mean | 703.626 |
| python | halstead_difficulty_mean | 17.094 |
| python | halstead_effort_mean | 18065.993 |
| python | maintainability_index_mean | 58.347 |
| python | target_token_count_mean | 116.912 |
| python | unique_tokens_corpus | 72248 |
