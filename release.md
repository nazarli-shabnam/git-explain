# Releases & tags (git-explain)

This project uses **git tags** to mark release points, and **GitHub Releases** so you and others can download and test a specific version.

**Want to publish a release so you and peers can install and test like any Python package?** → See **[Publish a release (so you and peers can install and test like any Python package)](#publish-a-release-so-you-and-peers-can-install-and-test-like-any-python-package)** for the full step-by-step.

The package version lives in `pyproject.toml` under `[project].version`.

---

## What `MANIFEST.in` is (and why it mentions `.md` files)

`MANIFEST.in` is used by **setuptools** when building a **source distribution** (sdist), i.e. when you run packaging commands like:

- `python -m build` (recommended)
- `python -m pip install .` (can build wheels/sdists internally)

It controls **which extra files** (docs, license, etc.) get included in the sdist tarball/zip **in addition to Python packages**.

It does **not** affect:

- what `git add` / `git commit` do
- what gets pushed to GitHub

Your current `MANIFEST.in`:

- includes `LICENSE`
- includes `README.md`
- includes `FEATURES.md`
- includes Python files under `git_explain/`

If you publish to PyPI (or build sdists), those included files should generally exist and be committed; otherwise your sdist may be missing docs, or the build may fail depending on tooling/settings.

If you are **not** packaging/publishing yet, you can ignore `MANIFEST.in` for now (or later simplify/remove it when you’re ready).

---

## When to create a tag / release

Use a new version tag when you have a meaningful, stable snapshot you want to refer to later, such as:

- users can install/run it and it works end-to-end
- you changed CLI behavior/options and want a clear milestone
- you fixed a notable bug and want to publish the fix
- you’re ready to publish to PyPI or share a downloadable build

If you’re still experimenting, you can either:

- tag less frequently, or
- use **pre-release** versions (e.g. `0.2.0-alpha.1`)

---

## Versioning (practical SemVer)

Use `MAJOR.MINOR.PATCH` (Semantic Versioning) as a guideline:

- **PATCH** `0.1.1`: bug fixes only, no behavior change users depend on
- **MINOR** `0.2.0`: new features, new CLI options, behavior changes that are still backwards compatible
- **MAJOR** `1.0.0`: stable public API/CLI expectations; breaking changes bump MAJOR

While version is `0.y.z`, it’s common to move faster and treat “breaking changes” as MINOR bumps. Once you hit `1.0.0`, follow SemVer more strictly.

Recommended tag format: **`v0.1.0`** (a leading `v` is conventional).

### Pre-release versions (e.g. 0.1.0-alpha.1)

Use the **full version string** in both places:

- **In `pyproject.toml`**: set `version = "0.1.0-alpha.1"` (or `0.1.0a1`, `0.2.0-beta.2`, etc.). PEP 440 allows this.
- **Git tag**: use the same with a `v` prefix: `v0.1.0-alpha.1`.

So yes — in `pyproject.toml` you use the full string (e.g. `0.1.0-alpha.1`), not just the number. When you’re ready for a stable release, change to `0.1.0` and tag `v0.1.0`.

---

## Release checklist (local)

Run these steps from the repo root.

### 1) Make sure you’re clean and on the right branch

```powershell
git status
git branch
```

### 2) Update version

Edit `pyproject.toml`:

- bump `[project].version` to the new version (example `0.1.0` → `0.1.1`)

Then commit that change (usually combined with release notes changes).

### 3) Run tests (if you have them)

```powershell
python -m pytest -q
```

If you don’t have deps installed yet:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

### 4) Build (optional but recommended before publishing)

```powershell
python -m pip install --upgrade build
python -m build
```

If build succeeds, you’re less likely to ship a broken release.

---

## Create an annotated tag

Annotated tags are preferred for releases because they have a message and metadata.

Example for `v0.1.1`:

```powershell
git tag -a v0.1.1 -m "v0.1.1"
git tag --list "v*"
```

To inspect a tag:

```powershell
git show v0.1.1
```

---

## Push commits and tags

Push your branch:

```powershell
git push
```

Push tags:

```powershell
git push --tags
```

Or push one tag:

```powershell
git push origin v0.1.1
```

---

## Publish a release (so you and peers can install and test like any Python package)

Publish a release on GitHub; then anyone can **install with pip** (no zip download, no cloning the repo) and run the CLI.

### Step 1: Prepare and push the tag

- Update `pyproject.toml` version (e.g. `0.1.0` or `0.1.0-alpha.1`), run tests, create the tag, push:

```powershell
git push
git push origin v0.1.0
```

For a pre-release use the same version as in `pyproject.toml`, e.g. `git push origin v0.1.0-alpha.1`.

### Step 2: Create the GitHub Release

1. Open **https://github.com/nazarli-shabnam/git-explain**
2. Click **Releases** → **Draft a new release**.
3. **Choose a tag**: select the tag you pushed (e.g. `v0.1.0` or `v0.1.0-alpha.1`).
4. **Release title**: e.g. `v0.1.0`.
5. **Describe this release**: paste your release notes (template below).
6. For alpha/beta, check **Set as a pre-release**.
7. Click **Publish release**.

Once published, the tag is installable via pip from GitHub (see below).

### Step 3: Test it yourself (install like any Python package)

In a terminal (venv recommended):

```powershell
pip install "git+https://github.com/nazarli-shabnam/git-explain.git@v0.1.0"
```

Replace `v0.1.0` with your tag (e.g. `v0.1.0-alpha.1`). Then:

```powershell
git-explain --help
git-explain
```

Run `git-explain` from inside a git repo that has changes. Put `GEMINI_API_KEY` in `.env` or your environment if you use `--ai`. That’s it — no repo clone, no zip.

### Step 4: What to send peers (install and run)

Give them the **tag name** (e.g. `v0.1.0` or `v0.1.0-alpha.1`) and these instructions:

**Install (one command):**

```powershell
pip install "git+https://github.com/nazarli-shabnam/git-explain.git@v0.1.0"
```

(On macOS/Linux use the same line; if they use `python3`/`pip3`, they can run `pip3 install ...`.)

**Run:**

- From any git repo with changes: `git-explain` (or `git-explain --ai` for Gemini).
- For `--ai` they need a Gemini API key in `.env` or environment (see your README).

**Optional:** Send the release link so they can read notes:  
`https://github.com/nazarli-shabnam/git-explain/releases/tag/v0.1.0`

---

**Later, if you publish to PyPI**, they can install with `pip install git-explain` (and `pip install git-explain==0.1.0` for a specific version). Until then, the `pip install git+https://...@tag` method is the “install like any Python package” way.

### Alternative: test from source (zip)

If someone prefers not to use pip-from-GitHub, they can still download **Source code (zip)** from the release page, unzip, then in that folder run: `pip install -e .` and use `git-explain` as above.

---

## GitHub Release (notes + binaries) — reference

When drafting the release:

- **Title**: e.g. `v0.1.1`
- **Description**: paste release notes (see template below)
- **Pre-release**: check if it’s alpha/beta

You can attach built artifacts (wheels, sdist) to the release if you ran `python -m build`.

---

## Release notes template

Use this structure consistently; it makes releases easy to scan.

```text
## Highlights
- ...

## Added
- ...

## Changed
- ...

## Fixed
- ...

## Security
- ...

## Upgrade notes
- ...
```

Guidelines:

- Prefer user-facing language (“`git-explain --ai` now …”) over internal refactors.
- Link to issues/PRs if you have them.
- Mention any breaking behavior changes under **Upgrade notes**.

---

## How to draft release notes from git history

If this is your first release, you can base notes on the commits since the beginning:

```powershell
git log --oneline --no-merges
```

If you have a previous tag (example `v0.1.0`), list what changed since then:

```powershell
git log v0.1.0..HEAD --oneline --no-merges
```

For a more detailed view (good for categorizing notes):

```powershell
git log v0.1.0..HEAD --name-status --no-merges
```

Paste that output to me and tell me the new version you want (e.g. `v0.1.1`), and I’ll write polished release notes in the template above.

---

## Fixing mistakes

### Delete a local tag (before pushing)

```powershell
git tag -d v0.1.1
```

### Delete a remote tag (only if you already pushed it)

```powershell
git push --delete origin v0.1.1
```

Then recreate the correct tag and push it again.

