# Replication package

These are the **original study scripts and result summaries**, provided as-is. They expect the source dataset / intermediate artifacts laid out at the repository root, as described in [`../data/DATA.md`](../data/DATA.md) (Zenodo DOI [10.5281/zenodo.21282648](https://doi.org/10.5281/zenodo.21282648)). They are **not** imported by the `cqbench` evaluator, which reproduces the same tool behavior independently (`../cqbench/analyzers.py`).

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

Structural-complexity metrics are computed by `../support/complexity_metrics_extended.py` (kept in the benchmark because the evaluator imports the exact definitions).

## `scripts/naturalness/`

Statistical-naturalness pipeline (KenLM self-cross-entropy; paper §6.1.2),
orchestrated by `run_naturalness_experiment.sh`.

- `run_naturalness_experiment.sh` → `llm_kenlm_crossentropy_cv.py` — KenLM n-gram cross-entropy with 10-fold CV (6-grams).
- `normalize_{c,java,python}.py` — the structure-preserving normalization / regex tokenization used for the reported scores (produces the `*_normalized.jsonl` inputs).
- `kenlm_setup.py` — KenLM build/install helper.

## `results/`

- `rq1_structural_style/` — `{python,java,c}_metrics.txt` (full per-function structural-complexity summaries).
- `rq2_defects/` — per-author Pylint/PMD/Clang-tidy + ODC defect statistics for all three languages (`{python,java}_{human,chatgpt,dsc,qwen}_defects.txt`, `c_{human,gptoss,dsc,qwen}_defects.txt`; `gptoss` is the OpenAI model for C).
- `rq3_security/` — per-author Semgrep + CWE security statistics for all three languages (`{lang}_{author}_security.txt`).
- `rq4/` — `{python,java,c}_rq4_correlations.csv`, `*_rq4_findings_report.md`, `*_rq4_validation.json`.

## `calibration/` (paper §4.2 — model consistency calibration)

Because the "OpenAI GPT" category is ChatGPT for Python/Java and GPT-OSS-20B for C, §4.2 verifies the two models are consistent enough to report jointly. This folder holds the GPT-OSS-20B generations on a 1,000-prompt stratified subset of Python and Java (each row also carries the human / ChatGPT / DeepSeek / Qwen code for comparison):

- `calibration_{python,java}_generations.jsonl` — the GPT-OSS-20B generations
