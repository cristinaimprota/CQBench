"""
Re-process existing calibration outputs to fix two bugs in the original
extraction code:

  (1) Python (954 rows) and Java (42 rows) had `<|endoftext|>` padding
      tokens leak into `generated_body` / `generated_function`. The model's
      true output ends at `<|return|>`; everything after is padding from
      `tokenizer.batch_decode(..., skip_special_tokens=False)` decoding the
      padded batch tensor. The fix: in the cleaner, cut everything from the
      first `<|`-marker onwards.

  (2) Java (42 rows) had the brace tracker walk past the matching `}` because
      apostrophes in line comments (e.g. `// line's pattern`) flipped
      `in_char = True` and never flipped back, hiding all subsequent braces.
      The fix: in the brace tracker, recognise `//` line comments and
      `/* ... */` block comments and skip over them before entering
      string/char-literal state.

Re-processing is done from `raw_generated_text` (preserved per row) so no
generation is needed — this script runs offline on the JSONLs in seconds.

USAGE:
    python reprocess_calibration.py \
        --input  out_calibration_python_1000.jsonl \
        --output out_calibration_python_1000_fixed.jsonl \
        --lang   python

    python reprocess_calibration.py \
        --input  out_calibration_java_1000.jsonl \
        --output out_calibration_java_1000_fixed.jsonl \
        --lang   java
"""
import argparse
import json
import re
from pathlib import Path
from typing import Optional


# ============================================================
# Shared cleanup
# ============================================================
def cut_at_first_harmony_marker(text: str) -> str:
    """
    Cut text at the first `<|...|>` marker. This kills `<|return|>` plus the
    long run of `<|endoftext|>` padding tokens that follows when the model's
    real output ends before the batch's max sequence length.
    """
    if not text:
        return ""
    m = re.search(r"<\|[^|>\n]*\|>", text)
    if m:
        return text[:m.start()]
    return text


def parse_final_from_raw(raw_text: str) -> str:
    """
    Extract the assistant final-channel content from a raw decoded output.

    The original prompt appended `<|start|>assistant<|channel|>final<|message|>`
    so the model's continuation IS the final-channel content. Trim everything
    from the first Harmony marker (`<|return|>`, `<|endoftext|>`, etc.) onwards.

    IMPORTANT: we preserve leading whitespace because the model emits the
    body already at its target indent (e.g. 4 spaces for Python). A naive
    `.strip()` would eat that indent and break downstream indent normalisation.
    """
    if not raw_text:
        return ""

    # Some rows (rarely) contain proper `<|channel|>final<|message|>`
    # framing emitted by the model itself; honour it if present.
    m = re.search(
        r"<\|channel\|>final<\|message\|>(.*?)(?=<\|start\|>|<\|return\|>|<\|endoftext\|>|$)",
        raw_text,
        flags=re.DOTALL,
    )
    if m and m.group(1).strip():
        # Preserve leading whitespace inside the channel; only trim trailing.
        return m.group(1).lstrip("\n").rstrip()

    # Otherwise: cut at first marker. Preserve leading indent of first
    # body line; only trim leading blank lines and trailing whitespace.
    cut = cut_at_first_harmony_marker(raw_text)
    return cut.lstrip("\n").rstrip()


# ============================================================
# Python pipeline
# ============================================================
TARGET_INDENT_PY = 4


def extract_python_signature(py_code: str) -> str:
    """Walk to first `:` at paren-depth 0 starting from the first `def` keyword."""
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
            return py_code[start:i + 1].rstrip()
        i += 1
    return ""


def _strip_markdown_fences(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"```(?:python|py|Python|PY)?[ \t]*\n?", "", text)
    text = re.sub(r"```", "", text)
    return text


def _strip_regenerated_python_signature(text: str, signature: str) -> str:
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
    if not pattern.match(text):
        return text
    paren_pos = text.find("(", pattern.match(text).start())
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
            nl = text.find("\n", i)
            if nl == -1:
                return ""
            return text[nl + 1:]
        i += 1
    return text


def _strip_leading_python_docstring(text: str) -> str:
    if not text:
        return ""
    lines = text.split("\n")
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
            if quote in rest_of_first:
                return "\n".join(lines[first_idx + 1:])
            for j in range(first_idx + 1, len(lines)):
                if quote in lines[j]:
                    return "\n".join(lines[j + 1:])
            return ""
    bare = re.match(r"^\s*[rRuUbB]*([\"'])(.*?)\1\s*$", lines[first_idx])
    if bare:
        return "\n".join(lines[first_idx + 1:])
    return text


