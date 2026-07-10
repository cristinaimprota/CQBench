#!/bin/bash
#SBATCH --account=IscrC_ARGOS
#SBATCH --partition=boost_usr_prod
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:4
#SBATCH --job-name=gptoss-codegen-java
#SBATCH --output=/leonardo/home/userexternal/cimprota/gptoss-transformers/gptoss_java_%j.out
#SBATCH --error=/leonardo/home/userexternal/cimprota/gptoss-transformers/gptoss_java_%j.err

set -euo pipefail

if [ $# -ne 2 ]; then
  echo "Usage: sbatch run_codegen_java.x <input_jsonl> <output_jsonl>"
  exit 1
fi

INPUT_PATH="$1"
OUTPUT_PATH="$2"

module purge
module load profile/deeplrn
module load cineca-ai/4.1.1

unset PYTHONPATH
unset PYTHONHOME
export PYTHONNOUSERSITE=1

source /leonardo/home/userexternal/cimprota/venvs/gptoss-transformers/bin/activate

echo "=== ENV CHECK ==="
which python
python --version
python -c "import sys; print('PYTHON', sys.executable)"
python -c "import torch, transformers, tokenizers, huggingface_hub, accelerate; print('torch', torch.__version__, torch.__file__); print('transformers', transformers.__version__, transformers.__file__); print('tokenizers', tokenizers.__version__, tokenizers.__file__); print('huggingface_hub', huggingface_hub.__version__, huggingface_hub.__file__); print('accelerate', accelerate.__version__, accelerate.__file__)"
nvidia-smi
echo "INPUT_PATH=$INPUT_PATH"
echo "OUTPUT_PATH=$OUTPUT_PATH"
echo "================="

export INPUT_PATH
export OUTPUT_PATH
export TIKTOKEN_RS_CACHE_DIR=/leonardo_scratch/large/userexternal/cimprota/harmony_cache

python /leonardo/home/userexternal/cimprota/gptoss-transformers/run_codegen_java.py
