# Release checklist

Automated package validation is complete. Before publishing this directory:

- Source dataset deposited on Zenodo: DOI 10.5281/zenodo.21282648 (recorded in
  `data/DATA.md`). Publish `data/dataset.sha256` alongside the deposit and confirm
  the archive's file paths match the table in `data/DATA.md`.
- Add the license selected by the dataset/code owners. No license is inferred
  here because that is a legal/ownership decision.
- Add repository URL, author list, version date, and DOI/archive identifier to
  the final citation metadata.
- Run the Docker build and one full evaluation on a Docker-capable host.
- Review prompts and baseline code against the source datasets' redistribution
  terms and privacy policy.
- Regenerate `MANIFEST.sha256` after any change:

  ```bash
  python tools/build_checksums.py
  ```
