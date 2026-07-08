from cqbench.structural import analyze_structure, extract_signature


def test_python_structural_states():
    human = "def increment(value):\n    return value + 1\n"
    signature = extract_signature(human, "python")
    reference = analyze_structure(human, "python", signature)
    assert reference.strict_nontrivial
    stub = analyze_structure(
        "def increment(value):\n    pass\n",
        "python",
        signature,
        human_token_count=reference.token_count,
        human_ast_count=reference.ast_node_count,
    )
    assert stub.status == "explicit_stub"
    assert not stub.nonstub
    renamed = analyze_structure("def other(value):\n    return value + 1\n", "python", signature)
    assert renamed.status == "target_missing"


def test_java_and_c_constant_gate():
    for language, code in (
        ("java", "int increment(int value) { return value + 1; }"),
        ("c", "int increment(int value) { return value + 1; }"),
    ):
        signature = extract_signature(code, language)
        reference = analyze_structure(code, language, signature)
        assert reference.strict_nontrivial
        constant = analyze_structure(
            "int increment(int value) { return 0; }",
            language,
            signature,
            human_token_count=reference.token_count,
            human_ast_count=reference.ast_node_count,
        )
        assert constant.status == "constant_noop"
        assert constant.nonstub
        assert not constant.strict_nontrivial


def test_parse_error_and_arity_mismatch():
    human = "def combine(left, right):\n    return left + right\n"
    signature = extract_signature(human, "python")
    broken = analyze_structure("def combine(left, right):\n return (", "python", signature)
    assert broken.status == "parse_error"
    mismatch = analyze_structure("def combine(left):\n    return left\n", "python", signature)
    assert mismatch.status == "arity_mismatch"

