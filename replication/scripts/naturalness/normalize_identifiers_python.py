#!/usr/bin/env python3
"""
normalize_jsonl_identifiers.py

Normalize identifiers inside the Python code fields of a JSONL dataset and
write a new JSONL with the modified code.

Dataset format (matches your previous script):
  - one JSON object per line
  - code fields: "human_code", "chatgpt_code", "dsc_code", "qwen_code" (customizable)

Identifier normalization strategies
-----------------------------------
- none            : leave code unchanged
- placeholder     : every non-keyword/builtin identifier becomes "<ID>"
- per-file-hash   : each distinct identifier within a snippet is mapped to a
                    stable short hash, consistent *within that snippet* only
- global-hash     : each identifier → stable short hash computed from its
                    spelling (consistent across snippets)

Optional preprocessing
----------------------
- --strip-docstrings : remove module/class/(async)function docstrings
                       (inserts 'pass' if a block would be empty)
- --strip-comments   : remove inline '# ...' comments (preserves code layout)

Examples
--------
Overwrite original code fields:
    python normalize_jsonl_identifiers.py \
        --input python_dataset.jsonl \
        --output python_dataset_norm.jsonl \
        --mode global-hash \
        --strip-docstrings --strip-comments \
        --write_policy overwrite

Keep originals and add parallel *_norm fields:
    python normalize_jsonl_identifiers.py \
        --input python_dataset.jsonl \
        --output python_dataset_norm.jsonl \
        --mode placeholder \
        --strip-comments \
        --write_policy add_suffix

Limit to specific fields:
    python normalize_jsonl_identifiers.py \
        --input python_dataset.jsonl \
        --output out.jsonl \
        --mode per-file-hash \
        --fields human_code chatgpt_code
"""

import argparse
import ast
import builtins
import hashlib
import io
import json
import keyword
import sys
import tokenize
from typing import Dict, Iterable, List, Tuple

from tqdm import tqdm

# --------------------------
# Tokenization / Normalizer
# --------------------------

PY_KEYWORDS = set(keyword.kwlist)
PY_BUILTINS = set(dir(builtins))


def _hash_id(name: str, nbytes: int = 3) -> str:
    """Stable short hash for an identifier (hex length = 2*nbytes)."""
    h = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"ID_{h[:2*nbytes]}"


def _should_normalize(tok_type: int, tok_str: str) -> bool:
    """True if this token is a non-keyword/builtin identifier."""
    if tok_type != tokenize.NAME:
        return False
    if tok_str in PY_KEYWORDS:
        return False
    if tok_str in PY_BUILTINS:
        return False
    return True


def _remove_docstrings(code: str) -> str:
    """
    Remove module/class/function/async function docstrings while keeping code valid.
    If a class/function block would be empty after removing its sole docstring,
    insert an indented 'pass' to maintain syntactic correctness.
    """
    try:
        tree = ast.parse(code)
    except Exception:
        # If it doesn't parse, don't touch it
        return code

    spans: List[Tuple[int, int, int, int, str]] = []  # (sl, sc, el, ec, replacement)

    def record_docstring_span(node, only_stmt: bool):
        if not getattr(node, "body", None):
            return
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), (ast.Str, ast.Constant)):
            val = first.value
            s = val.s if isinstance(val, ast.Str) else (val.value if isinstance(val, ast.Constant) and isinstance(val.value, str) else None)
            if s is None:
                return
            if not hasattr(first, "lineno") or not hasattr(first, "end_lineno"):
                return
            sl, sc = first.lineno, first.col_offset
            el, ec = first.end_lineno, first.end_col_offset
            replacement = ""
            if only_stmt:
                indent = " " * sc
                replacement = indent + "pass\n"
            spans.append((sl, sc, el, ec, replacement))

    # Module docstring
    record_docstring_span(tree, only_stmt=(len(getattr(tree, "body", [])) == 1))

    # Class / Function / AsyncFunction docstrings
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            only_stmt = len(getattr(node, "body", [])) == 1
            record_docstring_span(node, only_stmt)

    if not spans:
        return code

    # Apply replacements from bottom to top
    lines = code.splitlines(keepends=True)

    def apply_span(sl, sc, el, ec, repl):
        sl0, el0 = sl - 1, el - 1
        if sl0 == el0:
            lines[sl0] = lines[sl0][:sc] + repl + lines[sl0][ec:]
        else:
            start_part = lines[sl0][:sc]
            end_part = lines[el0][ec:]
            lines[sl0] = start_part + repl + end_part
            for i in range(sl0 + 1, el0 + 1):
                lines[i] = ""

    spans.sort(key=lambda t: (t[0], t[1], t[2], t[3]), reverse=True)
    for sl, sc, el, ec, repl in spans:
        apply_span(sl, sc, el, ec, repl)

    return "".join(lines)


def _strip_inline_comments(code: str) -> str:
    """
    Remove '# ...' comments while preserving newlines/spacing where possible.
    Uses tokenize: drops COMMENT tokens and rebuilds source.
    """
    reader = io.BytesIO(code.encode("utf-8", errors="ignore")).readline
    try:
        toks = list(tokenize.tokenize(reader))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return code

    out = []
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            continue
        out.append(tok)

    try:
        rebuilt = tokenize.untokenize(out)
        return rebuilt if isinstance(rebuilt, str) else rebuilt.decode("utf-8", errors="ignore")
    except Exception:
        return code


