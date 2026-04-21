# git-explain

Suggests **conventional** `git add` / `git commit` messages from your changes. Uses AI when you configure a key; otherwise uses simple local rules.

[![PyPI](https://img.shields.io/pypi/v/git-explain.svg?label=pypi)](https://pypi.org/project/git-explain/)
[![GitHub tag](https://img.shields.io/github/v/tag/nazarli-shabnam/git-explain?label=repo)](https://github.com/nazarli-shabnam/git-explain/tags)
<!-- GitAds-Verify: 29ITVVWNRUVU524NJ5ZRR6DSZKIHP3EX -->

---

## Install and upgrade

```bash
pip install git-explain
pip install --upgrade git-explain
```

Use the second command anytime you want the latest release from PyPI.

In a terminal, go to your project folder (the one that contains `.git`) and run:

```bash
git-explain
```

The first time you run it without `AI_MODEL` in `.env`, the tool asks whether to use **Gemini** or **Mistral** and can write `.env` for you.

---

## Configure (`.env`)

Put a file named **`.env` in the repo root** (next to `.git`). Typical variables:

| Variable | Role |
|----------|------|
| `AI_MODEL` | Model id, e.g. `gemini-2.5-flash` or `codestral-latest`. Filled by the first-run prompt if missing. |
| `AI_API_KEY` | API key for whichever provider matches `AI_MODEL`. |
| `AI_MODEL_FALLBACKS` | Optional, **Gemini only**: comma-separated backup models if the first is rate-limited or overloaded. |

Older names still work if `AI_API_KEY` is empty: **`GEMINI_API_KEY`** (Gemini) or **`MISTRAL_API_KEY`** (Mistral).

**Keys:** [Google AI Studio](https://aistudio.google.com/apikey) (Gemini — names usually start with `gemini-`) · [Mistral API keys](https://admin.mistral.ai/organization/api-keys) (names starting with `mistral` or `codestral`). Mistral does not use automatic model fallback; Gemini can try fallbacks when the API is busy.

---

## Flags

| | |
|--|--|
| `--auto` | Apply suggested commands without a confirmation prompt. |
| `--staged-only` | Work with staged changes only (no `git add` from the tool). |
| `--cwd` | Use another directory as the git repo root. |
| `--with-diff` | Send the full diff to the AI (more context). |
| `--suggest` | Print one suggested `git commit -m "…"` line (staged, AI only). |

If you pick **more than one changed file**, you can choose **one** commit or **split** into several (split is not available with `--staged-only`). **Enter** applies the suggestion; **n** skips so you can copy instead.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, optional scope, etc.).

---

## When AI fails

Wrong key, bad model name, network issues, or quota errors → the tool falls back to local heuristics and shows a warning. Gemini may switch to `AI_MODEL_FALLBACKS` on retryable limits; Mistral does not.

---

## Install a specific version from GitHub

```bash
pip install "git+https://github.com/nazarli-shabnam/git-explain.git@v2.3.0"
pip install "git+https://github.com/nazarli-shabnam/git-explain.git@v2.4.0"
```

Replace `v2.3.0` with the [tag](https://github.com/nazarli-shabnam/git-explain/tags) you want.

---

## Develop

From a clone of this repo:

```bash
pip install -r requirements.txt
python -m git_explain
```

Contributors: `pip install -e ".[dev]"` then `pytest -q`, `ruff check .`, `ruff format --check .`.

## GitAds Sponsored
[![Sponsored by GitAds](https://gitads.dev/v1/ad-serve?source=nazarli-shabnam/git-explain@github)](https://gitads.dev/v1/ad-track?source=nazarli-shabnam/git-explain@github)

