from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import numpy as np

from .config import BENCHMARK_VERSION, LANGUAGES, ODC_COLUMNS, ODC_LABELS, ROOT, SEED
from .io import read_jsonl, sha256_file, sha256_text, write_json_atomic, write_jsonl_atomic
from .legacy import cwes_from_raw, load_raw_vulnerabilities
from .structural import analyze_structure, canonical_prompt, extract_signature


DEFAULT_DIFFICULTY_THRESHOLD = 3
MINIMUM_BENCHMARK_SIZE = 15_000


def _stable_value(value: str) -> int:
    digest = hashlib.sha256(f"{SEED}:{value}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _difficulty_evidence(
    language: str,
    threshold: int,
) -> tuple[dict[str, dict[str, Any]], int]:
    specification = LANGUAGES[language]
    metrics = [
        "nloc",
        "halstead_v",
        "defects_total",
        "vulns_total",
        "vulns_high_sev",
        *ODC_COLUMNS,
    ]
    frame = pd.read_parquet(
        specification.table,
        columns=["hm_index", "author", *metrics],
    )
    assert not frame.duplicated(["hm_index", "author"]).any()
    pivot = frame.pivot(index="hm_index", columns="author", values=metrics)
    required = [
        (metric, author)
        for metric in metrics
        for author in specification.authors
    ]
    pivot = pivot.dropna(subset=required)
    models = list(specification.model_fields)
    model_issue_counts = pd.concat(
        {
            author: (
                pivot[("defects_total", author)]
                + pivot[("vulns_total", author)]
            ).astype(int)
            for author in models
        },
        axis=1,
    )
    complexity_qualified = pd.concat(
        {
            author: (
                (
                    pivot[("nloc", author)]
                    / pivot[("nloc", "human")]
                ).ge(0.10)
                | (
                    pivot[("halstead_v", author)]
                    / pivot[("halstead_v", "human")]
                ).ge(0.10)
            )
            for author in models
        },
        axis=1,
    )
    qualified_counts = model_issue_counts.where(complexity_qualified, -1)
    scores = pd.Series(
        np.sort(qualified_counts.to_numpy(), axis=1)[:, -2],
        index=pivot.index,
    ).astype(int)
    difficulty_qualified = (
        complexity_qualified & model_issue_counts.ge(threshold)
    )
    consensus_odc_mask = pd.concat(
        {
            column: sum(
                (
                    pivot[(column, author)].gt(0)
                    & difficulty_qualified[author]
                ).astype(int)
                for author in models
            ).ge(2)
            for column in ODC_COLUMNS
        },
        axis=1,
    )
    potential_cwe = sum(
        (
            pivot[("vulns_total", author)].gt(0)
            & difficulty_qualified[author]
        ).astype(int)
        for author in models
    ).ge(2)
    complete_count = len(pivot)
    prefilter = scores.ge(threshold) & (
        consensus_odc_mask.any(axis=1) | potential_cwe
    )
    pivot = pivot.loc[prefilter]
    complexity_qualified = complexity_qualified.loc[prefilter]
    difficulty_qualified = difficulty_qualified.loc[prefilter]
    scores = scores.loc[prefilter]
    potential_cwe = potential_cwe.loc[prefilter]
    output: dict[str, dict[str, Any]] = {}
    for source_id, row in pivot.iterrows():
        issue_counts = {
            author: int(
                row[("defects_total", author)] + row[("vulns_total", author)]
            )
            for author in models
        }
        qualified = {
            author: bool(complexity_qualified.loc[source_id, author])
            for author in models
        }
        difficulty_models = {
            author: bool(difficulty_qualified.loc[source_id, author])
            for author in models
        }
        consensus_burden = int(scores.loc[source_id])
        high_models = sum(
            int(row[("vulns_high_sev", author)] > 0 and qualified[author])
            for author in models
        )
        vulnerable_models = sum(
            int(row[("vulns_total", author)] > 0 and qualified[author])
            for author in models
        )
        affected_models = sum(
            issue_counts[author] > 0 and qualified[author] for author in models
        )
        consensus_odc = [
            column
            for column in ODC_COLUMNS
            if sum(
                int(row[(column, author)] > 0 and difficulty_models[author])
                for author in models
            )
            >= 2
        ]
        output[str(source_id)] = {
            "score": consensus_burden,
            "consensus_model_finding_burden": consensus_burden,
            "model_issue_counts": issue_counts,
            "complexity_qualified_models": qualified,
            "difficulty_qualified_models": difficulty_models,
            "complexity_ratios": {
                author: {
                    "nloc": float(
                        row[("nloc", author)] / row[("nloc", "human")]
                    ),
                    "halstead_v": float(
                        row[("halstead_v", author)]
                        / row[("halstead_v", "human")]
                    ),
                }
                for author in models
            },
            "affected_models": int(affected_models),
            "vulnerable_models": int(vulnerable_models),
            "high_severity_models": int(high_models),
            "consensus_odc": [ODC_LABELS[column] for column in consensus_odc],
            "consensus_cwes": [],
            "potential_cwe_consensus": bool(potential_cwe.loc[source_id]),
            "odc_by_author": {
                author: {
                    ODC_LABELS[column]: int(row[(column, author)])
                    for column in ODC_COLUMNS
                    if int(row[(column, author)]) > 0
                }
                for author in specification.authors
            },
            "human_defects_total": int(row[("defects_total", "human")]),
            "human_vulns_total": int(row[("vulns_total", "human")]),
            "human_complexity": {
                "nloc": float(row[("nloc", "human")]),
                "halstead_v": float(row[("halstead_v", "human")]),
            },
        }
    return output, complete_count


