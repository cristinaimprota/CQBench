#!/usr/bin/env python3
"""
normalize_jsonl_identifiers_java.py

Normalize identifiers inside **Java** code fields in a JSONL dataset and
optionally strip Javadoc/docstrings and comments.

Dataset format (same idea as your Python version):
  - one JSON object per line
  - code fields (customizable): "human_code", "chatgpt_code", "dsc_code", "qwen_code"

Identifier normalization strategies
-----------------------------------
- none            : leave identifiers unchanged
- placeholder     : every non-keyword identifier becomes "<ID>"
- per-file-hash   : each distinct identifier (per snippet) maps to a short stable hash (ID_ab12cd)
- global-hash     : each identifier -> short stable hash computed from its spelling (consistent across snippets)

Optional preprocessing
----------------------
- --strip-docstrings : remove Javadoc blocks /** ... */ (docstrings)
- --strip-comments   : remove line (// ...) and block (/* ... */) comments
                       (Javadoc is controlled separately by --strip-docstrings)

Notes
-----
- We **never** touch strings or character literals.
- We **do** normalize class names, method names, variable names, annotation names, and qualified-name parts.
- Java keywords are **not** normalized.
- This script is language-aware but not a full parser; it uses a careful scanner
  that respects string/char literals when removing comments or replacing identifiers.

Examples
--------
Overwrite original code fields (strip docs+comments, keep identifiers as-is):
    python normalize_jsonl_identifiers_java.py \
        --input java_dataset.jsonl \
        --output java_dataset_stripped.jsonl \
        --mode none \
        --strip-docstrings --strip-comments \
        --write_policy overwrite

Add normalized versions alongside originals:
    python normalize_jsonl_identifiers_java.py \
        --input java_dataset.jsonl \
        --output java_dataset_norm.jsonl \
        --mode global-hash \
        --strip-docstrings \
        --write_policy add_suffix

Limit to certain fields:
    python normalize_jsonl_identifiers_java.py \
        --input java_dataset.jsonl \
        --output out.jsonl \
        --mode placeholder \
        --fields human_code chatgpt_code
"""

import argparse
import hashlib
import io
import json
import re
import sys
from typing import Dict, List

from tqdm import tqdm

# --------------------------
# Java language data
# --------------------------

JAVA_KEYWORDS = {
    # Java keywords (incl. reserved literals)
    "abstract","assert","boolean","break","byte","case","catch","char","class","const","continue",
    "default","do","double","else","enum","extends","final","finally","float","for","goto","if",
    "implements","import","instanceof","int","interface","long","native","new","package","private",
    "protected","public","return","short","static","strictfp","super","switch","synchronized","this",
    "throw","throws","transient","try","void","volatile","while","true","false","null","var","record",
    "sealed","permits","non-sealed","yield"
}
# Split "non-sealed" into tokens; our scanner will see IDENT "non" "-" "sealed".
# We'll treat only recognized exact identifiers as keywords; "non" and "sealed" are not keywords.

IDENT_START = re.compile(r"[A-Za-z_$]")
IDENT_CONT  = re.compile(r"[A-Za-z0-9_$]")

def is_ident_start(ch: str) -> bool:
    return bool(ch) and bool(IDENT_START.match(ch))

def is_ident_cont(ch: str) -> bool:
    return bool(ch) and bool(IDENT_CONT.match(ch))


# --------------------------
# Hashing / modes
# --------------------------

def short_hash(name: str, nbytes: int = 3) -> str:
    h = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"ID_{h[:2*nbytes]}"


# --------------------------
# Comment stripping for Java
# --------------------------

