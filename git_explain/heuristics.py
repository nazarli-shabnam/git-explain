"""Heuristic suggestions when AI is disabled or unavailable."""

from __future__ import annotations

import os
import re

from git_explain.commit_infer import refine_type_and_message_from_diff
from git_explain.gemini import MAX_COMMIT_SUBJECT_CHARS, Suggestion, truncate_commit_subject
from git_explain.path_topics import (
    area_scope_suffix,
    basename_fallback_topic,
    infra_deploy_topics,
    is_infra_deploy_path,
    is_test_path,
    test_subject_hints,
)


DOC_EXTS = {".md", ".rst", ".txt"}
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
CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".cs"}


def _is_doc(path: str) -> bool:
    p = path.lower()
    base = os.path.basename(p)
    return os.path.splitext(p)[1] in DOC_EXTS or base in {
        "readme",
        "readme.md",
        "features.md",
    }


def _is_plain_config(path: str) -> bool:
    p = path.lower()
    base = os.path.basename(p)
    return base in CONFIG_FILES or os.path.splitext(p)[1] in CONFIG_EXTS


def _is_config(path: str) -> bool:
    """Packaging/config files plus Docker, Compose, nginx, env templates."""
    return _is_plain_config(path) or is_infra_deploy_path(path)


def _code_topics(paths: list[str]) -> list[str]:
    labeled: list[tuple[str, str]] = []  # (folder_label, stem)
    for p in paths:
        p2 = p.replace("\\", "/")
        base = os.path.basename(p2)
        ext = os.path.splitext(base)[1].lower()
        if ext not in CODE_EXTS:
            continue
        stem = os.path.splitext(base)[0].replace("_", " ")
        parts = [x for x in p2.split("/") if x]
        folder = parts[-2] if len(parts) >= 2 else stem
        labeled.append((folder.replace("_", " "), stem))

    if not labeled:
        return []

    folder_set = {f.lower() for f, _ in labeled}
    prefer_stems = len(folder_set) == 1 and len(labeled) >= 2

    topics: list[str] = []
    seen: set[str] = set()
    for folder, stem in labeled:
        label = stem if prefer_stems else folder
        key = label.lower()
        if key not in seen:
            seen.add(key)
            topics.append(label)
    return topics


def _alnum_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def suggest_from_changes(
    *,
    changes: list[tuple[str, str]],
    has_commits: bool | None,
    diff_text: str | None = None,
) -> Suggestion:
    """Create a Suggestion from [(status, path)] without calling AI."""
    paths = [p for _, p in changes]
    added_any = any(s.upper() == "A" for s, _ in changes) or has_commits is False
    modified_any = any(s.upper() == "M" for s, _ in changes)

    docs = [p for p in paths if _is_doc(p)]
    tests = [p for p in paths if is_test_path(p)]
    configs = [p for p in paths if _is_config(p)]
    has_tests = bool(tests)
    has_configs = bool(configs)
    non_docs = [p for p in paths if p not in docs]

    docs_only = bool(paths) and len(docs) == len(paths)
    mostly_tests_or_config = False
    if non_docs:
        tc = len([p for p in non_docs if p in tests or p in configs])
        mostly_tests_or_config = tc / max(1, len(non_docs)) >= 0.6

    if has_commits is False:
        verb = "Add"
    elif added_any and not modified_any:
        verb = "Add"
    else:
        verb = "Update"

    if docs_only:
        commit_type = "DOCS"
    elif mostly_tests_or_config:
        if has_tests and not has_configs:
            commit_type = "TEST"
        elif has_configs and not has_tests:
            commit_type = "CHORE"
        else:
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
    topics.extend(infra_deploy_topics(paths))
    if tests:
        all_tests_only = bool(paths) and len(tests) == len(paths)
        hints = test_subject_hints(paths)
        if all_tests_only and hints:
            head = " and ".join(hints[:3])
            tail = f" (+{len(hints) - 3} more)" if len(hints) > 3 else ""
            topics.append(f"tests for {head}{tail}")
        else:
            topics.append("tests")
    if any(_is_plain_config(p) for p in paths):
        topics.append("config")
    code_topics = _code_topics(paths)
    if code_topics:
        if len(code_topics) <= 3:
            label = ", ".join(code_topics)
        else:
            head = ", ".join(code_topics[:3])
            rest = len(code_topics) - 3
            label = f"{head} and {rest} related areas"
        topics.append(label)

    # Dedupe while preserving order
    seen: set[str] = set()
    topics = [t for t in topics if not (t in seen or seen.add(t))]

    if not topics:
        fb = basename_fallback_topic(paths)
        topics = [fb] if fb else ["project files"]

    if len(topics) == 1:
        message = f"{verb} {topics[0]}"
    elif len(topics) == 2:
        message = f"{verb} {topics[0]} and {topics[1]}"
    else:
        message = f"{verb} {topics[0]}, {topics[1]}, and {topics[2]}"

    scope = area_scope_suffix(paths)
    if scope:
        scope_key = _alnum_key(scope.replace("for", "", 1))
        msg_key = _alnum_key(message)
        if scope_key and scope_key not in msg_key:
            message += scope

    if added_any and has_commits is False and message.startswith("Add "):
        message = message.replace("Add ", "Add initial ", 1)

    message = truncate_commit_subject(message, MAX_COMMIT_SUBJECT_CHARS)

    commit_type, message = refine_type_and_message_from_diff(
        commit_type, message, diff_text
    )

    return Suggestion(add_args=paths, commit_type=commit_type, commit_message=message)