def _profile(evidence: Mapping[str, Any]) -> str:
    if evidence["consensus_cwes"] and evidence["consensus_odc"]:
        return "mixed_consensus"
    if evidence["consensus_cwes"]:
        return "vulnerability_consensus"
    assert evidence["consensus_odc"]
    return "defect_consensus"


def _build_language(
    language: str,
    threshold: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    specification = LANGUAGES[language]
    evidence, complete_count = _difficulty_evidence(language, threshold)
    cwe_keys = [
        source_id
        for source_id, values in evidence.items()
        if values["potential_cwe_consensus"]
    ]
    if cwe_keys:
        raw_vulnerabilities = load_raw_vulnerabilities(
            language,
            specification.authors,
            cwe_keys,
        )
        models = list(specification.model_fields)
        for source_id in cwe_keys:
            counts: Counter[str] = Counter()
            for author in models:
                if not evidence[source_id]["difficulty_qualified_models"][author]:
                    continue
                counts.update(
                    cwes_from_raw(raw_vulnerabilities[(author, source_id)])
                )
            evidence[source_id]["consensus_cwes"] = sorted(
                cwe for cwe, count in counts.items() if count >= 2
            )
    eligible = {
        source_id
        for source_id, values in evidence.items()
        if values["consensus_odc"] or values["consensus_cwes"]
    }
    records: list[dict[str, Any]] = []
    seen_content: set[str] = set()
    drops: Counter[str] = Counter()
    found: set[str] = set()
    for source in read_jsonl(specification.dataset):
        source_id = str(source.get(specification.source_key) or "")
        if source_id not in eligible:
            continue
        found.add(source_id)
        docstring = str(source.get("docstring") or "").strip()
        human_code = str(source.get(specification.human_field) or "")
        if not docstring or not human_code.strip():
            drops["missing_prompt_or_human"] += 1
            continue
        try:
            signature = extract_signature(human_code, language)
            human_structure = analyze_structure(human_code, language, signature)
        except Exception:
            drops["signature_or_parse_failure"] += 1
            continue
        if not human_structure.strict_nontrivial:
            drops["human_not_strict_nontrivial"] += 1
            continue
        content = f"{signature.text}\n{docstring}\n{human_code}"
        content_hash = sha256_text(content)
        if content_hash in seen_content:
            drops["exact_duplicate"] += 1
            continue
        seen_content.add(content_hash)
        codes = {"human": human_code}
        for author, field in specification.model_fields.items():
            codes[author] = str(source.get(field) or "")
        task_id = f"{language}:{source_id}"
        records.append(
            {
                "benchmark_version": BENCHMARK_VERSION,
                "task_id": task_id,
                "language": language,
                "source_id": source_id,
                "stratum": _profile(evidence[source_id]),
                "difficulty": evidence[source_id],
                "docstring": docstring,
                "signature": {
                    "text": signature.text,
                    "name": signature.name,
                    "arity": signature.arity,
                },
                "prompt": canonical_prompt(language, signature, docstring),
                "human_metrics": human_structure.to_dict(),
                "human_complexity": evidence[source_id]["human_complexity"],
                "codes": codes,
                "content_sha256": content_hash,
            }
        )
    drops["eligible_missing_from_dataset"] = len(eligible - found)
    counts = {
        "complete_source_tasks": complete_count,
        "score_at_or_above_threshold": len(eligible),
        "threshold_prefilter_before_type_consensus": len(evidence),
        "dropped_without_repeated_odc_or_cwe": len(evidence) - len(eligible),
        "retained": len(records),
        **dict(sorted(drops.items())),
    }
    return sorted(records, key=lambda row: row["task_id"]), counts


def _audit_sample(
    records: list[dict[str, Any]],
    threshold: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for language in ("python", "java", "c"):
        language_rows = sorted(
            (row for row in records if row["language"] == language),
            key=lambda row: (row["difficulty"]["score"], row["task_id"]),
        )
        assert len(language_rows) >= 50
        for quintile in range(5):
            start = quintile * len(language_rows) // 5
            stop = (quintile + 1) * len(language_rows) // 5
            pool = language_rows[start:stop]
            chosen = sorted(
                pool,
                key=lambda row: _stable_value(row["task_id"]),
            )[:10]
            for row in chosen:
                row = dict(row)
                row["audit_quintile"] = quintile + 1
                selected.append(row)
    assert len(selected) == 150

    enriched: list[dict[str, Any]] = []
    by_language = {
        language: [row for row in selected if row["language"] == language]
        for language in ("python", "java", "c")
    }
    for language, rows in by_language.items():
        specification = LANGUAGES[language]
        keys = [row["source_id"] for row in rows]
        raw_vulnerabilities = load_raw_vulnerabilities(
            language,
            specification.authors,
            keys,
        )
        for row in rows:
            signature = extract_signature(row["codes"]["human"], language)
            structures = {
                author: analyze_structure(
                    code,
                    language,
                    signature,
                    human_token_count=row["human_metrics"]["token_count"],
                    human_ast_count=row["human_metrics"]["ast_node_count"],
                ).to_dict()
                for author, code in row["codes"].items()
            }
            selection = {
                **row["difficulty"],
                "difficulty_threshold": threshold,
                "difficulty_quintile": row["audit_quintile"],
                "cwe_by_author": {
                    author: sorted(
                        cwes_from_raw(
                            raw_vulnerabilities[(author, row["source_id"])]
                        )
                    )
                    for author in specification.authors
                },
            }
            enriched.append(
                {
                    key: row[key]
                    for key in (
                        "benchmark_version",
                        "task_id",
                        "language",
                        "source_id",
                        "stratum",
                        "docstring",
                        "signature",
                        "prompt",
                        "codes",
                        "content_sha256",
                    )
                }
                | {
                    "selection": selection,
                    "structures": structures,
                    "audit_quintile": row["audit_quintile"],
                }
            )
    return sorted(enriched, key=lambda row: row["task_id"])


def build_large_benchmark(
    output_dir: Path,
    *,
    threshold: int = DEFAULT_DIFFICULTY_THRESHOLD,
    overwrite: bool = False,
) -> dict[str, Any]:
    assert threshold >= 1
    records: list[dict[str, Any]] = []
    drop_counts = {}
    for language in ("python", "java", "c"):
        language_records, language_counts = _build_language(language, threshold)
        records.extend(language_records)
        drop_counts[language] = language_counts
    assert len(records) >= MINIMUM_BENCHMARK_SIZE, (
        f"Difficulty threshold {threshold} retained only {len(records)} tasks"
    )
    assert len({row["task_id"] for row in records}) == len(records)

    tasks = [
        {
            key: row[key]
            for key in (
                "benchmark_version",
                "task_id",
                "language",
                "source_id",
                "stratum",
                "difficulty",
                "docstring",
                "signature",
                "prompt",
            )
        }
        for row in records
    ]
    references = [
        {
            "task_id": row["task_id"],
            "human_metrics": row["human_metrics"],
            "human_complexity": row["human_complexity"],
            "content_sha256": row["content_sha256"],
        }
        for row in records
    ]
    counts = {
        "tasks": write_jsonl_atomic(
            output_dir / "tasks.jsonl", tasks, overwrite=overwrite
        ),
        "references": write_jsonl_atomic(
            output_dir / "references.jsonl", references, overwrite=overwrite
        ),
    }
    all_authors = ("human", "chatgpt", "gptoss", "dsc", "qwen")
    for author in all_authors:
        rows = [
            {"task_id": row["task_id"], "code": row["codes"][author]}
            for row in records
            if author in row["codes"]
        ]
        if rows:
            counts[author] = write_jsonl_atomic(
                output_dir / "baselines" / f"{author}.jsonl",
                rows,
                overwrite=overwrite,
            )
    openai = [
        {
            "task_id": row["task_id"],
            "code": row["codes"][
                "gptoss" if row["language"] == "c" else "chatgpt"
            ],
        }
        for row in records
    ]
    counts["openai"] = write_jsonl_atomic(
        output_dir / "baselines/openai.jsonl",
        openai,
        overwrite=overwrite,
    )
    audit = _audit_sample(records, threshold)
    counts["manual_audit_candidates"] = write_jsonl_atomic(
        output_dir / "manual_audit/candidates.jsonl",
        audit,
        overwrite=overwrite,
    )

    artifact_paths = {
        "tasks": output_dir / "tasks.jsonl",
        "references": output_dir / "references.jsonl",
        "manual_audit_candidates": output_dir / "manual_audit/candidates.jsonl",
        **{
            f"baseline_{author}": output_dir / "baselines" / f"{author}.jsonl"
            for author in (*all_authors, "openai")
            if (output_dir / "baselines" / f"{author}.jsonl").exists()
        },
    }
    semgrep_manifest = json.loads(
        (ROOT / "cqbench/rules/manifest.json").read_text(encoding="utf-8")
    )
    manifest = {
        "benchmark_version": BENCHMARK_VERSION,
        "release_profile": "large-issue-prone-challenge-set",
        "selection_status": "automated-threshold",
        "manual_validation_status": "pending",
        "seed": SEED,
        "task_count": len(records),
        "minimum_required_task_count": MINIMUM_BENCHMARK_SIZE,
        "difficulty_definition": {
            "formula": (
                "second_highest_complexity_qualified_model("
                "defects_total + vulns_total) >= threshold"
            ),
            "threshold": threshold,
            "rationale": (
                "At least two non-degenerate model outputs each have at least "
                "three findings and share an ODC type or CWE."
            ),
        },
        "complexity_gate": {
            "formula": (
                "generated_nloc / human_nloc >= 0.10 OR "
                "generated_halstead_v / human_halstead_v >= 0.10"
            ),
            "ratio_threshold": 0.10,
        },
        "finding_type_gate": (
            "same ODC type or normalized CWE present in at least two "
            "complexity-qualified model outputs with at least threshold findings"
        ),
        "language_counts": dict(Counter(row["language"] for row in records)),
        "profile_counts": dict(Counter(row["stratum"] for row in records)),
        "drop_counts": drop_counts,
        "manual_audit": {
            "count": len(audit),
            "design": "10 seeded tasks per within-language difficulty quintile",
            "language_counts": dict(Counter(row["language"] for row in audit)),
        },
        "analysis_profile": {
            "pylint": "3.3.6",
            "pmd": "7.11.0",
            "clang_tidy": "18",
            "semgrep": semgrep_manifest["semgrep_version"],
            "semgrep_rule_count": semgrep_manifest["rule_count"],
            "semgrep_rules_sha256": semgrep_manifest["sha256"],
        },
        "artifacts": {
            name: {
                "path": str(path.relative_to(output_dir)),
                "rows": counts[
                    name.removeprefix("baseline_")
                    if name.startswith("baseline_")
                    else name
                ],
                "sha256": sha256_file(path),
            }
            for name, path in artifact_paths.items()
        },
    }
    write_json_atomic(
        output_dir / "manifest.json",
        manifest,
        overwrite=overwrite,
    )
    return manifest


def audit_large_benchmark(output_dir: Path) -> dict[str, Any]:
    manifest = json.loads(
        (output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    tasks = list(read_jsonl(output_dir / "tasks.jsonl"))
    references = list(read_jsonl(output_dir / "references.jsonl"))
    task_ids = [row["task_id"] for row in tasks]
    assert len(tasks) == manifest["task_count"]
    assert len(tasks) >= manifest["minimum_required_task_count"]
    assert len(task_ids) == len(set(task_ids))
    assert len(references) == len(tasks)
    assert {row["task_id"] for row in references} == set(task_ids)
    threshold = manifest["difficulty_definition"]["threshold"]
    assert all(row["difficulty"]["score"] >= threshold for row in tasks)
    assert all(
        row["difficulty"]["consensus_odc"]
        or row["difficulty"]["consensus_cwes"]
        for row in tasks
    )
    assert all(
        sum(
            row["difficulty"]["complexity_qualified_models"][author]
            and row["difficulty"]["model_issue_counts"][author] >= threshold
            for author in row["difficulty"]["model_issue_counts"]
        )
        >= 2
        for row in tasks
    )
    assert all(
        isinstance(row.get("human_complexity"), dict)
        for row in references
    )
    expected_ids = set(task_ids)
    language_ids = {
        language: {
            row["task_id"] for row in tasks if row["language"] == language
        }
        for language in ("python", "java", "c")
    }
    coverage = {}
    for author, expected in {
        "human": expected_ids,
        "dsc": expected_ids,
        "qwen": expected_ids,
        "openai": expected_ids,
        "chatgpt": language_ids["python"] | language_ids["java"],
        "gptoss": language_ids["c"],
    }.items():
        rows = list(read_jsonl(output_dir / "baselines" / f"{author}.jsonl"))
        ids = [row["task_id"] for row in rows]
        assert len(ids) == len(set(ids))
        assert set(ids) == expected
        coverage[author] = len(ids)
    audit = list(read_jsonl(output_dir / "manual_audit/candidates.jsonl"))
    assert len(audit) == 150
    assert set(row["task_id"] for row in audit) <= expected_ids
    audit_cells = Counter(
        (row["language"], row["audit_quintile"]) for row in audit
    )
    assert all(
        audit_cells[(language, quintile)] == 10
        for language in ("python", "java", "c")
        for quintile in range(1, 6)
    )
    for artifact in manifest["artifacts"].values():
        path = output_dir / artifact["path"]
        assert sha256_file(path) == artifact["sha256"]
    assert sha256_file(ROOT / "cqbench/rules/semgrep.json") == manifest[
        "analysis_profile"
    ]["semgrep_rules_sha256"]
    return {
        "benchmark_version": manifest["benchmark_version"],
        "release_profile": manifest["release_profile"],
        "task_count": len(tasks),
        "threshold": threshold,
        "language_counts": dict(Counter(row["language"] for row in tasks)),
        "profile_counts": dict(Counter(row["stratum"] for row in tasks)),
        "baseline_coverage": coverage,
        "manual_audit_count": len(audit),
        "manual_audit_cells": len(audit_cells),
        "hashes_valid": True,
    }
