# CQBench run report — Claude Opus 4.8

**Model under test:** Claude Opus 4.8 (`claude-opus-4-8`), used as the code-generation
model. Each function was implemented from its task `prompt` alone — no execution
feedback, no access to the human reference, and no knowledge of the analyzer rules.

**Subset:** 600 tasks = **200 per language** (Python / Java / C), sampled deterministically
(seed 2025), proportional-by-stratum, spread across the difficulty score. This is a
*stress subset*, not the benchmark population.

**Scoring:** the standard evaluator — pylint 3.3.6 (Python), PMD 7.11.0 (Java),
clang-tidy 18 (C), Semgrep 1.120.0 (all) — mapped to ODC defect categories and CWEs.
Static analysis only: no execution, so this measures cleanliness, not correctness.
Scored with the study-aligned analyzer pipeline (clang-tidy `--checks=*`; Semgrep
Java-wrapping + error-discard; PMD `error_recovery` + package/import-aware wrapping).

Artifacts: `runs/claude-opus-4-8/` (predictions, results, report, comparison,
issue distribution).

## Headline — `clean_strict_at_1`

Fraction of tasks whose single generated function is parseable, present with the right
arity, non-stub, non-constant, complexity-nondegenerate, **and** has zero analyzer
defect and vulnerability findings.

| language | n | parseable | strict-nontrivial | defect-free | vuln-free | **clean_strict@1** |
|----------|---|-----------|-------------------|-------------|-----------|--------------------|
| Python   | 200 | 1.00 | 1.00 | 0.37 | 0.72 | **0.275** |
| Java     | 200 | 1.00 | 1.00 | 0.355 | 0.840 | **0.320** |
| C        | 200 | 0.99 | 0.99 | 0.315 | 0.535 | **0.140** |

Claude produces real, substantive code on essentially every task (≈100% parseable and
non-trivial), but only **14–32%** of solutions are free of all analyzer findings. **The
benchmark remains hard for a frontier model** — the difficulty is in producing
analyzer-clean, not merely plausible, code.

## Claude vs. historical baselines (same 600 tasks)

`clean_strict_at_1`, delta = Claude − baseline, 95% paired bootstrap CI (10k resamples):

| baseline | Python | Java | C |
|----------|--------|------|---|
| **human**  | −0.040 [−0.110, +0.030] | −0.070 [−0.140, 0.000] | −0.030 [−0.095, +0.030] |
| openai   | **+0.270** [+0.210, +0.330] | **+0.320** [+0.260, +0.385] | **+0.075** [+0.015, +0.135] |
| dsc      | **+0.250** [+0.185, +0.315] | **+0.300** [+0.230, +0.365] | **+0.135** [+0.085, +0.185] |
| qwen     | **+0.220** [+0.155, +0.290] | **+0.240** [+0.180, +0.300] | **+0.100** [+0.045, +0.155] |

- **Claude clearly beats the historical AI baselines** (OpenAI / DeepSeek / Qwen) in every
  language — CIs exclude zero. (These baselines were selected as failure-prone on these
  tasks, so this is a favorable-by-construction comparison, not a general ranking.)
- **Claude is statistically tied with, and slightly below, the human references** — every
  human CI straddles zero. On this stress set a frontier model roughly matches
  human-written code but does not surpass it.

## Issue-type distribution — are the issues different?

ODC defect-type incidence (fraction of tasks with ≥1 finding of that category), all 600
tasks. Full per-language breakdown in `runs/claude-opus-4-8/issue_distribution.csv`.

| author | Assignment | Algorithm | Interface | Checking | Timing/Serial | Func/Class/Obj | any defect | any vuln |
|--------|-----------|-----------|-----------|----------|---------------|----------------|-----------|----------|
| claude | 0.20 | 0.16 | 0.26 | 0.23 | 0.08 | **0.03** | 0.66 | 0.30 |
| human  | 0.22 | 0.20 | 0.23 | 0.17 | 0.07 | **0.03** | 0.64 | 0.23 |
| openai | 0.27 | 0.22 | 0.29 | 0.29 | 0.08 | 0.12 | 0.77 | 0.50 |
| dsc    | 0.31 | 0.23 | 0.35 | 0.43 | 0.13 | 0.27 | 0.91 | 0.59 |
| qwen   | 0.37 | 0.24 | 0.28 | 0.24 | 0.10 | 0.17 | 0.79 | 0.45 |

**Yes, the mix differs — and Claude's profile mirrors the human references, not the other
AI authors:**

