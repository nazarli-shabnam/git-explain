import pytest
from google.genai import errors as genai_errors

from git_explain import gemini as gemini_module
from git_explain.gemini import suggest_commands


class _FakeModels:
    def __init__(self, fn):
        self._fn = fn

    def generate_content(self, *, model, contents, config):
        return self._fn(model=model, contents=contents, config=config)


class _FakeClient:
    def __init__(self, fn):
        self.models = _FakeModels(fn)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


def _patch_client(monkeypatch, fn) -> None:
    monkeypatch.setattr(gemini_module.genai, "Client", lambda api_key: _FakeClient(fn))


_DIFF = "## Meta\nhas_commits: true\n\n## Staged\nM a.txt"


def test_suggest_commands_successful_parse(monkeypatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.delenv("AI_MODEL_FALLBACKS", raising=False)

    def fake(*, model, contents, config):
        return _FakeResponse('git add a.txt\ngit commit -m "fix: correct the bug"')

    _patch_client(monkeypatch, fake)

    sug, raw = suggest_commands(_DIFF, model="gemini-2.5-flash")

    assert sug is not None
    assert sug.commit_type == "FIX"
    assert sug.commit_message == "correct the bug"
    assert sug.add_args == ["a.txt"]
    assert "correct the bug" in raw


def test_suggest_commands_retries_fallback_on_rate_limit(monkeypatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL_FALLBACKS", "gemini-2.5-flash-lite")

    calls: list[str] = []

    def fake(*, model, contents, config):
        calls.append(model)
        if model == "gemini-2.5-flash":
            raise genai_errors.ClientError(429, {"error": {"message": "rate"}}, None)
        return _FakeResponse('git add a.txt\ngit commit -m "fix: correct the bug"')

    _patch_client(monkeypatch, fake)

    notified: list[str] = []
    sug, _raw = suggest_commands(
        _DIFF,
        model="gemini-2.5-flash",
        fallback_notifier=notified.append,
    )

    assert calls == ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    assert notified == ["gemini-2.5-flash-lite"]
    assert sug is not None
    assert sug.commit_type == "FIX"


def test_suggest_commands_non_retryable_error_propagates_without_fallback(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL_FALLBACKS", "gemini-2.5-flash-lite")

    calls: list[str] = []

    def fake(*, model, contents, config):
        calls.append(model)
        raise genai_errors.ClientError(400, {"error": {"message": "bad request"}}, None)

    _patch_client(monkeypatch, fake)

    with pytest.raises(genai_errors.ClientError):
        suggest_commands(_DIFF, model="gemini-2.5-flash")

    assert calls == ["gemini-2.5-flash"]


def test_suggest_commands_generic_ai_message_falls_back_to_heuristic_message(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.delenv("AI_MODEL_FALLBACKS", raising=False)

    def fake(*, model, contents, config):
        return _FakeResponse('git add a.txt\ngit commit -m "chore: update"')

    _patch_client(monkeypatch, fake)

    sug, _raw = suggest_commands(_DIFF, model="gemini-2.5-flash")

    assert sug is not None
    assert sug.commit_message != "update"


def test_suggest_commands_missing_api_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError):
        suggest_commands(_DIFF, model="gemini-2.5-flash")


def test_suggest_commands_empty_diff_returns_none(monkeypatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")
    sug, raw = suggest_commands("   ", model="gemini-2.5-flash")
    assert sug is None
    assert raw == ""
