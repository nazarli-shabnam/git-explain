from git_explain.commit_infer import (
    infer_fix_subject_from_diff,
    refine_type_and_message_from_diff,
)
from git_explain.heuristics import suggest_from_changes


def test_infer_fix_subject_staged_only_split() -> None:
    diff = """
+        if staged_only:
+            console.print(
+                "split commits are not available with --staged-only"
+            )
"""
    assert infer_fix_subject_from_diff(diff) is not None
    assert "staged-only" in (infer_fix_subject_from_diff(diff) or "").lower()


def test_infer_fix_subject_commit_classification_helpers_in_diff() -> None:
    diff = """
diff --git a/git_explain/commit_infer.py b/git_explain/commit_infer.py
+def refine_type_and_message_from_diff
+def infer_fix_subject_from_diff
"""
    subj = infer_fix_subject_from_diff(diff)
    assert subj is not None
    assert "diff" in subj.lower() or "classification" in subj.lower()


def test_infer_fix_subject_empty_index_message() -> None:
    diff = """
+            raise RuntimeError(
+                "Nothing is currently staged. With --staged-only, git-explain does "
+                "not run git add; stage your changes first, then try again."
+            )
"""
    assert infer_fix_subject_from_diff(diff) is not None


def test_refine_refactor_to_fix() -> None:
    diff = "split commits are not available with --staged-only"
    ct, msg = refine_type_and_message_from_diff(
        "REFACTOR", "Update git-explain CLI", diff
    )
    assert ct == "FIX"
    assert "staged-only" in msg.lower()


def test_refine_does_not_override_docs() -> None:
    diff = "split commits are not available with --staged-only"
    ct, msg = refine_type_and_message_from_diff("DOCS", "Update README", diff)
    assert ct == "DOCS"
    assert msg == "Update README"


def test_suggest_from_changes_with_staged_only_diff() -> None:
    diff = """
## Unstaged diff
diff --git a/git_explain/cli.py b/git_explain/cli.py
+        if staged_only:
+                "split commits are not available with --staged-only"
"""
    s = suggest_from_changes(
        changes=[
            ("M", "git_explain/cli.py"),
            ("M", "git_explain/run.py"),
        ],
        has_commits=True,
        diff_text=diff,
    )
    assert s.commit_type == "FIX"
    assert "staged-only" in s.commit_message.lower()
