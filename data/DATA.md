# CQBench dataset

The `benchmark/` directory in this repository is self-contained for **using** the
benchmark (tasks, references, baselines, results, reports). The **full source
dataset** the tasks were derived from is large (multiple GB) and is hosted
externally on Zenodo rather than in git.

- **Zenodo DOI:** [10.5281/zenodo.21282648](https://doi.org/10.5281/zenodo.21282648)
- **Zenodo record:** <https://doi.org/10.5281/zenodo.21282648>

## Contents of the Zenodo archive

| File | Description |
|------|-------------|
| `datasets/final_datasets/python_dataset_nodocs_dsc_qwen_FINAL.jsonl` | Python ⟨docstring, human-code, ChatGPT/DeepSeek/Qwen-code⟩ tuples |
| `datasets/final_datasets/java_dataset_dsc_qwen_FINAL.jsonl` | Java tuples |
| `c_dataset_final_corrected.jsonl` | C ⟨docstring, human-code, GPT-OSS/DeepSeek/Qwen-code⟩ tuples |
| `python_rq4_table.parquet`, `java_rq4_table.parquet`, `c_rq4_table.parquet` | Per-function metric + defect/vulnerability tables used for task selection (RQ4) |

(Adjust this list to match the final Zenodo deposit.)

## How the dataset relates to the code

- `benchmark/tasks.jsonl` + `benchmark/references.jsonl` are **derived** from the
  dataset above by `cqbench build-large`.
- The evaluator (`cqbench evaluate`) does **not** need this dataset — it only needs
  `benchmark/` and the analyzers on `PATH`.
- The dataset is required only to **re-derive** the benchmark or reproduce the
  study's selection/aggregation.

## Download and placement

To re-derive or reproduce, download the archive and place the files at the
repository root so the `ROOT`-relative paths in `support/rq4_build_table.py` and
`cqbench/config.py` resolve:

```bash
# from the repository root
mkdir -p datasets/final_datasets
# download from https://doi.org/10.5281/zenodo.21282648 and extract here,
# preserving the paths in the table above
# e.g.:
#   datasets/final_datasets/python_dataset_nodocs_dsc_qwen_FINAL.jsonl
#   datasets/final_datasets/java_dataset_dsc_qwen_FINAL.jsonl
#   c_dataset_final_corrected.jsonl
#   python_rq4_table.parquet  java_rq4_table.parquet  c_rq4_table.parquet

# verify integrity against the Zenodo-published checksums
sha256sum -c data/dataset.sha256   # (publish this file alongside the Zenodo deposit)
```

These dataset files are intentionally **not** tracked by git or listed in the
repository's `MANIFEST.sha256`; their integrity is covered by the Zenodo record
and `data/dataset.sha256`.
