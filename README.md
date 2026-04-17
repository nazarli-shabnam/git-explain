# git-explain

Suggest **conventional** `git add` / `git commit` messages from your changes. **Local heuristics by default** (no network); add **`--ai`** for Google Gemini.

[![PyPI](https://img.shields.io/pypi/v/git-explain.svg?label=pypi)](https://pypi.org/project/git-explain/)
[![GitHub tag](https://img.shields.io/github/v/tag/nazarli-shabnam/git-explain?label=repo)](https://github.com/nazarli-shabnam/git-explain/tags)
<!-- GitAds-Verify: 29ITVVWNRUVU524NJ5ZRR6DSZKIHP3EX -->

---

## Install & run

```bash
pip install git-explain
cd /path/to/your/git/repo   # repo with local changes
git-explain
```

**Using `--ai`?** Put **`GEMINI_API_KEY=…`** (or **`GOOGLE_API_KEY`**) in a **`.env` file at your project’s git root** — the top of the repo you’re working in, not the folder where `git-explain` is installed.

**Enter** applies the suggested commands; **n** skips (copy only). Pin a release from GitHub:  
`pip install "git+https://github.com/nazarli-shabnam/git-explain.git@v2.3.0"` (swap the tag as needed).

---

## Flags, keys, and AI

| | |
|--|--|
| **Conventional commits** | `feat:`, `fix:`, optional `(scope)`, etc. — see [spec](https://www.conventionalcommits.org/). |
| **`.env`** | `GEMINI_API_KEY` or `GOOGLE_API_KEY` in **`.env` at that repo’s git root** (loaded after the repo is resolved). |
| **Shell (one session)** | Set the variable in the terminal; it overrides `.env` for that window. PowerShell: `$env:GEMINI_API_KEY="…"` then `git-explain --ai`. bash/zsh: `export GEMINI_API_KEY="…"`. |
| **`--auto`** | Apply without the apply prompt. |
| **`--staged-only`** | Commit the index only (no `git add` from the tool). |
| **`--cwd`** | Treat another directory as the git repo root. |

**`--ai`** — model sees paths + status. **`--ai --with-diff`** — also sends the diff (more detail, data goes to the API). **`--suggest`** — staged + AI only: prints one `git commit -m "…"` line (no other flags). More: **`git-explain --help`**.

---

## If Gemini errors

- **429 / quota** — [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).
- **404 / model** — e.g. **`GEMINI_MODEL=gemini-2.5-flash`**; [model list](https://ai.google.dev/api/models).

---

## Develop

**Smoke-test a branch:** clone, `pip install -r requirements.txt`, run **`python -m git_explain`** from any git working tree (no `pip install -e .`). **Day-to-day hacking:** `pip install -e ".[dev]"` then `pytest -q`, `ruff check .`, `ruff format --check .`.

```bash
cd path/to/git-explain
pip install -r requirements.txt
python -m git_explain
```

## GitAds Sponsored
[![Sponsored by GitAds](https://gitads.dev/v1/ad-serve?source=nazarli-shabnam/git-explain@github)](https://gitads.dev/v1/ad-track?source=nazarli-shabnam/git-explain@github)

