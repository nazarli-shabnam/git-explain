"""CLI for git-explain: suggest and optionally apply commit message from diffs."""

import os
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from collections.abc import Callable
from typing import Iterable

import typer
from dotenv import dotenv_values
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from git_explain.gemini import DEFAULT_MODEL, Suggestion, suggest_commands
from git_explain.heuristics import suggest_from_changes
from git_explain.git import (
    get_combined_diff,
    get_diff_for_paths,
    get_staged_diff_for_paths,
)
from git_explain.run import (
    apply_commands,
    format_commit_message,
    normalize_commit_subject_for_dash_m,
)

app = typer.Typer()
console = Console()

_DIFF_INFER_MAX_CHARS = 50_000
_AI_ENV_KEYS = (
    "AI_MODEL",
    "AI_API_KEY",
    "GEMINI_API_KEY",
    "AI_MODEL_FALLBACKS",
)
# Terminal hyperlinks (OSC 8) for first-run setup — Ctrl+click in supported terminals.
_GOOGLE_AI_API_KEY_URL = "https://aistudio.google.com/apikey"


def _gemini_fallback_notifier(
    group_label: str | None = None,
) -> Callable[[str], None]:
    """Dim one-line notices when switching models after rate limits / overload.

    ``group_label`` prefixes the line in split-commit mode (one AI call per group),
    so repeated "primary busy" messages are distinguishable.
    """
    first: list[bool] = [True]
    prefix = f"{group_label}: " if group_label else ""

    def _notify(next_model: str) -> None:
        if first[0]:
            console.print(
                Text(
                    f"{prefix}Primary model busy; trying fallback: {next_model}",
                    style="dim",
                )
            )
            first[0] = False
        else:
            console.print(
                Text(f"{prefix}Model busy; trying fallback: {next_model}", style="dim")
            )

    return _notify


def _model_picker_line(
    num: int, label: str, link_url: str, model_id: str | None = None
) -> Text:
    """OSC 8 link on `label`; optional cyan tail in parentheses (e.g. model id)."""
    line = Text()
    line.append(f"  {num}. ")
    line.append(label, style=f"link {link_url}")
    if model_id:
        line.append(" (")
        line.append(model_id, style="cyan")
        line.append(")")
    return line


@dataclass(frozen=True)
class Change:
    status: str  # A/M/D/R/C
    path: str
    sections: tuple[str, ...]  # Staged/Unstaged/Untracked


def _ps_quote(arg: str) -> str:
    # PowerShell single-quote escaping: ' becomes ''
    return "'" + arg.replace("'", "''") + "'"


def _parse_combined(combined: str) -> tuple[bool | None, list[Change]]:
    has_commits: bool | None = None
    section: str | None = None
    by_path: dict[str, dict[str, object]] = {}
    for raw in combined.splitlines():
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
        # A/M/D/R/C: add/modify/delete/rename/copy; T: type change; U: unmerged (git name-status)
        m = re.match(r"^([AMDRCUT])\s+(.+)$", line, re.IGNORECASE)
        if not m:
            continue
        status = m.group(1).upper()
        path = m.group(2).strip()
        rec = by_path.get(path)
        if rec is None:
            by_path[path] = {"status": status, "sections": {section or "Unknown"}}
        else:
            rec["sections"].add(section or "Unknown")  # type: ignore[union-attr]
            # Prefer A over M, M over others for display
            cur = rec["status"]  # type: ignore[index]
            if cur != "A" and status == "A":
                rec["status"] = "A"  # type: ignore[index]
            elif cur not in ("A", "M") and status == "M":
                rec["status"] = "M"  # type: ignore[index]
    changes: list[Change] = []
    for path, rec in sorted(by_path.items(), key=lambda kv: kv[0].lower()):
        changes.append(
            Change(
                status=str(rec["status"]),
                path=path,
                sections=tuple(sorted(rec["sections"])),  # type: ignore[arg-type]
            )
        )
    return has_commits, changes


def _load_ai_env_from_dotenv(dotenv_path: Path) -> None:
    """Load only AI-related vars from .env, overriding existing process values."""
    values = dotenv_values(dotenv_path)
    for key in _AI_ENV_KEYS:
        raw = values.get(key)
        if raw is None:
            continue
        val = str(raw).strip()
        if val:
            os.environ[key] = val


