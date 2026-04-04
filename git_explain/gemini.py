"""Suggest git add and commit from diff using Google Gemini."""

import os
import re
import time
from dataclasses import dataclass

from google import genai
from google.genai import types

from git_explain.commit_infer import refine_type_and_message_from_diff
from git_explain.path_topics import (
    area_scope_suffix,
    basename_fallback_topic,
    infer_scope,
    infra_deploy_topics,
    is_test_path,
    test_subject_hints,
)

VALID_TYPES = frozenset(
    {
        "FEAT",
        "FIX",
        "DOCS",
        "REFACTOR",
        "TEST",
        "CHORE",
        "BUILD",
        "CI",
        "STYLE",
        "PERF",
        "REVERT",
    }
)

_TYPE_RE_ALT = "|".join(sorted(VALID_TYPES | {"TESTS"}, key=len, reverse=True))

SYSTEM_PROMPT = f"""You are given a list of changed/added files under ## Staged, ## Unstaged, ## Untracked.
Each file line is: <STATUS> <PATH> where STATUS is one of:
- A = added/new file
- M = modified
- D = deleted
- R = renamed
- C = copied

Suggest one commit that includes ALL of these files using Conventional Commits format.

Rules:
1. Line 1 must be: git add <path1> <path2> ... with EVERY PATH from the list (all sections). Do not omit any file. Do not truncate. Do not include status letters.
2. Line 2 must be: git commit -m "type(scope): description"
   - type: exactly one of: feat, fix, docs, refactor, test, chore, build, ci, style, perf
   - scope (optional): a noun in parentheses describing the area of the codebase (e.g., cli, api, parser). Omit if the change spans many unrelated areas.
   - If the change introduces a breaking API change, add ! after the type/scope: feat!: or feat(api)!:
   - description: imperative mood, lowercase first letter, no period at end. Up to about 200 characters—finish the thought completely.
3. The description must state **what the change does** (behavior, feature, fix)—not a comma-separated list of folders or path segments. You may mention one path if it disambiguates. Never use only generic words like "update", "changes", or "refactor" by themselves.
4. Infer concrete artifacts from paths when obvious: Dockerfiles, Docker Compose files, nginx configs, .env/.env.example templates, CI workflows—not vague summaries. For test paths (e.g. tests/test_foo.py), name the area under test (e.g. "expand tests for foo and bar").
5. Use fix when the change corrects broken behavior, wrong CLI flow, or misleading errors—not refactor for those cases.
6. Use build for build system / dependency changes (Dockerfile, pyproject.toml, requirements.txt, Makefile). Use ci for CI/CD config (.github/workflows, .gitlab-ci.yml, etc.).

Example for files README.md, FEATURES.md, git_explain/gemini.py:
git add README.md FEATURES.md git_explain/gemini.py
git commit -m "docs: add README and FEATURES doc, tune Gemini prompt"

Example for Docker + nginx under api/:
git add api/Dockerfile api/nginx.conf
git commit -m "build(api): add Docker and nginx configuration"
"""

SYSTEM_PROMPT_WITH_DIFF = f"""You are given:
1. A list of changed/added files (## Staged, ## Unstaged, ## Untracked) with <STATUS> <PATH>.
2. The full diff (## Diff) showing exact code changes.

Use the diff to write a **specific, detailed** commit message in Conventional Commits format about **what changed in behavior, UI, data flow, or APIs**. Quote or paraphrase the actual diff: new props, renamed state, conditional logic, extracted components, bug fixes, etc.
**Do not** summarize by only listing directories, modules, or file names. If many files move together, state the **theme** of the change in plain language.
Avoid hollow words like "update" or "changes" without saying what moved or why.
Prefer fix when the diff corrects incorrect behavior or user-visible bugs; use refactor only for internal restructuring without behavior change.
Use build for build/dependency changes, ci for CI/CD config changes.

Output format:
- Line 1: git add <path1> <path2> ... with EVERY path from the file list. Do not omit any.
- Line 2: git commit -m "type(scope): description"
  - type: exactly one of: feat, fix, docs, refactor, test, chore, build, ci, style, perf
  - scope (optional): noun in parentheses describing the area. Omit if change spans many areas.
  - If breaking change, add ! after type/scope: feat!: or feat(api)!:
  - description: imperative mood, lowercase first letter, no period at end. Up to 200 characters—complete the sentence, never cut mid-word.

Example:
git add git_explain/cli.py git_explain/gemini.py
git commit -m "feat(cli): add opt-in --with-diff for detailed AI commit messages"
"""

ADD_LINE_RE = re.compile(r"git\s+add\s+(.+)", re.IGNORECASE)

