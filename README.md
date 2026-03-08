# git-explain

CLI that suggests `git add` and `git commit` from your diffs. Uses local heuristics by default; optional **Gemini** integration (`--ai`) for AI-generated messages.

## Install

**From GitHub (any Python 3.10+ env):**

```bash
pip install "git+https://github.com/nazarli-shabnam/git-explain.git@main"
```

Or from a specific release:

```bash
pip install "git+https://github.com/nazarli-shabnam/git-explain.git@v0.1.0"
```

**From source** (repo root, where `pyproject.toml` and `git_explain/` are):

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -e .
```

## API key (for `--ai` only)

Put your Gemini API key in a `.env` file where you run the CLI (or set it in your environment):

```
GEMINI_API_KEY=your_key_here
```

Or use `GOOGLE_API_KEY`. Optional: set `GEMINI_MODEL` to override the default (e.g. `GEMINI_MODEL=gemini-2.5-flash`). See [Troubleshooting](#troubleshooting) for 404/429.

## Use

Run from **inside a git repository** that has changes:

```bash
git-explain
```

- **Default:** no API call; local heuristics suggest commit type and message.
- **With `--ai`:** sends only file paths and statuses to Gemini for the message (no file contents).
- You're prompted **Apply these commands? (y/n/auto)** — **n** = preview only, **y** = apply, **auto** = apply and remember.

**Options:**

| Option | Description |
|--------|-------------|
| `--help` | Show all options. |
| `--auto` | Apply without prompting. |
| `--ai` | Use Gemini for commit type/message (file paths only). |
| `--staged-only` | Commit only what's already staged (no `git add`). |
| `--cwd PATH` | Run as if current directory is `PATH`. |
| `--install-completion [SHELL]` | Install shell completion (`bash`, `zsh`). |
| `--show-completion [SHELL]` | Print completion script for `SHELL`. |

**Quick try:** Make a small change, run `git-explain`, answer **n** to only preview. If you see "No staged, unstaged, or untracked changes", ensure you have modified or added files that are not ignored by `.gitignore`.

**Interactive:** It shows a numbered list of changed files; you choose which to include (e.g. `1,2,5-7` or `all`), then **one** commit or **split** by docs/tests/config/code.

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
