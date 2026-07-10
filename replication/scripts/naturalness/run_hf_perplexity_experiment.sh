#!/bin/bash
set -euo pipefail

# ===============================
# CONFIGURATION (override via env)
# ===============================
PYTHON_SCRIPT="../code/hf_evaluate_perplexity.py"
DATASET="${DATASET:-dataset_no_comments_less_normalized}"
LANGUAGE="${LANGUAGE:-python}"
INPUT="${INPUT:-../../datasets/${LANGUAGE}_${DATASET}.jsonl}"
MODEL_ID="${MODEL_ID:-Salesforce/codegen-350M-multi}"
BATCH_SIZE="${BATCH_SIZE:-16}"
DEVICE="${DEVICE:-auto}"
ADD_START_TOKEN="${ADD_START_TOKEN:-true}"
MAX_SAMPLES="${MAX_SAMPLES:-}"
MAX_LENGTH="${MAX_LENGTH:-}"

if [ -n "${FIELDS_CSV:-}" ]; then
    IFS=',' read -r -a FIELDS <<< "$FIELDS_CSV"
elif [ "$LANGUAGE" = "c" ]; then
    FIELDS=("human_code" "dsc_code" "qwen_code")
else
    FIELDS=("human_code" "chatgpt_code" "dsc_code" "qwen_code")
fi

MODEL_SLUG="${MODEL_ID//\//-}"
OUTPUT="${OUTPUT:-${LANGUAGE}_HFPerplexity_${MODEL_SLUG}_${DATASET}.csv}"
SUMMARY_OUTPUT="${SUMMARY_OUTPUT:-${LANGUAGE}_HFPerplexity_${MODEL_SLUG}_${DATASET}_summary.csv}"

ARGS=(
    --input "$INPUT"
    --output "$OUTPUT"
    --summary-output "$SUMMARY_OUTPUT"
    --model-id "$MODEL_ID"
    --batch-size "$BATCH_SIZE"
    --device "$DEVICE"
    --fields "${FIELDS[@]}"
)

if [ "$ADD_START_TOKEN" = "true" ]; then
    ARGS+=(--add-start-token)
else
    ARGS+=(--no-add-start-token)
fi

if [ -n "$MAX_SAMPLES" ]; then
    ARGS+=(--max-samples "$MAX_SAMPLES")
fi

if [ -n "$MAX_LENGTH" ]; then
    ARGS+=(--max-length "$MAX_LENGTH")
fi

echo "Running: python $PYTHON_SCRIPT ${ARGS[*]}"
python "$PYTHON_SCRIPT" "${ARGS[@]}"
