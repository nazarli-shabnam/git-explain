"""Apply git add and commit from suggested message."""

import subprocess
from pathlib import Path


def _has_staged_changes(repo_root: Path) -> bool:
    # Works even for initial commit (unborn HEAD).
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        check=False,
        cwd=repo_root,
        capture_output=True,
        text=True,
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
            text=True,
        )
    if not _has_staged_changes(root):
        if staged_only:
            raise RuntimeError(
                "Nothing is currently staged. With --staged-only, git-explain does "
                "not run git add; stage your changes first, then try again."
            )
        raise RuntimeError("Nothing staged after git add; aborting commit.")
    full_message = f"[{commit_type}] {commit_message}"
    subprocess.run(
        ["git", "commit", "-m", full_message],
        check=True,
        cwd=root,
        capture_output=True,
        text=True,
    )
