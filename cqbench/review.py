from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from .config import BENCHMARK_VERSION, SEED
from .io import read_jsonl, write_jsonl_atomic


REVIEW_FIELDS = (
    "specification_clear",
    "human_matches_signature",
    "human_nontrivial",
    "trigger_finding_valid",
    "missing_context_artifact",
)
VALID_LABELS = {"yes", "no", "uncertain"}


def _load_reviews(path: Path) -> dict[str, dict[str, Any]]:
    result = {}
    for row in read_jsonl(path):
        task_id = row.get("task_id")
        assert isinstance(task_id, str) and task_id
        assert task_id not in result, f"Duplicate review for {task_id}"
        for field in REVIEW_FIELDS:
            assert row.get(field) in VALID_LABELS, f"Invalid {field} for {task_id}"
        assert row.get("decision") in {"include", "exclude", "uncertain"}
        result[task_id] = row
    return result


def review_candidates(
    candidates_path: Path,
    output_path: Path,
    reviewer: str,
) -> None:
    candidates = list(read_jsonl(candidates_path))
    existing = _load_reviews(output_path) if output_path.exists() else {}
    rng = random.Random(SEED)
    author_aliases = {}
    for language in {row["language"] for row in candidates}:
        authors = sorted(
            author
            for author in next(
                row for row in candidates if row["language"] == language
            )["codes"]
            if author != "human"
        )
        shuffled = authors[:]
        rng.shuffle(shuffled)
        author_aliases[language] = dict(zip(authors, ("Model A", "Model B", "Model C")))

    rows = list(existing.values())
    for index, task in enumerate(candidates, 1):
        task_id = task["task_id"]
        if task_id in existing:
            continue
        print("\n" + "=" * 88)
        print(f"[{index}/{len(candidates)}] {task_id} | {task['stratum']}")
        print("\nPROMPT\n" + task["prompt"])
        print("\nHUMAN REFERENCE\n" + task["codes"]["human"])
        aliases = author_aliases[task["language"]]
        for author, alias in aliases.items():
            print(f"\n{alias} | structural={task['structures'][author]['status']}")
            print(task["codes"][author])
        print("\nSELECTION EVIDENCE")
        print(json.dumps(task["selection"], indent=2, ensure_ascii=False))
        answers: dict[str, str] = {}
        for field in REVIEW_FIELDS:
            while True:
                answer = input(f"{field} [y/n/u/q]: ").strip().lower()
                if answer == "q":
                    write_jsonl_atomic(output_path, rows, overwrite=True)
                    print(f"Saved {len(rows)} reviews to {output_path}")
                    return
                mapping = {"y": "yes", "n": "no", "u": "uncertain"}
                if answer in mapping:
                    answers[field] = mapping[answer]
                    break
        while True:
            answer = input("decision [i=include/e=exclude/u=uncertain]: ").strip().lower()
            if answer in {"i", "e", "u"}:
                decision = {"i": "include", "e": "exclude", "u": "uncertain"}[answer]
                break
        reason = input("reason/notes: ").strip()
        rows.append(
            {
                "benchmark_version": BENCHMARK_VERSION,
                "task_id": task_id,
                "reviewer": reviewer,
                **answers,
                "decision": decision,
                "reason": reason,
            }
        )
        write_jsonl_atomic(output_path, rows, overwrite=True)
    print(f"Completed {len(rows)} reviews in {output_path}")


def _cohen_kappa(left: list[str], right: list[str]) -> float | None:
    assert len(left) == len(right)
    if not left:
        return None
    labels = sorted(set(left) | set(right))
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        left_counts[label] / len(left) * right_counts[label] / len(right)
        for label in labels
    )
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


def agreement(left_path: Path, right_path: Path) -> dict[str, Any]:
    left, right = _load_reviews(left_path), _load_reviews(right_path)
    common = sorted(set(left) & set(right))
    report: dict[str, Any] = {
        "left_count": len(left),
        "right_count": len(right),
        "common_count": len(common),
        "fields": {},
    }
    for field in (*REVIEW_FIELDS, "decision"):
        a = [left[key][field] for key in common]
        b = [right[key][field] for key in common]
        report["fields"][field] = {
            "agreement": sum(x == y for x, y in zip(a, b)) / len(common)
            if common
            else None,
            "kappa": _cohen_kappa(a, b),
        }
    report["disagreements"] = [
        key
        for key in common
        if any(left[key][field] != right[key][field] for field in (*REVIEW_FIELDS, "decision"))
    ]
    return report


def write_adjudication_template(
    left_path: Path,
    right_path: Path,
    output_path: Path,
    *,
    overwrite: bool = False,
) -> int:
    left, right = _load_reviews(left_path), _load_reviews(right_path)
    report = agreement(left_path, right_path)
    rows = []
    for key in report["disagreements"]:
        rows.append(
            {
                "task_id": key,
                "reviewer_left": left[key],
                "reviewer_right": right[key],
                "decision": "uncertain",
                "reason": "",
            }
        )
    return write_jsonl_atomic(output_path, rows, overwrite=overwrite)

