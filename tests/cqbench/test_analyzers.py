from pathlib import Path

from cqbench.analyzers import analyze_pylint, analyze_semgrep


def test_pylint_uses_odc_mapping_and_exclusions():
    result = analyze_pylint("def example(unused):\n    return 1\n")
    assert result["defects_total"] >= 1
    assert result["def_assignment"] >= 1
    assert all(
        finding.get("symbol") != "missing-function-docstring"
        for finding in result["defect_findings"]
    )


def test_semgrep_keeps_cwe_and_high_severity():
    rules = Path(__file__).parent / "fixtures/semgrep-test.yml"
    result = analyze_semgrep(
        "def example(value):\n    return eval(value)\n",
        "python",
        rules,
    )
    assert result["vulns_total"] == 1
    assert result["vulns_high_sev"] == 1
    assert result["cwes"] == ["CWE-95"]
