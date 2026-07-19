#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalize_jsonl_identifiers.py  (structure-focused masking)

Goal: preserve structural cues (keywords, punctuation, operators, (), :, ., etc.)
and the presence/positions of types, while masking naming style into category
placeholders so cross-entropy reflects *structural naturalness* more than lexemes.

Placeholders:
  <FUNC>  function names (defs and likely call sites without preceding '.')
  <CLASS> class names (after 'class')
  <PARAM> parameter names in def (...) lists
  <VAR>   other bare identifiers
  <ATTR>  attribute names after a dot '.'
  <SELF>, <CLS> for 'self'/'cls' conventions
  <MOD>   module/package segments in imports
  <SYM>   imported symbols (from X import Y)
  <TYPE>  names inside function parameter/return annotations
  <NUM>   numeric literals; <STR> string literals

Booleans/None and Python keywords stay verbatim.
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
from typing import Dict, Iterable, List, Tuple, Optional

from tqdm import tqdm

# --------------------------
# Token classes / sets
# --------------------------

PY_KEYWORDS = set(keyword.kwlist)
PY_BUILTINS = set(dir(builtins))

NON_SIG_TOKS = {
    tokenize.ENCODING,
    tokenize.NL,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.COMMENT,
    tokenize.ENDMARKER,
}

# --------------------------
# Optional helpers reused
# --------------------------

def _remove_docstrings(code: str) -> str:
    """Remove module/class/func docstrings; insert 'pass' where block would be empty."""
    try:
        tree = ast.parse(code)
    except Exception:
        return code

    spans: List[Tuple[int, int, int, int, str]] = []

    def record_docstring_span(node, only_stmt: bool):
        if not getattr(node, "body", None):
            return
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), (ast.Str, ast.Constant)):
            val = first.value
            s = val.s if isinstance(val, ast.Str) else (val.value if isinstance(val, ast.Constant) and isinstance(val.value, str) else None)
            if s is None or not hasattr(first, "lineno") or not hasattr(first, "end_lineno"):
                return
            sl, sc = first.lineno, first.col_offset
            el, ec = first.end_lineno, first.end_col_offset
            replacement = ""
            if only_stmt:
                indent = " " * sc
                replacement = indent + "pass\n"
            spans.append((sl, sc, el, ec, replacement))

    record_docstring_span(tree, only_stmt=(len(getattr(tree, "body", [])) == 1))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            only_stmt = len(getattr(node, "body", [])) == 1
            record_docstring_span(node, only_stmt)

    if not spans:
        return code

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
    reader = io.BytesIO(code.encode("utf-8", errors="ignore")).readline
    try:
        toks = list(tokenize.tokenize(reader))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return code
    out = [t for t in toks if t.type != tokenize.COMMENT]
    try:
        rebuilt = tokenize.untokenize(out)
        return rebuilt if isinstance(rebuilt, str) else rebuilt.decode("utf-8", errors="ignore")
    except Exception:
        return code


# --------------------------
# Structure-focused normalizer
# --------------------------

def _is_name_token(tok: tokenize.TokenInfo) -> bool:
    return tok.type == tokenize.NAME

def _is_keyword_or_builtin(name: str) -> bool:
    return name in PY_KEYWORDS or name in PY_BUILTINS or name in {"True", "False", "None"}

def _next_sig_token(tokens: List[tokenize.TokenInfo], k: int) -> Optional[tokenize.TokenInfo]:
    i = k + 1
    while i < len(tokens) and tokens[i].type in NON_SIG_TOKS:
        i += 1
    return tokens[i] if i < len(tokens) else None

def _prev_sig_token(tokens: List[tokenize.TokenInfo], k: int) -> Optional[tokenize.TokenInfo]:
    i = k - 1
    while i >= 0 and tokens[i].type in NON_SIG_TOKS:
        i -= 1
    return tokens[i] if i >= 0 else None


