import json
import os
import re
import time
from pathlib import Path
from typing import List, Dict, Any

from tqdm import tqdm
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from openai_harmony import (
    HarmonyEncodingName,
    load_harmony_encoding,
)

# ============================================================
# CONFIG
# ============================================================
USER = "cimprota"

HOME = Path(f"/leonardo/home/userexternal/{USER}")
SCRATCH = Path(f"/leonardo_scratch/large/userexternal/{USER}")

MODEL_PATH = SCRATCH / "models" / "gpt-oss-20b"

INPUT_PATH = Path(
    os.environ.get(
        "INPUT_PATH",
        str(SCRATCH / "datasets" / "calibration" / "calibration_java_1000.jsonl")
    )
)

OUTPUT_PATH = Path(
    os.environ.get(
        "OUTPUT_PATH",
        str(SCRATCH / "results" / "calibration" / "out_calibration_java_1000.jsonl")
    )
)

MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "512"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "40"))
LIMIT_SAMPLES = None
DO_SAMPLE = os.environ.get("DO_SAMPLE", "0") == "1"
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.2"))
TOP_P = float(os.environ.get("TOP_P", "0.9"))
REPETITION_PENALTY = float(os.environ.get("REPETITION_PENALTY", "1.05"))

PRINT_FIRST_N_BATCHES = 2
PRINT_PROMPT_CHARS = 1200
PRINT_OUTPUT_CHARS = 1200

FORCE_BATCH_SIZE_ONE = os.environ.get("FORCE_BATCH_SIZE_ONE", "0") == "1"


