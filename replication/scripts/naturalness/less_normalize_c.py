#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalize_jsonl_identifiers_c.py  --  structure-focused masking for C

Goal: preserve structural cues (keywords, punctuation/operators, (), {}, [], ., ->,
preprocessor syntax, etc.) while collapsing naming style into placeholders so
cross-entropy emphasizes structural naturalness more than lexemes.

Placeholders used in --mode structure:
  <FUNC>    function names (declarations and likely call sites)
  <TYPE>    typedef aliases, struct/union/enum tags, and other known type names
  <PARAM>   parameter names in function signatures
  <VAR>     other standalone identifiers
  <ATTR>    field names after '.' or '->'
  <MACRO>   preprocessor macro names
  <HEADER>  identifiers inside #include paths
  <NUM>     numeric literals
  <STR>     string and char literals

As in the Python and Java versions, keywords and built-in primitive types stay
verbatim. The script also keeps legacy identifier-only modes for compatibility.
"""

import argparse
import hashlib
import json
import re
from typing import Dict, List, Set, Tuple

from tqdm import tqdm


C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "_Alignas", "_Alignof",
    "_Atomic", "_Bool", "_Complex", "_Generic", "_Imaginary", "_Noreturn",
    "_Static_assert", "_Thread_local",
}

TYPE_KEYWORDS = {
    "char", "double", "enum", "float", "int", "long", "short", "signed",
    "struct", "union", "unsigned", "void", "_Atomic", "_Bool", "_Complex",
    "_Imaginary",
}

QUALIFIER_KEYWORDS = {
    "const", "extern", "inline", "register", "restrict", "static", "volatile",
}

PREPROC_DIRECTIVES = {
    "define", "elif", "else", "endif", "error", "if", "ifdef", "ifndef",
    "include", "line", "pragma", "undef",
}

IDENT_START = re.compile(r"[A-Za-z_]")
IDENT_CONT = re.compile(r"[A-Za-z0-9_]")
NON_SIG_CHARS = {" ", "\t", "\r", "\n"}


def is_ident_start(ch: str) -> bool:
    return bool(ch) and bool(IDENT_START.match(ch))


def is_ident_cont(ch: str) -> bool:
    return bool(ch) and bool(IDENT_CONT.match(ch))


def short_hash(name: str, nbytes: int = 3) -> str:
    h = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"ID_{h[:2 * nbytes]}"


def _skip_c_string(src: str, i: int) -> int:
    n = len(src)
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


def _skip_c_char(src: str, i: int) -> int:
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


def _read_ident(src: str, i: int) -> Tuple[str, int]:
    j = i + 1
    while j < len(src) and is_ident_cont(src[j]):
        j += 1
    return src[i:j], j


def next_sig_idx(s: str, i: int) -> int:
    n = len(s)
    while i < n and s[i] in NON_SIG_CHARS:
        i += 1
    return i


def prev_sig_idx(s: str, i: int) -> int:
    i -= 1
    while i >= 0 and s[i] in NON_SIG_CHARS:
        i -= 1
    return i


def at_line_start(src: str, i: int) -> bool:
    j = i - 1
    while j >= 0 and src[j] in {" ", "\t", "\r"}:
        j -= 1
    return j < 0 or src[j] == "\n"


def strip_c_comments(src: str, strip_docs: bool, strip_comments: bool) -> str:
    """
    Remove comments from C source while preserving strings/chars.
    - strip_docs removes only /** ... */ comment blocks.
    - strip_comments removes // ... and /* ... */ comments.
    """
    out = []
    i, n = 0, len(src)
    IN_CODE, IN_LINE_COMMENT, IN_BLOCK_COMMENT, IN_DOCCOMMENT = range(4)
    state = IN_CODE

    while i < n:
        ch = src[i]
        ch2 = src[i:i + 2]

        if state == IN_CODE:
            if ch2 == "//":
                if strip_comments:
                    state = IN_LINE_COMMENT
                    i += 2
                    continue
                out.append("//")
                i += 2
                continue
            if ch2 == "/*":
                is_doc = i + 2 < n and src[i:i + 3] == "/**"
                if is_doc and strip_docs:
                    state = IN_DOCCOMMENT
                    i += 3
                    continue
                if (not is_doc) and strip_comments:
                    state = IN_BLOCK_COMMENT
                    i += 2
                    continue
                out.append("/**" if is_doc else "/*")
                i += 3 if is_doc else 2
                continue
            if ch == '"':
                start = i
                i = _skip_c_string(src, i)
                out.append(src[start:i])
                continue
            if ch == "'":
                start = i
                i = _skip_c_char(src, i)
                out.append(src[start:i])
                continue
            out.append(ch)
            i += 1
            continue

        if state == IN_LINE_COMMENT:
            if ch == "\n":
                out.append("\n")
                state = IN_CODE
            i += 1
            continue

        if state in {IN_BLOCK_COMMENT, IN_DOCCOMMENT}:
            if ch2 == "*/":
                state = IN_CODE
                i += 2
            else:
                i += 1
            continue

    return "".join(out)


def _strip_strings_for_typedef_scan(src: str) -> str:
    out = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch == '"':
            end = _skip_c_string(src, i)
            out.append(" " * (end - i))
            i = end
            continue
        if ch == "'":
            end = _skip_c_char(src, i)
            out.append(" " * (end - i))
            i = end
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_top_level_declarators(segment: str) -> List[str]:
    parts = []
    buf = []
    paren = bracket = brace = 0
    for ch in segment:
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(0, bracket - 1)
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(0, brace - 1)
        if ch == "," and paren == 0 and bracket == 0 and brace == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _extract_typedef_aliases(segment: str) -> List[str]:
    aliases = []
    for decl in _split_top_level_declarators(segment):
        idents = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", decl)
        idents = [x for x in idents if x not in C_KEYWORDS]
        if idents:
            aliases.append(idents[-1])
    return aliases


def collect_c_type_names(src: str) -> Set[str]:
    """
    Recover likely user-defined type names before masking:
    - struct/union/enum tags
    - typedef aliases
    """
    known_types: Set[str] = set()
    cleaned = strip_c_comments(src, strip_docs=True, strip_comments=True)
    cleaned = _strip_strings_for_typedef_scan(cleaned)

    # struct/union/enum tags
    for m in re.finditer(r"\b(?:struct|union|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", cleaned):
        known_types.add(m.group(1))

    # typedef aliases
    i, n = 0, len(cleaned)
    while i < n:
        if is_ident_start(cleaned[i]):
            ident, j = _read_ident(cleaned, i)
            if ident == "typedef":
                start = j
                paren = bracket = brace = 0
                while j < n:
                    ch = cleaned[j]
                    if ch == "(":
                        paren += 1
                    elif ch == ")":
                        paren = max(0, paren - 1)
                    elif ch == "[":
                        bracket += 1
                    elif ch == "]":
                        bracket = max(0, bracket - 1)
                    elif ch == "{":
                        brace += 1
                    elif ch == "}":
                        brace = max(0, brace - 1)
                    elif ch == ";" and paren == 0 and bracket == 0 and brace == 0:
                        aliases = _extract_typedef_aliases(cleaned[start:j])
                        known_types.update(aliases)
                        j += 1
                        break
                    j += 1
                i = j
                continue
            i = j
            continue
        i += 1

    return known_types


def normalize_include_payload(payload: str) -> str:
    out = []
    i = 0
    while i < len(payload):
        ch = payload[i]
        if is_ident_start(ch):
            _, j = _read_ident(payload, i)
            out.append("<HEADER>")
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def normalize_c_identifiers_legacy(src: str, mode: str, nbytes: int = 3) -> str:
    if mode == "none":
        return src

    out = []
    i, n = 0, len(src)
    mapping: Dict[str, str] = {}

    while i < n:
        ch = src[i]
        ch2 = src[i:i + 2]

        if ch == '"':
            start = i
            i = _skip_c_string(src, i)
            out.append(src[start:i])
            continue
        if ch == "'":
            start = i
            i = _skip_c_char(src, i)
            out.append(src[start:i])
            continue
        if ch2 == "//" or ch2 == "/*":
            out.append(ch)
            i += 1
            continue
        if is_ident_start(ch):
            ident, j = _read_ident(src, i)
            if ident in C_KEYWORDS:
                out.append(ident)
            else:
                if mode == "placeholder":
                    out.append("<ID>")
                elif mode == "per-file-hash":
                    if ident not in mapping:
                        mapping[ident] = short_hash(ident, nbytes)
                    out.append(mapping[ident])
                elif mode == "global-hash":
                    out.append(short_hash(ident, nbytes))
                else:
                    out.append(ident)
            i = j
            continue
        out.append(ch)
        i += 1

    return "".join(out)


def _segment_unknown_roles(segment: str) -> Set[int]:
    """
    In a declaration-like segment, the rightmost unknown identifier is usually the
    variable/parameter name; earlier unknown identifiers tend to be type aliases.
    """
    unknown_positions = []
    i = 0
    while i < len(segment):
        if is_ident_start(segment[i]):
            _, j = _read_ident(segment, i)
            unknown_positions.append((i, j))
            i = j
        elif segment[i] == '"':
            i = _skip_c_string(segment, i)
        elif segment[i] == "'":
            i = _skip_c_char(segment, i)
        else:
            i += 1
    return {unknown_positions[-1][0]} if unknown_positions else set()


def mask_c_param_segment(segment: str, known_types: Set[str]) -> str:
    out = []
    i, n = 0, len(segment)
    unknown_positions = []
    expect_tag_name = False

    while i < n:
        ch = segment[i]
        ch2 = segment[i:i + 2]

        if ch in NON_SIG_CHARS:
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            out.append("<STR>")
            i = _skip_c_string(segment, i)
            continue
        if ch == "'":
            out.append("<STR>")
            i = _skip_c_char(segment, i)
            continue
        if ch.isdigit():
            j = i + 1
            while j < n and (segment[j].isdigit() or segment[j] in "._xXbBeEpPuUlLfF+-"):
                j += 1
            out.append("<NUM>")
            i = j
            continue
        if ch2 == "->":
            out.append("->")
            i += 2
            continue
        if ch2 == "::":
            out.append("::")
            i += 2
            continue
        if is_ident_start(ch):
            ident, j = _read_ident(segment, i)
            if ident in C_KEYWORDS:
                out.append(ident)
                expect_tag_name = ident in {"struct", "union", "enum"}
                i = j
                continue
            if expect_tag_name or ident in known_types:
                out.append("<TYPE>")
                expect_tag_name = False
                i = j
                continue
            p = prev_sig_idx(segment, i)
            prev_two = segment[p - 1:p + 1] if p > 0 else ""
            next_two = segment[j:j + 2]
            if prev_two == "::" or next_two == "::":
                out.append("<TYPE>")
                i = j
                continue
            if p >= 0 and (segment[p] == "." or prev_two == "->"):
                out.append("<ATTR>")
                i = j
                continue
            unknown_positions.append(len(out))
            out.append(("__UNKNOWN__", ident))
            i = j
            continue

        out.append(ch)
        i += 1

    # Resolve unknowns: last unknown -> <PARAM>, earlier unknowns -> <TYPE>
    last_unknown = unknown_positions[-1] if unknown_positions else None
    rebuilt = []
    for idx, item in enumerate(out):
        if isinstance(item, tuple) and item[0] == "__UNKNOWN__":
            rebuilt.append("<PARAM>" if idx == last_unknown else "<TYPE>")
        else:
            rebuilt.append(item)
    return "".join(rebuilt)


def mask_c_function_params(src: str, open_idx: int, known_types: Set[str]) -> Tuple[str, int]:
    """
    Normalize a function parameter list starting at '('.
    Returns the normalized substring and the index just after the matching ')'.
    """
    assert src[open_idx] == "("
    i = open_idx + 1
    depth = 1
    seg_start = i
    pieces = ["("]

    while i < len(src) and depth > 0:
        ch = src[i]
        ch2 = src[i:i + 2]
        if ch == '"':
            i = _skip_c_string(src, i)
            continue
        if ch == "'":
            i = _skip_c_char(src, i)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                segment = src[seg_start:i]
                pieces.append(mask_c_param_segment(segment, known_types))
                pieces.append(")")
                return "".join(pieces), i + 1
        elif ch == "," and depth == 1:
            segment = src[seg_start:i]
            pieces.append(mask_c_param_segment(segment, known_types))
            pieces.append(",")
            seg_start = i + 1
        elif ch2 == "->":
            i += 2
            continue
        elif ch2 == "::":
            i += 2
            continue
        i += 1

    return "".join(pieces), i


def normalize_c_structure(src: str) -> str:
    known_types = collect_c_type_names(src)
    out = []
    i, n = 0, len(src)
    expect_tag_name = False
    expect_macro_name = False

    while i < n:
        ch = src[i]
        ch2 = src[i:i + 2]

        if at_line_start(src, i) and ch == "#":
            out.append("#")
            i += 1
            while i < n and src[i] in NON_SIG_CHARS:
                out.append(src[i])
                i += 1
            if i < n and is_ident_start(src[i]):
                directive, j = _read_ident(src, i)
                out.append(directive if directive in PREPROC_DIRECTIVES else directive)
                expect_macro_name = directive in {"define", "ifdef", "ifndef", "undef"}
                i = j
                if directive == "include":
                    while i < n and src[i] in NON_SIG_CHARS:
                        out.append(src[i])
                        i += 1
                    if i < n and src[i] in {'<', '"'}:
                        closer = ">" if src[i] == "<" else '"'
                        out.append(src[i])
                        i += 1
                        start = i
                        while i < n and src[i] != closer:
                            if src[i] == "\\" and i + 1 < n:
                                i += 2
                            else:
                                i += 1
                        out.append(normalize_include_payload(src[start:i]))
                        if i < n and src[i] == closer:
                            out.append(closer)
                            i += 1
                    continue
                continue

        if ch in NON_SIG_CHARS:
            out.append(ch)
            i += 1
            continue

        if ch == '"':
            out.append("<STR>")
            i = _skip_c_string(src, i)
            continue
        if ch == "'":
            out.append("<STR>")
            i = _skip_c_char(src, i)
            continue

        if ch.isdigit():
            j = i + 1
            while j < n and (src[j].isdigit() or src[j] in "._xXbBeEpPuUlLfF+-"):
                j += 1
            out.append("<NUM>")
            i = j
            continue

        if ch2 == "->":
            out.append("->")
            i += 2
            continue
        if ch2 == "::":
            out.append("::")
            i += 2
            continue

        if ch2 == "//" or ch2 == "/*":
            out.append(ch)
            i += 1
            continue

        if is_ident_start(ch):
            ident, j = _read_ident(src, i)

            if ident in C_KEYWORDS:
                out.append(ident)
                expect_tag_name = ident in {"struct", "union", "enum"}
                i = j
                continue

            if expect_macro_name:
                out.append("<MACRO>")
                expect_macro_name = False
                i = j
                continue

            if expect_tag_name or ident in known_types:
                out.append("<TYPE>")
                expect_tag_name = False
                i = j
                continue

            p = prev_sig_idx(src, i)
            prev_two = src[p - 1:p + 1] if p > 0 else ""
            next_two = src[j:j + 2]
            if prev_two == "::" or next_two == "::":
                out.append("<TYPE>")
                i = j
                continue
            if p >= 0 and (src[p] == "." or prev_two == "->"):
                out.append("<ATTR>")
                i = j
                continue

            k = next_sig_idx(src, j)
            if k < n and src[k] == "(" and not (p >= 0 and src[p] in {".", "#"}):
                out.append("<FUNC>")
                params_masked, new_idx = mask_c_function_params(src, k, known_types)
                out.append(params_masked)
                i = new_idx
                continue

            out.append("<VAR>")
            i = j
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def process_c_snippet(
    code: str,
    mode: str,
    nbytes: int,
    strip_docstrings: bool,
    strip_comments: bool,
) -> str:
    if code is None:
        return code
    if strip_docstrings or strip_comments:
        code = strip_c_comments(code, strip_docs=strip_docstrings, strip_comments=strip_comments)
    if mode == "structure":
        return normalize_c_structure(code)
    return normalize_c_identifiers_legacy(code, mode=mode, nbytes=nbytes)


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
        for line in tqdm(fin, desc=f"Normalizing JSONL (C, mode={mode})"):
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
                norm = process_c_snippet(
                    orig,
                    mode=mode,
                    nbytes=nbytes,
                    strip_docstrings=strip_docstrings,
                    strip_comments=strip_comments,
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


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Normalize C code in a JSONL dataset. Default mode 'structure' masks naming while preserving structure; legacy modes available."
    )
    ap.add_argument("--input", required=True, help="Path to input JSONL (e.g., c_dataset.jsonl)")
    ap.add_argument("--output", required=True, help="Path to output JSONL")
    ap.add_argument(
        "--mode",
        choices=["structure", "none", "placeholder", "per-file-hash", "global-hash"],
        default="structure",
        help="Masking strategy: 'structure' (recommended) or legacy identifier modes",
    )
    ap.add_argument(
        "--nbytes",
        type=int,
        default=3,
        help="Hash length in bytes (for *_hash legacy modes). 3 -> 6 hex chars (ID_ab12cd)",
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
        help="overwrite: replace original fields; add_suffix: write to <field>_norm and keep originals",
    )
    ap.add_argument(
        "--strip-docstrings",
        action="store_true",
        help="Remove /** ... */ doc comments before normalization",
    )
    ap.add_argument(
        "--strip-comments",
        action="store_true",
        help="Remove line (// ...) and block (/* ... */) comments before normalization",
    )
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
