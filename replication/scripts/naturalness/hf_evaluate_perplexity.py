#!/usr/bin/env python3
"""
hf_evaluate_perplexity.py

Score code snippets stored in JSONL fields with the Hugging Face `evaluate`
perplexity metric and write:
1. a per-snippet CSV, and
2. a per-source summary CSV.

This is intended as a complementary naturalness analysis to the KenLM pipeline.
Unlike the KenLM workflow, this script does not use cross-validation because the
judge model is a fixed pretrained causal LM.
"""

import argparse
import csv
import importlib.metadata
import importlib.util
import json
import math
import os
import statistics
from pathlib import Path
from contextlib import contextmanager

from tqdm import tqdm


def parse_args():
    parser = argparse.ArgumentParser(
        description="Score JSONL code fields with Hugging Face evaluate perplexity."
    )
    parser.add_argument("--input", required=True, help="Input JSONL file")
    parser.add_argument("--output", required=True, help="Per-snippet output CSV")
    parser.add_argument(
        "--summary-output",
        default=None,
        help="Per-source summary CSV (default: derive from --output)",
    )
    parser.add_argument(
        "--model-id",
        required=True,
        help="Causal LM used by the Hugging Face evaluate perplexity metric",
    )
    parser.add_argument(
        "--fields",
        nargs="+",
        required=True,
        help="JSONL fields to score, e.g. human_code dsc_code qwen_code",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Batch size forwarded to evaluate perplexity (default: 16)",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="Device for inference: auto | cpu | cuda | gpu (default: auto)",
    )
    parser.add_argument(
        "--add-start-token",
        dest="add_start_token",
        action="store_true",
        help="Add BOS/start token before scoring (default)",
    )
    parser.add_argument(
        "--no-add-start-token",
        dest="add_start_token",
        action="store_false",
        help="Do not add a BOS/start token before scoring",
    )
    parser.set_defaults(add_start_token=True)
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Optional cap on rows read from the JSONL for smoke tests",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=None,
        help="Optional max token length forwarded to the HF perplexity metric",
    )
    return parser.parse_args()


def load_perplexity_metric():
    prepare_hf_cache_dirs()
    # Some environments expose a broken DeepSpeed/Triton stack. Hiding it during
    # import keeps evaluate/transformers on the standard PyTorch code path.
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    try:
        with hidden_packages("deepspeed"):
            import evaluate
    except ImportError as exc:
        raise RuntimeError(
            "The 'evaluate' package is required. Install it in your experiment environment."
        ) from exc

    local_metric_dir = Path(__file__).with_name("perplexity")
    attempts = []
    if local_metric_dir.exists():
        attempts.extend(
            [
                {"path": str(local_metric_dir), "kwargs": {"module_type": "measurement"}},
                {"path": str(local_metric_dir), "kwargs": {}},
            ]
        )
    attempts.extend(
        [
            {"path": "perplexity", "kwargs": {"module_type": "measurement"}},
            {"path": "perplexity", "kwargs": {"module_type": "metric"}},
            {"path": "perplexity", "kwargs": {}},
        ]
    )
    last_error = None
    for attempt in attempts:
        try:
            with hidden_packages("deepspeed"):
                return evaluate.load(attempt["path"], **attempt["kwargs"])
        except Exception as exc:  # pragma: no cover - depends on local evaluate version
            last_error = exc
    raise RuntimeError(
        "Unable to load the Hugging Face 'perplexity' evaluate module."
    ) from last_error


def compute_perplexities(metric, texts, model_id, batch_size, add_start_token, device, max_length=None):
    base_kwargs = {
        "model_id": model_id,
        "batch_size": batch_size,
        "add_start_token": add_start_token,
        "device": device,
    }
    if max_length is not None:
        base_kwargs["max_length"] = max_length
    attempts = [
        {"data": texts},
        {"input_texts": texts},
        {"predictions": texts},
    ]
    last_error = None
    for payload in attempts:
        try:
            return metric.compute(**base_kwargs, **payload)
        except TypeError as exc:
            last_error = exc
    raise RuntimeError(
        "Unable to call the Hugging Face perplexity module with any supported input key "
        "('data', 'input_texts', or 'predictions')."
    ) from last_error


def normalize_device(device_name):
    if device_name != "auto":
        return device_name
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_tokenizer(model_id):
    prepare_hf_cache_dirs()
    try:
        with hidden_packages("deepspeed"):
            from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "The 'transformers' package is required. Install it in your experiment environment."
        ) from exc
    return AutoTokenizer.from_pretrained(model_id)


