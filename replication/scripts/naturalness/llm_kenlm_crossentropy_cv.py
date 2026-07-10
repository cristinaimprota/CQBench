#!/usr/bin/env python3
"""
llm_kenlm_crossentropy_cv.py

10-fold cross-validation for code cross-entropy & perplexity,
using KenLM and/or LLM, and supporting multiple tokenization strategies:
    --tokenizer whitespace | regex | llm | treesitter
    --language python | java | c
        Note: --tokenizer treesitter is currently only available for python/java.
"""

import argparse, json, math, os, random, subprocess, tempfile, csv
import numpy as np
from pathlib import Path
from tqdm import tqdm
from sklearn.model_selection import KFold

# ------------------ Tokenizer strategies --------------------
import re
TOKEN_RE = re.compile(r"\w+|[^\s\w]", flags=re.UNICODE)

# ---- Optional Tree-sitter setup (for --tokenizer treesitter) ----
# We lazily build parsers per language to keep startup snappy.
_TS_PARSERS = {}
try:
    # preferred: modern, maintained package
    from tree_sitter_language_pack import get_parser as _get_ts_parser
except Exception:
    # fallback if you still have the old package installed
    try:
        from tree_sitter_languages import get_parser as _get_ts_parser
    except Exception:
        _get_ts_parser = None

def _ensure_ts_parser(lang: str):
    """
    Get or build a Tree-sitter parser for the given language ('python' or 'java').
    """
    if _get_ts_parser is None:
        raise RuntimeError(
            "Tree-sitter not available. Install 'tree_sitter' and 'tree_sitter_languages'."
        )
    key = lang.lower()
    if key not in ("python", "java"):
        raise ValueError(f"Unsupported Tree-sitter language: {lang}")
    if key not in _TS_PARSERS:
        _TS_PARSERS[key] = _get_ts_parser(key)
    return _TS_PARSERS[key]

def tokenize_whitespace(code):
    return code.strip().split()

def tokenize_regex(code):
    return TOKEN_RE.findall(code)

def tokenize_llm(code, hf_tokenizer):
    ids = hf_tokenizer(code, return_tensors=None)["input_ids"]
    tokens = hf_tokenizer.convert_ids_to_tokens(ids)
    return tokens

def _ts_collect_leaf_tokens(node, src_bytes, include_unnamed=True):
    """
    Collect terminal (leaf) tokens from the Tree-sitter parse.
    include_unnamed=True keeps punctuation/operators etc.
    """
    if len(node.children) == 0:
        if include_unnamed or node.is_named:
            return [src_bytes[node.start_byte:node.end_byte].decode("utf-8")]
        return []
    out = []
    for ch in node.children:
        out.extend(_ts_collect_leaf_tokens(ch, src_bytes, include_unnamed))
    return out

def make_treesitter_tokenizer(language: str):
    """
    Factory returning a tokenizer function for the chosen language.
    """
    parser = _ensure_ts_parser(language)

    def _tok(code: str):
        src = code.encode("utf-8")
        tree = parser.parse(src)
        return _ts_collect_leaf_tokens(tree.root_node, src, include_unnamed=True)

    return _tok

def get_tokenizer(strategy, hf_tokenizer=None, language="python"):
    if strategy == "whitespace":
        return tokenize_whitespace
    elif strategy == "regex":
        return tokenize_regex
    elif strategy == "llm":
        if hf_tokenizer is None:
            raise ValueError("hf_tokenizer must be provided for LLM tokenization")
        return lambda code: tokenize_llm(code, hf_tokenizer)
    elif strategy == "treesitter":
        return make_treesitter_tokenizer(language)
    else:
        raise ValueError(f"Unknown tokenizer: {strategy}")

def filter_special_tokens(tokens):
    return [t for t in tokens if t not in ("<s>", "</s>", "<unk>")]

# ------------------ KenLM helpers --------------------
def run(cmd, **kwargs):
    subprocess.run(cmd, check=True, **kwargs)

