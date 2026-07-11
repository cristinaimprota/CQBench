#!/usr/bin/env python3
"""Run `cqbench evaluate` with a live progress bar.

The core evaluator writes its output atomically at the end, so a long run shows
no progress. This wrapper splits the submission into shards, evaluates each with
the real evaluator (identical results), and prints a bar with elapsed time / ETA.
Shard outputs are concatenated back in the original task order.

Usage (from the repository root):

  python tools/evaluate_with_progress.py \
    --tasks runs/claude-opus-4-8/subset_tasks.jsonl \
    --references runs/claude-opus-4-8/subset_refs.jsonl \
    --predictions runs/claude-opus-4-8/predictions.jsonl \
    --output runs/claude-opus-4-8/results.jsonl \
    --shards 30

Add --structural-only to skip the analyzers. Full analyzer runs need pylint,
PMD, clang-tidy, and semgrep on PATH.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

# Ensure the package is importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cqbench.evaluate import evaluate  # noqa: E402
from cqbench.io import read_jsonl, write_jsonl_atomic  # noqa: E402


def _fmt(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def _bar(done: int, total: int, elapsed: float, width: int = 32) -> str:
    frac = done / total if total else 1.0
    filled = int(round(frac * width))
    eta = (elapsed / done * (total - done)) if done else 0.0
    return (
        f"\r[{'#' * filled}{'-' * (width - filled)}] "
        f"{frac * 100:5.1f}%  {done}/{total} tasks  "
        f"elapsed {_fmt(elapsed)}  ETA {_fmt(eta)}   "
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="cqbench evaluate with a progress bar")
    ap.add_argument("--tasks", type=Path, required=True)
    ap.add_argument("--references", type=Path, required=True)
    ap.add_argument("--predictions", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--rules", type=Path)
    ap.add_argument("--structural-only", action="store_true")
    ap.add_argument("--shards", type=int, default=30,
                    help="number of shards; more = finer progress (default 30)")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    if args.output.exists() and not args.overwrite:
        sys.exit(f"Refusing to overwrite {args.output} (pass --overwrite)")

    tasks = list(read_jsonl(args.tasks))
    references = {r["task_id"]: r for r in read_jsonl(args.references)}
    preds = {r["task_id"]: r for r in read_jsonl(args.predictions)}
    order = [t["task_id"] for t in tasks]
    n = len(tasks)
    shards = max(1, min(args.shards, n))
    print(f"Evaluating {n} tasks in {shards} shards "
          f"({'structural-only' if args.structural_only else 'full analyzers'})",
          file=sys.stderr)

    results_by_id: dict[str, dict] = {}
    start = time.monotonic()
    done = 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for si in range(shards):
            lo = si * n // shards
            hi = (si + 1) * n // shards
            if lo == hi:
                continue
            chunk_tasks = tasks[lo:hi]
            ids = [t["task_id"] for t in chunk_tasks]
            t_path = tmp / "t.jsonl"
            r_path = tmp / "r.jsonl"
            p_path = tmp / "p.jsonl"
            o_path = tmp / "o.jsonl"
            write_jsonl_atomic(t_path, chunk_tasks, overwrite=True)
            write_jsonl_atomic(r_path, [references[i] for i in ids], overwrite=True)
            write_jsonl_atomic(
                p_path, [preds[i] for i in ids if i in preds], overwrite=True
            )
            evaluate(
                t_path, r_path, p_path, o_path,
                rules_path=args.rules,
                structural_only=args.structural_only,
                overwrite=True,
            )
            for row in read_jsonl(o_path):
                results_by_id[row["task_id"]] = row
            done = hi
            sys.stderr.write(_bar(done, n, time.monotonic() - start))
            sys.stderr.flush()
    sys.stderr.write("\n")

    ordered = [results_by_id[i] for i in order]
    assert len(ordered) == n
    write_jsonl_atomic(args.output, ordered, overwrite=args.overwrite)
    print(f"Wrote {len(ordered)} results to {args.output} "
          f"in {_fmt(time.monotonic() - start)}", file=sys.stderr)


if __name__ == "__main__":
    main()
