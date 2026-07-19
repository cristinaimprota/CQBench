# Example run — Claude Opus 4.8

An example CQBench evaluation with **Claude Opus 4.8** (`claude-opus-4-8`) as the
model under test, on a **600-task stress subset** (200 per language, seed 2025),
scored with the study-aligned analyzer pipeline. A worked example of the
submit → evaluate → compare flow; not part of the benchmark itself.

## Files
- `subset_tasks.jsonl`, `subset_refs.jsonl` — the 600-task subset (prompts) and
  human references it was scored against.
- `predictions.jsonl` — the submission: one `{task_id, code}` per task (600 rows).
- `comparison.csv` — Claude vs the human/dsc/qwen baselines on the same task_ids,
  with paired bootstrap-CI deltas (`cqbench compare` output).
- `cwe_distribution.csv` — per-author CWE finding counts (RQ3).
- `issue_distribution.csv` — per-author ODC defect-type incidence (RQ2).

## Reproduce the scoring
```bash
# from the repository root
python -m cqbench evaluate \
  --tasks experiments/claude-opus-4-8/subset_tasks.jsonl \
  --references experiments/claude-opus-4-8/subset_refs.jsonl \
  --predictions experiments/claude-opus-4-8/predictions.jsonl \
  --output /tmp/results.jsonl
```
Requires pylint 3.3.6, PMD 7.11.0, clang-tidy 18, and Semgrep 1.120.0 on `PATH`
(clang-tidy `--checks=*` makes the C pass slow).

## Headline
`clean_strict_at_1`: Python 0.275, Java 0.320, C 0.140 — Claude clears the
clean-code bar on only 14–32% of these stress tasks: statistically ≈ the human
references and clearly above the OpenAI/DeepSeek/Qwen baselines.
