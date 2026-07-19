# Replication package

Transparency materials for the study *Code Quality Benchmark: Human-written vs.
AI-generated*. This complements the runnable benchmark (top-level `README.md`):
the benchmark scores new submissions; this folder documents how the paper's
corpus-wide results were produced.

These are the **original study scripts and result summaries**, provided as-is.
They expect the source dataset / intermediate artifacts laid out at the
repository root, as described in [`../data/DATA.md`](../data/DATA.md) (Zenodo
DOI [10.5281/zenodo.21282648](https://doi.org/10.5281/zenodo.21282648)). They are
**not** imported by the `cqbench` evaluator, which reproduces the same tool
behavior independently (`../cqbench/analyzers.py`).

## What is where

| Paper artifact | Location |
|----------------|----------|
| Analyzer→ODC mappings | **benchmark** — `../mappings/{python,java,c}/*.xlsx` |
| Tool configs + frozen rules | **benchmark** — `../cqbench/rules/` + `../cqbench/analyzers.py` |
| Complexity-metric computation | **benchmark** — `../support/complexity_metrics_extended.py` |
| Naturalness training + scoring | `scripts/naturalness/` |
| RQ1 structural/style results | `results/rq1_structural_style/` |
| RQ2 defect results | `results/rq2_defects/` |
| RQ3 security results | `results/rq3_security/` |
| RQ4 correlation results | `results/rq4/` |
| Model consistency calibration (§4.2) | `calibration/` |
| Source dataset + per-function tables | **Zenodo** — `../data/DATA.md` |

Structural-complexity metrics are computed by
`../support/complexity_metrics_extended.py` (kept in the benchmark because the
evaluator imports the exact definitions).

## `scripts/naturalness/`

Statistical-naturalness pipeline (KenLM self-cross-entropy and transformer
perplexity; paper §6.1.2). Orchestrated by the two `run_*.sh` wrappers.

- `run_naturalness_experiment.sh` → `llm_kenlm_crossentropy_cv.py` — KenLM
  n-gram cross-entropy with 10-fold CV (6-grams).
- `run_hf_perplexity_experiment.sh` → `hf_evaluate_perplexity.py` +
  `perplexity/perplexity.py` — transformer (HF) perplexity.
- `less_normalize_{c,java,python}.py` — the "less-normalized"/regex tokenization
  used for the reported scores (matches the `RESULTS_REGEX` entropy inputs).
- `normalize_identifiers_{java,python}.py` — identifier-normalized setting that
  separates lexical from structural naturalness.
- `compute_metrics.py` — aggregate naturalness metrics.
- `kenlm_setup.py` — KenLM build/install helper.

LM training corpora and fold outputs (tens of GB) are on Zenodo, not in git.
Figure/plot scripts are intentionally omitted.

## `results/`

- `rq1_structural_style/` — `{python,java,c}_metrics.txt` (full per-function
  structural-complexity summaries).
- `rq2_defects/` — per-author Pylint/PMD/Clang-tidy + ODC defect statistics for
  all three languages (`{python,java}_{human,chatgpt,dsc,qwen}_defects.txt`,
  `c_{human,gptoss,dsc,qwen}_defects.txt`; `gptoss` is the OpenAI model for C).
- `rq3_security/` — per-author Semgrep + CWE security statistics for all three
  languages (`{lang}_{author}_security.txt`).
- `rq4/` — `{python,java,c}_rq4_correlations.csv`, `*_rq4_findings_report.md`,
  `*_rq4_validation.json`.

The full per-function result tables (`*_rq4_table.parquet`) are large and hosted
on Zenodo (`../data/DATA.md`).

## `calibration/` (paper §4.2 — model consistency calibration)

Because the "OpenAI GPT" category is ChatGPT for Python/Java and GPT-OSS-20B for
C, §4.2 verifies the two models are consistent enough to report jointly. This
folder holds the calibration code-generation for a 1,000-prompt stratified
subset and its outputs (see `README_calibration.md`):

- `sample_calibration_subset.py` — build the 1,000-prompt subsets.
- `run_codegen_python.py` / `run_codegen_java.py` (+ `.x` SLURM wrappers) —
  GPT-OSS-20B generation matching the C pipeline.
- `reprocess_calibration.py` — post-process outputs into the analysis schema.
- `calibration_{python,java}_1000.jsonl` — the 1,000-prompt input subsets.
- `out_calibration_{python,java}_1000.jsonl` — the GPT-OSS-20B generations
  (self-contained: each row also carries the human/ChatGPT/DeepSeek/Qwen code).

Place the per-metric calibration **panel figure** (the §4.2 comparison of
ChatGPT vs GPT-OSS across metrics) here when exported.
