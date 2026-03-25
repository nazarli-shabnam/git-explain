import pytest

from git_explain.cli import (
    _group_changes,
    _parse_combined,
    _parse_selection,
    _ps_quote,
    _validate_suggest_flags,
)


def test_parse_selection_all() -> None:
    idx, paths = _parse_selection("all", 5)
    assert idx == [1, 2, 3, 4, 5]
    assert paths == []

    idx, paths = _parse_selection("", 3)
    assert idx == [1, 2, 3]
    assert paths == []


def test_parse_selection_ranges() -> None:
    idx, paths = _parse_selection("1,3-4", 5)
    assert idx == [1, 3, 4]
    assert paths == []

    idx, paths = _parse_selection("2-1", 3)
    assert idx == [1, 2]
    assert paths == []


def test_parse_selection_path_tokens() -> None:
    idx, paths = _parse_selection("main.py", 5)
    assert idx == []
    assert paths == ["main.py"]

    idx, paths = _parse_selection("src/", 5)
    assert idx == []
    assert paths == ["src/"]

    idx, paths = _parse_selection("git_explain/cli.py,2", 5)
    assert idx == [2]
    assert paths == ["git_explain/cli.py"]

    idx, paths = _parse_selection("1-2, tests/", 5)
    assert idx == [1, 2]
    assert paths == ["tests/"]


def test_parse_combined() -> None:
    combined = "## Meta\nhas_commits: true\n\n## Staged\nM foo.py\nA bar.txt"
    has_commits, changes = _parse_combined(combined)
    assert has_commits is True
    assert len(changes) == 2
    assert changes[0].path == "bar.txt"
    assert changes[0].status == "A"
    assert changes[1].path == "foo.py"
    assert changes[1].status == "M"

    combined_no_meta = "## Unstaged\nD old.py"
    has_commits, changes = _parse_combined(combined_no_meta)
    assert has_commits is None
    assert len(changes) == 1
    assert changes[0].path == "old.py"
    assert changes[0].status == "D"


def test_parse_combined_same_path_multiple_sections() -> None:
    combined = "## Staged\nM foo.py\n\n## Unstaged\nM foo.py"
    has_commits, changes = _parse_combined(combined)
    assert len(changes) == 1
    assert changes[0].path == "foo.py"
    assert "Staged" in changes[0].sections
    assert "Unstaged" in changes[0].sections


def test_ps_quote() -> None:
    assert _ps_quote("simple") == "'simple'"
    assert _ps_quote("path with spaces") == "'path with spaces'"
    assert _ps_quote("it's") == "'it''s'"
    assert _ps_quote("") == "''"


def test_group_changes_buckets() -> None:
    changes = [
        ("M", "README.md"),
        ("M", "tests/test_app.py"),
        ("M", "pyproject.toml"),
        ("M", "git_explain/cli.py"),
        ("M", "misc/file.bin"),
    ]
    groups = _group_changes(changes)
    assert "docs" in groups
    assert "tests" in groups
    assert "config" in groups
    assert "code" in groups
    assert "other" in groups


def test_group_changes_test_patterns() -> None:
    changes = [
        ("M", "tests/test_app.py"),
        ("M", "src/utils_test.py"),
        ("M", "foo.spec.ts"),
    ]
    groups = _group_changes(changes)
    assert len(groups["tests"]) == 3


def test_group_changes_config_patterns() -> None:
    changes = [
        ("M", ".gitignore"),
        ("M", "config.yml"),
    ]
    groups = _group_changes(changes)
    assert len(groups["config"]) == 2


def test_group_changes_code_bucket() -> None:
    changes = [("M", "src/app.ts")]
    groups = _group_changes(changes)
    assert groups["code"] == [("M", "src/app.ts")]


def test_validate_suggest_flags_allows_suggest_alone() -> None:
    _validate_suggest_flags(
        suggest=True,
        auto=False,
        ai=False,
        staged_only=False,
        model=None,
        with_diff=False,
    )


def test_validate_suggest_flags_rejects_combined_flags() -> None:
    with pytest.raises(Exception) as ex:
        _validate_suggest_flags(
            suggest=True,
            auto=True,
            ai=True,
            staged_only=False,
            model="gemini-2.5-flash",
            with_diff=False,
        )
    assert "--suggest is a dedicated mode" in str(ex.value)
