from git_explain.gemini import COMMIT_LINE_CONVENTIONAL_RE, COMMIT_LINE_RE


def test_commit_line_re_matches_tests_not_test() -> None:
    """COMMIT_LINE_RE should match [TESTS] but not [TEST]."""
    line_tests = 'git commit -m "[TESTS] Add unit tests"'
    m = COMMIT_LINE_RE.match(line_tests)
    assert m is not None
    assert m.group(1).upper() == "TESTS"
    assert "Add unit tests" in m.group(2)

    line_test = 'git commit -m "[TEST] Add unit test"'
    m = COMMIT_LINE_RE.match(line_test)
    assert m is None


def test_commit_line_conventional_re_matches_tests() -> None:
    """COMMIT_LINE_CONVENTIONAL_RE should match 'tests:' not 'test:'."""
    line = 'git commit -m "tests: add unit tests"'
    m = COMMIT_LINE_CONVENTIONAL_RE.match(line)
    assert m is not None
    assert m.group(1).lower() == "tests"

    line_test = 'git commit -m "test: add unit test"'
    m = COMMIT_LINE_CONVENTIONAL_RE.match(line_test)
    assert m is None


def test_commit_line_re_matches_other_types() -> None:
    for line in [
        'git commit -m "[FEAT] Add feature"',
        'git commit -m "[FIX] Fix bug"',
        'git commit -m "[DOCS] Update readme"',
        'git commit -m "[REFACTOR] Simplify logic"',
    ]:
        m = COMMIT_LINE_RE.match(line)
        assert m is not None, f"Expected match for {line}"
