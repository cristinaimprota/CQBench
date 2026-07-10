# RQ4 C Findings and Interpretation

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

- [Sample-level analysis table](c_rq4_table.parquet)
- [Full correlation results](c_rq4_correlations.csv)
- [Validation report](c_rq4_validation.json)

The table contains 999,578 sample-author observations, 14 reported
predictors, 9 outcomes, and 504 author-predictor-outcome combinations.

| Author | Retained | Dropped: no computable function | Dropped: nonfinite naturalness |
|---|---:|---:|---:|
| human | 280,330 | 188 | 0 |
| gptoss | 270,936 | 9,582 | 0 |
| dsc | 228,258 | 52,260 | 0 |
| qwen | 220,054 | 60,461 | 3 |

All retained keys are unique. Predictors are finite and non-null; outcomes
are nonnegative integers. Own-author out-of-fold entropy has exactly one
value per retained sample. Finding-free samples are represented by zeros.
Semgrep findings emitted alongside partial-parse errors are retained.

## Magnitude summary after size adjustment

- Negligible (`|rho| < 0.10`): 376
- Weak (`0.10 <= |rho| < 0.30`): 86
- Moderate (`0.30 <= |rho| < 0.50`): 4
- Strong (`|rho| >= 0.50`): 2

These counts exclude the raw-only `sample_nloc` rows and undefined
constant-outcome pairs.

## Strongest size-adjusted associations

| Author | Predictor | Outcome | Partial rho | 95% CI |
|---|---|---|---:|---:|
| human | parameter_count | def_interface | +0.556 | [+0.553, +0.558] |
| gptoss | parameter_count | def_interface | +0.537 | [+0.534, +0.539] |
| qwen | parameter_count | def_interface | +0.488 | [+0.485, +0.492] |
| gptoss | parameter_count | defects_total | +0.441 | [+0.438, +0.444] |
| human | parameter_count | defects_total | +0.428 | [+0.425, +0.431] |
| qwen | parameter_count | defects_total | +0.409 | [+0.405, +0.412] |
| dsc | parameter_count | def_interface | +0.298 | [+0.294, +0.302] |
| dsc | parameter_count | defects_total | +0.260 | [+0.256, +0.264] |
| dsc | parameter_count | def_function_class_object | +0.219 | [+0.215, +0.223] |
| dsc | total_operands | vulns_total | +0.210 | [+0.206, +0.213] |
| gptoss | parameter_count | def_function_class_object | +0.205 | [+0.202, +0.208] |
| dsc | distinct_operands | vulns_total | +0.203 | [+0.199, +0.206] |

Because complexity predictors are means across functions while findings are
counts over the whole sample, coefficients can partly reflect how code is
partitioned among functions. Negative coefficients do not show that greater
complexity prevents defects. These are associations, not causal effects.

## Whole-sample size

| Author | Outcome | Raw rho | 95% CI |
|---|---|---:|---:|
| human | defects_total | +0.309 | [+0.305, +0.312] |
| human | vulns_total | +0.197 | [+0.193, +0.200] |
| gptoss | defects_total | +0.250 | [+0.246, +0.253] |
| gptoss | vulns_total | +0.211 | [+0.207, +0.214] |
| dsc | defects_total | +0.166 | [+0.162, +0.170] |
| dsc | vulns_total | +0.262 | [+0.259, +0.266] |
| qwen | defects_total | +0.181 | [+0.177, +0.185] |
| qwen | vulns_total | +0.191 | [+0.188, +0.194] |

Positive size correlations show detector exposure: larger samples provide
more code locations where static-analysis rules can match. This is why the
size-adjusted coefficients are the primary structural results.

## Naturalness

| Author | Outcome | Raw rho | Size-adjusted rho |
|---|---|---:|---:|
| human | defects_total | +0.049 | +0.046 |
| human | vulns_total | +0.040 | +0.037 |
| human | vulns_high_sev | +0.011 | +0.009 |
| gptoss | defects_total | +0.038 | +0.028 |
| gptoss | vulns_total | +0.039 | +0.031 |
| gptoss | vulns_high_sev | +0.023 | +0.020 |
| dsc | defects_total | +0.115 | +0.069 |
| dsc | vulns_total | +0.073 | -0.007 |
| dsc | vulns_high_sev | +0.018 | -0.031 |
| qwen | defects_total | +0.011 | +0.001 |
| qwen | vulns_total | +0.027 | +0.017 |
| qwen | vulns_high_sev | -0.001 | -0.006 |

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