def clean_python_completion(text: str, signature: str) -> str:
    """Strip Harmony residue, markdown fences, regenerated signature, leading docstring."""
    if not text:
        return ""
    text = cut_at_first_harmony_marker(text)        # bug fix #1: kills <|return|> + <|endoftext|> tail
    text = _strip_markdown_fences(text)
    text = text.lstrip("\n").rstrip()               # preserve leading indent of first non-blank line
    text = _strip_regenerated_python_signature(text, signature)
    text = _strip_leading_python_docstring(text)
    return text.rstrip()


def take_until_python_dedent(text: str) -> str:
    if not text:
        return ""
    lines = text.split("\n")
    body_lines = []
    base_indent = -1
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


def normalize_body_indent_py(body: str, target: int = TARGET_INDENT_PY) -> str:
    if not body:
        return ""
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


# ============================================================
# Java pipeline
# ============================================================
def normalize_newlines(s: str) -> str:
    if not s:
        return ""
    return s.replace("\r\n", "\n").replace("\r", "\n")


def clean_java_completion(text: str, signature: str) -> str:
    """Strip Harmony residue, markdown fences, regenerated method header."""
    if not text:
        return ""
    text = cut_at_first_harmony_marker(text)        # <-- bug fix
    text = re.sub(r"```(?:java|Java)?[ \t]*\n?", "", text)
    text = re.sub(r"```", "", text)
    text = normalize_newlines(text).strip()

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


def take_until_balanced_function_body_java(generated: str) -> str:
    """
    Balanced-brace tracking that respects Java string/char literals AND
    `//` line comments + `/* */` block comments. Starts at depth 1 (one
    opening `{` already consumed by the cleaner).
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

        # ---- comments take precedence over string/char ----
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

        # not in any quoted/comment context: detect openers
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


# ============================================================
# Sanitize / assemble (shared)
# ============================================================
def sanitize_docstring(text: str) -> str:
    if not text:
        return ""
    t = text
    t = re.sub(r"<\|.*?\|>", "", t, flags=re.DOTALL)
    t = re.sub(r"to=repo_browser\.\w+", "", t)
    t = re.sub(r"repo_browser\.\w+", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def assemble_function(signature: str, body: str) -> str:
    body = body.rstrip()
    if not body:
        return ""
    return f"{signature}\n{body}"


# ============================================================
# Per-language reprocess
# ============================================================
def reprocess_python_row(row: dict) -> dict:
    raw = row.get("raw_generated_text", "")
    sig = row.get("signature", "")

    parsed = parse_final_from_raw(raw)
    cleaned = clean_python_completion(parsed, sig)
    body_raw = take_until_python_dedent(cleaned)
    body = normalize_body_indent_py(body_raw, TARGET_INDENT_PY)
    full = assemble_function(sig, body)

    out = dict(row)
    out["parsed_final_text"] = parsed
    out["cleaned_generated_text"] = cleaned
    out["generated_body"] = body
    out["generated_function"] = full
    return out


def reprocess_java_row(row: dict) -> dict:
    raw = row.get("raw_generated_text", "")
    sig = row.get("signature", "")

    parsed = parse_final_from_raw(raw)
    cleaned = clean_java_completion(parsed, sig)
    body = take_until_balanced_function_body_java(cleaned)
    full = assemble_function(sig, body)

    out = dict(row)
    out["parsed_final_text"] = parsed
    out["cleaned_generated_text"] = cleaned
    out["generated_body"] = body
    out["generated_function"] = full
    return out


# ============================================================
# CLI
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--lang", required=True, choices=("python", "java"))
    args = ap.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    reprocess = reprocess_python_row if args.lang == "python" else reprocess_java_row

    n_in = 0
    n_truncated = 0  # rows whose raw output had no <|return|>
    n_eot_after = 0  # rows whose new body still has <|endoftext|> (should be 0)

    with open(args.input, "r", encoding="utf-8") as fin, \
         open(args.output, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            n_in += 1
            if "<|return|>" not in row.get("raw_generated_text", ""):
                n_truncated += 1
            new_row = reprocess(row)
            if "<|endoftext|>" in new_row["generated_body"]:
                n_eot_after += 1
            fout.write(json.dumps(new_row, ensure_ascii=False) + "\n")

    print(f"Re-processed {n_in} rows -> {args.output}")
    print(f"  rows whose model output was truncated (no <|return|>): {n_truncated}")
    print(f"  rows still containing <|endoftext|> after fix: {n_eot_after}  (should be 0)")


if __name__ == "__main__":
    main()
