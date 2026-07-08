# CQBench report: DeepSeek

This benchmark measures static-analysis findings and structural non-triviality; it does not establish functional correctness or actual exploitability.

| Language | N | Non-stub | Strict non-trivial | Defect incidence | Vulnerability incidence | High-severity incidence | Clean strict@1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| c | 6889 | 78.8% | 74.6% | 83.5% | 61.0% | 29.5% | 2.2% |
| java | 10103 | 77.7% | 77.4% | 95.1% | 64.5% | 16.6% | 1.7% |
| python | 10354 | 80.3% | 79.6% | 91.9% | 54.9% | 12.7% | 1.7% |

## Structural metrics among strict non-trivial outputs

| Language | Metric | Mean |
|---|---|---:|
| c | nloc_mean | 12.109 |
| c | ccn_mean | 2.959 |
| c | parameter_count_mean | 2.166 |
| c | max_nesting_depth_mean | 1.030 |
| c | distinct_operators_mean | 15.921 |
| c | total_operators_mean | 56.636 |
| c | distinct_operands_mean | 14.056 |
| c | total_operands_mean | 30.417 |
| c | halstead_volume_mean | 437.720 |
| c | halstead_difficulty_mean | 17.243 |
| c | halstead_effort_mean | 9117.227 |
| c | maintainability_index_mean | 59.262 |
| c | target_token_count_mean | 151.083 |
| c | unique_tokens_corpus | 28774 |
| java | nloc_mean | 10.649 |
| java | ccn_mean | 2.557 |
| java | parameter_count_mean | 1.421 |
| java | max_nesting_depth_mean | 1.162 |
| java | distinct_operators_mean | 15.530 |
| java | total_operators_mean | 50.564 |
| java | distinct_operands_mean | 16.204 |
| java | total_operands_mean | 30.660 |
| java | halstead_volume_mean | 421.717 |
| java | halstead_difficulty_mean | 14.367 |
| java | halstead_effort_mean | 7636.905 |
| java | maintainability_index_mean | 61.398 |
| java | target_token_count_mean | 150.486 |
| java | unique_tokens_corpus | 34529 |
| python | nloc_mean | 7.766 |
| python | ccn_mean | 2.507 |
| python | parameter_count_mean | 2.904 |
| python | max_nesting_depth_mean | 1.024 |
| python | distinct_operators_mean | 12.507 |
| python | total_operators_mean | 34.644 |
| python | distinct_operands_mean | 15.932 |
| python | total_operands_mean | 31.954 |
| python | halstead_volume_mean | 334.195 |
| python | halstead_difficulty_mean | 12.370 |
| python | halstead_effort_mean | 5169.318 |
| python | maintainability_index_mean | 65.282 |
| python | target_token_count_mean | 73.438 |
| python | unique_tokens_corpus | 40109 |