def prepare_hf_cache_dirs():
    hf_home = Path(os.environ.get("HF_HOME", "/tmp/huggingface"))
    os.environ.setdefault("HF_HOME", str(hf_home))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_home / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_home / "transformers"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(hf_home / "datasets"))
    os.environ.setdefault("HF_EVALUATE_CACHE", str(hf_home / "evaluate"))

    for env_name in [
        "HF_HOME",
        "HUGGINGFACE_HUB_CACHE",
        "TRANSFORMERS_CACHE",
        "HF_DATASETS_CACHE",
        "HF_EVALUATE_CACHE",
    ]:
        Path(os.environ[env_name]).mkdir(parents=True, exist_ok=True)


@contextmanager
def hidden_packages(*package_names):
    hidden = set(package_names)

    real_find_spec = importlib.util.find_spec
    real_version = importlib.metadata.version
    real_distribution = importlib.metadata.distribution

    def fake_find_spec(name, *args, **kwargs):
        if name.split(".")[0] in hidden:
            return None
        return real_find_spec(name, *args, **kwargs)

    def fake_version(name):
        if name.split(".")[0] in hidden:
            raise importlib.metadata.PackageNotFoundError(name)
        return real_version(name)

    def fake_distribution(name):
        if name.split(".")[0] in hidden:
            raise importlib.metadata.PackageNotFoundError(name)
        return real_distribution(name)

    importlib.util.find_spec = fake_find_spec
    importlib.metadata.version = fake_version
    importlib.metadata.distribution = fake_distribution
    try:
        yield
    finally:
        importlib.util.find_spec = real_find_spec
        importlib.metadata.version = real_version
        importlib.metadata.distribution = real_distribution


def infer_model_max_length(tokenizer):
    max_len = getattr(tokenizer, "model_max_length", None)
    if max_len is None:
        return None
    # Some tokenizers expose a very large sentinel for "unknown/unbounded".
    if max_len > 1_000_000:
        return None
    return int(max_len)


def batched_token_stats(texts, tokenizer, model_max_length, chunk_size=256):
    stats = []
    for start in tqdm(
        range(0, len(texts), chunk_size),
        desc="  [token stats]",
        leave=False,
    ):
        batch = texts[start : start + chunk_size]
        encoded = tokenizer(batch, add_special_tokens=False, truncation=False)
        for input_ids in encoded["input_ids"]:
            raw_tokens = len(input_ids)
            truncated = model_max_length is not None and raw_tokens > model_max_length
            tokens_used = min(raw_tokens, model_max_length) if truncated else raw_tokens
            stats.append(
                {
                    "raw_tokens": raw_tokens,
                    "tokens_used": tokens_used,
                    "truncated": truncated,
                }
            )
    return stats


def iter_jsonl_field(input_path, field, max_samples=None):
    with open(input_path, "r", encoding="utf-8") as fin:
        for sample_idx, line in enumerate(fin):
            if max_samples is not None and sample_idx >= max_samples:
                break
            if not line.strip():
                continue
            obj = json.loads(line)
            text = obj.get(field, "")
            yield sample_idx, text if text is not None else ""


def source_label(field_name):
    return field_name.replace("_code", "")


def safe_mean(values):
    return statistics.fmean(values) if values else float("nan")


def safe_median(values):
    return statistics.median(values) if values else float("nan")


def safe_stdev(values):
    return statistics.stdev(values) if len(values) > 1 else float("nan")


def make_summary_row(source, model_type, rows):
    scored = [row for row in rows if not math.isnan(row["perplexity"])]
    perplexities = [row["perplexity"] for row in scored]
    ce_bits = [row["cross_entropy_bits"] for row in scored]
    tokens = [row["tokens"] for row in scored]
    truncated_count = sum(1 for row in rows if row["truncated"])
    empty_count = sum(1 for row in rows if row["is_empty"])

    return {
        "source": source,
        "model_type": model_type,
        "rows_total": len(rows),
        "rows_scored": len(scored),
        "rows_empty": empty_count,
        "rows_truncated": truncated_count,
        "mean_perplexity": safe_mean(perplexities),
        "median_perplexity": safe_median(perplexities),
        "std_perplexity": safe_stdev(perplexities),
        "mean_cross_entropy_bits": safe_mean(ce_bits),
        "median_cross_entropy_bits": safe_median(ce_bits),
        "std_cross_entropy_bits": safe_stdev(ce_bits),
        "mean_tokens": safe_mean(tokens),
        "median_tokens": safe_median(tokens),
    }


