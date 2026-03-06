from git_explain.cli import _group_changes, _parse_selection


def test_parse_selection_all() -> None:
    assert _parse_selection("all", 5) == [1, 2, 3, 4, 5]
    assert _parse_selection("", 3) == [1, 2, 3]


def test_parse_selection_ranges() -> None:
    assert _parse_selection("1,3-4", 5) == [1, 3, 4]
    assert _parse_selection("2-1", 3) == [1, 2]


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
