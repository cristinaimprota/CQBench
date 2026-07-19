#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalize_jsonl_identifiers_java.py  —  structure-focused masking for Java

Goal: preserve structural cues (keywords, punctuation/operators, (), {}, ., ;, <>, etc.)
and the presence/positions of types, while collapsing naming style into category
placeholders so cross-entropy emphasizes *structural naturalness* over lexemes.

Placeholders used in --mode structure:
  <CLASS>   class/interface/enum/record names and constructor names
  <METHOD>  method names (declarations and likely call sites not preceded by '.')
  <ATTR>    attribute/field names after a dot '.'
  <PARAM>   parameter/var names in parameter lists (heuristic)
  <VAR>     other standalone identifiers
  <PKG>     package segments in 'package' and 'import' qualified names
  <SYM>     imported symbol (final segment of an import)
  <ANNOT>   annotation names after '@' (qualified segments mapped to <ANNOT>)
  <TYPE>    reference type names (heuristics: after 'new', before generics '<',
            CamelCase, before '[]', in parameter lists before a <PARAM>, etc.)
  <NUM>     numeric literals
  <STR>     string and char literals

Booleans/null and Java keywords remain verbatim.
"""

import argparse
import hashlib
import io
import json
import re
from typing import Dict, List

from tqdm import tqdm

# --------------------------
# Java language data
# --------------------------

JAVA_KEYWORDS = {
    "abstract","assert","boolean","break","byte","case","catch","char","class","const","continue",
    "default","do","double","else","enum","extends","final","finally","float","for","goto","if",
    "implements","import","instanceof","int","interface","long","native","new","package","private",
    "protected","public","return","short","static","strictfp","super","switch","synchronized","this",
    "throw","throws","transient","try","void","volatile","while","true","false","null","var","record",
    "sealed","permits","non","sealed","yield"
}
# Note: "non-sealed" is tokenized as NAME "non", OP '-', NAME "sealed"; both names added here.

IDENT_START = re.compile(r"[A-Za-z_$]")
IDENT_CONT  = re.compile(r"[A-Za-z0-9_$]")

def is_ident_start(ch: str) -> bool:
    return bool(ch) and bool(IDENT_START.match(ch))

def is_ident_cont(ch: str) -> bool:
    return bool(ch) and bool(IDENT_CONT.match(ch))

def looks_camel_type(name: str) -> bool:
    # Simple heuristic: starts with uppercase letter (typical for class/interface/enum names)
    return len(name) > 0 and name[0].isupper()

PRIMITIVE_TYPES = {"byte","short","int","long","float","double","boolean","char","void"}

# --------------------------
# Hash helpers (legacy modes)
# --------------------------

def short_hash(name: str, nbytes: int = 3) -> str:
    h = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"ID_{h[:2*nbytes]}"

# --------------------------
# Robust string/char skipping
# --------------------------

def _skip_java_string(src: str, i: int) -> int:
    """
    Skip over a Java string starting at index i (i points to the opening quote).
    Supports text blocks (\"\"\" ... \"\"\") and regular strings. Returns index
    just after the closing delimiter or end-of-input if unterminated.
    """
    n = len(src)
    # Text block (Java 15+): """..."""
    if i + 2 < n and src[i:i+3] == '"""':
        i += 3
        while i < n:
            if i + 2 < n and src[i:i+3] == '"""':
                return i + 3
            if src[i] == "\\" and i + 1 < n:
                i += 2
            else:
                i += 1
        return i
    # Regular string: "..."
    i += 1
    while i < n:
        ch = src[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == '"':
            return i + 1
        i += 1
    return i

def _skip_java_char(src: str, i: int) -> int:
    """
    Skip over a Java char literal starting at index i (i points to the opening apostrophe).
    Returns index after closing quote or EOF.
    """
    n = len(src)
    i += 1
    while i < n:
        ch = src[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "'":
            return i + 1
        i += 1
    return i

# --------------------------
# Comment/Javadoc stripping
# --------------------------

def strip_java_comments(src: str, strip_docs: bool, strip_comments: bool) -> str:
    """
    Remove comments from Java source while preserving string/char literals.
    - strip_docs removes only Javadoc /** ... */
    - strip_comments removes // ... and /* ... */ (non-Javadoc)
    """
    out = []
    i, n = 0, len(src)
    IN_CODE, IN_LINE_COMMENT, IN_BLOCK_COMMENT, IN_JAVADOC = range(4)
    state = IN_CODE
    while i < n:
        ch = src[i]
        ch2 = src[i:i+2]
        if state == IN_CODE:
            if ch2 == "//":
                if strip_comments:
                    state = IN_LINE_COMMENT; i += 2; continue
                else:
                    out.append("//"); i += 2; continue
            if ch2 == "/*":
                if i+3 < n and src[i:i+3] == "/**":
                    if strip_docs:
                        state = IN_JAVADOC; i += 3; continue
                    else:
                        out.append("/**"); i += 3; continue
                else:
                    if strip_comments:
                        state = IN_BLOCK_COMMENT; i += 2; continue
                    else:
                        out.append("/*"); i += 2; continue
            if ch == '"':
                start = i
                i = _skip_java_string(src, i)
                out.append(src[start:i])  # keep literal as-is (we normalize later)
                continue
            if ch == "'":
                start = i
                i = _skip_java_char(src, i)
                out.append(src[start:i])
                continue
            out.append(ch); i += 1; continue
        elif state == IN_LINE_COMMENT:
            if ch == "\n":
                out.append("\n"); state = IN_CODE
            i += 1; continue
        elif state == IN_BLOCK_COMMENT:
            if ch2 == "*/":
                state = IN_CODE; i += 2
            else:
                i += 1
            continue
        elif state == IN_JAVADOC:
            if ch2 == "*/":
                state = IN_CODE; i += 2
            else:
                i += 1
            continue
    return "".join(out)

# --------------------------
# Scanner utilities
# --------------------------

NON_SIG = {" ", "\t", "\r", "\n"}

def next_sig_idx(s: str, i: int) -> int:
    n = len(s)
    while i < n and s[i] in NON_SIG:
        i += 1
    return i

def prev_sig_idx(s: str, i: int) -> int:
    i -= 1
    while i >= 0 and s[i] in NON_SIG:
        i -= 1
    return i

# --------------------------
# Structure-focused masking
# --------------------------

def normalize_java_structure(src: str) -> str:
    """
    Structure-focused masking:
      - keep keywords/punct/operators
      - mask names into role-aware placeholders
      - preserve presence/positions of types (map to <TYPE>)
    Heuristics are lightweight (no full parse) but robust enough for entropy studies.
    """
    out = []
    i, n = 0, len(src)

    in_package = False
    in_import = False
    import_seen_static = False

    after_at = False            # annotation '@'
    in_annotation_qual = False

    expect_class_name = False   # after class/interface/enum/record
    just_saw_new = False        # after 'new', next qualified ident is a type/constructor
    generic_depth = 0           # inside < ... >

    def emit(ch: str):
        nonlocal generic_depth
        out.append(ch)
        if ch == "<":
            generic_depth += 1
        elif ch == ">":
            generic_depth = max(0, generic_depth - 1)

    STEP_GUARD = 10 * max(1, n) + 1_000
    steps = 0

    while i < n:
        steps += 1
        if steps > STEP_GUARD:
            # Failsafe: append the rest unchanged to avoid pathological loops
            out.append(src[i:])
            break

        ch = src[i]
        ch2 = src[i:i+2]

        # String/char literals -> <STR> (robust skip)
        if ch == '"':
            out.append("<STR>")
            i = _skip_java_string(src, i)
            continue
        if ch == "'":
            out.append("<STR>")
            i = _skip_java_char(src, i)
            continue

        # Numbers -> <NUM>
        if ch.isdigit():
            j = i + 1
            while j < n and (src[j].isdigit() or src[j] in "._xXbBeEfFdDlL"):
                j += 1
            out.append("<NUM>")
            i = j
            continue

        # Comments should be stripped already if requested, but keep safe:
        if ch2 == "//" or ch2 == "/*":
            out.append(ch); i += 1; continue  # leave as-is (or rely on stripper)

        # Identifiers
        if is_ident_start(ch):
            j = i + 1
            while j < n and is_ident_cont(src[j]):
                j += 1
            ident = src[i:j]

            # Keywords stay (includes primitives/true/false/null)
            if ident in JAVA_KEYWORDS:
                kw = ident
                out.append(kw)
                if kw in {"class", "interface", "enum", "record"}:
                    expect_class_name = True
                elif kw == "package":
                    in_package = True
                    in_import = False
                elif kw == "import":
                    in_import = True
                    in_package = False
                    import_seen_static = False
                elif kw == "static" and in_import:
                    import_seen_static = True
                elif kw == "new":
                    just_saw_new = True
                i = j
                continue

            # package qualified name: map segments to <PKG>
            if in_package:
                out.append("<PKG>")
                i = j
                while True:
                    k = next_sig_idx(src, i)
                    if k < n and src[k] == '.':
                        out.append("."); i = k + 1
                        if i < n and is_ident_start(src[i]):
                            m = i + 1
                            while m < n and is_ident_cont(src[m]): m += 1
                            out.append("<PKG>"); i = m; continue
                    break
                i = next_sig_idx(src, i)
                if i < n and src[i] == ';':
                    out.append(";"); i += 1
                    in_package = False
                continue

            # import qualified name: <PKG>.<PKG>.<SYM> or .*
            if in_import:
                segs = [ident]; i = j
                while True:
                    k = next_sig_idx(src, i)
                    if k < n and src[k] == '.':
                        i = k + 1
                        k2 = next_sig_idx(src, i)
                        if k2 < n and is_ident_start(src[k2]):
                            m = k2 + 1
                            while m < n and is_ident_cont(src[m]): m += 1
                            segs.append(src[k2:m]); i = m; continue
                        elif k2 < n and src[k2] == '*':
                            segs.append('*'); i = k2 + 1; break
                        else:
                            break
                    else:
                        break
                if segs and segs[-1] == '*':
                    for sidx, _s in enumerate(segs[:-1]):
                        out.append("<PKG>")
                        if sidx < len(segs) - 2:
                            out.append(".")
                    out.append(".*")
                else:
                    for sidx, _s in enumerate(segs):
                        if sidx < len(segs) - 1:
                            out.append("<PKG>"); out.append(".")
                        else:
                            out.append("<SYM>")
                i = next_sig_idx(src, i)
                while i < n and src[i] != ';':
                    out.append(src[i]); i += 1
                if i < n and src[i] == ';':
                    out.append(";"); i += 1
                in_import = False
                continue

            # annotation name after '@'
            if after_at:
                out.append("<ANNOT>")
                i = j
                while True:
                    k = next_sig_idx(src, i)
                    if k < n and src[k] == '.':
                        out.append("."); i = k + 1
                        k2 = next_sig_idx(src, i)
                        if k2 < n and is_ident_start(src[k2]):
                            m = k2 + 1
                            while m < n and is_ident_cont(src[m]): m += 1
                            out.append("<ANNOT>"); i = m; continue
                    break
                after_at = False
                continue

            # Attribute after dot
            p = prev_sig_idx(src, i)
            if p >= 0 and src[p] == '.':
                out.append("<ATTR>")
                i = j
                continue

            # Constructor or type right after 'new'
            if just_saw_new:
                out.append("<TYPE>")
                i = j
                while True:
                    k = next_sig_idx(src, i)
                    if k < n and src[k] == '.':
                        out.append("."); i = k + 1
                        if i < n and is_ident_start(src[i]):
                            m = i + 1
                            while m < n and is_ident_cont(src[m]): m += 1
                            out.append("<TYPE>"); i = m; continue
                    elif k < n and src[k] == '<':
                        emit("<"); i = k + 1
                        while i < n and generic_depth > 0:
                            if is_ident_start(src[i]):
                                m = i + 1
                                while m < n and is_ident_cont(src[m]): m += 1
                                out.append("<TYPE>"); i = m; continue
                            emit(src[i]); i += 1
                        continue
                    break
                just_saw_new = False
                continue

            # Class/interface/enum/record name expected
            if expect_class_name:
                out.append("<CLASS>")
                i = j
                k = next_sig_idx(src, i)
                if k < n and src[k] == '<':
                    emit("<"); i = k + 1
                    while i < n and generic_depth > 0:
                        if is_ident_start(src[i]):
                            m = i + 1
                            while m < n and is_ident_cont(src[m]): m += 1
                            out.append("<TYPE>"); i = m; continue
                        emit(src[i]); i += 1
                expect_class_name = False
                continue

            # Likely method decl/call: NAME followed by '(' and not preceded by '.'
            k = next_sig_idx(src, j)
            p = prev_sig_idx(src, i)
            prev_char = src[p] if p >= 0 else ""
            next_char = src[k] if k < n else ""
            if next_char == "(" and prev_char != '.' and not just_saw_new:
                out.append("<METHOD>")
                i = j
                # enter and copy '('
                out.append("("); i = k + 1
                depth = 1
                last_was_type = False
                while i < n and depth > 0:
                    c = src[i]
                    if c in " \t\r\n":
                        out.append(c); i += 1; continue
                    if c == '"':
                        out.append("<STR>")
                        i = _skip_java_string(src, i)
                        continue
                    if c == "'":
                        out.append("<STR>")
                        i = _skip_java_char(src, i)
                        continue
                    if c.isdigit():
                        j2 = i + 1
                        while j2 < n and (src[j2].isdigit() or src[j2] in "._xXbBeEfFdDlL"): j2 += 1
                        out.append("<NUM>"); i = j2; continue
                    if c == '(':
                        out.append("("); depth += 1; i += 1; continue
                    if c == ')':
                        out.append(")"); depth -= 1; i += 1; continue
                    if c in "{},[]=;:?":
                        out.append(c); i += 1; continue
                    if c in "<>":
                        emit(c); i += 1; continue
                    if c == '.':
                        out.append('.'); i += 1; continue
                    if is_ident_start(c):
                        m = i + 1
                        while m < n and is_ident_cont(src[m]): m += 1
                        name2 = src[i:m]
                        if name2 in JAVA_KEYWORDS:
                            out.append(name2); i = m; continue
                        k2 = next_sig_idx(src, m)
                        nxt = src[k2] if k2 < n else ""
                        if looks_camel_type(name2) or nxt == '<':
                            out.append("<TYPE>"); i = m; last_was_type = True; continue
                        if last_was_type:
                            out.append("<PARAM>"); i = m; last_was_type = False; continue
                        out.append("<PARAM>"); i = m; last_was_type = False; continue
                    else:
                        out.append(c); i += 1; continue
                continue

            # Inside generics <...> treat identifiers as <TYPE>
            if generic_depth > 0:
                out.append("<TYPE>")
                i = j
                continue

            # If next significant token is '<', this is a type with generics
            k2 = next_sig_idx(src, j)
            if k2 < n and src[k2] == '<':
                out.append("<TYPE>")
                i = j
                continue

            # CamelCase heuristic => type
            if looks_camel_type(ident):
                out.append("<TYPE>")
                i = j
                continue

            # Default standalone variable
            out.append("<VAR>")
            i = j
            continue

        # Non-identifier characters
        if ch == '@':
            out.append('@')
            after_at = True
            in_annotation_qual = True
            i += 1
            continue
        else:
            if ch in "{}[];:.,=+-*/%!&|^~?<>\\":
                emit(ch)
                i += 1
                continue
            if ch in NON_SIG:
                out.append(ch); i += 1; continue
            out.append(ch); i += 1; continue

    return "".join(out)

# --------------------------
# Legacy identifier normalization (kept for compatibility)
# --------------------------

def normalize_java_identifiers_legacy(src: str, mode: str, nbytes: int = 3) -> str:
    if mode == "none":
        return src
    out = []
    i, n = 0, len(src)
    mapping: Dict[str, str] = {}
    STEP_GUARD = 10 * max(1, n) + 1_000
    steps = 0
    while i < n:
        steps += 1
        if steps > STEP_GUARD:
            out.append(src[i:]); break
        ch = src[i]
        ch2 = src[i:i+2]
        if ch == '"':
            start = i
            i = _skip_java_string(src, i)
            out.append(src[start:i])  # keep literal content as-is in legacy modes
            continue
        if ch == "'":
            start = i
            i = _skip_java_char(src, i)
            out.append(src[start:i])
            continue
        if ch2 == "//" or ch2 == "/*":
            out.append(ch); i += 1; continue  # expect pre-strip
        if is_ident_start(ch):
            j = i + 1
            while j < n and is_ident_cont(src[j]): j += 1
            ident = src[i:j]
            if ident in JAVA_KEYWORDS:
                out.append(ident)
            else:
                if mode == "placeholder":
                    out.append("<ID>")
                elif mode == "per-file-hash":
                    if ident not in mapping: mapping[ident] = short_hash(ident, nbytes)
                    out.append(mapping[ident])
                elif mode == "global-hash":
                    out.append(short_hash(ident, nbytes))
                else:
                    out.append(ident)
            i = j; continue
        out.append(ch); i += 1
    return "".join(out)

# --------------------------
# Glue: process one snippet
# --------------------------

DEFAULT_FIELDS = ["human_code", "chatgpt_code", "dsc_code", "qwen_code"]

def process_java_snippet(code: str, mode: str, nbytes: int,
                         strip_docstrings: bool, strip_comments: bool) -> str:
    if code is None:
        return code
    if strip_docstrings or strip_comments:
        code = strip_java_comments(code, strip_docs=strip_docstrings, strip_comments=strip_comments)
    if mode == "structure":
        return normalize_java_structure(code)
    else:
        return normalize_java_identifiers_legacy(code, mode=mode, nbytes=nbytes)

# --------------------------
# JSONL processing
# --------------------------

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
        for line in tqdm(fin, desc=f"Normalizing JSONL (Java, mode={mode})"):
            total_lines += 1
            raw = line.rstrip("\n")
            if not raw.strip():
                fout.write("\n"); continue
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

    print(f"Done. Lines processed: {total_lines} | snippets changed: {changed_snippets} | lines failed to parse: {failed_lines}")

# --------------------------
# CLI
# --------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Normalize Java code in a JSONL dataset. Default mode 'structure' masks naming while preserving structure; legacy modes available."
    )
    ap.add_argument("--input", required=True, help="Path to input JSONL (e.g., java_dataset.jsonl)")
    ap.add_argument("--output", required=True, help="Path to output JSONL")
    ap.add_argument(
        "--mode",
        choices=["structure", "none", "placeholder", "per-file-hash", "global-hash"],
        default="structure",
        help="Masking strategy: 'structure' (recommended) or legacy identifier modes"
    )
    ap.add_argument("--nbytes", type=int, default=3,
                    help="Hash length in bytes (for *_hash legacy modes). 3 -> 6 hex chars (ID_ab12cd)")
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
        fields=DEFAULT_FIELDS if args.fields is None else args.fields,
        write_policy=args.write_policy,
        strip_docstrings=args.strip_docstrings,
        strip_comments=args.strip_comments,
    )

if __name__ == "__main__":
    main()
