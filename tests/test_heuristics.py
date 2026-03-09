from git_explain.heuristics import suggest_from_changes


def test_docs_only_is_docs() -> None:
    s = suggest_from_changes(
        changes=[("M", "README.md"), ("A", "FEATURES.md")],
        has_commits=True,
    )
    assert s.commit_type == "DOCS"
    assert s.commit_message.lower().startswith(
        "add"
    ) or s.commit_message.lower().startswith("update")


def test_added_files_prefer_feat() -> None:
    s = suggest_from_changes(
        changes=[("A", "git_explain/cli.py"), ("M", "pyproject.toml")],
        has_commits=True,
    )
    assert s.commit_type == "FEAT"
    assert s.commit_message.lower().startswith("add")


def test_mostly_tests_or_config_is_test() -> None:
    s = suggest_from_changes(
        changes=[
            ("M", "tests/test_cli.py"),
            ("M", "pyproject.toml"),
            ("M", "requirements.txt"),
        ],
        has_commits=True,
    )
    assert s.commit_type == "TEST"


def test_config_only_is_chore_not_test() -> None:
    s = suggest_from_changes(
        changes=[("M", ".gitignore"), ("M", "pyproject.toml")],
        has_commits=True,
    )
    assert s.commit_type == "CHORE"
