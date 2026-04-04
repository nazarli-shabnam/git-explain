"""Apply git add and commit from suggested message."""

import subprocess
from pathlib import Path

# Match git_explain.git: git stdout is UTF-8; avoid Windows default code page decoding.
_GIT_TEXT = {"encoding": "utf-8", "errors": "replace"}


def _lowercase_first(s: str) -> str:
    """Lowercase the first character unless the first word is an acronym."""
    if not s:
        return s
    first_space = s.find(" ")
    first_word = s[:first_space] if first_space > 0 else s
    if first_word == first_word.upper() and len(first_word) > 1:
        return s
    return s[0].lower() + s[1:]


def format_commit_message(
    commit_type: str,
    commit_message: str,
    *,
    scope: str | None = None,
    breaking: bool = False,
) -> str:
    """Format a conventional commit subject: type(scope)!: description."""
    type_str = commit_type.lower()
    scope_str = f"({scope})" if scope else ""
    bang = "!" if breaking else ""
    msg = _lowercase_first(commit_message)
    return f"{type_str}{scope_str}{bang}: {msg}"


def normalize_commit_subject_for_dash_m(message: str | None) -> str:
    """Single line for ``git commit -m``: newlines/tabs become spaces, strip ends.

    Multi-line text breaks one-line -m and looks wrong when copied into a shell.
    """
    return " ".join((message or "").replace("\t", " ").splitlines()).strip()


def _has_staged_changes(repo_root: Path) -> bool:
    # Works even for initial commit (unborn HEAD).
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        check=False,
        cwd=repo_root,
        capture_output=True,
        **_GIT_TEXT,
    )
    for raw in (r.stdout or "").splitlines():
        if not raw:
            continue
        # XY <path> (or ?? for untracked). Staged changes => X != ' ' and X != '?'
        if len(raw) >= 2 and raw[0] not in (" ", "?"):
            return True
    return False


def apply_commands(
    repo_root: str | Path,
    add_args: list[str],
    commit_type: str,
    commit_message: str,
    *,
    scope: str | None = None,
    body: str | None = None,
    breaking: bool = False,
    staged_only: bool = False,
) -> None:
    """Stage selected paths and commit. Raises on failure.

    Uses `git add -A -- <paths...>` to properly handle deletes/renames.
    Verifies that something is staged before attempting the commit.

    When ``staged_only`` is True, ``git add`` is skipped (``add_args`` should be
    empty); the current index is committed as-is. Split multi-commit plans are
    not supported in that mode because each ``git commit`` empties the index.
    """
    root = Path(repo_root)
    if add_args:
        subprocess.run(
            ["git", "add", "-A", "--"] + add_args,
            check=True,
            cwd=root,
            capture_output=True,
            **_GIT_TEXT,
        )
    if not _has_staged_changes(root):
        if staged_only:
            raise RuntimeError(
                "Nothing is currently staged. With --staged-only, git-explain does "
                "not run git add; stage your changes first, then try again."
            )
        raise RuntimeError("Nothing staged after git add; aborting commit.")
    safe_msg = normalize_commit_subject_for_dash_m(commit_message)
    full_message = format_commit_message(
        commit_type, safe_msg, scope=scope, breaking=breaking
    )
    cmd = ["git", "commit", "-m", full_message]
    if body:
        safe_body = normalize_commit_subject_for_dash_m(body)
        cmd.extend(["-m", safe_body])
    subprocess.run(
        cmd,
        check=True,
        cwd=root,
        capture_output=True,
        **_GIT_TEXT,
    )