def normalize_code(
    code: str,
    mode: str,
    nbytes: int = 3,
    strip_docstrings: bool = False,
    strip_comments: bool = False,
) -> str:
    """
    Normalize Python identifiers in a single code snippet.
    Optionally removes docstrings and inline comments first.

    mode: 'none' | 'placeholder' | 'per-file-hash' | 'global-hash'
    """
    if not code:
        return code

    # Optional preprocessing
    if strip_docstrings:
        code = _remove_docstrings(code)
    if strip_comments:
        code = _strip_inline_comments(code)

    # Make tokenizer happier: ensure trailing newline
    if not code.endswith("\n"):
        code = code + "\n"

    mapping: Dict[str, str] = {}  # per-snippet map (for per-file-hash)
    data = code.encode("utf-8", errors="ignore")
    reader = io.BytesIO(data).readline

    try:
        tokens = list(tokenize.tokenize(reader))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Fallback: keep snippet untouched rather than abort the entire run
        return code

    out_tokens: List[tokenize.TokenInfo] = []
    for tok in tokens:
        ttype, tstr, start, end, line = tok
        if _should_normalize(ttype, tstr):
            if mode == "none":
                new_str = tstr
            elif mode == "placeholder":
                new_str = "<ID>"
            elif mode == "per-file-hash":
                if tstr not in mapping:
                    mapping[tstr] = _hash_id(tstr, nbytes=nbytes)
                new_str = mapping[tstr]
            elif mode == "global-hash":
                new_str = _hash_id(tstr, nbytes=nbytes)
            else:
                new_str = tstr
            out_tokens.append(tokenize.TokenInfo(ttype, new_str, start, end, line))
        else:
            out_tokens.append(tok)

    try:
        out = tokenize.untokenize(out_tokens)
        return out if isinstance(out, str) else out.decode("utf-8", errors="ignore")
    except Exception:
        # If rebuilding fails for any reason, keep original snippet
        return code


# --------------------------
# JSONL Processing
# --------------------------

DEFAULT_FIELDS = ["human_code", "chatgpt_code", "dsc_code", "qwen_code"]


def process_jsonl(
    input_path: str,
    output_path: str,
    mode: str,
    nbytes: int,
    fields: List[str],
    write_policy: str,
    strip_docstrings: bool,
    strip_comments: bool,
) -> None:
    """
    Read input JSONL, normalize identifiers in specified code fields, and
    write a new JSONL file.

    write_policy:
        - "overwrite": replace the original fields
        - "add_suffix": write to <field>_norm and keep originals
    """
    assert write_policy in ("overwrite", "add_suffix")

    total_lines = 0
    changed_snippets = 0
    failed_lines = 0

    with open(input_path, "r", encoding="utf-8") as fin, open(
        output_path, "w", encoding="utf-8"
    ) as fout:
        for line in tqdm(fin, desc="Normalizing JSONL"):
            total_lines += 1
            line = line.strip()
            if not line:
                fout.write("\n")
                continue
            try:
                obj = json.loads(line)
            except Exception:
                failed_lines += 1
                # write original line to keep row count stable
                fout.write(line + "\n")
                continue

            for field in fields:
                if field not in obj or not isinstance(obj[field], str):
                    continue
                orig = obj[field]
                norm = normalize_code(
                    orig,
                    mode=mode,
                    nbytes=nbytes,
                    strip_docstrings=strip_docstrings,
                    strip_comments=strip_comments,
                )
                if write_policy == "overwrite":
                    obj[field] = norm
                else:  # add_suffix
                    obj[field + "_norm"] = norm
                if norm != orig:
                    changed_snippets += 1

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(
        f"Done. Lines processed: {total_lines} | snippets changed: {changed_snippets} | lines failed to parse: {failed_lines}"
    )


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Normalize identifiers in a JSONL dataset of Python code, with optional docstring/comment stripping."
    )
    ap.add_argument(
        "--input",
        required=True,
        help="Path to input JSONL (e.g., python_dataset.jsonl)",
    )
    ap.add_argument(
        "--output",
        required=True,
        help="Path to output JSONL with normalized identifiers",
    )
    ap.add_argument(
        "--mode",
        choices=["none", "placeholder", "per-file-hash", "global-hash"],
        default="global-hash",
        help="Identifier normalization strategy",
    )
    ap.add_argument(
        "--nbytes",
        type=int,
        default=3,
        help="Hash length in bytes (for *_hash modes). 3 → 6 hex chars (ID_ab12cd).",
    )
    ap.add_argument(
        "--fields",
        nargs="*",
        default=DEFAULT_FIELDS,
        help=f"Which JSON fields to normalize (default: {DEFAULT_FIELDS})",
    )
    ap.add_argument(
        "--write_policy",
        choices=["overwrite", "add_suffix"],
        default="overwrite",
        help=(
            "overwrite: replace original fields in output; "
            "add_suffix: keep originals and write normalized code to <field>_norm"
        ),
    )
    ap.add_argument(
        "--strip-docstrings",
        action="store_true",
        help="Remove module/class/function docstrings before normalization",
    )
    ap.add_argument(
        "--strip-comments",
        action="store_true",
        help="Remove inline '# ...' comments before normalization",
    )
    return ap.parse_args()


def main():
    args = parse_args()
    process_jsonl(
        input_path=args.input,
        output_path=args.output,
        mode=args.mode,
        nbytes=args.nbytes,
        fields=args.fields,
        write_policy=args.write_policy,
        strip_docstrings=args.strip_docstrings,
        strip_comments=args.strip_comments,
    )


if __name__ == "__main__":
    main()
