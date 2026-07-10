"""
Sample stratified subsets of HMCorp Python and Java for the gpt-oss vs ChatGPT
calibration study (paper Section 5.2).

Sampling design:
  - For each language, draw N_PER_LANG samples stratified by human-code NLOC
    into four bins: [1,15), [15,40), [40,80), [80, inf).
  - Equal allocation per bin (N_PER_LANG / 4 from each).
  - If a bin has fewer rows than the per-bin quota, take all of them and
    redistribute the deficit across the other bins proportionally.
  - Random seed fixed for reproducibility.

Output:
  Two JSONL files, one per language, with the same schema as the input:
    {
      "hm_index": ...,
      "docstring": ...,
      "human_code": ...,
      "chatgpt_code": ...,
      "dsc_code": ..., "qwen_code": ...   # passed through if present
    }

Usage:
  python3 sample_calibration_subset.py \\
      --python-input  ../1_Dataset/python_dataset_nodocs_dsc_qwen_FINAL.jsonl \\
      --java-input    ../1_Dataset/java_dataset_nodocs_dsc_qwen_FINAL.jsonl \\
      --python-output calibration_python_1000.jsonl \\
      --java-output   calibration_java_1000.jsonl \\
      --n-per-lang    1000 \\
      --seed          42
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


# Stratification bins on human-code NLOC (line count, comments and blanks excluded).
# Tweak if your population is shifted.
NLOC_BINS = [(1, 15), (15, 40), (40, 80), (80, float("inf"))]


def count_nloc(code: str) -> int:
    """Lightweight NLOC counter: non-empty, non-comment lines.

    For calibration sampling, we don't need lizard's structural NLOC -- a
    cheap line-count is enough to bin samples by length. Comments are stripped
    by a simple heuristic that works for Python (#) and Java (// and /* */).
    """
    if not code:
        return 0
    lines = code.split("\n")
    count = 0
    in_block = False
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if in_block:
            if "*/" in s:
                in_block = False
            continue
        if s.startswith("/*"):
            if "*/" not in s:
                in_block = True
            continue
        if s.startswith("//") or s.startswith("#"):
            continue
        count += 1
    return count


def assign_bin(nloc: int) -> int:
    for i, (lo, hi) in enumerate(NLOC_BINS):
        if lo <= nloc < hi:
            return i
    return len(NLOC_BINS) - 1  # fallback to top bin


def load_rows(path: Path) -> list[dict]:
    """Load JSONL rows that have all the fields we need for calibration."""
    rows = []
    skipped_no_chatgpt = 0
    skipped_no_human = 0
    skipped_no_doc = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if not d.get("human_code"):
                skipped_no_human += 1
                continue
            if not d.get("chatgpt_code"):
                skipped_no_chatgpt += 1
                continue
            if not (d.get("docstring") or "").strip():
                skipped_no_doc += 1
                continue
            rows.append(d)
    print(f"  Loaded {len(rows)} usable rows from {path}")
    if skipped_no_human or skipped_no_chatgpt or skipped_no_doc:
        print(f"    (skipped: no human={skipped_no_human}, "
              f"no chatgpt={skipped_no_chatgpt}, "
              f"no docstring={skipped_no_doc})")
    return rows


def stratified_sample(rows: list[dict], n_target: int, rng: random.Random) -> list[dict]:
    """Stratified sample by human-code NLOC bin, with deficit redistribution."""
    by_bin: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        b = assign_bin(count_nloc(r["human_code"]))
        by_bin[b].append(r)

    n_bins = len(NLOC_BINS)
    base_quota = n_target // n_bins
    quotas = [base_quota] * n_bins
    # Distribute remainder across the largest bins first
    remainder = n_target - sum(quotas)
    sorted_bins = sorted(range(n_bins), key=lambda i: -len(by_bin[i]))
    for i in range(remainder):
        quotas[sorted_bins[i % n_bins]] += 1

    # Two-pass deficit redistribution: any bin too small gives its deficit
    # back to the global pool, redistributed proportionally to bins with surplus
    deficits = 0
    sampled_per_bin: dict[int, list[dict]] = {}
    for b in range(n_bins):
        avail = len(by_bin[b])
        if avail <= quotas[b]:
            sampled_per_bin[b] = list(by_bin[b])
            deficits += quotas[b] - avail
        else:
            sampled_per_bin[b] = rng.sample(by_bin[b], quotas[b])

    if deficits > 0:
        # Bins with leftover capacity
        leftover = []
        for b in range(n_bins):
            unused = [r for r in by_bin[b] if r not in sampled_per_bin[b]]
            leftover.append(unused)
        # Allocate the deficit across bins proportionally to remaining capacity
        total_leftover = sum(len(l) for l in leftover)
        if total_leftover == 0:
            print(f"  Warning: cannot fill deficit of {deficits} -- not enough rows.")
        else:
            extra_quotas = [
                round(deficits * len(l) / total_leftover) for l in leftover
            ]
            # Fix rounding so it sums to deficits
            diff = deficits - sum(extra_quotas)
            for i in range(abs(diff)):
                idx = sorted(
                    range(n_bins), key=lambda b: -len(leftover[b])
                )[i % n_bins]
                extra_quotas[idx] += 1 if diff > 0 else -1
            for b in range(n_bins):
                k = min(extra_quotas[b], len(leftover[b]))
                if k > 0:
                    sampled_per_bin[b].extend(rng.sample(leftover[b], k))

    out = []
    for b in range(n_bins):
        out.extend(sampled_per_bin[b])
    rng.shuffle(out)

    print(f"  Bin allocation:")
    for b, (lo, hi) in enumerate(NLOC_BINS):
        hi_str = "inf" if hi == float("inf") else str(hi)
        n_in_bin = len([r for r in out if assign_bin(count_nloc(r["human_code"])) == b])
        n_avail = len(by_bin[b])
        print(f"    [{lo:>3}, {hi_str:>3}): sampled {n_in_bin:>4} / available {n_avail:>6}")
    print(f"  Total sampled: {len(out)}")
    return out


def write_subset(rows: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"  Wrote {len(rows)} rows to {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Sample stratified Python+Java subsets for the gpt-oss vs ChatGPT calibration study."
    )
    parser.add_argument("--python-input", required=True)
    parser.add_argument("--java-input",   required=True)
    parser.add_argument("--python-output", required=True)
    parser.add_argument("--java-output",   required=True)
    parser.add_argument("--n-per-lang", type=int, default=1000,
                        help="Target sample size per language (default 1000)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)

    print(f"\n=== Python ===")
    py_rows = load_rows(Path(args.python_input))
    py_sample = stratified_sample(py_rows, args.n_per_lang, rng)
    write_subset(py_sample, Path(args.python_output))

    print(f"\n=== Java ===")
    java_rows = load_rows(Path(args.java_input))
    java_sample = stratified_sample(java_rows, args.n_per_lang, rng)
    write_subset(java_sample, Path(args.java_output))

    print("\nDone.")


if __name__ == "__main__":
    main()