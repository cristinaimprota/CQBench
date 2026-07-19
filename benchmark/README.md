# CQBench large issue-prone challenge benchmark

This is the primary CQBench artifact. It contains 27,346 tasks:

- Python: 10,354
- Java: 10,103
- C: 6,889

## Inclusion criterion

For each baseline model output, require:

```text
generated_nloc / human_nloc >= 0.10
OR generated_halstead_volume / human_halstead_volume >= 0.10
```

A task is eligible only when at least two complexity-qualified models each have three or more included findings and those models share the same ODC type
or normalized CWE. Existing Pylint, PMD, and Clang-tidy exclusion lists are applied before counting. The human reference must be parseable and strictly nontrivial. There is no top-N cap.

The same complexity gate applies to evaluated submissions. A structurally valid output with both ratios below 0.10 is labeled `complexity_degenerate` and is excluded from strict-clean credit.

## Evaluation

Validate a model's JSONL predictions before running analyzers:

```bash
python -m cqbench validate-submission \
  --tasks benchmark/tasks.jsonl \
  --predictions predictions.jsonl
```

Frozen baseline results for Human, OpenAI, DeepSeek, and Qwen are in `results/`. They reuse existing study findings and metrics through explicit
`(source_id, author)` keys. Generate report tables and figures for any result file with `python -m cqbench report`.

Compare a new evaluated result file with the baselines:

```bash
python -m cqbench compare \
  --submission my-results.jsonl \
  --baseline benchmark/results/openai.jsonl \
  --baseline benchmark/results/dsc.jsonl \
  --baseline benchmark/results/qwen.jsonl \
  --output my-comparison.csv
```

This is deliberately a failure-derived challenge set. It measures robustness on known issue-prone tasks, not unbiased performance over the original corpus.
