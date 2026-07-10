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
        str(SCRATCH / "datasets" / "calibration" / "calibration_python_1000.jsonl")
    )
)

OUTPUT_PATH = Path(
    os.environ.get(
        "OUTPUT_PATH",
        str(SCRATCH / "results" / "calibration" / "out_calibration_python_1000.jsonl")
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

TARGET_INDENT = 4  # Spaces of indentation for the assembled function body.


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


def extract_python_signature(py_code: str) -> str:
    """
    Extract the Python function signature: from the first `def` (or `async def`)
    keyword through the matching colon at parenthesis-depth 0.

    Handles multi-line signatures and string literals containing colons or parens
    (e.g. default arg values).
    """
    if not py_code:
        return ""

    m = re.search(r"\b(?:async\s+)?def\s+", py_code)
    if not m:
        return ""
    start = m.start()

    depth = 0
    in_str = False
    str_quote = ""
    triple = False
    i = start
    n = len(py_code)

    while i < n:
        if in_str:
            if triple:
                if py_code[i:i + 3] == str_quote:
                    in_str = False
                    triple = False
                    i += 3
                    continue
            else:
                if py_code[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if py_code[i] == str_quote:
                    in_str = False
            i += 1
            continue

        # Triple-quoted string start
        if py_code[i:i + 3] in ('"""', "'''"):
            in_str = True
            triple = True
            str_quote = py_code[i:i + 3]
            i += 3
            continue

        ch = py_code[i]

        if ch in ('"', "'"):
            in_str = True
            triple = False
            str_quote = ch
            i += 1
            continue

        if ch == "#":
            # Comment runs to end of line
            nl = py_code.find("\n", i)
            if nl == -1:
                return ""
            i = nl + 1
            continue

        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ":" and depth == 0:
            sig = py_code[start:i + 1]
            # Collapse internal whitespace runs except inside string literals;
            # for our purposes a single-line normalised signature is enough.
            return sig.rstrip()

        i += 1

    return ""


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
                "You are a careful Python code generation assistant.\n"
                "Write Python code only.\n"
                "Do not explain your answer.\n"
                "Do not think out loud.\n"
                "Do not browse, inspect repositories, or call tools.\n"
                "Do not add markdown fences.\n"
                "Do not add `import` statements.\n"
                "Do not add example usage, test code, or `if __name__ == \"__main__\":` blocks.\n"
                "Use the exact function signature provided.\n"
                "Complete only this function.\n"
                "Do not repeat the `def` line or the function name.\n"
                "Do not include the docstring; it is documented separately.\n"
                "Output only the indented function body, starting with the first statement of the body.\n"
                "Prefer preserving the apparent implementation style of an existing Python codebase.\n"
                "If the function appears to be a thin wrapper, adapter, or convenience helper, keep it as a thin wrapper.\n"
                "Prefer existing API calls already implied by the function name, parameters, and docstring instead of inventing new logic.\n"
                "Do not replace obvious existing APIs with different ones.\n"
                "Do not invent undeclared helper functions or new abstractions.\n"
                "Preserve obvious sentinel/error return values such as `None`, `-1`, or empty results when the task suggests not-found or failure behavior.\n"
                "Keep the implementation minimal and direct."
            ),
        },
        {
            "role": "user",
            "content": (
                "Implement the following Python function from its docstring.\n\n"
                f"Docstring:\n{doc}\n\n"
                f"Signature:\n{sig}"
            ),
        },
    ]


def parse_final_from_harmony(raw_text: str, harmony_encoding) -> str:
    """
    Extract assistant final-channel content from the model's raw output.

    The prompt appends `<|start|>assistant<|channel|>final<|message|>`
    so the model's continuation IS the final channel. The model output ends at
    `<|return|>` and is followed by `<|endoftext|>` padding from the batch
    tensor. We cut at the first Harmony marker and preserve leading
    whitespace (so the body's first-line indent is kept).
    """
    if not raw_text:
        return ""

    # Defensive: try the proper harmony parser in the rare case the model
    # itself emitted full channel framing.
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

    # Regex fallback for partial framing.
    m = re.search(
        r"<\|channel\|>final<\|message\|>(.*?)(?=<\|start\|>|<\|return\|>|<\|endoftext\|>|$)",
        raw_text,
        flags=re.DOTALL,
    )
    if m and m.group(1).strip():
        return m.group(1).lstrip("\n").rstrip()

    # Default: cut everything from the first <|...|> marker (kills both
    # <|return|> and the long <|endoftext|> padding tail). Preserve leading
    # indent on the first body line; only strip leading blank lines.
    cut_match = re.search(r"<\|[^|>\n]*\|>", raw_text)
    cut = raw_text[:cut_match.start()] if cut_match else raw_text
    return cut.lstrip("\n").rstrip()


def _strip_markdown_fences(text: str) -> str:
    """Remove ```python / ```py / ``` fences, wherever they appear."""
    if not text:
        return ""
    # Remove opening fences anywhere (top of message or repeated)
    text = re.sub(r"```(?:python|py|Python|PY)?[ \t]*\n?", "", text)
    text = re.sub(r"```", "", text)
    return text


