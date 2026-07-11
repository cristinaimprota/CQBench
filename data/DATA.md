# CQBench dataset

The `benchmark/` directory in this repository is self-contained for **using** the
benchmark (tasks, references, baselines, results, reports). The **full source
dataset** the tasks were derived from is large (~1.9 GB) and is hosted externally
on Zenodo rather than in git.

- **Zenodo DOI:** [10.5281/zenodo.21282648](https://doi.org/10.5281/zenodo.21282648)
- **Zenodo record:** <https://doi.org/10.5281/zenodo.21282648>

## Contents of the Zenodo archive

| File | Description |
|------|-------------|
| `python_dataset.jsonl` | Python ⟨docstring, human-code, ChatGPT/DeepSeek/Qwen-code⟩ tuples |
| `java_dataset.jsonl` | Java ⟨docstring, human-code, ChatGPT/DeepSeek/Qwen-code⟩ tuples |
| `c_dataset.jsonl` | C ⟨docstring, human-code, GPT-OSS/DeepSeek/Qwen-code⟩ tuples |

## How the dataset relates to the code

- `benchmark/tasks.jsonl` + `benchmark/references.jsonl` are **derived** from the
  dataset above by `cqbench build-large`.
- The evaluator (`cqbench evaluate`) does **not** need this dataset — it only needs
  `benchmark/` and the analyzers on `PATH`.
- The dataset is required only to **re-derive** the benchmark or reproduce the
  study's selection/aggregation.

## Re-deriving the benchmark

The per-function metric / defect / vulnerability tables used for task selection
(the `*_rq4_table.parquet` files consumed by `support/rq4_build_table.py`) are
**not** published as artifacts — they are **rebuilt from the dataset** by the
study pipeline in [`replication/`](../replication/README.md) (complexity metrics,
the analyzer runs, and `rq4_build_table.py`). Re-derivation therefore needs the
dataset above plus the analyzer toolchain (pylint 3.3.6, PMD 7.11.0, clang-tidy
18, Semgrep 1.120.0); it does not depend on any pre-built parquet from the
deposit.

## Download

```bash
# from the repository root
mkdir -p datasets
# download python_dataset.jsonl, java_dataset.jsonl, c_dataset.jsonl from
# https://doi.org/10.5281/zenodo.21282648 into datasets/, then verify against
# the checksums published on the Zenodo record.
```

The dataset files are intentionally **not** tracked by git or listed in this
repository's `MANIFEST.sha256`; their integrity is covered by the Zenodo record.
