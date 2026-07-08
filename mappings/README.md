# Analyzer-to-ODC mappings

The mapping files are organized consistently by language:

| Language | Analyzer | File | Rows |
|---|---|---|---:|
| Python | Pylint | `python/pylint_odc.xlsx` | 352 |
| Java | PMD | `java/pmd_odc.xlsx` | 283 |
| C | Clang-Tidy | `c/clang_tidy_odc.xlsx` | 401 |

Each analyzer rule or message symbol maps to one of the six included ODC
types: Assignment, Algorithm, Interface, Checking, Timing/Serialization, or
Function/Class/Object. A `--` value denotes a finding excluded from ODC
counts. The additional explicit exclusions used by CQBench are frozen in
`support/rq4_build_table.py` and reused by `cqbench/analyzers.py`.

The original spreadsheets used different column languages and naming
conventions. They are preserved internally; only their filenames and package
locations were normalized.