- **Claude ≈ human** across every ODC category; both sit well below the weaker AI baselines
  on overall defect and vulnerability incidence.
- The AI baselines' extra defects concentrate in **Checking** (dsc 0.43 vs Claude/human
  ~0.17–0.23) and **Function/Class/Object** (dsc 0.27, qwen 0.17 vs Claude/human 0.03) —
  i.e. missing validation/guards and structural/definition issues. Claude and humans
  largely avoid the Func/Class/Obj category entirely.
- Per-language highlights (see CSV): in **Python**, dsc/qwen have very high **Assignment**
  defects (0.55/0.62 — unused vars/imports, bad assignments) vs Claude 0.29/human 0.26; in
  **Java**, Claude has near-zero **Interface** defects (0.02) vs openai/dsc ~0.20; in **C**,
  **Interface** issues are high for everyone (~0.41–0.45) and Claude's **vulnerability**
  incidence is highest of its languages (0.47), driven by memory/OS-command patterns.

### Vulnerability types (CWE) — cross-author

The shipped historical *results* store empty CWE lists, but the raw Semgrep findings are
in the repo (`risultati_{python,java}/report_semgrep/…`, `C_security/…`). Extracted with
the benchmark's own loader (`legacy.load_raw_vulnerabilities` + `cwes_from_raw`) on the same
600 tasks and authors (`openai` = ChatGPT for Python/Java, GPT-OSS for C). Finding counts:

| CWE | what | claude | human | openai | dsc | qwen |
|-----|------|-------:|------:|-------:|----:|-----:|
| CWE-120 | buffer overflow (unbounded copy) | 61 | 47 | 73 | 83 | 65 |
| CWE-126 | buffer over-read | 39 | 36 | 50 | 49 | 48 |
| CWE-676 | use of dangerous function | 23 | 28 | 27 | 63 | 52 |
| CWE-78  | OS command injection | 33 | 12 | 47 | 47 | 37 |
| CWE-489 | leftover debug/active-debug code | **0** | 5 | 30 | 71 | 37 |
| CWE-532 | info exposure via log | 13 | 7 | 26 | 59 | 30 |
| CWE-400 | uncontrolled resource consumption | 6 | 7 | 26 | 39 | 27 |
| CWE-362 | race condition | 18 | 9 | 25 | 20 | 20 |
| CWE-611 | XML external entity (XXE) | 11 | 4 | 15 | 16 | 17 |
| CWE-22  | path traversal | **0** | 1 | 16 | 19 | 1 |
| CWE-319 | cleartext transmission | 4 | 2 | 7 | 16 | 7 |
| CWE-89  | SQL injection | 4 | 5 | 9 | 11 | 5 |

Vulnerability incidence (tasks with ≥1 CWE / 600): claude **0.30**, human 0.23, openai 0.50,
dsc 0.59, qwen 0.45 — matching the ODC-table `any vuln` column.

**The vulnerability *type* mix also tracks human, not the AI baselines:**
- The AI baselines' surplus is concentrated in **hygiene/leftover-artifact** CWEs that Claude
  and humans almost never emit: **CWE-489** (leftover debug code — Claude **0**, dsc 71, qwen 37),
  **CWE-532** (secrets in logs), **CWE-400**, and **CWE-22** (path traversal — Claude **0**, dsc 19).
- **CWE-676** (dangerous C functions like `strcpy`/`gets`) is far higher for dsc/qwen (63/52) than
  Claude/human (23/28).
- Everyone's top categories are the C memory-safety patterns **CWE-120 / CWE-126**; these are
  intrinsic to the C tasks and Claude is mid-pack, not immune.
- Claude is **not** uniformly best: it logs more command-injection findings than the human
  reference (**CWE-78** 33 vs 12) and slightly more race conditions (CWE-362 18 vs 9) — those
  are its relative weak spots.

Full per-language breakdown in `runs/claude-opus-4-8/cwe_distribution.csv`
(extractor: `extract_cwes.py`).

## Caveats

- 600-task stress subset, **not** the benchmark population; results speak to robustness on
  known issue-prone tasks, not population-wide quality.
- Static analysis only — no execution, no functional-correctness check; analyzer findings
  include false positives.
- The AI baselines were selected as failure-prone, biasing the Claude-vs-baseline gap upward.
- CWE cross-author figures come from the raw Semgrep findings (the packaged historical
  *results* files carry no CWE detail); ODC defect figures come from the frozen study tables.
