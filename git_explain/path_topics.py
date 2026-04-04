"""Derive concrete commit-message topics from paths (Docker, nginx, env templates, areas)."""

from __future__ import annotations

import os


def _norm(p: str) -> str:
    return p.replace("\\", "/").strip()


_TEST_HINTS = ("pytest", "unittest", "tests/", "/tests/")


def is_test_path(path: str) -> bool:
    """True if path looks like a test file (mirrors heuristics rules; paths normalized)."""
    p = _norm(path).lower()
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
    return any(h in p for h in _TEST_HINTS)


def test_subject_hints(paths: list[str]) -> list[str]:
    """Short labels from test filenames, e.g. test_gemini.py -> gemini (deduped, stable order)."""
    hints: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if not is_test_path(raw):
            continue
        base = os.path.basename(_norm(raw))
        stem, _ext = os.path.splitext(base)
        s = stem
        low = s.lower()
        if low.startswith("test_"):
            core = s[5:]
        elif low.endswith("_test"):
            core = s[: -len("_test")]
        else:
            core = s
        core = core.strip().replace("_", " ").strip()
        if not core:
            continue
        key = core.lower()
        if key not in seen:
            seen.add(key)
            hints.append(core)
    return hints


def is_infra_deploy_path(path: str) -> bool:
    """True if path looks like Docker, Compose, nginx, or env-template deploy config."""
    p = _norm(path).lower()
    base = os.path.basename(p)
    if base == "dockerfile" or base.endswith(".dockerfile"):
        return True
    if base == ".dockerignore":
        return True
    if base.startswith("docker-compose") and base.endswith((".yml", ".yaml")):
        return True
    if base in ("compose.yaml", "compose.yml"):
        return True
    if "nginx" in base and base.endswith(".conf"):
        return True
    if base.endswith((".env.example", ".env.sample")):
        return True
    if base in ("compose.env.example", ".env.example"):
        return True
    return False


def infra_deploy_topics(paths: list[str]) -> list[str]:
    """Ordered, deduplicated topic phrases (no leading verb)."""
    has_dockerfile = False
    has_dockerignore = False
    has_compose = False
    has_nginx = False
    has_env_example = False

    for raw in paths:
        p = _norm(raw).lower()
        base = os.path.basename(p)
        if base == "dockerfile" or base.endswith(".dockerfile"):
            has_dockerfile = True
        if base == ".dockerignore":
            has_dockerignore = True
        if base.startswith("docker-compose") and base.endswith((".yml", ".yaml")):
            has_compose = True
        if base in ("compose.yaml", "compose.yml"):
            has_compose = True
        if "nginx" in base and base.endswith(".conf"):
            has_nginx = True
        if base.endswith((".env.example", ".env.sample")):
            has_env_example = True
        if base in ("compose.env.example", ".env.example"):
            has_env_example = True

    topics: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        if s not in seen:
            seen.add(s)
            topics.append(s)

    if has_dockerfile or has_dockerignore:
        add("Docker")
    if has_compose:
        add("Docker Compose")
    if has_nginx:
        add("nginx")
    if has_env_example:
        add("env examples")

    return topics


def area_scope_suffix(paths: list[str]) -> str:
    """Return ' for api and frontend' style suffix, or ''."""
    labels: list[str] = []
    seen: set[str] = set()

    for raw in paths:
        p = _norm(raw)
        if not p or p == ".":
            continue
        parts = [x for x in p.split("/") if x]
        if len(parts) < 2:
            continue
        first, second = parts[0], parts[1]
        if first.lower() in {"apps", "packages", "services"}:
            label = second
        else:
            label = first
        low = label.lower()
        if low not in seen:
            seen.add(low)
            labels.append(label)

    if not labels:
        return ""

    def fmt(lbl: str) -> str:
        return "API" if lbl.lower() == "api" else lbl

    labels = [fmt(x) for x in labels]
    if len(labels) == 1:
        return f" for {labels[0]}"
    if len(labels) == 2:
        return f" for {labels[0]} and {labels[1]}"
    return f" for {labels[0]}, {labels[1]}, and {labels[2]}"


_CI_FILES = {
    ".gitlab-ci.yml",
    ".travis.yml",
    "azure-pipelines.yml",
    "jenkinsfile",
    "bitbucket-pipelines.yml",
}


def is_ci_path(path: str) -> bool:
    """True if path looks like a CI/CD configuration file."""
    p = _norm(path).lower()
    base = os.path.basename(p)
    if ".github/workflows/" in p or ".github/actions/" in p:
        return True
    if base in _CI_FILES:
        return True
    if ".circleci/" in p:
        return True
    return False


_BUILD_FILES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "makefile",
    "gnumakefile",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "cargo.toml",
    "cargo.lock",
    "go.mod",
    "go.sum",
    "gemfile",
    "gemfile.lock",
    "build.gradle",
    "pom.xml",
}


def is_build_path(path: str) -> bool:
    """True if path is a build system, packaging, or containerization file."""
    p = _norm(path).lower()
    base = os.path.basename(p)
    if base in _BUILD_FILES:
        return True
    return is_infra_deploy_path(path)


def infer_scope(paths: list[str]) -> str | None:
    """Infer a conventional commits scope from file paths.

    Returns a single scope when all non-root files share one top-level
    directory, otherwise None.
    """
    if not paths:
        return None

    candidates: set[str] = set()
    for raw in paths:
        p = _norm(raw).lower()
        parts = [x for x in p.split("/") if x]
        if len(parts) < 2:
            continue
        first = parts[0]
        if first in ("apps", "packages", "services") and len(parts) >= 3:
            candidates.add(parts[1])
        else:
            candidates.add(first)

    if len(candidates) == 1:
        return candidates.pop().replace("_", "-")
    return None


def basename_fallback_topic(paths: list[str], max_names: int = 4) -> str | None:
    """Short description from basenames when no other topic matched."""
    bases: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        b = os.path.basename(_norm(raw))
        if not b:
            continue
        key = b.lower()
        if key not in seen:
            seen.add(key)
            bases.append(b)
    if not bases:
        return None
    if len(bases) <= max_names:
        return ", ".join(bases)
    head = ", ".join(bases[:max_names])
    return f"{head} (+{len(bases) - max_names} more)"
