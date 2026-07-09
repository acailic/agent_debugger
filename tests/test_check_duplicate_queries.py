"""Tests for the PreToolUse duplicate-query hook shape extractor.

Regression coverage for a double-offset bug where ``remaining[start:]`` skipped the
``.where(...)`` clause for any select() that was not at the very start of the content,
so non-leading duplicate queries went undetected.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_HOOK_PATH = Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "check_duplicate_queries.py"


@pytest.fixture(scope="module")
def hook():
    """Load the hook module directly from its file path."""
    spec = importlib.util.spec_from_file_location("check_duplicate_queries", _HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_shape_leading_select(hook):
    """A select() at the start of the content is matched."""
    content = "q = select(EventModel).where(EventModel.session_id == sid)\n"
    assert hook.extract_query_shapes(content) == ["EventModel.where[session_id]"]


def test_extract_shape_non_leading_select(hook):
    """Regression: a select() preceded by other code must still have its where() found.

    Previously ``remaining[start:]`` double-offset the search window, so the where
    clause immediately following a non-leading select() fell in the skipped region.
    """
    content = (
        "# leading comment padding\n"
        "# more padding to push select forward\n"
        "async def list_events(session, sid):\n"
        "    return await session.execute(select(EventModel).where(EventModel.session_id == sid))\n"
    )
    assert hook.extract_query_shapes(content) == ["EventModel.where[session_id]"]


def test_extract_shape_unknown_model_allowed(hook):
    """A select on a model not in the pattern registry is still extracted but not flagged."""
    content = "q = select(NewModel).where(NewModel.foo == bar)\n"
    assert hook.extract_query_shapes(content) == ["NewModel.where[foo]"]


def test_extract_shape_multiple_conditions_sorted(hook):
    """Where condition field names are sorted alphabetically and are order-independent."""
    content = (
        "q = select(SessionModel).where(SessionModel.tenant_id == t, SessionModel.id == i)\n"
    )
    assert hook.extract_query_shapes(content) == ["SessionModel.where[id, tenant_id]"]


def test_check_duplicates_flags_known_pattern(hook):
    """A known duplicate shape is reported as a duplicate."""
    content = "q = select(EventModel).where(EventModel.session_id == sid)\n"
    result = hook.check_duplicates(content)
    assert result["duplicates"]
    assert result["duplicates"][0]["shape"] == "EventModel.where[session_id]"
    assert result["duplicates"][0]["method"] == "list_events"


def test_check_duplicates_allows_unknown_pattern(hook):
    """A shape not in the registry produces no duplicates."""
    content = "q = select(BrandNewModel).where(BrandNewModel.x == y)\n"
    result = hook.check_duplicates(content)
    assert result["duplicates"] == []


def test_main_denies_in_scope_duplicate(hook, capsys, monkeypatch):
    """main() denies an in-scope path with a duplicate query."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_duplicate_queries.py",
            "--path",
            "api/foo.py",
            "--content",
            "q = select(EventModel).where(EventModel.session_id == sid)\n",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        hook.main()
    import json

    out = json.loads(capsys.readouterr().out)
    assert exc.value.code == 1
    assert out["decision"] == "deny"


def test_main_allows_out_of_scope_path(hook, capsys, monkeypatch):
    """main() allows paths outside api/ auth/ collector/."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_duplicate_queries.py",
            "--path",
            "frontend/src/App.tsx",
            "--content",
            "select(EventModel).where(EventModel.session_id == sid)\n",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        hook.main()
    import json

    out = json.loads(capsys.readouterr().out)
    assert exc.value.code == 0
    assert out["decision"] == "allow"
