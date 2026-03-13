"""Capture git diffs (staged and unstaged)."""

import subprocess
from pathlib import Path


def get_repo_root(cwd: str | Path | None = None) -> Path:
    """Return the git repository root. Raises if not in a repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=cwd or ".",
    )
    if result.returncode != 0:
        raise RuntimeError("Not a git repository (or any of the parent directories).")
    return Path(result.stdout.strip())


def ensure_git_repo(cwd: str | Path | None = None) -> Path:
    """Ensure current directory is inside a git repo; return repo root."""
    r = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        cwd=cwd or ".",
    )
    if r.returncode != 0 or r.stdout.strip().lower() != "true":
        raise RuntimeError("Not a git repository (or any of the parent directories).")
    return get_repo_root(cwd)


def repo_has_commits(cwd: str | Path | None = None) -> bool:
    """Return True if the repository has at least one commit."""
    root = get_repo_root(cwd)
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    return result.returncode == 0


def _name_status(
    args: list[str], cwd: str | Path | None = None
) -> list[tuple[str, str]]:
    """Run a git command that outputs --name-status and return (status, path) pairs.

    Normalizes rename/copy lines to ('R', new_path) or ('C', new_path).
    """
    root = get_repo_root(cwd)
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        cwd=root,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    out: list[tuple[str, str]] = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Typical formats:
        # M\tpath
        # A\tpath
        # D\tpath
        # R100\told\tnew
        parts = line.split("\t")
        if len(parts) >= 2:
            status = parts[0].strip()
            code = status[:1].upper()
            path = parts[-1].strip()
            if code and path:
                out.append((code, path))
            continue
        # Fallback for whitespace-delimited output (should be rare)
        toks = line.split()
        if len(toks) >= 2:
            out.append((toks[0][:1].upper(), toks[-1]))
    return out


def get_staged_changes(cwd: str | Path | None = None) -> list[tuple[str, str]]:
    """Return (status, path) for staged changes."""
    return _name_status(["diff", "--cached", "--name-status"], cwd=cwd)


def get_unstaged_changes(cwd: str | Path | None = None) -> list[tuple[str, str]]:
    """Return (status, path) for unstaged changes (tracked files)."""
    return _name_status(["diff", "--name-status"], cwd=cwd)


def get_untracked_changes(cwd: str | Path | None = None) -> list[tuple[str, str]]:
    """Return (status, path) for untracked files (not ignored by .gitignore)."""
    root = get_repo_root(cwd)
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    paths = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
    return [("A", p) for p in paths]


def get_combined_diff(cwd: str | Path | None = None) -> tuple[str, Path]:
    """Return (file_list_text, repo_root).

    The text includes sections with status codes (A/M/D/R/C) and paths only (no file contents).
    """
    root = ensure_git_repo(cwd)
    has_commits = repo_has_commits(cwd=root)
    staged = get_staged_changes(cwd=root)
    unstaged = get_unstaged_changes(cwd=root)
    untracked = get_untracked_changes(cwd=root)
    parts = []
    parts.append(f"## Meta\nhas_commits: {str(has_commits).lower()}")
    if staged:
        parts.append("## Staged\n" + "\n".join([f"{s} {p}" for s, p in staged]))
    if unstaged:
        parts.append("## Unstaged\n" + "\n".join([f"{s} {p}" for s, p in unstaged]))
    if untracked:
        parts.append("## Untracked\n" + "\n".join([f"{s} {p}" for s, p in untracked]))
    combined = "\n\n".join(parts) if parts else ""
    return combined, root


def get_diff_for_paths(paths: list[str], cwd: str | Path | None = None) -> str:
    """Return combined diff (staged + unstaged) for the given paths.
    Untracked files are shown as full file content.
    """
    if not paths:
        return ""
    root = get_repo_root(cwd)
    parts: list[str] = []

    result = subprocess.run(
        ["git", "diff", "--cached", "--"] + paths,
        capture_output=True,
        text=True,
        cwd=root,
    )
    if result.returncode == 0 and result.stdout.strip():
        parts.append("## Staged diff\n" + result.stdout.strip())

    result = subprocess.run(
        ["git", "diff", "--"] + paths,
        capture_output=True,
        text=True,
        cwd=root,
    )
    if result.returncode == 0 and result.stdout.strip():
        parts.append("## Unstaged diff\n" + result.stdout.strip())

    untracked = get_untracked_changes(cwd=root)
    untracked_set = {p for _, p in untracked}
    for p in paths:
        if p in untracked_set:
            try:
                content = (root / p).read_text(encoding="utf-8", errors="replace")
                parts.append(f"## Untracked (new file): {p}\n{content}")
            except Exception:
                parts.append(f"## Untracked (new file): {p}\n<binary or unreadable>")

    return "\n\n".join(parts)