# ============================================================
# HELPERS
# ============================================================
def sanitize(text: str) -> str:
    if not text:
        return ""
    t = text
    t = re.sub(r"<\|.*?\|>", "", t, flags=re.DOTALL)
    t = re.sub(r"to=repo_browser\.\w+", "", t)
    t = re.sub(r"repo_browser\.\w+", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def normalize_newlines(s: str) -> str:
    if not s:
        return ""
    return s.replace("\r\n", "\n").replace("\r", "\n")


def extract_java_signature(java_code: str) -> str:
    """
    Extract a Java method signature: everything up to (and including) the first
    `{` at brace-depth 0, with internal whitespace runs collapsed to single spaces.

    The user is responsible for any class-wrapper stripping upstream; this
    function operates on either a bare method or a method body that begins at
    column 0.

    Annotations, modifiers, generics, return type, parameters, and `throws`
    clauses are all preserved.
    """
    if not java_code:
        return ""

    code = normalize_newlines(java_code)

    # Conservative: find the first '{' that is not inside a string or char literal
    # or a line comment. We do a small scan instead of a naive .find('{') to avoid
    # the (rare) case of a default-string or annotation that contains '{'.
    in_str = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escape = False

    brace_index = -1
    i = 0
    n = len(code)
    while i < n:
        ch = code[i]

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and i + 1 < n and code[i + 1] == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if escape:
            escape = False
            i += 1
            continue

        if in_str:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue

        if in_char:
            if ch == "\\":
                escape = True
            elif ch == "'":
                in_char = False
            i += 1
            continue

        # Line comment?
        if ch == "/" and i + 1 < n and code[i + 1] == "/":
            in_line_comment = True
            i += 2
            continue
        # Block comment?
        if ch == "/" and i + 1 < n and code[i + 1] == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_str = True
        elif ch == "'":
            in_char = True
        elif ch == "{":
            brace_index = i
            break
        i += 1

    snippet = code if brace_index == -1 else code[:brace_index]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet + " {" if snippet else ""


def load_rows(path: Path) -> List[Dict[str, Any]]:
    """
    Load rows from the calibration JSONL.

    Required fields: hm_index, docstring, human_code.
    Reference completions (chatgpt_code, dsc_code, qwen_code) are preserved
    pass-through so downstream comparison can join on the same row.
    """
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            hm_index = data.get("hm_index") or data.get("hexsha")
            docstring = data.get("docstring")
            human_code = data.get("human_code") or data.get("code")

            if hm_index and docstring and human_code:
                row = {
                    "hm_index": hm_index,
                    "docstring": docstring,
                    "human_code": human_code,
                }
                for k in ("chatgpt_code", "dsc_code", "qwen_code"):
                    if k in data:
                        row[k] = data[k]
                rows.append(row)

    if LIMIT_SAMPLES is not None:
        rows = rows[:LIMIT_SAMPLES]

    print(f"Loaded {len(rows)} rows from {path}")
    return rows


def build_messages(docstring: str, signature: str):
    doc = sanitize(docstring)
    sig = sanitize(signature)

    return [
        {
            "role": "system",
            "content": (
                "You are a careful Java code generation assistant.\n"
                "Write Java code only.\n"
                "Do not explain your answer.\n"
                "Do not think out loud.\n"
                "Do not browse, inspect repositories, or call tools.\n"
                "Do not add markdown fences.\n"
                "Do not add `import` statements.\n"
                "Do not wrap the method in a class or interface.\n"
                "Do not add extra annotations beyond those already present in the signature.\n"
                "Use the exact method signature provided, including any annotations, modifiers, generics, return type, parameters, and `throws` clauses.\n"
                "Complete only this method.\n"
                "Do not repeat the signature or the method name.\n"
                "Start with the first statement inside the body and end with the matching closing brace.\n"
                "Prefer preserving the apparent implementation style of an existing Java codebase.\n"
                "If the method appears to be a thin wrapper, adapter, or convenience helper, keep it as a thin wrapper.\n"
                "Prefer existing API calls already implied by the method name, parameters, and docstring instead of inventing new logic.\n"
                "Do not replace obvious existing APIs with different ones.\n"
                "Do not invent undeclared helper methods or new abstractions.\n"
                "Preserve obvious sentinel/error return values such as `null`, `-1`, or empty results when the task suggests not-found or failure behavior.\n"
                "Keep the implementation minimal and direct."
            ),
        },
        {
            "role": "user",
            "content": (
                "Implement the following Java method from its docstring.\n\n"
                f"Docstring:\n{doc}\n\n"
                f"Signature:\n{sig}"
            ),
        },
    ]


def parse_final_from_harmony(raw_text: str, harmony_encoding) -> str:
    """
    Extract assistant final-channel content from the model's raw output.
    See run_codegen_python.py for the rationale; same logic here.
    """
    if not raw_text:
        return ""

    try:
        parsed = harmony_encoding.parse_messages(raw_text)
        final_chunks = []
        for msg in parsed:
            if getattr(msg, "channel", None) == "final":
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    final_chunks.append(content)
                elif content is not None:
                    final_chunks.append(str(content))
        joined = "\n".join(x for x in final_chunks if x)
        if joined.strip():
            return joined.lstrip("\n").rstrip()
    except Exception:
        pass

    m = re.search(
        r"<\|channel\|>final<\|message\|>(.*?)(?=<\|start\|>|<\|return\|>|<\|endoftext\|>|$)",
        raw_text,
        flags=re.DOTALL,
    )
    if m and m.group(1).strip():
        return m.group(1).lstrip("\n").rstrip()

    cut_match = re.search(r"<\|[^|>\n]*\|>", raw_text)
    cut = raw_text[:cut_match.start()] if cut_match else raw_text
    return cut.lstrip("\n").rstrip()


def clean_java_completion(text: str, signature: str) -> str:
    """
    Strip Harmony residue, markdown fences, and a regenerated signature header
    if the model echoed one before the body.
    """
    if not text:
        return ""
    # Defensive: cut at any residual <|...|> marker.
    cut_match = re.search(r"<\|[^|>\n]*\|>", text)
    if cut_match:
        text = text[:cut_match.start()]
    # Remove markdown fences anywhere.
    text = re.sub(r"```(?:java|Java)?[ \t]*\n?", "", text)
    text = re.sub(r"```", "", text)
    text = normalize_newlines(text).strip()

    # If there's a header before the first '{' that looks like a method signature
    # (contains '(' and ')'), assume the model regenerated the signature and
    # peel it off, leaving the body that begins after the opening brace.
    stripped = text.lstrip()
    first_brace = stripped.find("{")
    if first_brace != -1:
        header = stripped[:first_brace].strip()
        looks_like_signature = (
            "(" in header
            and ")" in header
            and not header.startswith((
                "if ", "if(",
                "for ", "for(",
                "while ", "while(",
                "switch ", "switch(",
                "do", "else",
                "try", "catch",
                "synchronized ", "synchronized(",
                "static {", "static{",
            ))
        )
        if looks_like_signature:
            stripped = stripped[first_brace + 1:].lstrip()
    return stripped.strip()


def take_until_balanced_function_body(generated: str) -> str:
    """
    Balanced-brace tracking that respects Java string literals, char literals,
    `//` line comments, AND `/* ... */` block comments. Starts at depth 1 (the
    method's opening `{` has already been consumed by the cleaner).

    Comment-handling is critical: an apostrophe in a `//` line comment
    (e.g. `// match the line's pattern`) used to flip `in_char = True`
    indefinitely and hide every subsequent `}`, causing the tracker to walk
    past the real end of the method.
    """
    if not generated:
        return ""

    out = []
    depth = 1
    in_str = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escape = False

    i = 0
    n = len(generated)
    while i < n:
        ch = generated[i]
        out.append(ch)

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and i + 1 < n and generated[i + 1] == "/":
                out.append(generated[i + 1])
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if escape:
            escape = False
            i += 1
            continue

        if in_str:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue

        if in_char:
            if ch == "\\":
                escape = True
            elif ch == "'":
                in_char = False
            i += 1
            continue

        if ch == "/" and i + 1 < n and generated[i + 1] == "/":
            out.append(generated[i + 1])
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and i + 1 < n and generated[i + 1] == "*":
            out.append(generated[i + 1])
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_str = True
        elif ch == "'":
            in_char = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1

    return "".join(out).strip()


def assemble_function(signature: str, generated_body: str) -> str:
    body = generated_body.rstrip()
    if not body:
        return ""
    return f"{signature}\n{body}"


def print_all_gpu_mem(prefix: str):
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            allocated = torch.cuda.memory_allocated(i) / 1024**3
            reserved = torch.cuda.memory_reserved(i) / 1024**3
            print(f"{prefix} | GPU {i}: allocated={allocated:.2f} GB reserved={reserved:.2f} GB")


def chunk_rows(rows: List[Dict[str, Any]], batch_size: int):
    for i in range(0, len(rows), batch_size):
        yield i, rows[i:i + batch_size]


# ============================================================
# MAIN
# ============================================================
def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    import transformers
    import tokenizers
    import huggingface_hub
    import accelerate
    import sys

    print("PYTHON:", sys.executable)
    print("TRANSFORMERS:", transformers.__version__, transformers.__file__)
    print("TOKENIZERS:", tokenizers.__version__, tokenizers.__file__)
    print("HF HUB:", huggingface_hub.__version__, huggingface_hub.__file__)
    print("ACCELERATE:", accelerate.__version__, accelerate.__file__)

    print(f"MODEL_PATH = {MODEL_PATH}")
    print(f"INPUT_PATH = {INPUT_PATH}")
    print(f"OUTPUT_PATH = {OUTPUT_PATH}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"MAX_NEW_TOKENS = {MAX_NEW_TOKENS}")
    print(f"BATCH_SIZE = {BATCH_SIZE}")
    print(f"DO_SAMPLE = {DO_SAMPLE}")
    print(f"TEMPERATURE = {TEMPERATURE}")
    print(f"TOP_P = {TOP_P}")
    print(f"REPETITION_PENALTY = {REPETITION_PENALTY}")
    if torch.cuda.is_available():
        print(f"CUDA device count: {torch.cuda.device_count()}")
        print(f"Current device: {torch.cuda.current_device()}")
        print(f"Device name: {torch.cuda.get_device_name(torch.cuda.current_device())}")

    harmony_encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token_id is None:
        if tokenizer.eos_token_id is None:
            raise ValueError("Tokenizer has neither pad_token_id nor eos_token_id.")
        tokenizer.pad_token = tokenizer.eos_token

    print("Loading model...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()

    print("Model loaded.\n")
    print_all_gpu_mem("AFTER MODEL LOAD")

    rows = load_rows(INPUT_PATH)

    effective_batch_size = 1 if FORCE_BATCH_SIZE_ONE else BATCH_SIZE
    print(f"EFFECTIVE_BATCH_SIZE = {effective_batch_size}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as _:
        pass

    pbar = tqdm(total=len(rows))
    total_written = 0

    model_device = next(model.parameters()).device

    for batch_idx, (start_idx, current_batch) in enumerate(chunk_rows(rows, effective_batch_size)):
        prompts_text = []
        metadata = []

        for row in current_batch:
            sig = extract_java_signature(row["human_code"])
            messages = build_messages(row["docstring"], sig)
            prompt_text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            prompt_text += "<|start|>assistant<|channel|>final<|message|>"

            prompts_text.append(prompt_text)
            meta = {
                "hm_index": row["hm_index"],
                "docstring": row["docstring"],
                "human_code": row["human_code"],
                "signature": sig,
                "prompt": prompt_text,
            }
            for k in ("chatgpt_code", "dsc_code", "qwen_code"):
                if k in row:
                    meta[k] = row[k]
            metadata.append(meta)

        if batch_idx < PRINT_FIRST_N_BATCHES and prompts_text:
            print("\n" + "=" * 120)
            print(f"BATCH DEBUG | batch_size={len(current_batch)}")
            print("-" * 120)
            print("FIRST PROMPT (truncated):")
            print(prompts_text[0][:PRINT_PROMPT_CHARS])
            if len(prompts_text[0]) > PRINT_PROMPT_CHARS:
                print(f"... [prompt truncated, total chars={len(prompts_text[0])}]")
            print("=" * 120 + "\n")

        encoded = tokenizer(
            prompts_text,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=2048,
        )
        encoded = {k: v.to(model_device) for k, v in encoded.items()}
        prompt_len = encoded["input_ids"].shape[1]

        start_t = time.time()
        generate_kwargs = {
            "max_new_tokens": MAX_NEW_TOKENS,
            "do_sample": DO_SAMPLE,
            "repetition_penalty": REPETITION_PENALTY,
            "use_cache": True,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
            "return_dict_in_generate": False,
        }
        if DO_SAMPLE:
            generate_kwargs["temperature"] = TEMPERATURE
            generate_kwargs["top_p"] = TOP_P

        with torch.no_grad():
            outputs = model.generate(
                **encoded,
                **generate_kwargs,
            )
        elapsed = time.time() - start_t

        generated_ids = outputs[:, prompt_len:]
        raw_out_texts = tokenizer.batch_decode(
            generated_ids,
            skip_special_tokens=False,
        )

        if batch_idx < PRINT_FIRST_N_BATCHES and raw_out_texts:
            print("FIRST RAW OUTPUT (truncated):")
            print(raw_out_texts[0][:PRINT_OUTPUT_CHARS])
            if len(raw_out_texts[0]) > PRINT_OUTPUT_CHARS:
                print(f"... [output truncated, total chars={len(raw_out_texts[0])}]")
            print()

        with open(OUTPUT_PATH, "a", encoding="utf-8") as f:
            for meta, raw_out_text in zip(metadata, raw_out_texts):
                final_text = parse_final_from_harmony(raw_out_text, harmony_encoding)
                cleaned = clean_java_completion(final_text, meta["signature"])
                body = take_until_balanced_function_body(cleaned)
                full_function = assemble_function(meta["signature"], body)

                out_row = {
                    "hm_index": meta["hm_index"],
                    "docstring": sanitize(meta["docstring"]),
                    "human_code": meta["human_code"],
                    "signature": meta["signature"],
                    "prompt": meta["prompt"],
                    "raw_generated_text": raw_out_text,
                    "parsed_final_text": final_text,
                    "cleaned_generated_text": cleaned,
                    "generated_body": body,
                    "generated_function": full_function,
                    "model": str(MODEL_PATH),
                    "max_new_tokens": MAX_NEW_TOKENS,
                    "batch_size_used": effective_batch_size,
                }
                for k in ("chatgpt_code", "dsc_code", "qwen_code"):
                    if k in meta:
                        out_row[k] = meta[k]
                f.write(json.dumps(out_row, ensure_ascii=False) + "\n")
                total_written += 1

        print(
            f"[OK] idx={start_idx}..{start_idx + len(current_batch) - 1} "
            f"batch_size={len(current_batch)} "
            f"elapsed={elapsed:.2f}s "
            f"sec/sample={elapsed / len(current_batch):.2f} "
            f"written={total_written}"
        )
        print_all_gpu_mem("AFTER BATCH")
        pbar.update(len(current_batch))

    pbar.close()
    print(f"Done. Wrote {total_written} rows to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
