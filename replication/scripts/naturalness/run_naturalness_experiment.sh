#!/bin/bash

# ===============================
# CONFIGURATION (edit these only)
# ===============================
PYTHON_SCRIPT="../code/llm_kenlm_crossentropy_cv.py"
LANGUAGE="${LANGUAGE:-python}"                                   # Language name (for output files)
if [ "$LANGUAGE" = "c" ]; then
    DATASET="${DATASET:-dataset_final_no_comments_less_normalized}"           # C defaults to c_dataset_final_...
else
    DATASET="${DATASET:-dataset_no_comments_less_normalized}"                 # Dataset name: dataset | dataset_no_comments | dataset_no_comments_normalized
fi
INPUT="../../datasets/${LANGUAGE}_${DATASET}.jsonl"           # Input JSONL file
KENLM="${KENLM:-true}"                                         # true/false: Enable KenLM
HF="${HF:-false}"                                             # true/false: Enable HuggingFace LLM
MODEL="${MODEL:-Salesforce/codet5-small}"                  # HuggingFace model ID | microsoft/CodeGPT-small-py | Salesforce/codegen-350M-multi
TOKENIZER="${TOKENIZER:-treesitter}"                                     # regex | whitespace | llm | treesitter
ORDER_START="${ORDER_START:-2}"                                       # Start n-gram order
ORDER_END="${ORDER_END:-10}"                                         # End n-gram order
MEMORY="${MEMORY:-80%}"                                        # KenLM memory limit
KFOLDS="${KFOLDS:-10}"                                            # Number of CV folds
SEED="${SEED:-42}"                                             # Random seed
DEVICE="${DEVICE:-cuda}"                                       # cuda | cpu | auto
METHOD="${METHOD:-KenLM}"                                      

# List of code authors/variants (fields in JSONL) to train/test on.
# C uses regex tokenization and may include gptoss_code in the final dataset.
if [ "$LANGUAGE" = "c" ]; then
    TRAIN_AUTHORS=("human_code" "dsc_code" "qwen_code" "gptoss_code")
    TEST_AUTHORS="human_code,dsc_code,qwen_code,gptoss_code"
    if [ "$TOKENIZER" = "treesitter" ]; then
        TOKENIZER="regex"
    fi
else
    TRAIN_AUTHORS=("human_code" "chatgpt_code" "dsc_code" "qwen_code")
    TEST_AUTHORS="human_code,chatgpt_code,dsc_code,qwen_code"
fi

# ===============================
# MAIN LOGIC
# ===============================
if $KENLM; then
    # ===============================
    # LOOP OVER N-GRAM ORDERS & TRAIN AUTHORS (KENLM)
    # ===============================
    for ORDER in $(seq $ORDER_START $ORDER_END); do
        for TRAIN_AUTHOR in "${TRAIN_AUTHORS[@]}"; do
            OUTPUT="${LANGUAGE}_${METHOD}_${TRAIN_AUTHOR}_${ORDER}gram_${TOKENIZER}_${DATASET}.csv"
            ARGS="--input $INPUT --output $OUTPUT --k $KFOLDS --seed $SEED --tokenizer $TOKENIZER --train_author $TRAIN_AUTHOR --test_authors $TEST_AUTHORS --language $LANGUAGE"
            
            ARGS="$ARGS --kenlm --order $ORDER --memory $MEMORY"
            
            if $HF; then
                ARGS="$ARGS --hf --model $MODEL --device $DEVICE"
            fi

            echo "Running: python $PYTHON_SCRIPT $ARGS"
            python $PYTHON_SCRIPT $ARGS
        done
    done

elif $HF; then
    # ===============================
    # ONLY ONE RUN NEEDED FOR LLM (HF) SCORING
    # ===============================
    OUTPUT="${LANGUAGE}_llm_${MODEL//\//-}_${TOKENIZER}_${DATASET}.csv"
    ARGS="--input $INPUT --output $OUTPUT --k $KFOLDS --seed $SEED --tokenizer $TOKENIZER --test_authors $TEST_AUTHORS --hf --model $MODEL --device $DEVICE --language $LANGUAGE"
    echo "Running: python $PYTHON_SCRIPT $ARGS"
    python -s $PYTHON_SCRIPT $ARGS

else
    echo "ERROR: Please set either KENLM=true or HF=true"
    exit 1
fi
