# git-explain

Suggests **conventional** `git add` / `git commit` messages from your changes. Uses AI when you configure a key; otherwise uses simple local rules.

[![PyPI](https://img.shields.io/pypi/v/git-explain.svg?label=pypi)](https://pypi.org/project/git-explain/)
[![GitHub tag](https://img.shields.io/github/v/tag/nazarli-shabnam/git-explain?label=repo)](https://github.com/nazarli-shabnam/git-explain/tags)

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

The first time you run it without `AI_MODEL` set, the tool offers to create `.env` for your API key and shows a link to create one — it uses a built-in default Gemini model for that run but does **not** write a model into `.env`. Google renames and retires model ids over time, so nothing is pinned automatically; set `AI_MODEL` yourself (or pass `--model`) once you want a specific one to stick.

---

## Configure (`.env`)

Put a file named **`.env` in the repo root** (next to `.git`). Typical variables:

| Variable | Role |
|----------|------|
| `AI_MODEL` | Gemini model id, e.g. `gemini-2.5-flash`. **Optional** — if unset, the tool uses its built-in default for that run without writing anything to `.env`. |
| `AI_API_KEY` | From [Google AI Studio](https://aistudio.google.com/apikey). |
| `AI_MODEL_FALLBACKS` | Optional: comma-separated backup models, tried **in order** after `AI_MODEL` when it's busy, overloaded, or not a valid model id. If you omit this variable, the tool uses the **default fallbacks** below. |

You never have to get the model id exactly right: an unset, mistyped, or retired `AI_MODEL` all fall through to the same fallback chain as a busy/rate-limited model, so the tool keeps working even if Google renames or removes a model you had pinned.

**Default `AI_MODEL_FALLBACKS` (when the variable is unset):** `gemini-2.5-flash-lite`, then `gemini-3-flash-preview` — each is tried in sequence after a failed attempt on the previous model in the chain (starting from `AI_MODEL`).

If `AI_API_KEY` is empty, **`GEMINI_API_KEY`** is still read (same key, older name).

---

## Flags

| | |
|--|--|
| `--auto` | Apply suggested commands without a confirmation prompt. |
| `--staged-only` | Work with staged changes only (no `git add` from the tool). |
| `--cwd` | Use another directory as the git repo root. |
| `--model` | Override the AI model for this run (defaults to `AI_MODEL` from the repo `.env`). |
| `--with-diff` | Send the full diff to the AI (more context). |
| `--suggest` | Print one suggested `git commit -m "…"` line (staged, AI only). |

If you pick **more than one changed file**, you can choose **one** commit or **split** into several (split is not available with `--staged-only`). **Enter** applies the suggestion; **n** skips so you can copy instead.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, optional scope, etc.).

---

## When AI fails

Wrong key or network/quota errors that survive the whole fallback chain → the tool falls back to local heuristics and shows a warning. A busy/overloaded model *or* a bad/unknown model id steps through the fallback chain instead: your `AI_MODEL` (or the built-in default, if unset) first, then the models in `AI_MODEL_FALLBACKS` (or the **default** `gemini-2.5-flash-lite` → `gemini-3-flash-preview` list if that variable is unset).

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

