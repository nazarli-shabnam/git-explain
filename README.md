# git-explain

Suggest **conventional** `git add` / `git commit` messages from your changes. Uses AI automatically when configured; falls back to local heuristics on errors.

[![PyPI](https://img.shields.io/pypi/v/git-explain.svg?label=pypi)](https://pypi.org/project/git-explain/)
[![GitHub tag](https://img.shields.io/github/v/tag/nazarli-shabnam/git-explain?label=repo)](https://github.com/nazarli-shabnam/git-explain/tags)

---

## Install & run

```bash
pip install git-explain
cd /path/to/your/git/repo   # repo with local changes
git-explain
```

Put AI config in **`.env` at your project’s git root** (the repo you run in). Uses the **Google Gemini API** (same `AI_API_KEY` for every Gemini model id):
- **`AI_MODEL`** — primary model id (e.g. `gemini-2.5-flash`). Get a key from [Google AI Studio](https://aistudio.google.com/apikey).
- **`AI_API_KEY`** — your Gemini API key.
- **`AI_MODEL_FALLBACKS`** (optional) — comma-separated Gemini model ids tried **in order** if the primary hits **rate limits or overload** (429 / 503-style errors only). Default is a small built-in list; override to match your quotas.

**Enter** applies the suggested commands; **n** skips (copy only). Pin a release from GitHub:  
`pip install "git+https://github.com/nazarli-shabnam/git-explain.git@v2.3.0"`
(swap the tag as needed).

---

## Flags, keys, and AI

| | |
|--|--|
| **Conventional commits** | `feat:`, `fix:`, optional `(scope)`, etc. — see [spec](https://www.conventionalcommits.org/). |
| **`.env`** | `AI_MODEL`, `AI_API_KEY`, and optionally `AI_MODEL_FALLBACKS` in **`.env` at that repo’s git root** (loaded after repo root is resolved). |
| **Provider choice** | First run without `AI_MODEL` prompts for **Gemini** only (same key); primary model is set automatically with built-in fallbacks on rate limits. Other providers may be added later. |
| **`--auto`** | Apply without the apply prompt. |
| **`--staged-only`** | Commit the index only (no `git add` from the tool). |
| **`--cwd`** | Treat another directory as the git repo root. |

**Default run** uses configured AI model if available; otherwise local heuristics.  
**`--with-diff`** sends full diff to AI (more detail, data goes to provider API).  
**`--suggest`** is AI-only staged mode: prints one `git commit -m "…"` line.

**One vs split commits:** after you choose which changed files to include, if **more than one path** is selected you are prompted for **one** commit (default) or **split**. Split suggests separate commits grouped by area (docs, tests, config, code, other). With **`--staged-only`**, split is not available; the tool explains why and suggests a **single** commit for what is already staged.

---

## If AI errors

- **429 / quota** — limits on the current model; the tool may try **`AI_MODEL_FALLBACKS`** next (one dim line per switch), then heuristics if everything fails.
- **503 / unavailable** — transient overload; same fallback behavior when the API signals retryable overload.
- Other failures (bad key, invalid model, etc.) → local heuristics and a warning without burning through fallbacks.

---

## Develop

**Smoke-test a branch:** clone, `pip install -r requirements.txt`, run **`python -m git_explain`** from any git working tree (no `pip install -e .`). **Day-to-day hacking:** `pip install -e ".[dev]"` then `pytest -q`, `ruff check .`, `ruff format --check .`.

```bash
cd path/to/git-explain
pip install -r requirements.txt
python -m git_explain
```
