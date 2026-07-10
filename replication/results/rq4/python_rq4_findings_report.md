# RQ4 Python Findings and Interpretation

## Analysis design

The analysis unit is one code sample for one author, keyed by the explicit
`(hm_index, author)` pair. Structural predictors are the within-sample means
over all computable functions; they are not restricted to Lizard function
index 0. Defect, vulnerability, and naturalness outcomes are sample-level.

Partial Spearman correlations rank-residualize both variables against
`sample_nloc`, the physical nonblank, non-comment line count of the complete
sample. The `sample_nloc` predictor therefore has a raw correlation only.
Confidence intervals use 1,000 deterministic bootstrap resamples. No
p-values are calculated or interpreted.

## Outputs and validation

- [Sample-level analysis table](python_rq4_table.parquet)
- [Full correlation results](python_rq4_correlations.csv)
- [Validation report](python_rq4_validation.json)

The table contains 1,110,344 sample-author observations, 14 reported
predictors, 9 outcomes, and 504 author-predictor-outcome combinations.

| Author | Retained | Dropped: no computable function |
|---|---:|---:|
| human | 285,230 | 19 |
| chatgpt | 285,202 | 47 |
| dsc | 261,772 | 23,477 |
| qwen | 278,140 | 7,109 |

All retained keys are unique. Predictors are finite and non-null; outcomes
are nonnegative integers. Own-author out-of-fold entropy has exactly one
value per retained sample. Finding-free samples are represented by zeros.
Semgrep findings emitted alongside partial-parse errors are retained.

## Magnitude summary after size adjustment

- Negligible (`|rho| < 0.10`): 287
- Weak (`0.10 <= |rho| < 0.30`): 131
- Moderate (`0.30 <= |rho| < 0.50`): 11
- Strong (`|rho| >= 0.50`): 0

These counts exclude the raw-only `sample_nloc` rows and undefined
constant-outcome pairs.

## Strongest size-adjusted associations

| Author | Predictor | Outcome | Partial rho | 95% CI |
|---|---|---|---:|---:|
| dsc | mi | def_function_class_object | +0.488 | [+0.484, +0.491] |
| dsc | total_operators | def_function_class_object | -0.465 | [-0.468, -0.462] |
| dsc | halstead_v | def_function_class_object | -0.445 | [-0.448, -0.442] |
| dsc | nloc | def_function_class_object | -0.443 | [-0.446, -0.439] |
| dsc | distinct_operands | def_function_class_object | -0.426 | [-0.429, -0.422] |
| dsc | distinct_operators | def_function_class_object | -0.417 | [-0.420, -0.414] |
| dsc | halstead_effort | def_function_class_object | -0.393 | [-0.397, -0.390] |
| dsc | total_operands | def_function_class_object | -0.391 | [-0.394, -0.388] |
| dsc | parameter_count | def_assignment | +0.333 | [+0.329, +0.336] |
| dsc | max_nesting_depth | def_function_class_object | -0.320 | [-0.323, -0.317] |
| dsc | halstead_difficulty | def_function_class_object | -0.313 | [-0.316, -0.310] |
| qwen | halstead_difficulty | def_assignment | -0.291 | [-0.294, -0.287] |

The largest adjusted associations are concentrated in DeepSeek's
`Function/Class/Object` findings. Because complexity predictors are means
across functions while findings are counts over the whole sample, negative
coefficients can indicate samples composed of more, smaller functions—not
that complexity prevents defects. These are associations, not causal effects.

## Whole-sample size

| Author | Outcome | Raw rho | 95% CI |
|---|---|---:|---:|
| human | defects_total | +0.348 | [+0.345, +0.352] |
| human | vulns_total | +0.121 | [+0.118, +0.125] |
| chatgpt | defects_total | +0.197 | [+0.193, +0.200] |
| chatgpt | vulns_total | +0.089 | [+0.086, +0.093] |
| dsc | defects_total | +0.190 | [+0.186, +0.194] |
| dsc | vulns_total | +0.127 | [+0.123, +0.131] |
| qwen | defects_total | +0.255 | [+0.252, +0.258] |
| qwen | vulns_total | +0.143 | [+0.140, +0.146] |

Positive size correlations show detector exposure: larger samples provide
more code locations where static-analysis rules can match. This is why the
size-adjusted coefficients are the primary structural results.

## Naturalness

| Author | Outcome | Raw rho | Size-adjusted rho |
|---|---|---:|---:|
| human | defects_total | +0.133 | +0.063 |
| human | vulns_total | +0.087 | +0.062 |
| human | vulns_high_sev | -0.006 | -0.014 |
| chatgpt | defects_total | +0.070 | +0.039 |
| chatgpt | vulns_total | -0.066 | -0.082 |
| chatgpt | vulns_high_sev | -0.054 | -0.063 |
| dsc | defects_total | -0.173 | -0.184 |
| dsc | vulns_total | -0.067 | -0.072 |
| dsc | vulns_high_sev | -0.053 | -0.055 |
| qwen | defects_total | -0.076 | -0.142 |
| qwen | vulns_total | +0.032 | -0.000 |
| qwen | vulns_high_sev | -0.014 | -0.029 |

Naturalness uses the own-author model and only the fold in which the sample
was held out. Positive rho means higher cross-entropy (less natural code)
is associated with more findings; negative rho means it is associated with
fewer findings. Magnitudes should be interpreted independently by author.

## Undefined constant outcomes

Raw and partial correlations are undefined for `def_timing` where the
outcome is identically zero for: dsc, human, qwen. These cells are reported as
`NaN`; they are not converted to zero correlations.

## Interpretation limits

- Static-analysis findings are detector outputs, not confirmed runtime failures.
- Correlation does not establish that a structural property causes a finding.
- Author cells are analyzed separately; coefficients do not compare authors.
- Corpus-level UT is constant within an author cell and cannot be correlated.
- Mean function metrics and whole-sample finding counts operate at different
  summaries of the same sample; composition and function count can influence
  the observed association even after controlling for physical sample size.
