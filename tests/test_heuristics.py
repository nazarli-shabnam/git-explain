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
    assert s.commit_message.lower().startswith(
        "add"
    ) or s.commit_message.lower().startswith("update")


def test_many_git_explain_paths_use_module_names_not_umbrella_cli() -> None:
    s = suggest_from_changes(
        changes=[
            ("M", "git_explain/cli.py"),
            ("M", "git_explain/run.py"),
            ("M", "git_explain/gemini.py"),
        ],
        has_commits=True,
    )
    m = s.commit_message.lower()
    assert "git-explain cli" not in m
    assert "cli" in m


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


def test_test_only_paths_get_specific_test_message() -> None:
    s = suggest_from_changes(
        changes=[
            ("M", "tests/test_gemini.py"),
            ("M", "tests/test_heuristics.py"),
        ],
        has_commits=True,
    )
    assert s.commit_type == "TEST"
    m = s.commit_message.lower()
    assert "gemini" in m
    assert "heuristics" in m
    assert "project files" not in m


def test_docker_nginx_env_paths_get_specific_chore_message() -> None:
    """Infra paths should not collapse to 'Add changes'."""
    s = suggest_from_changes(
        changes=[
            ("A", "api/app/.env.example"),
            ("A", "api/app/Dockerfile"),
            ("A", "apps/frontend/.dockerignore"),
            ("A", "apps/frontend/Dockerfile"),
            ("A", "apps/frontend/nginx.conf"),
            ("A", "compose.env.example"),
        ],
        has_commits=True,
    )
    assert s.commit_type == "CHORE"
    m = s.commit_message.lower()
    assert "docker" in m
    assert "nginx" in m
    assert "env" in m
    assert "changes" not in m
    assert "api" in m and "frontend" in m
