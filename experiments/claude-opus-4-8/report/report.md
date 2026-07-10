# CQBench report: claude-opus-4-8

This benchmark measures static-analysis findings and structural non-triviality; it does not establish functional correctness or actual exploitability.

| Language | N | Non-stub | Strict non-trivial | Defect incidence | Vulnerability incidence | High-severity incidence | Clean strict@1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| c | 200 | 99.5% | 99.5% | 68.5% | 46.5% | 14.0% | 14.0% |
| java | 200 | 100.0% | 100.0% | 64.5% | 16.0% | 2.5% | 32.0% |
| python | 200 | 100.0% | 100.0% | 63.0% | 28.0% | 7.5% | 27.5% |

## Structural metrics among strict non-trivial outputs

| Language | Metric | Mean |
|---|---|---:|
| c | nloc_mean | 23.296 |
| c | ccn_mean | 6.116 |
| c | parameter_count_mean | 2.540 |
| c | max_nesting_depth_mean | 1.093 |
| c | distinct_operators_mean | 20.515 |
| c | total_operators_mean | 105.344 |
| c | distinct_operands_mean | 21.789 |
| c | total_operands_mean | 58.070 |
| c | halstead_volume_mean | 907.054 |
| c | halstead_difficulty_mean | 27.508 |
| c | halstead_effort_mean | 29898.213 |
| c | maintainability_index_mean | 50.558 |
| c | function_name_length_mean | 15.849 |
| c | target_token_count_mean | 208.387 |
| c | unique_tokens_corpus | 3500 |
| java | nloc_mean | 14.520 |
| java | ccn_mean | 3.803 |
| java | parameter_count_mean | 1.567 |
| java | max_nesting_depth_mean | 1.482 |
| java | distinct_operators_mean | 17.848 |
| java | total_operators_mean | 72.642 |
| java | distinct_operands_mean | 20.152 |
| java | total_operands_mean | 40.460 |
| java | halstead_volume_mean | 617.092 |
| java | halstead_difficulty_mean | 17.348 |
| java | halstead_effort_mean | 13546.832 |
| java | maintainability_index_mean | 57.245 |
| java | function_name_length_mean | 12.755 |
| java | target_token_count_mean | 121.380 |
| java | unique_tokens_corpus | 2262 |
| python | nloc_mean | 13.263 |
| python | ccn_mean | 3.656 |
| python | parameter_count_mean | 3.100 |
| python | max_nesting_depth_mean | 1.302 |
| python | distinct_operators_mean | 16.061 |
| python | total_operators_mean | 57.760 |
| python | distinct_operands_mean | 22.491 |
| python | total_operands_mean | 49.430 |
| python | halstead_volume_mean | 587.523 |
| python | halstead_difficulty_mean | 17.401 |
| python | halstead_effort_mean | 12906.770 |
| python | maintainability_index_mean | 58.189 |
| python | function_name_length_mean | 12.995 |
| python | target_token_count_mean | 104.325 |
| python | unique_tokens_corpus | 3227 |