def strip_java_comments(src: str, strip_docs: bool, strip_comments: bool) -> str:
    """
    Remove comments from Java source while preserving string/char literals.
    - strip_docs removes only Javadoc /** ... */
    - strip_comments removes // ... and /* ... */ (non-doc)
    """
    out = []
    i, n = 0, len(src)
    IN_CODE, IN_SLASH, IN_LINE_COMMENT, IN_BLOCK_COMMENT, IN_JAVADOC = range(5)
    IN_STRING, IN_CHAR = 5, 6

    state = IN_CODE
    block_depth = 0  # not nested in Java, but we keep for clarity
    while i < n:
        ch = src[i]
        ch2 = src[i:i+2]

        if state == IN_CODE:
            if ch2 == "//":
                # start line comment
                if strip_comments:
                    state = IN_LINE_COMMENT
                    i += 2
                    continue
                else:
                    out.append(ch2); i += 2; continue
            elif ch2 == "/*":
                # block or Javadoc
                if i+3 < n and src[i:i+3] == "/**":
                    # Javadoc
                    if strip_docs:
                        state = IN_JAVADOC
                        i += 3
                        continue
                    else:
                        out.append("/**"); i += 3; continue
                else:
                    if strip_comments:
                        state = IN_BLOCK_COMMENT
                        i += 2
                        continue
                    else:
                        out.append("/*"); i += 2; continue
            elif ch == '"':
                out.append(ch)
                state = IN_STRING
                i += 1
                continue
            elif ch == "'":
                out.append(ch)
                state = IN_CHAR
                i += 1
                continue
            else:
                out.append(ch)
                i += 1
                continue

        elif state == IN_LINE_COMMENT:
            # consume until newline; keep newline
            if ch == "\n":
                out.append("\n")
                state = IN_CODE
            i += 1
            continue

        elif state == IN_BLOCK_COMMENT:
            if ch2 == "*/":
                state = IN_CODE
                i += 2
            else:
                i += 1
            continue

        elif state == IN_JAVADOC:
            if ch2 == "*/":
                state = IN_CODE
                i += 2
            else:
                i += 1
            continue

        elif state == IN_STRING:
            out.append(ch)
            if ch == "\\":
                # escape next char
                if i + 1 < n:
                    out.append(src[i+1])
                    i += 2
                    continue
            if ch == '"':
                state = IN_CODE
            i += 1
            continue

        elif state == IN_CHAR:
            out.append(ch)
            if ch == "\\":
                if i + 1 < n:
                    out.append(src[i+1])
                    i += 2
                    continue
            if ch == "'":
                state = IN_CODE
            i += 1
            continue

    return "".join(out)


# --------------------------
# Identifier normalization (Java)
# --------------------------

def normalize_java_identifiers(src: str, mode: str, nbytes: int = 3) -> str:
    """
    Replace non-keyword identifiers according to mode.
    Preserves strings/char literals and anything inside them.
    """
    if mode == "none":
        return src

    out = []
    i, n = 0, len(src)
    mapping: Dict[str, str] = {}  # per-snippet mapping for per-file-hash

    IN_CODE, IN_STRING, IN_CHAR, IN_BLOCK_COMMENT, IN_LINE_COMMENT = range(5)
    state = IN_CODE

    while i < n:
        ch = src[i]
        ch2 = src[i:i+2]

        if state == IN_CODE:
            # handle comments so we don't replace inside (even if already stripped)
            if ch2 == "/*":
                out.append("/*"); i += 2; state = IN_BLOCK_COMMENT; continue
            if ch2 == "//":
                out.append("//"); i += 2; state = IN_LINE_COMMENT; continue
            if ch == '"':
                out.append(ch); i += 1; state = IN_STRING; continue
            if ch == "'":
                out.append(ch); i += 1; state = IN_CHAR; continue

            # identifier?
            if is_ident_start(ch):
                j = i + 1
                while j < n and is_ident_cont(src[j]):
                    j += 1
                ident = src[i:j]

                # Keywords are not normalized
                if ident in JAVA_KEYWORDS:
                    out.append(ident)
                else:
                    if mode == "placeholder":
                        out.append("<ID>")
                    elif mode == "per-file-hash":
                        if ident not in mapping:
                            mapping[ident] = short_hash(ident, nbytes=nbytes)
                        out.append(mapping[ident])
                    elif mode == "global-hash":
                        out.append(short_hash(ident, nbytes=nbytes))
                    else:
                        out.append(ident)
                i = j
                continue
            else:
                out.append(ch); i += 1; continue

        elif state == IN_BLOCK_COMMENT:
            out.append(ch)
            if ch2 == "*/":
                out.append("/")  # we already appended '*', but careful: we appended ch (which is '*'), ch2 sees '*/'
                # correct the duplication: adjust last two chars properly
                # Simpler approach: replace last char and append '/', but keep simple by handling explicitly:
                # roll back one char and write '*/'
                out[-1] = '*'  # ensure previous char is '*'
                out.append('/')  # now '*/'
                i += 2
                state = IN_CODE
            else:
                i += 1
            continue

        elif state == IN_LINE_COMMENT:
            out.append(ch)
            if ch == "\n":
                state = IN_CODE
            i += 1
            continue

        elif state == IN_STRING:
            out.append(ch)
            if ch == "\\":
                if i + 1 < n:
                    out.append(src[i+1]); i += 2; continue
            if ch == '"':
                state = IN_CODE
            i += 1
            continue

        elif state == IN_CHAR:
            out.append(ch)
            if ch == "\\":
                if i + 1 < n:
                    out.append(src[i+1]); i += 2; continue
            if ch == "'":
                state = IN_CODE
            i += 1
            continue

    return "".join(out)


