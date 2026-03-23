"""Infer FIX-style commits from unified diff text (behavior fixes vs refactors)."""

from __future__ import annotations


def infer_fix_subject_from_diff(diff_text: str | None) -> str | None:
    """Return a short subject fragment after 'Fix …', or None if no strong signal.

    Uses high-precision phrases so we do not flip real refactors to FIX.
    """
    if not diff_text or len(diff_text.strip()) < 12:
        return None
    low = diff_text.lower()

    if "split commits are not available" in low and (
        "staged-only" in low or "staged_only" in low
    ):
        return "staged-only mode with multi-file split commits"

    if (
        "nothing is currently staged" in low
        and "--staged-only" in low
        and "git add" in low
    ):
        return "clearer error when index is empty under --staged-only"

    infer_signals = (
        "refine_type_and_message_from_diff",
        "infer_fix_subject_from_diff",
        "unified_diff_for_infer",
        "commit_infer.py",
    )
    if sum(1 for s in infer_signals if s in low) >= 2:
        return "commit message classification using unified diffs"

    return None


def refine_type_and_message_from_diff(
    commit_type: str,
    commit_message: str,
    diff_text: str | None,
) -> tuple[str, str]:
    """When diff shows a behavior fix, prefer FIX and a concrete subject.

    Does not override DOCS, TEST(S), or CHORE. May override REFACTOR or FEAT
    when the diff matches known bugfix patterns.
    """
    ct = (commit_type or "").upper()
    if ct in ("DOCS", "TEST", "TESTS", "CHORE"):
        return commit_type, commit_message

    subject = infer_fix_subject_from_diff(diff_text)
    if not subject:
        return commit_type, commit_message

    if ct == "FIX":
        msg = (commit_message or "").strip()
        if len(msg) < 8 or msg.lower() in {"fix", "fixes", "bugfix", "bug fix"}:
            return "FIX", f"Fix {subject}"
        return commit_type, commit_message

    if ct in ("REFACTOR", "FEAT"):
        return "FIX", f"Fix {subject}"

    return commit_type, commit_message
