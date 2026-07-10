# RQ4 Java Findings and Interpretation

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

- [Sample-level analysis table](java_rq4_table.parquet)
- [Full correlation results](java_rq4_correlations.csv)
- [Validation report](java_rq4_validation.json)

The table contains 857,329 sample-author observations, 14 reported
predictors, 9 outcomes, and 504 author-predictor-outcome combinations.

| Author | Retained | Dropped: no computable function |
|---|---:|---:|
| human | 220,940 | 856 |
| chatgpt | 221,155 | 641 |
| dsc | 198,180 | 23,616 |
| qwen | 217,054 | 4,742 |

All retained keys are unique. Predictors are finite and non-null; outcomes
are nonnegative integers. Own-author out-of-fold entropy has exactly one
value per retained sample. Finding-free samples are represented by zeros.
Semgrep findings emitted alongside partial-parse errors are retained.

## Magnitude summary after size adjustment

- Negligible (`|rho| < 0.10`): 376
- Weak (`0.10 <= |rho| < 0.30`): 84
- Moderate (`0.30 <= |rho| < 0.50`): 8
- Strong (`|rho| >= 0.50`): 0

These counts exclude the raw-only `sample_nloc` rows and undefined
constant-outcome pairs.

## Strongest size-adjusted associations

| Author | Predictor | Outcome | Partial rho | 95% CI |
|---|---|---|---:|---:|
| dsc | distinct_operands | def_function_class_object | -0.440 | [-0.443, -0.436] |
| dsc | mi | def_function_class_object | +0.424 | [+0.420, +0.428] |
| dsc | nloc | def_function_class_object | -0.417 | [-0.421, -0.413] |
| dsc | halstead_v | def_function_class_object | -0.415 | [-0.419, -0.411] |
| dsc | total_operands | def_function_class_object | -0.410 | [-0.413, -0.406] |
| dsc | total_operators | def_function_class_object | -0.402 | [-0.405, -0.397] |
| dsc | halstead_effort | def_function_class_object | -0.366 | [-0.370, -0.361] |
| dsc | distinct_operators | def_function_class_object | -0.309 | [-0.313, -0.305] |
| dsc | halstead_difficulty | def_function_class_object | -0.267 | [-0.271, -0.263] |
| dsc | max_nesting_depth | def_function_class_object | -0.262 | [-0.266, -0.258] |
| dsc | ccn | def_function_class_object | -0.259 | [-0.262, -0.255] |
| dsc | ccn | def_algorithm | +0.226 | [+0.222, +0.231] |

The largest adjusted associations are concentrated in DeepSeek's
`Function/Class/Object` findings. Because complexity predictors are means
across functions while findings are counts over the whole sample, negative
coefficients can indicate samples composed of more, smaller functions—not
that complexity prevents defects. These are associations, not causal effects.

## Whole-sample size

| Author | Outcome | Raw rho | 95% CI |
|---|---|---:|---:|
| human | defects_total | +0.552 | [+0.549, +0.555] |
| human | vulns_total | +0.138 | [+0.134, +0.141] |
| chatgpt | defects_total | +0.474 | [+0.471, +0.477] |
| chatgpt | vulns_total | +0.209 | [+0.205, +0.213] |
| dsc | defects_total | +0.539 | [+0.537, +0.543] |
| dsc | vulns_total | +0.378 | [+0.375, +0.382] |
| qwen | defects_total | +0.410 | [+0.406, +0.414] |
| qwen | vulns_total | +0.236 | [+0.233, +0.239] |

Positive size correlations show detector exposure: larger samples provide
more code locations where static-analysis rules can match. This is why the
size-adjusted coefficients are the primary structural results.

## Naturalness

| Author | Outcome | Raw rho | Size-adjusted rho |
|---|---|---:|---:|
| human | defects_total | +0.125 | +0.060 |
| human | vulns_total | -0.023 | -0.043 |
| human | vulns_high_sev | -0.027 | -0.034 |
| chatgpt | defects_total | +0.134 | +0.055 |
| chatgpt | vulns_total | -0.070 | -0.112 |
| chatgpt | vulns_high_sev | -0.097 | -0.126 |
| dsc | defects_total | -0.161 | -0.075 |
| dsc | vulns_total | -0.204 | -0.147 |
| dsc | vulns_high_sev | -0.117 | -0.092 |
| qwen | defects_total | +0.113 | +0.013 |
| qwen | vulns_total | +0.007 | -0.055 |
| qwen | vulns_high_sev | -0.019 | -0.038 |

Naturalness uses the own-author model and only the fold in which the sample
was held out. Positive rho means higher cross-entropy (less natural code)
is associated with more findings; negative rho means it is associated with
fewer findings. Magnitudes should be interpreted independently by author.

## Interpretation limits

- Static-analysis findings are detector outputs, not confirmed runtime failures.
- Correlation does not establish that a structural property causes a finding.
- Author cells are analyzed separately; coefficients do not compare authors.
- Corpus-level UT is constant within an author cell and cannot be correlated.
- Mean function metrics and whole-sample finding counts operate at different
  summaries of the same sample; composition and function count can influence
  the observed association even after controlling for physical sample size.