def _upsert_env_var(dotenv_path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    if dotenv_path.exists():
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    replaced = False
    out: list[str] = []
    prefix = key + "="
    for ln in lines:
        if ln.startswith(prefix):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    dotenv_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _ensure_repo_env_file(repo_env: Path) -> bool:
    if repo_env.is_file():
        return True
    create = (
        typer.prompt("No .env found. Create one now? (y/n)", default="y")
        .strip()
        .lower()
    )
    if create not in ("y", "yes"):
        return False
    repo_env.write_text("", encoding="utf-8")
    return True


def _choose_and_persist_ai_model(repo_env: Path) -> str:
    """First run: set default Gemini model and reload .env for API keys."""
    console.print(
        Text(
            "Add your API key to .env (create one in Google AI Studio if needed):",
            style="dim",
        )
    )
    console.print(
        _model_picker_line(
            1,
            "Google AI Studio",
            _GOOGLE_AI_API_KEY_URL,
            model_id=DEFAULT_MODEL,
        )
    )
    model = DEFAULT_MODEL
    _upsert_env_var(repo_env, "AI_MODEL", model)
    os.environ["AI_MODEL"] = model
    if repo_env.is_file():
        _load_ai_env_from_dotenv(repo_env)
    return model


def _resolve_project_ai_model(repo_env: Path, model_override: str | None) -> str | None:
    if model_override:
        return model_override
    model = (os.environ.get("AI_MODEL") or "").strip()
    if model:
        return model
    if not _ensure_repo_env_file(repo_env):
        return None
    return _choose_and_persist_ai_model(repo_env)


def _render_combined(
    has_commits: bool | None, items: Iterable[tuple[str, str]], title: str
) -> str:
    parts = []
    if has_commits is not None:
        parts.append("## Meta\nhas_commits: " + ("true" if has_commits else "false"))
    parts.append(f"## {title}\n" + "\n".join([f"{s} {p}" for s, p in items]))
    return "\n\n".join(parts).strip()


def _parse_selection(selection: str, n: int) -> tuple[list[int], list[str]]:
    """Parse a selection string into numeric indices and explicit path tokens.

    Supports:
    - \"\" / a / all        -> all indices 1..n
    - 1,2,5-7              -> numeric indices/ranges
    - anything not numeric -> treated as a path token (e.g. git_explain/cli.py)
    """
    s = (selection or "").strip()
    if s.lower() in ("", "a", "all"):
        return list(range(1, n + 1)), []
    out_indices: set[int] = set()
    path_tokens: list[str] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                start = int(a.strip())
                end = int(b.strip())
            except ValueError:
                path_tokens.append(part)
                continue
            for i in range(min(start, end), max(start, end) + 1):
                if 1 <= i <= n:
                    out_indices.add(i)
            continue
        try:
            i = int(part)
        except ValueError:
            path_tokens.append(part)
            continue
        if 1 <= i <= n:
            out_indices.add(i)
    return sorted(out_indices), path_tokens


def _group_changes(changes: list[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    # Simple grouping: docs, tests, config, code, other
    def is_doc(p: str) -> bool:
        p2 = p.lower()
        return p2.endswith((".md", ".rst", ".txt")) or p2.endswith(
            ("readme", "readme.md", "features.md")
        )

    def is_test(p: str) -> bool:
        p2 = p.lower().replace("\\", "/")
        base = p2.split("/")[-1]
        return (
            p2.startswith("tests/")
            or "/tests/" in p2
            or base.startswith("test_")
            or base.endswith("_test.py")
            or ".spec." in base
        )

    def is_config(p: str) -> bool:
        p2 = p.lower()
        base = p2.split("/")[-1].split("\\")[-1]
        return base in {
            "pyproject.toml",
            "requirements.txt",
            "setup.cfg",
            "setup.py",
            ".gitignore",
        } or p2.endswith((".toml", ".yml", ".yaml", ".json", ".ini", ".cfg", ".lock"))

    def is_code(p: str) -> bool:
        p2 = p.lower()
        return p2.endswith(
            (".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".cs")
        )

    groups: dict[str, list[tuple[str, str]]] = {
        "docs": [],
        "tests": [],
        "config": [],
        "code": [],
        "other": [],
    }
    for st, p in changes:
        if is_doc(p):
            groups["docs"].append((st, p))
        elif is_test(p):
            groups["tests"].append((st, p))
        elif is_config(p):
            groups["config"].append((st, p))
        elif is_code(p):
            groups["code"].append((st, p))
        else:
            groups["other"].append((st, p))
    return {k: v for k, v in groups.items() if v}


def _validate_suggest_flags(
    *,
    suggest: bool,
    auto: bool,
    staged_only: bool,
    model: str | None,
    with_diff: bool,
) -> None:
    if not suggest:
        return
    bad: list[str] = []
    if auto:
        bad.append("--auto")
    if staged_only:
        bad.append("--staged-only")
    if with_diff:
        bad.append("--with-diff")
    if bad:
        raise typer.BadParameter(
            "--suggest is a dedicated mode and cannot be combined with: "
            + ", ".join(bad)
        )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    auto: bool = typer.Option(
        False, "--auto", help="Apply suggestion without prompting"
    ),
    staged_only: bool = typer.Option(
        False,
        "--staged-only",
        help="Commit only already-staged changes (do not run git add). Useful for partial staging.",
    ),
    cwd: str | None = typer.Option(
        None, "--cwd", help="Working directory (default: current)"
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Override AI model for this run (defaults to AI_MODEL from repo .env).",
    ),
    with_diff: bool = typer.Option(
        False,
        "--with-diff",
        help="Send full diff to the configured AI model for more specific messages (opt-in).",
    ),
    suggest: bool = typer.Option(
        False,
        "--suggest",
        help="AI suggestion-only mode: use staged files + staged diff and print only commit command.",
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    _validate_suggest_flags(
        suggest=suggest,
        auto=auto,
        staged_only=staged_only,
        model=model,
        with_diff=with_diff,
    )
    run(
        cwd=Path(cwd) if cwd else None,
        auto=auto,
        staged_only=staged_only,
        model=model,
        with_diff=with_diff,
        suggest=suggest,
    )


def run(
    cwd: Path | None = None,
    auto: bool = False,
    staged_only: bool = False,
    model: str | None = None,
    with_diff: bool = False,
    suggest: bool = False,
) -> None:
    console.print(Text("git-explain", style="bold"))

    try:
        combined, repo_root = get_combined_diff(cwd=cwd)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    repo_env = repo_root / ".env"
    if repo_env.is_file():
        _load_ai_env_from_dotenv(repo_env)

    if not combined.strip():
        console.print("[yellow]No staged, unstaged, or untracked changes.[/yellow]")
        return
    ai_model = _resolve_project_ai_model(repo_env, model)
    if repo_env.is_file():
        _load_ai_env_from_dotenv(repo_env)
    has_commits, changes = _parse_combined(combined)
    console.print(Panel(combined, title="Changed files", border_style="dim"))

    if suggest:
        staged_changes = [c for c in changes if "Staged" in c.sections]
        if not staged_changes:
            console.print(
                "[yellow]Warning:[/yellow] --suggest requires staged changes. "
                "Stage files first (git add ...), then run --suggest again."
            )
            raise typer.Exit(1)
        selected_pairs = [(ch.status, ch.path) for ch in staged_changes]
        payload = _render_combined(has_commits, selected_pairs, title="Staged")
        paths = [p for _, p in selected_pairs]
        staged_diff = get_staged_diff_for_paths(paths, cwd=repo_root)
        if staged_diff:
            payload = payload + "\n\n## Diff\n" + staged_diff
        infer_diff = (
            staged_diff[:_DIFF_INFER_MAX_CHARS]
            if len(staged_diff) > _DIFF_INFER_MAX_CHARS
            else staged_diff
        )
        if not ai_model:
            console.print(
                "[red]Error:[/red] --suggest requires an AI model. "
                "Set AI_MODEL in repo .env or pass --model."
            )
            raise typer.Exit(1)
        try:
            sug, _raw = suggest_commands(
                payload,
                model=ai_model,
                with_diff=bool(staged_diff),
                unified_diff_for_infer=infer_diff,
                fallback_notifier=_gemini_fallback_notifier(),
            )
            if sug is None:
                raise RuntimeError("Could not parse AI suggestion.")
        except Exception as e:
            console.print(
                f"[red]Error:[/red] --suggest requires AI and failed to get a suggestion: {e}"
            )
            raise typer.Exit(1)

        cmsg = normalize_commit_subject_for_dash_m(sug.commit_message)
        full = format_commit_message(
            sug.commit_type, cmsg, scope=sug.scope, breaking=sug.breaking
        )
        print(f'git commit -m "{full}"')
        return

    if staged_only:
        changes = [c for c in changes if "Staged" in c.sections]
        console.print(
            "[dim]Note:[/dim] staged-only mode: only already-staged files are selectable."
        )

    if not changes:
        console.print("[yellow]No selectable changes found.[/yellow]")
        return

    norm_paths = [c.path.replace("\\", "/") for c in changes]
    display_items: list[tuple[str, list[int]]] = []
    for idx, ch in enumerate(changes):
        sec = ",".join([s.lower() for s in ch.sections if s and s != "Meta"])
        label = f"[{ch.status}] ({sec}) {ch.path}"
        display_items.append((label, [idx]))

    lines = []
    for idx, (label, _idxs) in enumerate(display_items, start=1):
        lines.append(f"{idx:>2}. {label}")
    console.print(Panel("\n".join(lines), title="Select files", border_style="blue"))
    selection = typer.prompt(
        "Select files to include (e.g. 1,2,5-7, 'all', or a path like folder/file.txt)",
        default="all",
    )
    picks, path_tokens = _parse_selection(selection, len(display_items))
    if not picks and not path_tokens:
        console.print("[yellow]No files selected.[/yellow]")
        return

    selected_indices: set[int] = set()
    for display_idx in picks:
        if 1 <= display_idx <= len(display_items):
            _, idxs = display_items[display_idx - 1]
            selected_indices.update(idxs)

    for token in path_tokens:
        t_norm = token.replace("\\", "/").strip()
        for idx, np in enumerate(norm_paths):
            if np == t_norm or np.startswith(t_norm.rstrip("/") + "/"):
                selected_indices.add(idx)

    if not selected_indices:
        console.print("[yellow]No files matched your selection.[/yellow]")
        return

    selected = [changes[i] for i in sorted(selected_indices)]
    if not staged_only:
        risky = [
            c for c in selected if ("Staged" in c.sections and "Unstaged" in c.sections)
        ]
        if risky:
            msg = "\n".join([f"- {c.path}" for c in risky])
            console.print(
                Panel(
                    "These files have both staged and unstaged changes.\n"
                    "If you apply, git-explain will stage the whole file, which can override partial staging.\n\n"
                    + msg
                    + "\n\nTip: re-run with --staged-only to commit only what's already staged.",
                    title="Warning: partial staging",
                    border_style="yellow",
                )
            )
            cont = typer.prompt("Continue anyway? (y/n)", default="n").strip().lower()
            if cont not in ("y", "yes"):
                return

    def suggest_for(
        change_items: list[tuple[str, str]], title: str
    ) -> tuple[Suggestion, str | None]:
        """Return (suggestion, ai_fallback_reason)."""
        paths_for_infer = [p for _, p in change_items]
        infer_diff: str | None = None
        if paths_for_infer:
            raw_d = get_diff_for_paths(paths_for_infer, cwd=repo_root)
            if raw_d.strip():
                infer_diff = (
                    raw_d[:_DIFF_INFER_MAX_CHARS]
                    if len(raw_d) > _DIFF_INFER_MAX_CHARS
                    else raw_d
                )

        if ai_model:
            payload = _render_combined(has_commits, change_items, title=title)
            if with_diff:
                paths_for_diff = [p for _, p in change_items]
                diff_text = get_diff_for_paths(paths_for_diff, cwd=repo_root)
                if diff_text:
                    payload = payload + "\n\n## Diff\n" + diff_text
            try:
                fb_label = title if mode == "split" else None
                sug, _raw = suggest_commands(
                    payload,
                    model=ai_model,
                    with_diff=with_diff,
                    unified_diff_for_infer=infer_diff,
                    fallback_notifier=_gemini_fallback_notifier(fb_label),
                )
                if sug is None:
                    raise RuntimeError("Could not parse AI suggestion.")
                return sug, None
            except Exception as e:
                h = suggest_from_changes(
                    changes=change_items,
                    has_commits=has_commits,
                    diff_text=infer_diff,
                )
                return h, str(e)
        h = suggest_from_changes(
            changes=change_items,
            has_commits=has_commits,
            diff_text=infer_diff,
        )
        return h, None

    selected_pairs = [(ch.status, ch.path) for ch in selected]
    unique_paths = {p for _, p in selected_pairs}

    mode = "one"
    if len(unique_paths) > 1:
        if staged_only:
            console.print(
                "[dim]Note:[/dim] split commits are not available with --staged-only: "
                "each commit would need its own staging, but this mode skips git add. "
                "Using a single commit for everything currently staged."
            )
        else:
            mode_input = (
                typer.prompt("Commit mode: one or split", default="one").strip().lower()
            )
            if mode_input in ("one", "split"):
                mode = mode_input

    plan: list[tuple[str, Suggestion]] = []
    ai_fallback_notes: list[tuple[str, str]] = []
    if mode == "split":
        groups = _group_changes(selected_pairs)
        for gname, items in groups.items():
            sug, fb = suggest_for(items, title=gname.capitalize())
            plan.append((gname, sug))
            if fb:
                ai_fallback_notes.append((gname, fb))
    else:
        sug, fb = suggest_for(selected_pairs, title="Selected")
        plan.append(("one", sug))
        if fb:
            ai_fallback_notes.append(("", fb))

    if ai_model and ai_fallback_notes:
        key_help = "Check AI_API_KEY, AI_MODEL, AI_MODEL_FALLBACKS, quota/model availability, and network."
        lines = [
            "[bold]Configured AI was not used for the suggestion below.[/bold]",
            "Commit message(s) come from [bold]local heuristics[/bold] instead.",
            "",
        ]
        if mode == "split":
            for gname, reason in ai_fallback_notes:
                lines.append(f"[dim]{gname}:[/dim] {reason}")
        else:
            lines.append(ai_fallback_notes[0][1])
        lines.append("")
        lines.append(f"[dim]{key_help}[/dim]")
        console.print(
            Panel(
                "\n".join(lines),
                title="[yellow]Warning: AI unavailable[/yellow]",
                border_style="yellow",
            )
        )

    def _render_plan(pl: list[tuple[str, Suggestion]]) -> str:
        rendered: list[str] = []
        for name, sug in pl:
            add_line = "git add -A -- " + " ".join(_ps_quote(p) for p in sug.add_args)
            subj = normalize_commit_subject_for_dash_m(sug.commit_message)
            full = format_commit_message(
                sug.commit_type, subj, scope=sug.scope, breaking=sug.breaking
            )
            commit_line = f'git commit -m "{full}"'
            rendered.append(f"### {name}\n{add_line}\n{commit_line}")
        return "\n\n".join(rendered)

    console.print(
        Panel(
            _render_plan(plan),
            title="Suggested commands",
            border_style="green",
        )
    )

    if not auto:
        edit_choice = (
            typer.prompt(
                "Edit commit message(s) before applying? (y/n)",
                default="n",
            )
            .strip()
            .lower()
        )
        if edit_choice in ("y", "yes"):
            updated: list[tuple[str, Suggestion]] = []
            for name, sug in plan:
                current = format_commit_message(
                    sug.commit_type,
                    sug.commit_message,
                    scope=sug.scope,
                    breaking=sug.breaking,
                )
                console.print(
                    f"[dim]{name}:[/dim] current message: [bold]{current}[/bold]"
                )
                try:
                    from prompt_toolkit import prompt as pt_prompt

                    new_msg = (
                        pt_prompt(
                            "New commit message (subject only, type/scope added automatically): ",
                            default=sug.commit_message,
                        ).strip()
                        or sug.commit_message
                    )
                except Exception:
                    new_msg = (
                        typer.prompt(
                            "New commit message (subject only, type/scope added automatically)",
                            default=sug.commit_message,
                        ).strip()
                    ) or sug.commit_message
                updated.append((name, replace(sug, commit_message=new_msg)))
            plan = updated
            console.print(
                Panel(
                    _render_plan(plan),
                    title="Updated commands",
                    border_style="green",
                )
            )

    if auto:
        do_apply = True
    else:
        prompt = (
            "Apply these commit(s)? (y/n)"
            if len(plan) > 1
            else "Apply these commands? (y/n)"
        )
        choice = typer.prompt(prompt, default="y").strip().lower()
        do_apply = choice in ("y", "yes")

    if do_apply:
        for name, sug in plan:
            try:
                apply_commands(
                    repo_root,
                    [] if staged_only else sug.add_args,
                    sug.commit_type,
                    sug.commit_message,
                    scope=sug.scope,
                    body=sug.body,
                    breaking=sug.breaking,
                    staged_only=staged_only,
                )
                console.print(f"[green]Commit created ({name}).[/green]")
            except subprocess.CalledProcessError as e:
                console.print("[red]git command failed.[/red]")
                console.print(f"[dim]Command:[/dim] {e.cmd}")
                if e.stdout:
                    console.print(e.stdout)
                if e.stderr:
                    console.print(e.stderr)
                raise typer.Exit(1)
            except RuntimeError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1)
