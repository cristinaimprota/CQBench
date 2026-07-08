# CQBench large issue-prone challenge benchmark

This is the primary CQBench artifact. It contains 27,346 tasks:

- Python: 10,354
- Java: 10,103
- C: 6,889

The 150 tasks under `manual_audit/` are a validation sample, not the benchmark
population.

## Inclusion criterion

For each historical model output, require:

```text
generated_nloc / human_nloc >= 0.10
OR generated_halstead_volume / human_halstead_volume >= 0.10
```

A task is eligible only when at least two complexity-qualified models each
have three or more included findings and those models share the same ODC type
or normalized CWE. Existing Pylint, PMD, and
Clang-tidy exclusion lists are applied before counting. The human reference
must be parseable and strictly nontrivial. Exact duplicate reference contents
are removed. There is no top-N cap.

The same complexity gate applies to evaluated submissions. A structurally
valid output with both ratios below 0.10 is labeled
`complexity_degenerate` and is excluded from strict-clean credit.

The formula, drop counts, analyzer versions, rule hash, artifact hashes, and
counts are recorded in `manifest.json`.

## Manual validation

`manual_audit/candidates.jsonl` contains 50 tasks per language and 10 per
within-language difficulty quintile. Two reviewers should independently check
prompt clarity, reference adequacy, missing context, and finding validity.

```bash
conda run -n labgpuenv python -m cqbench review \
  --candidates cqbench_data/v1/benchmark/manual_audit/candidates.jsonl \
  --reviewer reviewer-1 \
  --output cqbench_data/v1/benchmark/manual_audit/reviewer-1.jsonl
```

## Evaluation

Validate a model's JSONL predictions before running analyzers:

```bash
conda run -n labgpuenv python -m cqbench validate-submission \
  --tasks cqbench_data/v1/benchmark/tasks.jsonl \
  --predictions predictions.jsonl
```

Frozen historical results for Human, OpenAI, DeepSeek, and Qwen are in
`results/`; their reports and figures are in `reports/`. They reuse existing
study findings and metrics through explicit `(source_id, author)` keys.

Compare a new evaluated result file with the baselines:

```bash
conda run -n labgpuenv python -m cqbench compare \
  --submission my-results.jsonl \
  --baseline cqbench_data/v1/benchmark/results/openai.jsonl \
  --baseline cqbench_data/v1/benchmark/results/dsc.jsonl \
  --baseline cqbench_data/v1/benchmark/results/qwen.jsonl \
  --output my-comparison.csv
```

This is deliberately a failure-derived challenge set. It measures robustness
on known issue-prone tasks, not unbiased performance over the original corpus.
