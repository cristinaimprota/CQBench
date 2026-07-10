# Calibration codegen — Python and Java

These two scripts (`run_codegen_python.py`, `run_codegen_java.py`) extend the
existing C-generation pipeline (`run_codegen_try.py`) to produce gpt-oss-20b
completions for a 1,000-prompt stratified subset of HMCorp Python and Java
respectively. Output schema, batching, Harmony parsing, and SLURM wrapper
structure all match the C run, so downstream analysis tooling that already
consumes the C output works on these files too.

## Layout

```
gptoss-transformers/
├── run_codegen_try.py       # existing — C generation
├── run_codegen_try.x        # existing — SLURM wrapper for C
├── run_codegen_shard.x      # existing — SLURM wrapper for C shards
├── run_codegen_python.py    # NEW — Python generation
├── run_codegen_python.x     # NEW — SLURM wrapper for Python
├── run_codegen_java.py      # NEW — Java generation
└── run_codegen_java.x       # NEW — SLURM wrapper for Java
```

Place all `.py` and `.x` files in `/leonardo/home/userexternal/cimprota/gptoss-transformers/`.
Make the wrappers executable: `chmod +x run_codegen_python.x run_codegen_java.x`.

## Inputs

The calibration JSONLs are expected at:

```
$SCRATCH/datasets/calibration/calibration_python_1000.jsonl
$SCRATCH/datasets/calibration/calibration_java_1000.jsonl
```

Each row must contain at minimum `hm_index`, `docstring`, and `human_code`.
Reference completions (`chatgpt_code`, `dsc_code`, `qwen_code`) are passed
through verbatim so the output JSONL is a complete self-contained record for
later joining.

## Submitting jobs

Both wrappers take two positional arguments — input JSONL and output JSONL —
identical to `run_codegen_shard.x`.

```bash
# Python calibration
sbatch run_codegen_python.x \
  $SCRATCH/datasets/calibration/calibration_python_1000.jsonl \
  $SCRATCH/results/calibration/out_calibration_python_1000.jsonl

# Java calibration
sbatch run_codegen_java.x \
  $SCRATCH/datasets/calibration/calibration_java_1000.jsonl \
  $SCRATCH/results/calibration/out_calibration_java_1000.jsonl
```

The output directory is created automatically if missing.

## Tunables (env vars; same defaults as the C script)

| variable             | default | notes                                     |
|----------------------|---------|-------------------------------------------|
| `MAX_NEW_TOKENS`     | 512     | per-sample generation budget              |
| `BATCH_SIZE`         | 40      | drop to 16 if you hit OOM on long Java    |
| `DO_SAMPLE`          | 0       | greedy decoding by default                |
| `TEMPERATURE`        | 0.2     | only used when `DO_SAMPLE=1`              |
| `TOP_P`              | 0.9     | only used when `DO_SAMPLE=1`              |
| `REPETITION_PENALTY` | 1.05    |                                            |
| `FORCE_BATCH_SIZE_ONE` | 0     | set to 1 for the safest debug pass        |

Override at submission time:

```bash
BATCH_SIZE=16 sbatch run_codegen_java.x \
  $SCRATCH/datasets/calibration/calibration_java_1000.jsonl \
  $SCRATCH/results/calibration/out_calibration_java_1000.jsonl
```

## Output schema

Each output line contains:

```json
{
  "hm_index":              "...",
  "docstring":             "sanitized docstring",
  "human_code":            "original reference function",
  "signature":             "extracted from human_code",
  "prompt":                "full Harmony chat-template prompt sent to the model",
  "raw_generated_text":    "tokenizer.batch_decode of generated_ids",
  "parsed_final_text":     "final-channel content extracted from Harmony",
  "cleaned_generated_text":"after fence/signature/docstring stripping",
  "generated_body":        "function body only",
  "generated_function":    "signature + body, ready to parse",
  "model":                 "/path/to/gpt-oss-20b",
  "max_new_tokens":        512,
  "batch_size_used":       40,
  "chatgpt_code":          "...",
  "dsc_code":              "...",
  "qwen_code":             "..."
}
```

The reference-completion fields (`chatgpt_code`, `dsc_code`, `qwen_code`) are
copied through unchanged from the input JSONL.

## What's different per language

**Python** — `extract_python_signature` walks the source tracking paren depth
and string state, so multi-line signatures, default args containing `:` or
`(`, and `async def` all work. Body cleanup strips a regenerated `def` line,
strips a leading triple-quoted (or single-line) docstring if the model emits
one, then takes indented lines until the indent drops or two blank lines
appear, then normalizes to a 4-space indent.

**Java** — `extract_java_signature` normalizes `\r\n` → `\n` and finds the
first `{` outside string/char/comment context, so annotations, generics,
modifier ordering, `throws` clauses, and `{`-in-comments all behave. Body
extraction is the same balanced-brace tracking as the C pipeline (strings and
char literals respected), since Java's lexical structure here is essentially
identical to C.

**No bug-validation step.** The C script's `validate_generated_body` (with the
X11/cv-specific critical-call list and `-1` sentinel heuristics) was deliberately
not ported — the calibration goal is stylometric comparability against the
existing ChatGPT outputs, and bug detection happens downstream in the analysis
phase.

## Sanity check before submitting the full run

To verify the pipeline end-to-end on a tiny subset before launching the full
job, set `LIMIT_SAMPLES` (you'll need to expose it as an env var first — it's
currently hardcoded to `None` like in the C script) and `FORCE_BATCH_SIZE_ONE=1`,
or simply head -n 10 the JSONL into a temp file and run on that:

```bash
head -n 10 $SCRATCH/datasets/calibration/calibration_python_1000.jsonl \
  > /tmp/calib_py_smoke.jsonl
FORCE_BATCH_SIZE_ONE=1 sbatch run_codegen_python.x \
  /tmp/calib_py_smoke.jsonl \
  /tmp/calib_py_smoke_out.jsonl
```

Inspect the first few output rows, particularly `signature`, `cleaned_generated_text`,
and `generated_function`, before scaling to 1000.
