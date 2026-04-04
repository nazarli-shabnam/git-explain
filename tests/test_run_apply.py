import subprocess

from git_explain.run import apply_commands, normalize_commit_subject_for_dash_m


def _git(cwd, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def test_apply_commands_initial_commit(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    (repo / "a.txt").write_text("hello\n", encoding="utf-8")

    apply_commands(repo, ["a.txt"], "FEAT", "Add a")

    log = _git(repo, "log", "--oneline").stdout.strip()
    assert log


def test_normalize_commit_subject_collapses_multiline_and_tabs() -> None:
    assert normalize_commit_subject_for_dash_m("a\nb\tc") == "a b c"
    assert normalize_commit_subject_for_dash_m(None) == ""


def test_apply_commands_newlines_in_message_become_single_subject_line(
    tmp_path,
) -> None:
    repo = tmp_path / "repo_nl"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    apply_commands(repo, ["a.txt"], "FIX", "first line\nsecond line")
    subj = _git(repo, "log", "-1", "--format=%s").stdout.strip()
    assert subj == "fix: first line second line"


def test_apply_commands_deleted_file(tmp_path) -> None:
    repo = tmp_path / "repo2"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    p = repo / "a.txt"
    p.write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")

    p.unlink()
    apply_commands(repo, ["a.txt"], "REFACTOR", "Remove a")
    out = _git(repo, "status", "--porcelain").stdout.strip()
    assert out == ""
