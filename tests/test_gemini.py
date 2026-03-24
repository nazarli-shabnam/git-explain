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


def test_is_generic_message_flags_readme_docs_cli_combo() -> None:
    msg = "Update README, docs, and CLI for project"
    assert _is_generic_message(msg) is True


def test_is_generic_message_flags_for_clause_with_same_topic() -> None:
    msg = "Update git explain for git_explain"
    assert _is_generic_message(msg) is True


def test_is_generic_message_flags_update_git_explain() -> None:
    assert _is_generic_message("Update git explain") is True
    assert _is_generic_message("Update project CLI") is True


def test_fallback_uses_test_hints_for_test_files() -> None:
    ctype, msg = _fallback_type_and_message_with_context(
        files=["tests/test_gemini.py", "tests/test_heuristics.py"],
        added_any=False,
        has_commits=True,
    )
    assert ctype == "TEST"
    assert "gemini" in msg.lower()
    assert "heuristics" in msg.lower()


def test_fallback_uses_generic_code_topics_for_many_paths() -> None:
    ctype, msg = _fallback_type_and_message_with_context(
        files=[
            "src/api/router.py",
            "src/ui/view.ts",
            "services/auth/index.js",
            "README.md",
        ],
        added_any=False,
        has_commits=True,
    )
    assert ctype in {"REFACTOR", "FIX", "FEAT"}
    low = msg.lower()
    assert "git-explain cli" not in low
    assert "api" in low or "ui" in low or "auth" in low


def test_fallback_avoids_redundant_scope_suffix() -> None:
    _ctype, msg = _fallback_type_and_message_with_context(
        files=["git_explain/cli.py"],
        added_any=False,
        has_commits=True,
    )
    low = msg.lower()
    assert "for git_explain" not in low


def test_fallback_prefers_stems_when_folder_is_same() -> None:
    _ctype, msg = _fallback_type_and_message_with_context(
        files=[
            "git_explain/cli.py",
            "git_explain/gemini.py",
            "git_explain/git.py",
        ],
        added_any=False,
        has_commits=True,
    )
    low = msg.lower()
    assert "update git explain" not in low
    assert "cli" in low or "gemini" in low or "git" in low
