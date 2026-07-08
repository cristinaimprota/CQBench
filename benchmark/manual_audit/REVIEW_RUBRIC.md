# CQBench candidate review rubric

Reviewers work independently and must not discuss labels before the agreement
report is generated. Model identities are anonymized by the review command.
Review is about task clarity, structural adequacy, and visible static findings;
it is not a functional-correctness assessment.

## Labels

Use `yes`, `no`, or `uncertain` for each field.

- `specification_clear`: the docstring and signature provide enough information
  to produce a standalone implementation without unavailable repository state.
- `human_matches_signature`: the human reference contains the requested target
  with the displayed name and arity.
- `human_nontrivial`: the human implementation is not empty, a placeholder, or
  a constant/no-op implementation.
- `trigger_finding_valid`: the displayed ODC/CWE category corresponds to a
  pattern visible in at least two anonymized model outputs.
- `missing_context_artifact`: the trigger appears to arise only because imports,
  types, class state, or repository context were removed.

Choose `include` only when the first four labels are `yes` and
`missing_context_artifact` is `no`. Choose `exclude` for a definite failure.
Choose `uncertain` whenever repository context or analyzer validity cannot be
resolved from the review card.

## Pilot and adjudication

Review the same first 10 candidates per language as a pilot. Run
`review-agreement`; if Cohen's kappa is below 0.70 for specification clarity or
finding validity, discuss the rubric, discard the pilot labels, and repeat.
After full review, every disagreement and uncertain decision must be resolved
in the adjudication file before finalization.

