import os

import pytest

from git_explain.gemini import DEFAULT_MODEL
from git_explain.cli import (
    _choose_and_persist_ai_model,
    _ensure_repo_env_file,
    _group_changes,
    _load_ai_env_from_dotenv,
    _parse_combined,
    _parse_selection,
    _ps_quote,
    _resolve_project_ai_model,
    _upsert_env_var,
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


def test_parse_selection_ignores_out_of_range_indices() -> None:
    idx, paths = _parse_selection("0,2,7,3-10", 4)
    assert idx == [2, 3, 4]
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


def test_parse_combined_git_typechange_and_unmerged() -> None:
    """git diff --name-status can emit T (type change) and U (unmerged)."""
    combined = "## Staged\nT switch.sh\nU conflict.txt"
    _hc, changes = _parse_combined(combined)
    assert {(c.status, c.path) for c in changes} == {
        ("T", "switch.sh"),
        ("U", "conflict.txt"),
    }


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


def test_group_changes_prioritizes_test_bucket_over_code() -> None:
    changes = [
        ("M", "tests/foo.spec.ts"),
        ("M", "src/auth_test.py"),
    ]
    groups = _group_changes(changes)
    assert "tests" in groups
    assert ("M", "tests/foo.spec.ts") in groups["tests"]
    assert ("M", "src/auth_test.py") in groups["tests"]
    assert "code" not in groups or ("M", "tests/foo.spec.ts") not in groups["code"]


def test_group_changes_handles_windows_style_paths() -> None:
    changes = [
        ("M", r"tests\test_cli.py"),
        ("M", r"git_explain\cli.py"),
    ]
    groups = _group_changes(changes)
    assert ("M", r"tests\test_cli.py") in groups["tests"]
    assert ("M", r"git_explain\cli.py") in groups["code"]


def test_validate_suggest_flags_allows_suggest_alone() -> None:
    _validate_suggest_flags(
        suggest=True,
        auto=False,
        staged_only=False,
        model=None,
        with_diff=False,
    )


def test_validate_suggest_flags_allows_model_override() -> None:
    _validate_suggest_flags(
        suggest=True,
        auto=False,
        staged_only=False,
        model="gemini-2.5-flash-lite",
        with_diff=False,
    )


def test_validate_suggest_flags_rejects_combined_flags() -> None:
    with pytest.raises(Exception) as ex:
        _validate_suggest_flags(
            suggest=True,
            auto=True,
            staged_only=False,
            model=None,
            with_diff=False,
        )
    assert "--suggest is a dedicated mode" in str(ex.value)


def test_load_ai_env_from_dotenv_only_sets_ai_keys(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_API_KEY=from-file\nAI_MODEL=gemini-2.5-flash\nPATH=should-not-touch\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.setenv("PATH", "existing-path")

    _load_ai_env_from_dotenv(env_file)

    assert os.environ.get("AI_API_KEY") == "from-file"
    assert os.environ.get("AI_MODEL") == "gemini-2.5-flash"
    assert os.environ.get("PATH") == "existing-path"


def test_load_ai_env_from_dotenv_overrides_existing(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_API_KEY=from-file\nAI_MODEL=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_API_KEY", "existing-key")
    monkeypatch.setenv("AI_MODEL", "existing-model")

    _load_ai_env_from_dotenv(env_file)

    assert os.environ.get("AI_API_KEY") == "from-file"
    assert os.environ.get("AI_MODEL") == "from-file"


def test_load_ai_env_from_dotenv_ignores_empty_values(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_API_KEY=\nAI_MODEL=\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_API_KEY", "existing-key")
    monkeypatch.setenv("AI_MODEL", "existing-model")

    _load_ai_env_from_dotenv(env_file)

    assert os.environ.get("AI_API_KEY") == "existing-key"
    assert os.environ.get("AI_MODEL") == "existing-model"


def test_upsert_env_var_appends_and_updates(tmp_path) -> None:
    env_file = tmp_path / ".env"
    _upsert_env_var(env_file, "AI_MODEL", DEFAULT_MODEL)
    _upsert_env_var(env_file, "AI_MODEL", "gemini-2.5-flash-lite")
    text = env_file.read_text(encoding="utf-8")
    assert "AI_MODEL=gemini-2.5-flash-lite" in text
    assert text.count("AI_MODEL=") == 1


def test_ensure_repo_env_file_respects_no_choice(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    monkeypatch.setattr("typer.prompt", lambda *a, **k: "n")
    assert _ensure_repo_env_file(env_file) is False
    assert not env_file.exists()


def test_resolve_project_ai_model_uses_override(tmp_path) -> None:
    env_file = tmp_path / ".env"
    m = _resolve_project_ai_model(env_file, "gemini-2.5-flash-lite")
    assert m == "gemini-2.5-flash-lite"


def test_choose_and_persist_ai_model_default_is_gemini(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    monkeypatch.setattr("typer.prompt", lambda *a, **k: "1")
    model = _choose_and_persist_ai_model(env_file)
    assert model == DEFAULT_MODEL
    assert "AI_MODEL=gemini-2.5-flash" in env_file.read_text(encoding="utf-8")


