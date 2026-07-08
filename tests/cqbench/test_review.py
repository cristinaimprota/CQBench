from cqbench.io import write_jsonl_atomic
from cqbench.review import (
    agreement,
    write_adjudication_template,
)


def _review(task_id, reviewer, decision="include", finding="yes"):
    return {
        "benchmark_version": "cqbench-v1",
        "task_id": task_id,
        "reviewer": reviewer,
        "specification_clear": "yes",
        "human_matches_signature": "yes",
        "human_nontrivial": "yes",
        "trigger_finding_valid": finding,
        "missing_context_artifact": "no",
        "decision": decision,
        "reason": "",
    }


def test_agreement_and_adjudication_template(tmp_path):
    left, right = tmp_path / "left.jsonl", tmp_path / "right.jsonl"
    write_jsonl_atomic(left, [_review("python:a", "left"), _review("python:b", "left")])
    write_jsonl_atomic(
        right,
        [
            _review("python:a", "right"),
            _review("python:b", "right", decision="exclude", finding="no"),
        ],
    )
    report = agreement(left, right)
    assert report["common_count"] == 2
    assert report["disagreements"] == ["python:b"]
    output = tmp_path / "adjudications.jsonl"
    assert write_adjudication_template(left, right, output) == 1