def main():
    args = parse_args()
    summary_output = (
        Path(args.summary_output)
        if args.summary_output
        else Path(args.output).with_name(f"{Path(args.output).stem}_summary.csv")
    )

    metric = load_perplexity_metric()
    device = normalize_device(args.device)
    tokenizer = load_tokenizer(args.model_id)
    model_max_length = infer_model_max_length(tokenizer)
    model_type = f"hf-evaluate-perplexity::{args.model_id}"

    detail_fieldnames = [
        "sample_idx",
        "source",
        "model_type",
        "perplexity",
        "cross_entropy_bits",
        "cross_entropy_nats",
        "tokens",
        "raw_tokens",
        "truncated",
        "is_empty",
    ]
    summary_fieldnames = [
        "source",
        "model_type",
        "rows_total",
        "rows_scored",
        "rows_empty",
        "rows_truncated",
        "mean_perplexity",
        "median_perplexity",
        "std_perplexity",
        "mean_cross_entropy_bits",
        "median_cross_entropy_bits",
        "std_cross_entropy_bits",
        "mean_tokens",
        "median_tokens",
    ]

    summary_rows = []

    with open(args.output, "w", newline="", encoding="utf-8") as detail_f:
        detail_writer = csv.DictWriter(detail_f, fieldnames=detail_fieldnames)
        detail_writer.writeheader()

        for field in args.fields:
            label = source_label(field)
            print(f"\nScoring field '{field}' as source '{label}'")

            records = []
            nonempty_texts = []
            for sample_idx, text in tqdm(
                iter_jsonl_field(args.input, field, args.max_samples),
                desc=f"  [read {field}]",
            ):
                is_empty = not text.strip()
                record = {
                    "sample_idx": sample_idx,
                    "source": label,
                    "model_type": model_type,
                    "text": text,
                    "is_empty": is_empty,
                }
                records.append(record)
                if not is_empty:
                    nonempty_texts.append(text)

            if not records:
                continue

            token_stats = batched_token_stats(nonempty_texts, tokenizer, model_max_length)

            print(f"  [evaluate] model={args.model_id} device={device} snippets={len(nonempty_texts)}")
            metric_result = compute_perplexities(
                metric=metric,
                texts=nonempty_texts,
                model_id=args.model_id,
                batch_size=args.batch_size,
                add_start_token=args.add_start_token,
                device=device,
                max_length=args.max_length,
            )
            perplexities = metric_result["perplexities"]
            if len(perplexities) != len(nonempty_texts):
                raise RuntimeError(
                    f"Expected {len(nonempty_texts)} perplexity scores for field '{field}', "
                    f"got {len(perplexities)}."
                )

            scored_rows = []
            score_idx = 0
            for record in records:
                if record["is_empty"]:
                    row = {
                        "sample_idx": record["sample_idx"],
                        "source": record["source"],
                        "model_type": record["model_type"],
                        "perplexity": float("nan"),
                        "cross_entropy_bits": float("nan"),
                        "cross_entropy_nats": float("nan"),
                        "tokens": 0,
                        "raw_tokens": 0,
                        "truncated": False,
                        "is_empty": True,
                    }
                else:
                    ppl = float(perplexities[score_idx])
                    ce_nats = math.log(ppl)
                    ce_bits = ce_nats / math.log(2)
                    tok_info = token_stats[score_idx]
                    row = {
                        "sample_idx": record["sample_idx"],
                        "source": record["source"],
                        "model_type": record["model_type"],
                        "perplexity": ppl,
                        "cross_entropy_bits": ce_bits,
                        "cross_entropy_nats": ce_nats,
                        "tokens": tok_info["tokens_used"],
                        "raw_tokens": tok_info["raw_tokens"],
                        "truncated": tok_info["truncated"],
                        "is_empty": False,
                    }
                    score_idx += 1

                detail_writer.writerow(row)
                scored_rows.append(row)

            summary_rows.append(make_summary_row(label, model_type, scored_rows))

    with open(summary_output, "w", newline="", encoding="utf-8") as summary_f:
        summary_writer = csv.DictWriter(summary_f, fieldnames=summary_fieldnames)
        summary_writer.writeheader()
        for row in summary_rows:
            summary_writer.writerow(row)

    print(f"\nDetailed results written to: {args.output}")
    print(f"Summary results written to:  {summary_output}")
    if model_max_length is not None:
        print(f"Tokenizer/model max length used for truncation flagging: {model_max_length}")
    else:
        print("Tokenizer/model max length could not be inferred; truncation flags may be unavailable.")


if __name__ == "__main__":
    main()