def write_lines(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")

def train_kenlm(train_txt, arpa_path, klm_path, order, memory):
    run([
        "lmplz", "-o", str(order), "--discount_fallback", "--skip_symbols", "-S", memory
    ], stdin=open(train_txt, "r", encoding="utf-8"),
       stdout=open(arpa_path, "w", encoding="utf-8"))
    run(["build_binary", "-s", str(arpa_path), str(klm_path)])

def score_kenlm(model, tokens):
    if not tokens:
        return float("nan"), float("nan"), 0
    log2_p = model.score(" ".join(tokens), bos=True, eos=True)
    ce = -log2_p / len(tokens)
    ppl = 2 ** ce
    return ce, ppl, len(tokens)

# ------------------ HuggingFace LLM helpers --------------------
def load_hf(model_name, device="auto"):
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, AutoModelForSeq2SeqLM

    print(f"Loading HuggingFace model: {model_name}")
    tok = AutoTokenizer.from_pretrained(model_name)

    # Detect if model is CodeT5 (or any T5 variant)
    if "codet5" in model_name.lower() or "t5" in model_name.lower():
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    else:
        model = AutoModelForCausalLM.from_pretrained(model_name)
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    return tok, model, device

def score_llm(code, tok, model, device):
    import torch, math
    code = code.strip()
    if not code:
        return float("nan"), float("nan"), 0
    ids = tok(code, return_tensors="pt").input_ids.to(device)
    # Remove cases with only special tokens
    tokens = tok.convert_ids_to_tokens(ids[0])
    special_tokens = set([tok.cls_token, tok.sep_token, tok.pad_token, tok.bos_token, tok.eos_token, "<s>", "</s>", "<unk>"])
    content_tokens = [t for t in tokens if t not in special_tokens and t is not None]
    if len(content_tokens) == 0:
        return float("nan"), float("nan"), 0
    with torch.no_grad():
        loss = model(ids, labels=ids).loss
    ce_bits = loss.item() / math.log(2)
    ppl = 2 ** ce_bits
    return ce_bits, ppl, ids.size(1)

# ------------------ Main 10-fold CV routine --------------------
def parse_args():
    parser = argparse.ArgumentParser(description="KenLM + LLM cross-entropy 10-fold CV scorer")
    parser.add_argument("--input", type=str, required=True, help="Input JSONL file")
    parser.add_argument("--output", type=str, required=True, help="Output CSV path")
    # KenLM
    parser.add_argument("--kenlm", action="store_true", help="Enable KenLM scoring")
    parser.add_argument("--order", type=int, default=6, help="n-gram order (default 6)")
    parser.add_argument("--memory", default="80%", help="KenLM memory limit (default 80%%)")
    parser.add_argument("--train_author", type=str, default="human_code",
                        help="Field to train KenLM on (default: human_code)")
    parser.add_argument("--test_authors", type=str,
                        default="human_code,chatgpt_code,dsc_code,qwen_code",
                        help="Comma-separated list of fields to test KenLM on")
    # HuggingFace LLM
    parser.add_argument("--hf", action="store_true", help="Enable HuggingFace LLM scoring")
    parser.add_argument("--model", type=str, default="Salesforce/codegen-350M-multi",
                        help="HuggingFace model ID")
    parser.add_argument("--device", type=str, default="auto", help="'cuda', 'cpu', or 'auto'")
    # Cross-validation
    parser.add_argument("--k", type=int, default=10, help="Number of folds (default 10)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    # Tokenizer selection
    parser.add_argument(
        "--tokenizer",
        type=str,
        choices=["whitespace", "regex", "llm", "treesitter"],
        default="regex",
        help="Tokenization strategy for KenLM (default: regex)",
    )
    # Language for Tree-sitter
    parser.add_argument(
        "--language",
        type=str,
        choices=["python", "java", "c"],
        default="python",
        help="Source language. Tree-sitter tokenization currently supports only python/java.",
    )
    return parser.parse_args()

def main():
    args = parse_args()
    if args.tokenizer == "treesitter" and args.language not in ("python", "java"):
        raise ValueError(
            f"--tokenizer treesitter currently supports only python/java, not {args.language!r}"
        )
    random.seed(args.seed)
    np.random.seed(args.seed)
    data = []
    with open(args.input, "r", encoding="utf-8") as fin:
        for ln in fin:
            if ln.strip():
                data.append(json.loads(ln))
    data = np.array(data)
    kf = KFold(n_splits=args.k, shuffle=True, random_state=args.seed)

    # HuggingFace LLM setup
    hf_tokenizer = None
    if args.hf or args.tokenizer == "llm":
        import torch
        hf_tokenizer, hf_model, device = load_hf(args.model, args.device)
    else:
        hf_model = device = None

    # Select tokenization function
    tokenize_func = get_tokenizer(args.tokenizer, hf_tokenizer, language=args.language)
    test_author_fields = [field.strip() for field in args.test_authors.split(",")]

    all_results = []

    for fold, (train_idx, test_idx) in enumerate(kf.split(data)):
        print(f"\n=== Fold {fold+1}/{args.k} ===")
        train_samples = data[train_idx]
        test_samples = data[test_idx]

        # --- KenLM: train per fold, if requested ---
        if args.kenlm:
            print(f"  [KenLM] Training KenLM on '{args.train_author}' from train split using '{args.tokenizer}' tokenization (language={args.language}) ...")
            with tempfile.TemporaryDirectory() as tmpdir:
                train_txt = Path(tmpdir) / "train.txt"
                arpa_path = Path(tmpdir) / "model.arpa"
                klm_path = Path(tmpdir) / "model.klm"
                train_lines = []
                for obj in train_samples:
                    code = obj.get(args.train_author, "")
                    toks = tokenize_func(code)
                    toks = filter_special_tokens(toks)
                    if toks:
                        train_lines.append(" ".join(toks))
                write_lines(train_txt, train_lines)
                train_kenlm(train_txt, arpa_path, klm_path, args.order, args.memory)
                import kenlm
                km = kenlm.Model(str(klm_path))
                # Score selected variants in test fold
                for idx, obj in tqdm(enumerate(test_samples), total=len(test_samples), desc="[KenLM scoring]"):
                    for field in test_author_fields:
                        label = field.replace("_code", "")  # Clean label
                        code = obj.get(field, "")
                        toks = tokenize_func(code)
                        toks = filter_special_tokens(toks)
                        ce, ppl, n = score_kenlm(km, toks)
                        all_results.append({
                            "fold": fold,
                            "sample_idx": int(test_idx[idx]),
                            "source": label,
                            "model_type": f"kenlm-{args.order}gram-{args.tokenizer}-train{args.train_author}-lang{args.language}",
                            "cross_entropy_bits": ce,
                            "perplexity": ppl,
                            "tokens": n,
                        })

        # --- HuggingFace LLM scoring, if requested ---
        if args.hf:
            print("  [LLM] Scoring with HuggingFace model ...")
            for idx, obj in tqdm(enumerate(test_samples), total=len(test_samples), desc="[LLM scoring]"):
                for field in test_author_fields:
                    label = field.replace("_code", "")
                    code = obj.get(field, "")
                    ce, ppl, n = score_llm(code, hf_tokenizer, hf_model, device)
                    all_results.append({
                        "fold": fold,
                        "sample_idx": int(test_idx[idx]),
                        "source": label,
                        "model_type": args.model,
                        "cross_entropy_bits": ce,
                        "perplexity": ppl,
                        "tokens": n,
                    })

    # Write all results
    print(f"\nWriting results to {args.output} ...")
    fieldnames = ["fold", "sample_idx", "source", "model_type", "cross_entropy_bits", "perplexity", "tokens"]
    with open(args.output, "w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_results:
            writer.writerow(row)
    print("Done!")

if __name__ == "__main__":
    main()
