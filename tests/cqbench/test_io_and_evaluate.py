import json
from pathlib import Path

import pytest

from cqbench.evaluate import _complexity_gate, evaluate, validate_submission
from cqbench.historical import subset_results
from cqbench.io import read_jsonl, write_jsonl_atomic
from cqbench.structural import analyze_structure, extract_signature


def _write(path: Path, rows):
    write_jsonl_atomic(path, rows)


def _fixture(tmp_path: Path):
    human = "def increment(value):\n    return value + 1\n"
    signature = extract_signature(human, "python")
    structure = analyze_structure(human, "python", signature)
    tasks = tmp_path / "tasks.jsonl"
    references = tmp_path / "references.jsonl"
    _write(
        tasks,
        [
            {
                "benchmark_version": "cqbench-v1",
                "task_id": "python:test",
                "language": "python",
                "source_id": "test",
                "stratum": "clean_control",
                "docstring": "Increment the value.",
                "signature": {
                    "text": signature.text,
                    "name": signature.name,
                    "arity": signature.arity,
                },
                "prompt": "Implement increment.",
            }
        ],
    )
    _write(
        references,
        [
            {
                "task_id": "python:test",
                "human_metrics": structure.to_dict(),
                "content_sha256": "x",
            }
        ],
    )
    return tasks, references


def test_structural_only_evaluation(tmp_path):
    tasks, references = _fixture(tmp_path)
    predictions = tmp_path / "predictions.jsonl"
    results = tmp_path / "results.jsonl"
    _write(
        predictions,
        [{"task_id": "python:test", "code": "def increment(value):\n    return value + 2\n"}],
    )
    assert evaluate(
        tasks,
        references,
        predictions,
        results,
        structural_only=True,
    ) == 1
    row = list(read_jsonl(results))[0]
    assert row["strict_nontrivial"]
    assert row["static_analysis_status"] == "skipped"
    assert row["complexity"]["function_count_detected"] == 1


def test_submission_rejects_duplicate_and_unknown(tmp_path):
    tasks, _ = _fixture(tmp_path)
    duplicate = tmp_path / "duplicate.jsonl"
    _write(
        duplicate,
        [
            {"task_id": "python:test", "code": "x"},
            {"task_id": "python:test", "code": "y"},
        ],
    )
    with pytest.raises(AssertionError, match="Duplicate"):
        validate_submission(tasks, duplicate)
    unknown = tmp_path / "unknown.jsonl"
    _write(unknown, [{"task_id": "python:unknown", "code": "x"}])
    with pytest.raises(AssertionError, match="Unknown"):
        validate_submission(tasks, unknown)


def test_subset_results_uses_task_ids_and_task_order(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    results = tmp_path / "results.jsonl"
    output = tmp_path / "subset.jsonl"
    _write(tasks, [{"task_id": "b"}, {"task_id": "a"}])
    _write(
        results,
        [{"task_id": "a", "value": 1}, {"task_id": "b", "value": 2}],
    )
    assert subset_results(tasks, results, output) == 2
    assert [row["task_id"] for row in read_jsonl(output)] == ["b", "a"]


def test_complexity_gate_rejects_reference_relative_degenerate_output():
    human = {"nloc": 100.0, "halstead_v": 1000.0}
    rejected = _complexity_gate(
        {"nloc_mean": 5.0, "halstead_volume_mean": 50.0},
        human,
    )
    accepted = _complexity_gate(
        {"nloc_mean": 5.0, "halstead_volume_mean": 150.0},
        human,
    )
    assert rejected["complexity_non_degenerate"] is False
    assert accepted["complexity_non_degenerate"] is True