# --------------------------
# Glue: process one Java snippet
# --------------------------

def process_java_snippet(code: str, mode: str, nbytes: int, strip_docstrings: bool, strip_comments: bool) -> str:
    if code is None:
        return code
    # Step 1: optionally strip docs/comments
    if strip_docstrings or strip_comments:
        code = strip_java_comments(code, strip_docs=strip_docstrings, strip_comments=strip_comments)
    # Step 2: normalize identifiers
    code = normalize_java_identifiers(code, mode=mode, nbytes=nbytes)
    return code


# --------------------------
# JSONL processing
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
    assert write_policy in ("overwrite", "add_suffix")

    total_lines = 0
    changed_snippets = 0
    failed_lines = 0

    with open(input_path, "r", encoding="utf-8") as fin, open(output_path, "w", encoding="utf-8") as fout:
        for line in tqdm(fin, desc="Normalizing JSONL (Java)"):
            total_lines += 1
            raw = line.rstrip("\n")
            if not raw.strip():
                fout.write("\n")
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                failed_lines += 1
                fout.write(raw + "\n")
                continue

            for field in fields:
                if field not in obj or not isinstance(obj[field], str):
                    continue
                orig = obj[field]
                norm = process_java_snippet(
                    orig, mode=mode, nbytes=nbytes,
                    strip_docstrings=strip_docstrings, strip_comments=strip_comments
                )
                if write_policy == "overwrite":
                    obj[field] = norm
                else:
                    obj[field + "_norm"] = norm
                if norm != orig:
                    changed_snippets += 1

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(
        f"Done. Lines processed: {total_lines} | snippets changed: {changed_snippets} | lines failed to parse: {failed_lines}"
    )


# --------------------------
# CLI
# --------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Normalize Java identifiers in a JSONL dataset, with optional Javadoc/comment stripping."
    )
    ap.add_argument("--input", required=True, help="Path to input JSONL (e.g., java_dataset.jsonl)")
    ap.add_argument("--output", required=True, help="Path to output JSONL with normalized Java code")
    ap.add_argument("--mode",
                    choices=["none", "placeholder", "per-file-hash", "global-hash"],
                    default="global-hash",
                    help="Identifier normalization strategy")
    ap.add_argument("--nbytes", type=int, default=3,
                    help="Hash length in bytes (for *_hash modes). 3 -> 6 hex chars (ID_ab12cd)")
    ap.add_argument("--fields", nargs="*", default=DEFAULT_FIELDS,
                    help=f"Which JSON fields to normalize (default: {DEFAULT_FIELDS})")
    ap.add_argument("--write_policy", choices=["overwrite", "add_suffix"], default="overwrite",
                    help="overwrite: replace original fields; add_suffix: write to <field>_norm and keep originals")
    ap.add_argument("--strip-docstrings", action="store_true",
                    help="Remove Javadoc /** ... */ blocks before normalization")
    ap.add_argument("--strip-comments", action="store_true",
                    help="Remove line (// ...) and block (/* ... */) comments before normalization")
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