def normalize_code_structure_focused(
    code: str,
    strip_docstrings: bool = False,
    strip_comments: bool = False,
) -> str:
    """
    Mask naming lexemes while preserving structure and the presence/positions of types
    in function signatures. Uses a tokenizer-driven state machine (no heavy AST edits).
    """

    if not code:
        return code

    if strip_docstrings:
        code = _remove_docstrings(code)
    if strip_comments:
        code = _strip_inline_comments(code)
    if not code.endswith("\n"):
        code += "\n"

    reader = io.BytesIO(code.encode("utf-8", errors="ignore")).readline
    try:
        tokens = list(tokenize.tokenize(reader))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return code

    out: List[tokenize.TokenInfo] = []

    # State flags
    def_name_next = False
    class_name_next = False
    in_params = False          # inside def (...) parameter list
    paren_depth = 0            # depth for def signature tracking
    in_param_annotation = False
    in_return_annotation = False
    in_from_module = False     # after 'from' before 'import'
    in_import_names = False    # after 'import' (either top-level or after 'from X import')

    k = 0
    while k < len(tokens):
        tok = tokens[k]
        ttype, tstr = tok.type, tok.string

        # Track simple states based on exact keyword strings
        if ttype == tokenize.NAME and tstr == "def":
            def_name_next = True
            in_return_annotation = False
            in_param_annotation = False
            # params state will be set when we hit '('
            out.append(tok); k += 1
            continue
        if ttype == tokenize.NAME and tstr == "class":
            class_name_next = True
            out.append(tok); k += 1
            continue
        if ttype == tokenize.NAME and tstr == "from":
            in_from_module = True
            in_import_names = False
            out.append(tok); k += 1
            continue
        if ttype == tokenize.NAME and tstr == "import":
            # 'import' can appear at top-level or after 'from ... import'
            in_import_names = True
            in_from_module = False
            out.append(tok); k += 1
            continue

        # Parentheses / signature tracking
        if tok.exact_type == tokenize.LPAR:
            prev = _prev_sig_token(tokens, k)
            if def_name_next is False and prev and prev.string == "def":
                # shouldn't happen (we expect name after 'def' first), but keep safe
                pass
            if def_name_next is False and in_params is False:
                # entering possibly parameters if this follows function name
                # We detect entering params by checking previous non-trivia token was function name placeholder
                prev = _prev_sig_token(tokens, k)
                if prev and prev.type == tokenize.NAME or (prev and prev.type == tokenize.OP and prev.string in {"<FUNC>"}):
                    in_params = True
            paren_depth += 1

        if tok.exact_type == tokenize.RPAR:
            paren_depth -= 1
            if in_params and paren_depth == 0:
                in_params = False
                in_param_annotation = False  # end any lingering param annotation

        # Annotation tracking inside function signature
        if in_params and tok.type == tokenize.OP and tok.string == ":":
            in_param_annotation = True
        elif in_params and tok.type == tokenize.OP and tok.string in {",", "=", ")"}:
            in_param_annotation = False

        # Return annotation starts at '->' until the colon ending the def line
        if tok.type == tokenize.OP and tok.string == "->":
            in_return_annotation = True
        if in_return_annotation and tok.type == tokenize.OP and tok.string == ":":
            in_return_annotation = False

        # Literal normalization
        if ttype == tokenize.NUMBER:
            out.append(tokenize.TokenInfo(ttype, "<NUM>", tok.start, tok.end, tok.line))
            k += 1
            continue
        if ttype == tokenize.STRING:
            out.append(tokenize.TokenInfo(ttype, "<STR>", tok.start, tok.end, tok.line))
            k += 1
            continue

        # Names (identifiers, keywords, builtins)
        if _is_name_token(tok):
            name = tstr
            # Keep keywords/builtins/True/False/None
            if _is_keyword_or_builtin(name):
                out.append(tok); k += 1
                continue

            # After 'def' / 'class'
            if def_name_next:
                out.append(tokenize.TokenInfo(ttype, "<FUNC>", tok.start, tok.end, tok.line))
                def_name_next = False
                k += 1
                continue
            if class_name_next:
                out.append(tokenize.TokenInfo(ttype, "<CLASS>", tok.start, tok.end, tok.line))
                class_name_next = False
                k += 1
                continue

            # Import/module masking
            if in_from_module:
                # module path pieces before 'import'
                out.append(tokenize.TokenInfo(ttype, "<MOD>", tok.start, tok.end, tok.line))
                k += 1
                continue
            if in_import_names:
                out.append(tokenize.TokenInfo(ttype, "<SYM>", tok.start, tok.end, tok.line))
                k += 1
                continue

            # Function signature annotations (types)
            if in_param_annotation or in_return_annotation:
                out.append(tokenize.TokenInfo(ttype, "<TYPE>", tok.start, tok.end, tok.line))
                k += 1
                continue

            # Special conventional names
            if name == "self":
                out.append(tokenize.TokenInfo(ttype, "<SELF>", tok.start, tok.end, tok.line))
                k += 1
                continue
            if name == "cls":
                out.append(tokenize.TokenInfo(ttype, "<CLS>", tok.start, tok.end, tok.line))
                k += 1
                continue

            # Attribute after dot
            prev_tok = _prev_sig_token(tokens, k)
            if prev_tok and prev_tok.type == tokenize.OP and prev_tok.string == ".":
                out.append(tokenize.TokenInfo(ttype, "<ATTR>", tok.start, tok.end, tok.line))
                k += 1
                continue

            # Parameter names inside def (...)
            if in_params:
                out.append(tokenize.TokenInfo(ttype, "<PARAM>", tok.start, tok.end, tok.line))
                k += 1
                continue

            # Likely function call: NAME followed soon by '(' and not an attribute
            nxt = _next_sig_token(tokens, k)
            if nxt and nxt.exact_type == tokenize.LPAR:
                out.append(tokenize.TokenInfo(ttype, "<FUNC>", tok.start, tok.end, tok.line))
                k += 1
                continue

            # Fallback: general variable
            out.append(tokenize.TokenInfo(ttype, "<VAR>", tok.start, tok.end, tok.line))
            k += 1
            continue

        # End of 'from ... import ...' module section when we hit 'import'
        # (handled above when seeing NAME 'import')

        # Write other tokens unchanged (operators, punctuation, dots, colons, etc.)
        out.append(tok)
        k += 1

    try:
        rebuilt = tokenize.untokenize(out)
        return rebuilt if isinstance(rebuilt, str) else rebuilt.decode("utf-8", errors="ignore")
    except Exception:
        return code


