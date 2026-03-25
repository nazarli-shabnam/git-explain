# git-explain

CLI that suggests `git add` and `git commit` from your diffs. Uses local heuristics by default; optional **Gemini** integration for AI-generated messages.

[![PyPI version](https://badge.fury.io/py/git-explain.svg)](https://pypi.org/project/git-explain/)

---

## Install

**From PyPI** (recommended, Python 3.10+):

```bash
pip install git-explain
```

**From GitHub** (bleeding edge or specific version):

```bash
pip install "git+https://github.com/nazarli-shabnam/git-explain.git@main"
```

Or from a release tag:

```bash
pip install "git+https://github.com/nazarli-shabnam/git-explain.git@v1.1.0"
```

**From source** (repo root):

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -e .
```

---

## API key (for `--ai` only)

**Option 1 — Environment variable** (recommended for production, CI, scripts):

```powershell
# PowerShell
$env:GEMINI_API_KEY = "your_key_here"
```

```bash
# Bash / Zsh
export GEMINI_API_KEY=your_key_here
```

**Option 2 — `.env` file** (convenient for local development):

Create a `.env` file where you run the CLI:

```
GEMINI_API_KEY=your_key_here
```

You can also use `GOOGLE_API_KEY`. Optional: set `GEMINI_MODEL` to override the default (e.g. `GEMINI_MODEL=gemini-2.5-flash`). See [Troubleshooting](#troubleshooting) for 404/429.

---

## Usage

Run from **inside a git repository** that has changes:

```bash
git-explain
```

You’ll see a list of changed files, choose which to include, then get suggested `git add` and `git commit` commands. Answer **y** to apply, **n** to preview only, or **auto** to apply and remember for next time.

---

## Modes: `git-explain` vs `git-explain --ai` vs `git-explain --with-diff --ai` vs `git-explain --suggest`

| Command | What it does |
|---------|--------------|
| `git-explain` | **Heuristics only.** No API call. Suggests commit type and message from file names and status (e.g. docs, tests, config, code). Fast and private. |
| `git-explain --ai` | **AI (paths only).** Sends only file paths and statuses (A/M/D) to Gemini. No file contents. Good for smarter messages without sharing code. |
| `git-explain --with-diff --ai` | **AI (full diff).** Sends file list **plus** the full diff (staged, unstaged, untracked content) to Gemini. Produces detailed, specific messages (e.g. `feat: add opt-in --with-diff for detailed AI commit messages`). Opt-in; use when you want maximum accuracy and are okay sending diff content to the API. |
| `git-explain --suggest` | **AI staged-only suggestion mode.** Requires staged changes; sends staged file list + staged diff to Gemini and prints only `git commit -m ...`. It never applies changes and cannot be combined with other flags. |

**Summary:** Use plain `git-explain` for speed and privacy. Use `--ai` for better suggestions without sharing code. Use `--with-diff --ai` when you want the most accurate, context-aware messages and accept sending diff content to Gemini.

---

## Options

| Option | Description |
|--------|-------------|
| `--help` | Show all options. |
| `--auto` | Apply suggestion without prompting. |
| `--ai` | Use Gemini for commit type/message (file paths only). |
| `--with-diff` | With `--ai`: send full diff to the model for detailed messages. |
| `--model NAME` | Override Gemini model (e.g. `--model gemini-2.0-flash`). |
| `--staged-only` | Commit only what’s already staged (no `git add`). Always one commit for the whole index—split-by-group mode is disabled, because Git would commit the entire index on the first step and later steps would have nothing left staged. |
| `--cwd PATH` | Run as if current directory is `PATH`. |
| `--suggest` | Dedicated staged-only AI suggestion mode; prints only commit command and exits. Cannot be combined with other flags. |
| `--install-completion [SHELL]` | Install shell completion (`bash`, `zsh`). |
| `--show-completion [SHELL]` | Print completion script for `SHELL`. |

---

## Workflow

1. **Changed files** — Shows staged, unstaged, and untracked files. Untracked directories are expanded so you still see per-file paths.
2. **Select files** — Enter numbers (e.g. `1,2,5-7`), `all`, or a path (e.g. `main.py`, `src/utils/`).
3. **Commit mode** — If you selected 2+ files: choose `one` (single commit) or `split` (separate commits by docs/tests/config/code).
4. **Suggested commands** — Panel with `git add` and `git commit` lines.
5. **Edit (optional)** — You can tweak the commit message inline before applying.
6. **Apply** — Answer `y` to run the commands, `n` to preview only, or `auto` to apply and remember.

**Quick try:** Make a small change, run `git-explain`, answer **n** to only preview. If you see "No staged, unstaged, or untracked changes", ensure you have modified or added files that are not ignored by `.gitignore`.

---

## Troubleshooting

**429 RESOURCE_EXHAUSTED / "quota exceeded" / "limit: 0"**  
Quota or rate limit. Default model `gemini-2.5-flash` has free-tier quota; if you overrode `GEMINI_MODEL`, try removing it or set `GEMINI_MODEL=gemini-2.5-flash`. The app retries once after ~15s; see [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).

**404 NOT_FOUND / "models/... is not found"**  
Set a valid model in `.env`, e.g. `GEMINI_MODEL=gemini-2.5-flash`. Check [Google's model list](https://ai.google.dev/api/models).

---

## Test

From repo root:

```bash
pip install -e ".[dev]"
pytest -q
```
