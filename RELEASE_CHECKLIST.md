# Release record — CQBench v1

State of this release (not a to-do list):

- **License:** GPL-3.0 (`LICENSE`).
- **Source dataset:** deposited on Zenodo, DOI
  [10.5281/zenodo.21282648](https://doi.org/10.5281/zenodo.21282648); see
  `data/DATA.md`. The RQ4 metric tables are rebuilt from the dataset by the
  `replication/` pipeline, not shipped as artifacts.
- **Integrity:** every file in the repository is checksummed in
  `MANIFEST.sha256`. Verify with `sha256sum -c MANIFEST.sha256`; regenerate
  after any change with `python tools/build_checksums.py`.
- **Environment:** `pyproject.toml` pins the Python toolchain; full evaluation
  additionally needs PMD 7.11.0, Clang-Tidy 18, and Semgrep 1.120.0 on `PATH`
  (the `Dockerfile` installs them).