COMMIT_LINE_RE = re.compile(
    r"git\s+commit\s+-m\s+[\"']"
    rf"({_TYPE_RE_ALT})"
    r"(?:\(([^)]*)\))?"
    r"(!?)"
    r"\s*:\s*(.+?)"
    r"[\"']",
    re.IGNORECASE,
)

_COMMIT_LINE_BRACKET_RE = re.compile(
    r"git\s+commit\s+-m\s+[\"']"
    rf"\[({_TYPE_RE_ALT})\]"
    r"\s*(.+?)"
    r"[\"']",
    re.IGNORECASE,
)

DEFAULT_MODEL = "gemini-2.5-flash"


def _normalize_type(t: str) -> str:
    upper = (t or "").upper()
    if upper == "TESTS":
        return "TEST"
    return upper if upper in VALID_TYPES else "CHORE"

# Single-line subject for `git commit -m` (no body); allow longer than classic 72 when users want detail.
MAX_COMMIT_SUBJECT_CHARS = 200


def truncate_commit_subject(
    message: str, max_len: int = MAX_COMMIT_SUBJECT_CHARS
) -> str:
    """Trim subject for one-line -m; avoid cutting off mid-parenthetical e.g. '(+2 mo'."""
    msg = (message or "").strip().rstrip(".")
    if len(msg) <= max_len:
        return msg
    cut = msg[:max_len]
    # Drop dangling "(+N …" from path-bucket fallbacks when truncation bites
    if "(+" in cut:
        idx = cut.rfind("(+")
        if idx > 0 and not cut[idx:].rstrip().endswith(")"):
            cut = cut[:idx].rstrip(" ,;")
    if " " in cut:
        cut = cut[: cut.rfind(" ")].rstrip(" ,;")
    return cut


_VAGUE_VERB_NOUN = re.compile(
    r"^(add|update|modify|make)\s+(changes?|updates?|stuff|things)\s*$",
    re.IGNORECASE,
)

# After add/update/modify/make, these tails are too vague to keep as the final message.
_VAGUE_TAIL_AFTER_VERB = frozenset(
    {
        "project files",
        "the project",
        "the codebase",
        "codebase",
        "code",
        "files",
        "file",
        "some files",
        "various files",
        "multiple files",
        "dependencies",
        "deps",
    }
)

_GENERIC_MESSAGES = {
    "update",
    "updates",
    "change",
    "changes",
    "refactor",
    "refactoring",
    "fix",
    "fixes",
    "docs",
    "documentation",
    "test",
    "tests",
    "misc",
}

CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".cs"}
_WEAK_TOPIC_WORDS = {
    "project",
    "projects",
    "repo",
    "repository",
    "codebase",
    "code",
    "app",
    "apps",
    "service",
    "services",
    "package",
    "packages",
    "module",
    "modules",
    "library",
    "libraries",
    "cli",
    "tool",
    "tools",
    "git",
    "explain",
}


def _code_topics(files: list[str]) -> list[str]:
    labeled: list[tuple[str, str]] = []  # (folder_label, stem)
    for p in files:
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


def _is_generic_message(message: str) -> bool:
    msg = (message or "").strip().lower()
    if not msg:
        return True
    if msg in _GENERIC_MESSAGES:
        return True
    if _VAGUE_VERB_NOUN.match(msg):
        return True
    parts = msg.split()
    if (
        len(parts) == 2
        and parts[0]
        in (
            "add",
            "update",
            "modify",
            "make",
        )
        and parts[1] in ("changes", "change", "updates", "update", "files", "file")
    ):
        return True
    if len(parts) >= 2 and parts[0] in (
        "add",
        "update",
        "modify",
        "make",
    ):
        tail = " ".join(parts[1:]).strip()
        if tail in _VAGUE_TAIL_AFTER_VERB:
            return True
    if len(parts) >= 2 and parts[0] in ("add", "update", "modify", "make"):
        tail_words = re.findall(r"[a-z0-9]+", " ".join(parts[1:]))
        if (
            tail_words
            and len(tail_words) <= 2
            and all(w in _WEAK_TOPIC_WORDS for w in tail_words)
        ):
            return True
    # Catch category-heavy but still vague summaries such as:
    # "Update README, docs, and CLI for project"
    if "readme" in msg and ("docs" in msg or "documentation" in msg):
        if " for " in msg and any(k in msg for k in ("cli", "project", "codebase")):
            return True
    if msg.endswith(" for project") or msg.endswith(" for codebase"):
        return True
    m_for = re.match(r"^(add|update|modify|make)\s+(.+?)\s+for\s+(.+)$", msg)
    if m_for:
        left = _alnum_key(m_for.group(2))
        right = _alnum_key(m_for.group(3))
        if left and right and (left == right or left in right or right in left):
            return True
    # "update X" is okay, but bare "update" or "update stuff" isn't
    if re.fullmatch(
        r"(update|updates|change|changes|refactor|refactoring|misc)(\s+.+)?", msg
    ):
        return msg in _GENERIC_MESSAGES or len(msg.split()) < 2
    if len(msg) < 12:
        return True
    return False