# --------------------------
# JSONL Processing
# --------------------------

DEFAULT_FIELDS = ["human_code", "chatgpt_code", "dsc_code", "qwen_code"]

def process_jsonl(
    input_path: str,
    output_path: str,
    fields: List[str],
    write_policy: str,
    strip_docstrings: bool,
    strip_comments: bool,
) -> None:
    """
    Read input JSONL, apply structure-focused masking to specified code fields, and
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
        for line in tqdm(fin, desc="Normalizing JSONL (structure-focused)"):
            total_lines += 1
            line = line.strip()
            if not line:
                fout.write("\n")
                continue
            try:
                obj = json.loads(line)
            except Exception:
                failed_lines += 1
                fout.write(line + "\n")
                continue

            for field in fields:
                if field not in obj or not isinstance(obj[field], str):
                    continue
                orig = obj[field]
                norm = normalize_code_structure_focused(
                    orig,
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
        description="Mask naming lexemes (structure-focused) in a JSONL dataset of Python code; optionally strip docstrings/comments."
    )
    ap.add_argument("--input", required=True, help="Path to input JSONL")
    ap.add_argument("--output", required=True, help="Path to output JSONL")
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
        help=("overwrite: replace original fields in output; "
              "add_suffix: keep originals and write masked code to <field>_norm"),
    )
    ap.add_argument(
        "--strip-docstrings",
        action="store_true",
        help="Remove module/class/function docstrings before masking",
    )
    ap.add_argument(
        "--strip-comments",
        action="store_true",
        help="Remove inline '# ...' comments before masking",
    )
    return ap.parse_args()


def main():
    args = parse_args()
    process_jsonl(
        input_path=args.input,
        output_path=args.output,
        fields=args.fields,
        write_policy=args.write_policy,
        strip_docstrings=args.strip_docstrings,
        strip_comments=args.strip_comments,
    )


if __name__ == "__main__":
    main()
