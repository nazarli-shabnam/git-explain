from git_explain.gemini import (
    COMMIT_LINE_RE,
    _COMMIT_LINE_BRACKET_RE,
    _fallback_type_and_message_with_context,
    _is_generic_message,
    _normalize_type,
    truncate_commit_subject,
)


def test_commit_line_re_matches_conventional_types() -> None:
    """COMMIT_LINE_RE should match conventional commits: type: subject."""
    for line, expected_type in [
        ('git commit -m "feat: add new feature"', "FEAT"),
        ('git commit -m "fix: correct the bug"', "FIX"),
        ('git commit -m "docs: update readme"', "DOCS"),
        ('git commit -m "refactor: simplify logic"', "REFACTOR"),
        ('git commit -m "test: add unit tests"', "TEST"),
        ('git commit -m "chore: update deps"', "CHORE"),
        ('git commit -m "build: update dockerfile"', "BUILD"),
        ('git commit -m "ci: add github workflow"', "CI"),
        ('git commit -m "style: fix formatting"', "STYLE"),
        ('git commit -m "perf: optimize query"', "PERF"),
    ]:
        m = COMMIT_LINE_RE.match(line)
        assert m is not None, f"Expected match for {line}"
        assert _normalize_type(m.group(1)) == expected_type


def test_commit_line_re_matches_scope_and_breaking() -> None:
    """COMMIT_LINE_RE should parse scope and breaking change indicator."""
    line = 'git commit -m "feat(cli): add new flag"'
    m = COMMIT_LINE_RE.match(line)
    assert m is not None
    assert m.group(1).upper() == "FEAT"
    assert m.group(2) == "cli"
    assert m.group(3) == ""
    assert "add new flag" in m.group(4)

    line = 'git commit -m "feat(api)!: drop legacy endpoint"'
    m = COMMIT_LINE_RE.match(line)
    assert m is not None
    assert m.group(2) == "api"
    assert m.group(3) == "!"

    line = 'git commit -m "fix!: breaking bugfix"'
    m = COMMIT_LINE_RE.match(line)
    assert m is not None
    assert m.group(2) is None
    assert m.group(3) == "!"


def test_bracket_re_matches_legacy_format() -> None:
    """_COMMIT_LINE_BRACKET_RE should match [TYPE] format as fallback."""
    for line in [
        'git commit -m "[FEAT] Add feature"',
        'git commit -m "[FIX] Fix bug"',
        'git commit -m "[DOCS] Update readme"',
        'git commit -m "[TESTS] Add tests"',
        'git commit -m "[CHORE] Add Docker config"',
        'git commit -m "[BUILD] Update dockerfile"',
        'git commit -m "[CI] Add workflow"',
    ]:
        m = _COMMIT_LINE_BRACKET_RE.match(line)
        assert m is not None, f"Expected bracket match for {line}"


def test_normalize_type_converts_tests_to_test() -> None:
    assert _normalize_type("TESTS") == "TEST"
    assert _normalize_type("tests") == "TEST"
    assert _normalize_type("TEST") == "TEST"
    assert _normalize_type("feat") == "FEAT"
    assert _normalize_type("unknown") == "CHORE"


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


def test_truncate_commit_subject_drops_dangling_plus_more() -> None:
    """Regression: hard slice used to cut '(+N more)' into '(+N mo'."""
    long_msg = (
        "Update layout, module-work-items, project-issues, workspace-views "
        "and 5 related areas with extra detail for filters"
    )
    # Force a cut that would bisect a synthetic (+N more) tail
    cut = truncate_commit_subject(long_msg + " (+7 more)", max_len=72)
    assert not cut.endswith("mo")
    assert "(+" not in cut or cut.rstrip().endswith(")")


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


def test_fallback_many_folders_lists_topics_without_overflow() -> None:
    folders = [f"ui/src/area{i}/File.tsx" for i in range(8)]
    _ctype, msg = _fallback_type_and_message_with_context(
        files=folders,
        added_any=False,
        has_commits=True,
    )
    assert "(+" not in msg
    assert "related areas" not in msg.lower()
    assert "area0" in msg.lower() or "area1" in msg.lower()
