import subprocess

import pytest

from git_explain.git import (
    ensure_git_repo,
    get_combined_diff,
    get_diff_for_paths,
    get_repo_root,
    get_staged_changes,
    get_staged_diff_for_paths,
    get_untracked_changes,
    get_unstaged_changes,
    repo_has_commits,
)


def _git(cwd, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(repo) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    # Emit UTF-8 paths as-is instead of octal-escaped/quoted (git's default
    # for non-ASCII paths), matching the UTF-8 assumption in git_explain.git.
    _git(repo, "config", "core.quotepath", "false")


def test_get_repo_root_raises_outside_a_repo(tmp_path) -> None:
    outside = tmp_path / "not_a_repo"
    outside.mkdir()
    with pytest.raises(RuntimeError):
        get_repo_root(outside)


def test_ensure_git_repo_raises_outside_a_repo(tmp_path) -> None:
    outside = tmp_path / "not_a_repo"
    outside.mkdir()
    with pytest.raises(RuntimeError):
        ensure_git_repo(outside)


def test_get_repo_root_and_ensure_git_repo_return_root(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    assert get_repo_root(repo).resolve() == repo.resolve()
    assert ensure_git_repo(repo).resolve() == repo.resolve()


def test_repo_has_commits_before_and_after_first_commit(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    assert repo_has_commits(repo) is False

    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    assert repo_has_commits(repo) is True


def test_get_staged_changes(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    assert get_staged_changes(repo) == [("A", "a.txt")]


def test_get_unstaged_changes(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")

    (repo / "a.txt").write_text("hello world\n", encoding="utf-8")
    assert get_unstaged_changes(repo) == [("M", "a.txt")]


def test_get_untracked_changes(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "new.txt").write_text("new\n", encoding="utf-8")
    assert get_untracked_changes(repo) == [("A", "new.txt")]


def test_rename_is_normalized_to_single_r_status(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "old.txt").write_text("same content\n", encoding="utf-8")
    _git(repo, "add", "old.txt")
    _git(repo, "commit", "-m", "init")

    _git(repo, "mv", "old.txt", "new.txt")
    staged = get_staged_changes(repo)
    assert staged == [("R", "new.txt")]


def test_copy_without_detection_flags_shows_as_two_adds(tmp_path) -> None:
    # get_staged_changes() calls `git diff --name-status` without -C, so git
    # never detects copies (unlike renames, copy detection needs an explicit
    # flag) — both the original and the copy show up as separate adds.
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "old.txt").write_text("x\n" * 20, encoding="utf-8")
    _git(repo, "add", "old.txt")
    _git(repo, "commit", "-m", "init")

    (repo / "copy.txt").write_text((repo / "old.txt").read_text(encoding="utf-8"))
    _git(repo, "add", "copy.txt")
    assert get_staged_changes(repo) == [("A", "copy.txt")]


def test_non_ascii_path_round_trips(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    fname = "café.txt"
    (repo / fname).write_text("hello\n", encoding="utf-8")
    assert get_untracked_changes(repo) == [("A", fname)]


def test_get_combined_diff_sections(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "tracked.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "init")

    (repo / "tracked.txt").write_text("hello world\n", encoding="utf-8")
    (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "staged.txt")
    (repo / "untracked.txt").write_text("new\n", encoding="utf-8")

    combined, root = get_combined_diff(repo)
    assert root.resolve() == repo.resolve()
    assert "## Meta\nhas_commits: true" in combined
    assert "## Staged\nA staged.txt" in combined
    assert "## Unstaged\nM tracked.txt" in combined
    assert "## Untracked\nA untracked.txt" in combined


def test_get_combined_diff_empty_repo_has_no_commits(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    combined, _root = get_combined_diff(repo)
    assert "has_commits: false" in combined


def test_get_diff_for_paths_includes_untracked_file_content(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "new.txt").write_text("brand new content\n", encoding="utf-8")

    diff = get_diff_for_paths(["new.txt"], repo)
    assert "Untracked (new file): new.txt" in diff
    assert "brand new content" in diff


def test_get_diff_for_paths_includes_staged_and_unstaged_sections(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "a.txt").write_text("line1\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")

    (repo / "a.txt").write_text("line1\nline2\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    (repo / "a.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")

    diff = get_diff_for_paths(["a.txt"], repo)
    assert "## Staged diff" in diff
    assert "## Unstaged diff" in diff


def test_get_diff_for_paths_empty_paths_returns_empty_string(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    assert get_diff_for_paths([], repo) == ""


def test_get_staged_diff_for_paths(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "a.txt").write_text("line1\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")

    (repo / "a.txt").write_text("line1\nline2\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    (repo / "a.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")

    staged_diff = get_staged_diff_for_paths(["a.txt"], repo)
    assert "+line2" in staged_diff
    assert "line3" not in staged_diff


def test_get_staged_diff_for_paths_empty_paths_returns_empty_string(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    assert get_staged_diff_for_paths([], repo) == ""
