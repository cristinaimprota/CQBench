# Example run — Claude Opus 4.8

An example CQBench evaluation, with **Claude Opus 4.8** (`claude-opus-4-8`) as the
model under test, scored with the study-aligned analyzer pipeline. Provided as a
worked example of the submit → evaluate → report → compare flow; it is **not**
part of the benchmark itself.

## Scope
- **600-task stress subset** (200 per language), sampled deterministically
  (seed 2025), stratified by profile and difficulty. Not the full 27,346-task set.
- Each function was generated from its task `prompt` alone (no execution feedback,
  no access to the human reference or the analyzer rules).
- Static analysis only (no execution / functional correctness).

## Contents
- `predictions.jsonl` — the submission (`{task_id, code}`), 600 rows.
- `subset_tasks.jsonl`, `subset_refs.jsonl` — the 600-task subset + references.
- `results.jsonl` — scored evaluator output.
- `baselines/{human,openai,dsc,qwen}.jsonl` — historical results subset to the
  same 600 task_ids (for `compare`).
- `comparison.csv` — Claude vs baselines with paired bootstrap CIs.
- `report/` — `summary.json`/`.csv`, quality-rate + ODC-heatmap figures, `report.md`.
- `RUN_REPORT.md` — narrative results (headline metrics + baseline deltas + issue types).
- `RESULTS_paper_format.md` — results in the paper's Table/Figure layout.
- `paper_figures/` — RQ1/RQ2/RQ3 figures in the paper palette (+ `table4/5` CSVs).
- `EXAMPLES_defects_cwes.md` — sample generations with reproduced findings.
- `cwe_distribution.csv`, `issue_distribution.csv` — per-author CWE / ODC tables.
- `*.py` — analysis scripts used to produce the figures/tables/examples.

## Reproduce the scoring
```bash
# from the repository root
python -m cqbench evaluate \
  --tasks experiments/claude-opus-4-8/subset_tasks.jsonl \
  --references experiments/claude-opus-4-8/subset_refs.jsonl \
  --predictions experiments/claude-opus-4-8/predictions.jsonl \
  --output /tmp/results.jsonl
```
Requires pylint 3.3.6, PMD 7.11.0, clang-tidy 18, Semgrep 1.120.0 on `PATH`
(clang-tidy `--checks=*` makes the C pass slow).

## Headline
`clean_strict_at_1`: Python 0.275, Java 0.320, C 0.140 — Claude clears the clean-code
bar on only 14–32% of these stress tasks, statistically ≈ the human references and
clearly above the OpenAI/DeepSeek/Qwen baselines. See `RUN_REPORT.md`.