def _strip_regenerated_signature(text: str, signature: str) -> str:
    """
    If the model regenerated the `def name(...):` line at the start of its output,
    drop that line (and anything before it).
    """
    if not text or not signature:
        return text

    fn_name_match = re.search(r"def\s+([A-Za-z_][A-Za-z0-9_]*)", signature)
    if not fn_name_match:
        return text
    fn_name = fn_name_match.group(1)

    pattern = re.compile(
        rf"^\s*(?:async\s+)?def\s+{re.escape(fn_name)}\s*\(",
        re.DOTALL,
    )
    m = pattern.match(text)
    if not m:
        return text

    # Walk from the opening paren and find the colon at depth 0.
    paren_pos = text.find("(", m.start())
    if paren_pos == -1:
        return text

    depth = 0
    in_str = False
    str_quote = ""
    i = paren_pos
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == str_quote:
                in_str = False
        elif ch in ('"', "'"):
            in_str = True
            str_quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ":" and depth == 0:
            # Strip up to the end of the def line.
            nl = text.find("\n", i)
            if nl == -1:
                return ""
            return text[nl + 1:]
        i += 1

    return text


def _strip_leading_docstring(text: str) -> str:
    """
    If the body begins (after possibly some blank lines) with a triple-quoted
    string, strip the entire docstring.
    """
    if not text:
        return ""

    lines = text.split("\n")

    # Find the first non-blank line.
    first_idx = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_idx = idx
            break
    if first_idx is None:
        return ""

    first = lines[first_idx].lstrip()
    for quote in ('"""', "'''"):
        if first.startswith(quote):
            rest_of_first = first[len(quote):]
            # Single-line docstring closes on the same line.
            if quote in rest_of_first:
                return "\n".join(lines[first_idx + 1:])
            # Multi-line: scan forward.
            for j in range(first_idx + 1, len(lines)):
                if quote in lines[j]:
                    return "\n".join(lines[j + 1:])
            # Unclosed -- discard everything; nothing recoverable.
            return ""

    # Bare string literals like  "Some description"  also count as a docstring
    # if they are the very first non-blank line on their own.
    bare = re.match(r"^\s*[rRuUbB]*([\"'])(.*?)\1\s*$", lines[first_idx])
    if bare:
        return "\n".join(lines[first_idx + 1:])

    return text


def clean_python_completion(text: str, signature: str) -> str:
    """Strip Harmony residue, markdown fences, regenerated signature, leading docstring."""
    if not text:
        return ""
    # Defensive: cut at any remaining <|...|> marker (parse_final_from_harmony
    # already does this on the regex/cut path, but the harmony-parser path
    # could still leave residue if the parsed channel content embeds markers).
    cut_match = re.search(r"<\|[^|>\n]*\|>", text)
    if cut_match:
        text = text[:cut_match.start()]
    text = _strip_markdown_fences(text)
    text = text.lstrip("\n").rstrip()       # preserve first-line indent
    text = _strip_regenerated_signature(text, signature)
    text = _strip_leading_docstring(text)
    return text.rstrip()


def take_until_python_dedent(text: str) -> str:
    """
    Collect indented body lines until indentation drops below the body's base
    indent or two consecutive blank lines appear after some content.

    Returns the body lines joined as-is (original indentation preserved); the
    caller is responsible for normalising indentation level.
    """
    if not text:
        return ""

    lines = text.split("\n")
    body_lines: List[str] = []
    base_indent: int = -1
    blank_run = 0

    for line in lines:
        if not line.strip():
            blank_run += 1
            if blank_run >= 2 and body_lines:
                break
            if body_lines:
                body_lines.append(line)
            continue

        blank_run = 0
        leading = len(line) - len(line.lstrip(" \t"))

        if base_indent == -1:
            base_indent = leading
            body_lines.append(line)
        elif leading < base_indent:
            break
        else:
            body_lines.append(line)

    while body_lines and not body_lines[-1].strip():
        body_lines.pop()

    return "\n".join(body_lines)


def normalize_body_indent(body: str, target: int = TARGET_INDENT) -> str:
    """
    Re-indent the body so that its minimum-indent non-blank line sits at exactly
    `target` spaces. Handles unindented model output, over-indented model output
    (e.g. 8-space class-method-style), and tab-prefixed output.
    """
    if not body:
        return ""

    # Normalise tabs -> spaces (tabsize=4 is the conventional Python setting).
    body = body.expandtabs(4)
    lines = body.split("\n")

    indents = [len(l) - len(l.lstrip(" ")) for l in lines if l.strip()]
    if not indents:
        return ""
    min_indent = min(indents)

    if min_indent == target:
        return "\n".join(lines)

    if min_indent < target:
        pad = " " * (target - min_indent)
        return "\n".join((pad + l) if l.strip() else l for l in lines)

    # min_indent > target: dedent by the difference (only strip leading spaces).
    delta = min_indent - target
    out = []
    for l in lines:
        if not l.strip():
            out.append(l)
            continue
        i = 0
        while i < delta and i < len(l) and l[i] == " ":
            i += 1
        out.append(l[i:])
    return "\n".join(out)


def assemble_function(signature: str, body: str) -> str:
    body = body.rstrip()
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
            sig = extract_python_signature(row["human_code"])
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
                cleaned = clean_python_completion(final_text, meta["signature"])
                body_raw = take_until_python_dedent(cleaned)
                body = normalize_body_indent(body_raw, TARGET_INDENT)
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
