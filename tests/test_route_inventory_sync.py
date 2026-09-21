"""Route-inventory synchronization check.

docs/hosted-route-inventory.md is the documentary map of every HTTP route
the server mounts (auth model, tenant scoping, sinks). A doc that drifts
from the app is worse than no doc: reviewers audit the table, not the
router. This test parses the route tables out of the markdown and asserts
set equality against the routes registered on the real app:

- every (method, path) the app registers appears in the doc, and
- every (method, path) the doc lists exists on the app.

On mismatch both diff sets are printed so the failure names the exact
routes to add or remove. When the test fails after a code change, fix the
DOC; only fix the code when the code itself is wrong.

The app-route walker is replicated from tests/conftest.py's
``iter_app_api_routes`` (version-agnostic across FastAPI layouts) rather
than imported, so this file has no conftest dependency and conftest stays
untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.routing import APIRoute

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "hosted-route-inventory.md"

# A table row whose first cell is "METHOD /path" — the shape every route
# table in the inventory uses (other columns are prose and ignored).
_ROUTE_ROW = re.compile(
    r"^\|\s*(?P<method>GET|POST|PUT|DELETE|PATCH)\s+(?P<path>/[^\s|]*)\s*\|",
    re.MULTILINE,
)


def iter_app_api_routes(app):
    """Yield every registered API route as (path, methods, endpoint).

    Version-agnostic across FastAPI layouts: <=0.13x flattens APIRoute
    objects directly into ``app.routes``; >=0.141 wraps each included
    router in a lazy ``_IncludedRouter`` whose ``effective_candidates()``
    exposes the resolved routes as objects with ``path`` / ``methods`` /
    ``endpoint``. (Same walker as tests/conftest.py, replicated on
    purpose — see module docstring.)
    """

    def walk(routes):
        for route in routes:
            if isinstance(route, APIRoute):
                yield (route.path, route.methods, route.endpoint)
                continue
            inner = getattr(route, "router", None)
            if inner is not None and hasattr(inner, "routes"):
                yield from walk(inner.routes)
            candidates = getattr(route, "effective_candidates", None)
            if callable(candidates):
                for context in candidates():
                    path = getattr(context, "path", None)
                    endpoint = getattr(context, "endpoint", None)
                    if path is not None and endpoint is not None:
                        yield (path, getattr(context, "methods", None), endpoint)

    yield from walk(app.routes)


def app_route_set(app) -> set[tuple[str, str]]:
    """All (METHOD, path) pairs the app serves.

    HEAD is Starlette's automatic companion of GET, not a separately
    documented route, so it is dropped wherever GET is present.
    """
    pairs: set[tuple[str, str]] = set()
    for path, methods, _endpoint in iter_app_api_routes(app):
        method_set = set(methods or ())
        if "GET" in method_set:
            method_set.discard("HEAD")
        for method in method_set:
            pairs.add((method, path))
    return pairs


def doc_route_set(markdown: str) -> set[tuple[str, str]]:
    """All (METHOD, path) pairs listed in the inventory's route tables."""
    return {(m.group("method"), m.group("path")) for m in _ROUTE_ROW.finditer(markdown)}


def test_route_inventory_matches_app():
    from api.main import create_app

    markdown = DOC_PATH.read_text(encoding="utf-8")

    documented = doc_route_set(markdown)
    assert documented, "no route rows parsed from docs/hosted-route-inventory.md — parser drift?"

    actual = app_route_set(create_app())

    missing_from_doc = sorted(actual - documented)
    stale_in_doc = sorted(documented - actual)

    assert not missing_from_doc and not stale_in_doc, (
        "docs/hosted-route-inventory.md is out of sync with the app.\n"
        f"Routes registered on the app but missing from the doc ({len(missing_from_doc)}):\n"
        f"  {missing_from_doc}\n"
        f"Routes documented but not registered on the app ({len(stale_in_doc)}):\n"
        f"  {stale_in_doc}\n"
        "Fix the DOC (add/remove rows) unless the code itself is wrong."
    )


def test_doc_route_tables_are_well_formed():
    """Guard the parser's contract: every parsed row is a plausible route.

    Catches accidental matches in non-route tables (which would silently
    hide drift) and mangled rows the set comparison would otherwise treat
    as unique routes.
    """
    markdown = DOC_PATH.read_text(encoding="utf-8")
    documented = doc_route_set(markdown)
    assert documented, "no route rows parsed from docs/hosted-route-inventory.md — parser drift?"
    for method, path in documented:
        assert path.startswith("/"), f"non-absolute path parsed: {method} {path}"
        assert path.count("{") == path.count("}"), (
            f"unbalanced path parameter in doc row: {method} {path}"
        )
