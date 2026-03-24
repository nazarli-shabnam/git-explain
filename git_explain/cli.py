"""CLI for git-explain: suggest and optionally apply commit message from diffs."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from git_explain.gemini import suggest_commands
from git_explain.heuristics import suggest_from_changes
from git_explain.git import (
    get_combined_diff,
    get_diff_for_paths,
    get_staged_diff_for_paths,
)
from git_explain.run import apply_commands

load_dotenv()
app = typer.Typer()
console = Console()

_DIFF_INFER_MAX_CHARS = 50_000


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
        m = __import__("re").match(
            r"^([AMDRC])\s+(.+)$", line, __import__("re").IGNORECASE
        )
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
    ai: bool,
    staged_only: bool,
    model: str | None,
    with_diff: bool,
) -> None:
    if not suggest:
        return
    bad: list[str] = []
    if auto:
        bad.append("--auto")
    if ai:
        bad.append("--ai")
    if staged_only:
        bad.append("--staged-only")
    if with_diff:
        bad.append("--with-diff")
    if model is not None:
        bad.append("--model")
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
    ai: bool = typer.Option(
        False, "--ai", help="Use Gemini to suggest commit message (default: off)"
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
        help=(
            "Override Gemini model name for --ai "
            "(defaults to GEMINI_MODEL env var or internal default)."
        ),
    ),
    with_diff: bool = typer.Option(
        False,
        "--with-diff",
        help="With --ai: send full diff to the model for detailed, specific commit messages (opt-in).",
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
        ai=ai,
        staged_only=staged_only,
        model=model,
        with_diff=with_diff,
    )
    run(
        cwd=Path(cwd) if cwd else None,
        auto=auto,
        ai=ai,
        staged_only=staged_only,
        model=model,
        with_diff=with_diff,
        suggest=suggest,
    )


def run(
    cwd: Path | None = None,
    auto: bool = False,
    ai: bool = False,
    staged_only: bool = False,
    model: str | None = None,
    with_diff: bool = False,
    suggest: bool = False,
) -> None:
    console.print(Text("git-explain", style="bold"))
    if with_diff and not ai:
        console.print(
            "[yellow]Warning:[/yellow] --with-diff has no effect without --ai. "
            "It only affects AI-generated commit messages."
        )
        enable = typer.prompt("Enable AI? (y/n)", default="n").strip().lower()
        if enable in ("y", "yes"):
            ai = True
        else:
            with_diff = False

    try:
        combined, repo_root = get_combined_diff(cwd=cwd)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if not combined.strip():
        console.print("[yellow]No staged, unstaged, or untracked changes.[/yellow]")
        return
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
        try:
            sug, _raw = suggest_commands(
                payload,
                model=None,
                with_diff=True,
                unified_diff_for_infer=infer_diff,
            )
            if sug is None:
                raise RuntimeError("Could not parse AI suggestion.")
        except Exception as e:
            console.print(
                f"[red]Error:[/red] --suggest requires AI and failed to get a suggestion: {e}"
            )
            raise typer.Exit(1)

        console.print(
            Panel(
                f'git commit -m "[{sug.commit_type}] {sug.commit_message}"',
                title="Suggested commit command",
                border_style="green",
            )
        )
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
    ) -> tuple[list[str], str, str, str, str | None]:
        # Returns (paths, type, message, raw_text, ai_fallback_reason).
        # ai_fallback_reason is set when --ai was used but heuristics were used instead.
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

        if ai:
            payload = _render_combined(has_commits, change_items, title=title)
            if with_diff:
                paths_for_diff = [p for _, p in change_items]
                diff_text = get_diff_for_paths(paths_for_diff, cwd=repo_root)
                if diff_text:
                    payload = payload + "\n\n## Diff\n" + diff_text
            try:
                sug, raw = suggest_commands(
                    payload,
                    model=model,
                    with_diff=with_diff,
                    unified_diff_for_infer=infer_diff,
                )
                if sug is None:
                    raise RuntimeError("Could not parse AI suggestion.")
                return sug.add_args, sug.commit_type, sug.commit_message, raw, None
            except Exception as e:
                # Fall back to heuristics on quota / API errors
                h = suggest_from_changes(
                    changes=change_items,
                    has_commits=has_commits,
                    diff_text=infer_diff,
                )
                return (
                    h.add_args,
                    h.commit_type,
                    h.commit_message,
                    "",
                    str(e),
                )
        h = suggest_from_changes(
            changes=change_items,
            has_commits=has_commits,
            diff_text=infer_diff,
        )
        return h.add_args, h.commit_type, h.commit_message, "", None

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

    plan: list[tuple[str, list[str], str, str]] = []
    ai_fallback_notes: list[tuple[str, str]] = []
    if mode == "split":
        groups = _group_changes(selected_pairs)
        for gname, items in groups.items():
            paths, ctype, cmsg, _raw, fb = suggest_for(items, title=gname.capitalize())
            plan.append((gname, paths, ctype, cmsg))
            if fb:
                ai_fallback_notes.append((gname, fb))
    else:
        paths, ctype, cmsg, _raw, fb = suggest_for(selected_pairs, title="Selected")
        plan.append(("one", paths, ctype, cmsg))
        if fb:
            ai_fallback_notes.append(("", fb))

    if ai and ai_fallback_notes:
        lines = [
            "[bold]You used --ai, but Gemini was not used for the suggestion below.[/bold]",
            "Commit message(s) come from [bold]local heuristics[/bold] instead.",
            "",
        ]
        if mode == "split":
            for gname, reason in ai_fallback_notes:
                lines.append(f"[dim]{gname}:[/dim] {reason}")
        else:
            lines.append(ai_fallback_notes[0][1])
        lines.append("")
        lines.append(
            "[dim]Check API key (GEMINI_API_KEY / GOOGLE_API_KEY), quota, model name, and network.[/dim]"
        )
        console.print(
            Panel(
                "\n".join(lines),
                title="[yellow]Warning: AI unavailable[/yellow]",
                border_style="yellow",
            )
        )

    def _render_plan(pl: list[tuple[str, list[str], str, str]]) -> str:
        rendered: list[str] = []
        for name, paths, ctype, cmsg in pl:
            add_line = "git add -A -- " + " ".join(_ps_quote(p) for p in paths)
            commit_line = f'git commit -m "[{ctype}] {cmsg}"'
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
            updated: list[tuple[str, list[str], str, str]] = []
            for name, paths, ctype, cmsg in plan:
                console.print(
                    f"[dim]{name}:[/dim] current message: [bold][{ctype}] {cmsg}[/bold]"
                )
                try:
                    from prompt_toolkit import prompt as pt_prompt

                    new_msg = (
                        pt_prompt(
                            "New commit message (subject only, no [TYPE] prefix): ",
                            default=cmsg,
                        ).strip()
                        or cmsg
                    )
                except Exception:
                    new_msg = (
                        typer.prompt(
                            "New commit message (subject only, no [TYPE] prefix)",
                            default=cmsg,
                        ).strip()
                    ) or cmsg
                updated.append((name, paths, ctype, new_msg))
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
            "Apply these commit(s)? (y/n/auto)"
            if len(plan) > 1
            else "Apply these commands? (y/n/auto)"
        )
        choice = typer.prompt(prompt, default="n").strip().lower()
        do_apply = choice == "auto" or choice in ("y", "yes")

    if do_apply:
        for name, paths, ctype, cmsg in plan:
            try:
                apply_commands(
                    repo_root,
                    [] if staged_only else paths,
                    ctype,
                    cmsg,
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
