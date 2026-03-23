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
    infra_deploy_topics,
    is_test_path,
    test_subject_hints,
)

SYSTEM_PROMPT = """You are given a list of changed/added files under ## Staged, ## Unstaged, ## Untracked.
Each file line is: <STATUS> <PATH> where STATUS is one of:
- A = added/new file
- M = modified
- D = deleted
- R = renamed
- C = copied

Suggest one commit that includes ALL of these files.

Rules:
1. Line 1 must be: git add <path1> <path2> ... with EVERY PATH from the list (all sections). Do not omit any file. Do not truncate. Do not include status letters.
2. Line 2 must be: git commit -m "[TYPE] Message" with TYPE one of: FEAT, FIX, DOCS, REFACTOR, TEST, CHORE.
3. The message must be a short, specific summary of what the change does based on the file names (e.g. "Add README and feature status doc", "Fix Gemini model and add file-list mode"). Never use only generic words like "update", "changes", or "refactor" by themselves—always add what was updated (e.g. "Update docs and CLI prompt").
4. Infer concrete artifacts from paths when obvious: Dockerfiles, Docker Compose files, nginx configs, .env/.env.example templates, CI workflows—not vague summaries like "add changes" or "add files" with no subject. For test paths (e.g. tests/test_foo.py), name the area under test (e.g. "Expand tests for foo and bar")—not "update project files".
5. Use [FIX] (or "fix:" with --with-diff) when the change corrects broken behavior, wrong CLI flow, or misleading errors—not [REFACTOR] for those cases.
6. Use imperative, no period at end. Maximum one short line.

Example for files README.md, FEATURES.md, git_explain/gemini.py:
git add README.md FEATURES.md git_explain/gemini.py
git commit -m "[DOCS] Add README and FEATURES doc, tune Gemini prompt"

Example for Docker + nginx + env templates under api/ and apps/frontend/:
git add api/app/Dockerfile apps/frontend/nginx.conf
git commit -m "[CHORE] Add Docker and nginx config with env examples for api and frontend"
"""

SYSTEM_PROMPT_WITH_DIFF = """You are given:
1. A list of changed/added files (## Staged, ## Unstaged, ## Untracked) with <STATUS> <PATH>.
2. The full diff (## Staged diff, ## Unstaged diff, ## Untracked) showing exact code changes.

Use the diff to write a specific, detailed commit message. Do not use generic words like "update" or "changes"—describe what actually changed (e.g. "add opt-in --with-diff to send full diff to LLM for detailed messages", "tweak commit message edit flow to show suggestion before prompting to edit").
Name concrete pieces from paths when helpful (Docker, nginx, env templates, workflows)—avoid empty phrases like "add changes" that do not say what was added.
Prefer **fix:** when the diff corrects incorrect behavior or user-visible bugs; use **refactor:** only for internal restructuring without behavior change.

Output format (conventional commits style):
- Line 1: git add <path1> <path2> ... with EVERY path from the file list. Do not omit any.
- Line 2: git commit -m "type: subject" where type is exactly one of: feat, fix, docs, refactor, test, chore.
  The subject must be a short, specific summary in imperative mood, no period at end (e.g. "feat: allow editing commit message before apply", "fix: parse conventional commit line from AI").

Example:
git add git_explain/cli.py git_explain/gemini.py
git commit -m "feat: add opt-in --with-diff for detailed AI commit messages"
"""

ADD_LINE_RE = re.compile(r"git\s+add\s+(.+)", re.IGNORECASE)
COMMIT_LINE_RE = re.compile(
    r'git\s+commit\s+-m\s+["\']\[(FEAT|FIX|DOCS|REFACTOR|TESTS|CHORE)\]\s*(.+?)["\']',
    re.IGNORECASE,
)
# Conventional: "feat: subject" or "fix: subject" (use "tests" not "test")
COMMIT_LINE_CONVENTIONAL_RE = re.compile(
    r'git\s+commit\s+-m\s+["\'](feat|fix|docs|refactor|tests|chore)\s*:\s*(.+?)["\']',
    re.IGNORECASE,
)
DEFAULT_MODEL = "gemini-2.5-flash"

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

    verb = "Add" if (added_any or has_commits is False) else "Update"

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
            head = " and ".join(hints[:3])
            tail = f" (+{len(hints) - 3} more)" if len(hints) > 3 else ""
            topics.append(f"tests for {head}{tail}")
        else:
            topics.append("tests")
    if touches_docs and not docs_only:
        topics.append("docs")
    if any(f.startswith("git_explain/") for f in lower) or any(
        "/git_explain/" in f for f in lower
    ):
        topics.append("git-explain CLI")
    if any("git_explain/gemini.py" in f for f in lower):
        topics.append("Gemini integration")
    if any("git_explain/git.py" in f for f in lower):
        topics.append("change detection")
    if any("git_explain/cli.py" in f for f in lower):
        topics.append("CLI output")
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

    msg += area_scope_suffix(files)

    if verb == "Add" and (has_commits is False):
        # Make initial commits a little clearer but still "Add …"
        msg = msg.replace("Add ", "Add initial ", 1) if msg.startswith("Add ") else msg

    msg = msg.strip().rstrip(".")
    if len(msg) > 72:
        msg = msg[:72].rstrip()
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
        m = re.match(r"^([AMDRCU])\s+(.+)$", line, re.IGNORECASE)
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
                    max_output_tokens=512 if with_diff else 256,
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
    for line in lines:
        add_m = ADD_LINE_RE.match(line)
        if add_m:
            add_args = [f.strip() for f in add_m.group(1).split() if f.strip()]
            continue
        commit_m = COMMIT_LINE_CONVENTIONAL_RE.match(line) if with_diff else None
        if commit_m:
            commit_type = commit_m.group(1).upper()
            commit_message = commit_m.group(2).strip().rstrip(".")
            break
        commit_m = COMMIT_LINE_RE.match(line)
        if commit_m:
            commit_type = commit_m.group(1).upper()
            commit_message = commit_m.group(2).strip().rstrip(".")
            break
    if not add_args or not commit_message:
        return None, raw

    header_only = diff
    if with_diff:
        header_only = diff.split("\n## Diff", 1)[0]

    entries, has_commits = _parse_changed_file_list(header_only.strip())
    all_paths = [p for _, p in entries]
    added_any = any(s == "A" for s, _ in entries)

    # Always use the full path list we sent (model may truncate or omit)
    if all_paths:
        add_args = all_paths

    # If we're adding new files (or this is an initial commit), don't label it REFACTOR
    docs_only = all_paths and all(
        os.path.splitext(p)[1].lower() in {".md", ".rst", ".txt"} for p in all_paths
    )
    if (added_any or has_commits is False) and commit_type == "REFACTOR":
        commit_type = "DOCS" if docs_only else "FEAT"

    if _is_generic_message(commit_message):
        commit_type, commit_message = _fallback_type_and_message_with_context(
            files=add_args, added_any=added_any, has_commits=has_commits
        )

    infer_body = unified_diff_for_infer
    if not (infer_body and infer_body.strip()) and with_diff and "\n## Diff" in diff:
        infer_body = diff.split("\n## Diff", 1)[1]
    commit_type, commit_message = refine_type_and_message_from_diff(
        commit_type, commit_message, infer_body
    )

    return Suggestion(
        add_args=add_args, commit_type=commit_type, commit_message=commit_message
    ), raw
