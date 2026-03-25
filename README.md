# git-explain

**Commit message block?** Run this in your repo after you change files. It suggests `git add` and `git commit` lines you can copy—or apply in one step if you want. **Nothing leaves your machine** unless you turn on AI.

[![PyPI](https://img.shields.io/pypi/v/git-explain.svg?label=pypi)](https://pypi.org/project/git-explain/)
[![GitHub tag](https://img.shields.io/github/v/tag/nazarli-shabnam/git-explain?label=repo)](https://github.com/nazarli-shabnam/git-explain/tags)


---

## Install (Python 3.10+)

```bash
pip install git-explain
```

**From source** (this repo):

```bash
pip install -e .
```

Optional: install a specific tag from GitHub instead of PyPI:

```bash
pip install "git+https://github.com/nazarli-shabnam/git-explain.git@v2.1.8"
```

---

## Try it

1. In any git repo, change or add a file (not ignored).
2. Run:
   ```bash
   git-explain
   ```
3. Choose what to include (`all` is fine), read the suggestion, answer **`n`** if you only want to copy commands yourself—nothing bad happens.

Heuristics guess a sensible type and message from paths and statuses. **No account, no key, no network** for that path.

---

## Optional: Gemini

If you want sharper messages, set **`GEMINI_API_KEY`** (or `GOOGLE_API_KEY`) in the environment or a **`.env`** file in the folder where you run the tool.

| Command | In plain terms |
|--------|----------------|
| `git-explain --ai` | AI sees **paths and change type** only (no file contents). |
| `git-explain --ai --with-diff` | AI also sees the **diff**—better detail; only use if you’re OK sending that to the API. |
| `git-explain --suggest` | **Staged files only**; prints one **`git commit -m "..."`** line for scripting. Needs AI; don’t combine with other flags. |

Everything else (`--auto`, `--staged-only`, `--cwd`, model override, shell completion): **`git-explain --help`**.

---

## If Gemini complains

- **429 / quota** — wait a bit, or try the default model; see Google’s [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).
- **404 / model not found** — set something current, e.g. **`GEMINI_MODEL=gemini-2.5-flash`**, and check their [model list](https://ai.google.dev/api/models).

---

## Developers

```bash
pip install -e ".[dev]"
pytest -q
```