def _fallback_type_and_message(files: list[str]) -> tuple[str, str]:
    # Backward-compat wrapper (shouldn't be used now that we parse status codes)
    return _fallback_type_and_message_with_context(
        files=files, added_any=False, has_commits=True
    )


def _fallback_type_and_message_with_context(
    *,
    files: list[str],
    added_any: bool,
    has_commits: bool | None,
) -> tuple[str, str]:
    lower = [f.lower() for f in files]

    docs_exts = {".md", ".rst", ".txt"}
    code_exts = {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java"}

    def is_doc(f: str) -> bool:
        return os.path.splitext(f)[1].lower() in docs_exts or f.endswith(
            ("readme", "readme.md", "features.md")
        )

    def is_code(f: str) -> bool:
        return os.path.splitext(f)[1].lower() in code_exts

    def is_packaging(f: str) -> bool:
        return f.endswith(
            ("pyproject.toml", "requirements.txt", "setup.cfg", "setup.py")
        )

    docs_only = files and all(is_doc(f) for f in lower)
    touches_docs = any(is_doc(f) for f in lower)
    touches_packaging = any(is_packaging(f) for f in lower)

    # In fallback we don't have per-file status detail here, so use "Add" only
    # for initial commit. Otherwise prefer "Update" to avoid overclaiming.
    verb = "Add" if (has_commits is False) else "Update"

    all_test_paths = bool(files) and all(is_test_path(f) for f in files)

    if docs_only:
        commit_type = "DOCS"
    elif all_test_paths:
        commit_type = "TEST"
    elif verb == "Add":
        commit_type = "FEAT"
    else:
        commit_type = "REFACTOR"

    topics: list[str] = []
    if any(f.endswith("readme.md") or f.endswith("readme") for f in lower):
        topics.append("README")
    if any(f.endswith("features.md") for f in lower):
        topics.append("FEATURES doc")
    topics.extend(infra_deploy_topics(files))
    test_files = [f for f in files if is_test_path(f)]
    if test_files:
        all_tests_only = len(test_files) == len(files)
        hints = test_subject_hints(files)
        if all_tests_only and hints:
            if len(hints) <= 4:
                head = ", ".join(hints[:-1]) + " and " + hints[-1] if len(hints) > 1 else hints[0]
            else:
                head = ", ".join(hints[:4])
            topics.append(f"tests for {head}")
        else:
            topics.append("tests")
    if touches_docs and not docs_only:
        topics.append("docs")
    code_topics = _code_topics(files)
    if code_topics:
        topics.append(", ".join(code_topics[:5]))
    if touches_packaging:
        topics.append("packaging config")

    # Dedupe while keeping order
    seen: set[str] = set()
    topics = [t for t in topics if not (t in seen or seen.add(t))]

    if not topics:
        fb = basename_fallback_topic(files)
        topics = [fb] if fb else ["project files"]

    if len(topics) == 1:
        msg = f"{verb} {topics[0]}"
    elif len(topics) == 2:
        msg = f"{verb} {topics[0]} and {topics[1]}"
    else:
        msg = f"{verb} {topics[0]}, {topics[1]}, and {topics[2]}"

    scope = area_scope_suffix(files)
    if scope:
        scope_key = _alnum_key(scope.replace("for", "", 1))
        msg_key = _alnum_key(msg)
        if scope_key and scope_key not in msg_key:
            msg += scope

    if verb == "Add" and (has_commits is False):
        # Make initial commits a little clearer but still "Add …"
        msg = msg.replace("Add ", "Add initial ", 1) if msg.startswith("Add ") else msg

    if _is_generic_message(msg):
        fb = basename_fallback_topic(files)
        if fb:
            msg = f"{verb} {fb}"

    msg = truncate_commit_subject(msg)
    return commit_type, msg


def _parse_changed_file_list(diff: str) -> tuple[list[tuple[str, str]], bool | None]:
    """Parse the combined changed-file list into [(status, path)], plus has_commits if present."""
    entries: list[tuple[str, str]] = []
    section: str | None = None
    has_commits: bool | None = None
    for raw in diff.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section == "Meta" and line.lower().startswith("has_commits:"):
            v = line.split(":", 1)[1].strip().lower()
            if v in ("true", "false"):
                has_commits = v == "true"
            continue
        m = re.match(r"^([AMDRCUT])\s+(.+)$", line, re.IGNORECASE)
        if m:
            status = m.group(1).upper()
            path = m.group(2).strip()
            entries.append((status, path))
        else:
            # Backward compatibility: treat as modified path
            entries.append(("M", line))
    return entries, has_commits


@dataclass
class Suggestion:
    add_args: list[str]
    commit_type: str
    commit_message: str
    scope: str | None = None
    body: str | None = None
    breaking: bool = False


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY in environment.")
    return genai.Client(api_key=api_key)


def suggest_commands(
    diff: str,
    model: str | None = None,
    with_diff: bool = False,
    *,
    unified_diff_for_infer: str | None = None,
) -> tuple[Suggestion | None, str]:
    """Call Gemini with the file list (and optionally full diff); return (suggestion, raw_response). suggestion is None if unparseable.

    ``unified_diff_for_infer`` optional text (staged+unstaged unified diff) used to
    refine REFACTOR/FEAT into FIX when the diff matches behavior-fix patterns
    (e.g. ``--staged-only``), including when ``with_diff`` is False.
    """
    if not diff or not diff.strip():
        return None, ""
    model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
    system_instruction = SYSTEM_PROMPT_WITH_DIFF if with_diff else SYSTEM_PROMPT
    client = _get_client()
    last_err = None
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=model,
                contents=diff.strip(),
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                    max_output_tokens=1536 if with_diff else 512,
                ),
            )
            break
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if attempt == 0 and (
                "429" in err_str
                or "resource_exhausted" in err_str
                or "quota" in err_str
            ):
                wait = 15
                if "retry in " in err_str:
                    m = re.search(
                        r"retry in (\d+(?:\.\d+)?)\s*s", err_str, re.IGNORECASE
                    )
                    if m:
                        wait = min(60, max(5, int(float(m.group(1)) + 1)))
                time.sleep(wait)
                continue
            raise
    else:
        if last_err is not None:
            raise last_err
        raise RuntimeError("Unexpected state in suggest_commands")
    text = (response.text or "").strip()
    raw = text
    # Strip markdown code block if present
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    add_args: list[str] = []
    commit_type = "REFACTOR"
    commit_message = "update"
    scope: str | None = None
    breaking = False
    for line in lines:
        add_m = ADD_LINE_RE.match(line)
        if add_m:
            add_args = [f.strip() for f in add_m.group(1).split() if f.strip()]
            continue
        commit_m = COMMIT_LINE_RE.match(line)
        if commit_m:
            commit_type = _normalize_type(commit_m.group(1))
            scope = commit_m.group(2) or None
            breaking = commit_m.group(3) == "!"
            commit_message = commit_m.group(4).strip().rstrip(".")
            break
        bracket_m = _COMMIT_LINE_BRACKET_RE.match(line)
        if bracket_m:
            commit_type = _normalize_type(bracket_m.group(1))
            commit_message = bracket_m.group(2).strip().rstrip(".")
            break
    if not add_args or not commit_message:
        return None, raw

    header_only = diff
    if with_diff:
        header_only = diff.split("\n## Diff", 1)[0]

    entries, has_commits = _parse_changed_file_list(header_only.strip())
    all_paths = [p for _, p in entries]
    added_any = any(s == "A" for s, _ in entries)

    if all_paths:
        add_args = all_paths

    docs_only = all_paths and all(
        os.path.splitext(p)[1].lower() in {".md", ".rst", ".txt"} for p in all_paths
    )
    if (added_any or has_commits is False) and commit_type == "REFACTOR":
        commit_type = "DOCS" if docs_only else "FEAT"

    if _is_generic_message(commit_message):
        commit_type, commit_message = _fallback_type_and_message_with_context(
            files=add_args, added_any=added_any, has_commits=has_commits
        )

    if scope is None:
        scope = infer_scope(add_args)

    infer_body = unified_diff_for_infer
    if not (infer_body and infer_body.strip()) and with_diff and "\n## Diff" in diff:
        infer_body = diff.split("\n## Diff", 1)[1]
    commit_type, commit_message = refine_type_and_message_from_diff(
        commit_type, commit_message, infer_body
    )

    return Suggestion(
        add_args=add_args,
        commit_type=commit_type,
        commit_message=commit_message,
        scope=scope,
        breaking=breaking,
    ), raw
