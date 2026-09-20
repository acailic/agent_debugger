"""Regression checks for frontend HTTP methods and registered backend routes."""

from pathlib import Path

import pytest

from api.main import app
from scripts.hooks.route_contract import check_routes, extract_frontend_contract

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "frontend/src/api/client.ts"


@pytest.fixture(scope="module")
def contract():
    return extract_frontend_contract(ROOT)


def test_frontend_requests_match_registered_routes(contract):
    assert len(contract["requests"]) >= 70
    assert check_routes(contract["requests"], app.openapi()["paths"]) == []


def test_causal_route_typo_is_reported():
    source = CLIENT.read_text().replace("/failures/causes", "/causal-analysis")
    requests = extract_frontend_contract(ROOT, client_content=source)["requests"]
    drifts = check_routes(requests, app.openapi()["paths"])
    assert any(d["type"] == "missing_backend_route" and d["path"].endswith("/causal-analysis") for d in drifts)


def test_wrong_http_method_is_reported():
    source = CLIENT.read_text().replace("method: 'PUT'", "method: 'PATCH'", 1)
    requests = extract_frontend_contract(ROOT, client_content=source)["requests"]
    drifts = check_routes(requests, app.openapi()["paths"])
    assert any(d["function"] == "updateAlertStatus" and d["type"] == "route_method_mismatch" for d in drifts)


def test_extraction_resolves_local_urls_query_suffixes_and_sse(contract):
    requests = {r["function"]: (r["method"], r["path"]) for r in contract["requests"]}
    assert requests["getSessions"] == ("GET", "/api/sessions")
    assert requests["getAgentBaseline"] == ("GET", "/api/agents/{}/baseline")
    assert requests["setBreakpoint"] == ("POST", "/api/sessions/{}/breakpoints")
    assert requests["createEventSource"] == ("GET", "/api/sessions/{}/stream")


def test_unknown_url_expression_fails_explicitly():
    with pytest.raises(ValueError, match="Unsupported URL expression"):
        extract_frontend_contract(ROOT, client_content="export function broken() { return fetchJSON(makeUrl()) }")


def test_empty_extraction_fails_explicitly():
    with pytest.raises(ValueError, match="No frontend requests"):
        extract_frontend_contract(ROOT, client_content="// fetchJSON('/api/not-a-route')")


def test_ts_syntax_errors_fail_explicitly():
    with pytest.raises(ValueError, match="TypeScript contract extraction failed"):
        extract_frontend_contract(ROOT, client_content="export function broken( {")


def test_route_parameter_names_do_not_need_to_match():
    request = {"function": "example", "method": "GET", "path": "/api/sessions/{sessionId}"}
    assert check_routes([request], {"/api/sessions/{session_id}": {"get": {}}}) == []


def test_nested_interface_fields_do_not_leak_into_contract():
    content = """
    export interface Example {
      id: string;
      nested: { inner: string; deeper: { value: number } };
      optional?: boolean;
    }
    export type Status = 'active' | 'done';
    """
    contract = extract_frontend_contract(ROOT, types_content=content)
    assert contract["interfaces"]["Example"] == ["id", "nested", "optional"]
    assert contract["unions"]["Status"] == ["active", "done"]


def test_exported_arrow_requests_are_checked():
    source = "export const broken = () => fetch('/api/nonexistent', { method: 'POST' })"
    requests = extract_frontend_contract(ROOT, client_content=source)["requests"]
    assert check_routes(requests, app.openapi()["paths"])[0]["function"] == "broken"


def test_unknown_request_wrapper_fails_explicitly():
    source = "export function broken() { return differentFetch('/api/sessions') }"
    with pytest.raises(ValueError, match="no recognized HTTP call"):
        extract_frontend_contract(ROOT, client_content=source)
