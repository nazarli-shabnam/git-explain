"""Heuristic suggestions when AI is disabled or unavailable."""

from __future__ import annotations

import os

from git_explain.gemini import Suggestion


DOC_EXTS = {".md", ".rst", ".txt"}
TEST_HINTS = ("test", "tests", "pytest", "unittest")
CONFIG_FILES = {
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
    ".gitignore",
    "license",
    "license.txt",
    "license.md",
}
CONFIG_EXTS = {".toml", ".yml", ".yaml", ".json", ".ini", ".cfg", ".lock"}


def _is_doc(path: str) -> bool:
    p = path.lower()
    base = os.path.basename(p)
    return os.path.splitext(p)[1] in DOC_EXTS or base in {
        "readme",
        "readme.md",
        "features.md",
    }


def _is_test(path: str) -> bool:
    p = path.lower()
    base = os.path.basename(p)
    if p.startswith("tests/") or "/tests/" in p:
        return True
    if (
        base.startswith("test_")
        or base.endswith("_test.py")
        or base.endswith(".spec.ts")
        or base.endswith(".spec.tsx")
    ):
        return True
    return any(h in p for h in TEST_HINTS)


def _is_config(path: str) -> bool:
    p = path.lower()
    base = os.path.basename(p)
    return base in CONFIG_FILES or os.path.splitext(p)[1] in CONFIG_EXTS


def suggest_from_changes(
    *,
    changes: list[tuple[str, str]],
    has_commits: bool | None,
) -> Suggestion:
    """Create a Suggestion from [(status, path)] without calling AI."""
    paths = [p for _, p in changes]
    added_any = any(s.upper() == "A" for s, _ in changes) or has_commits is False

    docs = [p for p in paths if _is_doc(p)]
    tests = [p for p in paths if _is_test(p)]
    configs = [p for p in paths if _is_config(p)]
    non_docs = [p for p in paths if p not in docs]

    docs_only = bool(paths) and len(docs) == len(paths)
    mostly_tests_or_config = False
    if non_docs:
        tc = len([p for p in non_docs if p in tests or p in configs])
        mostly_tests_or_config = tc / max(1, len(non_docs)) >= 0.6

    verb = "Add" if added_any else "Update"

    if docs_only:
        commit_type = "DOCS"
    elif mostly_tests_or_config:
        commit_type = "TEST"
    elif added_any:
        commit_type = "FEAT"
    else:
        commit_type = "REFACTOR"

    topics: list[str] = []
    if any(os.path.basename(p).lower() in {"readme.md", "readme"} for p in paths):
        topics.append("README")
    if any(os.path.basename(p).lower() == "features.md" for p in paths):
        topics.append("FEATURES doc")
    if tests:
        topics.append("tests")
    if configs:
        topics.append("config")
    if any("git_explain/" in p.replace("\\", "/").lower() for p in paths):
        topics.append("git-explain CLI")

    if not topics:
        topics = ["changes"]

    # Dedupe while preserving order
    seen: set[str] = set()
    topics = [t for t in topics if not (t in seen or seen.add(t))]

    if len(topics) == 1:
        message = f"{verb} {topics[0]}"
    elif len(topics) == 2:
        message = f"{verb} {topics[0]} and {topics[1]}"
    else:
        message = f"{verb} {topics[0]}, {topics[1]}, and {topics[2]}"

    if added_any and has_commits is False and message.startswith("Add "):
        message = message.replace("Add ", "Add initial ", 1)

    return Suggestion(add_args=paths, commit_type=commit_type, commit_message=message)
