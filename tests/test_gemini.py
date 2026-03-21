from git_explain.gemini import (
    COMMIT_LINE_CONVENTIONAL_RE,
    COMMIT_LINE_RE,
    _fallback_type_and_message_with_context,
    _is_generic_message,
)


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
        'git commit -m "[CHORE] Add Docker and nginx config"',
    ]:
        m = COMMIT_LINE_RE.match(line)
        assert m is not None, f"Expected match for {line}"


def test_commit_line_conventional_matches_chore() -> None:
    line = 'git commit -m "chore: add docker compose"'
    m = COMMIT_LINE_CONVENTIONAL_RE.match(line)
    assert m is not None
    assert m.group(1).lower() == "chore"


def test_is_generic_message_flags_vague_add_changes() -> None:
    assert _is_generic_message("Add changes") is True
    assert _is_generic_message("Update changes") is True
    assert _is_generic_message("Add Docker and nginx for api") is False


def test_is_generic_message_flags_update_project_files() -> None:
    assert _is_generic_message("Update project files") is True
    assert _is_generic_message("Add project files") is True
    assert _is_generic_message("Update tests for gemini and heuristics") is False


def test_fallback_uses_test_hints_for_test_files() -> None:
    ctype, msg = _fallback_type_and_message_with_context(
        files=["tests/test_gemini.py", "tests/test_heuristics.py"],
        added_any=False,
        has_commits=True,
    )
    assert ctype == "TEST"
    assert "gemini" in msg.lower()
    assert "heuristics" in msg.lower()
