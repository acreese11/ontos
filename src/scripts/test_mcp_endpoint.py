#!/usr/bin/env python3
"""
test_mcp_endpoint.py - End-to-end test for the Ontos MCP server endpoint.

Exercises the full JSON-RPC 2.0 / MCP protocol lifecycle against a running
server: health check, initialize, ping, tools/list, tools/call, error cases,
and session cleanup.

Usage:
    # Local dev server
    python scripts/test_mcp_endpoint.py -t mcp_...

    # Remote Databricks App (needs both Databricks PAT + MCP token)
    python scripts/test_mcp_endpoint.py \\
        -e https://my-app.databricksapps.com \\
        -t mcp_... \\
        -b dapi...

    # Auto-detect bearer from Databricks CLI profile
    python scripts/test_mcp_endpoint.py \\
        -e https://my-app.databricksapps.com \\
        -t mcp_... \\
        --bearer-from-cli

Options:
    -e, --endpoint       Base URL of the server (default: http://localhost:8000)
    -t, --token          MCP API token (X-API-Key value)
    -b, --bearer         Databricks PAT for app-level auth (Authorization: Bearer)
    --bearer-from-cli    Auto-read token from `databricks auth token`
    -v, --verbose        Print full response bodies
    --no-color           Disable colored output
"""

import argparse
import json
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Base headers applied to every request (e.g. Authorization: Bearer for remote)
_base_headers: Dict[str, str] = {}


class Colors:
    PASS = "\033[92m"
    FAIL = "\033[91m"
    WARN = "\033[93m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

NO_COLOR = Colors()
for attr in ("PASS", "FAIL", "WARN", "BOLD", "DIM", "RESET"):
    setattr(NO_COLOR, attr, "")

C = Colors()

passed = 0
failed = 0
warnings = 0


def jsonrpc_body(method: str, params: Optional[Dict] = None, req_id: int = 1) -> bytes:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        payload["params"] = params
    return json.dumps(payload).encode()


def http_request(
    url: str,
    *,
    method: str = "GET",
    body: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> Tuple[int, Dict[str, str], bytes]:
    """Minimal HTTP helper using stdlib only — no external deps."""
    req = Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in _base_headers.items():
        req.add_header(k, v)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        resp = urlopen(req, timeout=timeout)
        resp_headers = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, resp_headers, resp.read()
    except HTTPError as e:
        resp_headers = {k.lower(): v for k, v in e.headers.items()}
        return e.code, resp_headers, e.read()
    except URLError as e:
        raise SystemExit(f"Cannot connect to {url}: {e.reason}")


def result_ok(label: str, detail: str = ""):
    global passed
    passed += 1
    extra = f" {C.DIM}{detail}{C.RESET}" if detail else ""
    print(f"  {C.PASS}PASS{C.RESET}  {label}{extra}")


def result_fail(label: str, detail: str = ""):
    global failed
    failed += 1
    extra = f" {C.DIM}{detail}{C.RESET}" if detail else ""
    print(f"  {C.FAIL}FAIL{C.RESET}  {label}{extra}")


def result_warn(label: str, detail: str = ""):
    global warnings
    warnings += 1
    extra = f" {C.DIM}{detail}{C.RESET}" if detail else ""
    print(f"  {C.WARN}WARN{C.RESET}  {label}{extra}")


def section(title: str):
    print(f"\n{C.BOLD}{'─' * 60}{C.RESET}")
    print(f"{C.BOLD}{title}{C.RESET}")
    print(f"{C.BOLD}{'─' * 60}{C.RESET}")


def safe_json(body: bytes) -> Optional[Dict]:
    """Try to parse JSON; return None if the body isn't valid JSON."""
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def dump(label: str, data: Any, verbose: bool):
    if verbose:
        print(f"  {C.DIM}[{label}]{C.RESET}")
        print(f"  {C.DIM}{json.dumps(data, indent=2, default=str)}{C.RESET}")


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_health(base: str, token: str, verbose: bool) -> bool:
    section("Health Check")
    # Send the API key — deployed Databricks Apps have an app-level auth
    # layer that rejects unauthenticated requests before they reach FastAPI.
    status, _, body = http_request(
        f"{base}/api/mcp/health",
        headers={"X-API-Key": token},
    )

    data = safe_json(body)
    if data is None:
        snippet = body[:200].decode("utf-8", errors="replace")
        result_fail("GET /api/mcp/health", f"HTTP {status}, non-JSON body: {snippet}")
        return False

    dump("response", data, verbose)

    if status != 200:
        result_fail("GET /api/mcp/health", f"HTTP {status}")
        return False

    ok = True
    if data.get("status") == "ok":
        result_ok("status is 'ok'")
    else:
        result_fail("status field", f"got {data.get('status')!r}")
        ok = False

    if data.get("protocol_version"):
        result_ok("protocol_version present", data["protocol_version"])
    else:
        result_warn("protocol_version missing")

    return ok


def test_no_auth(base: str, is_remote: bool, verbose: bool):
    section("Auth – missing / invalid key")

    if is_remote:
        # Deployed Databricks Apps have an app-level auth layer (OAuth /
        # session cookie) that rejects unauthenticated requests with a
        # redirect or 401 before they reach our MCP handler.  The MCP-level
        # auth tests are only meaningful against the local dev server.
        result_warn("Skipped on remote endpoint (app-level auth intercepts first)")
        return

    # No key at all. NOTE: if the local server has ENV=LOCAL or
    # MOCK_USER_DETAILS=true, "no credentials" now resolves to the configured
    # mock user via the identity-path auth (see routes/mcp_routes.py,
    # resolve_identity_caller) - matching how every other route in the app
    # already behaves locally. `ping` requires no scope either way, so a
    # mock-identity server will legitimately return pong here instead of
    # -32001. Treat that as expected, not a failure - only flag it as a real
    # failure if the response is neither an auth error nor a successful pong.
    status, _, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=jsonrpc_body("ping"),
    )
    data = safe_json(body) or {}
    dump("no-key response", data, verbose)

    if data.get("error", {}).get("code") == -32001:
        result_ok("No API key → error -32001")
    elif data.get("result", {}).get("pong") is True:
        result_warn(
            "No API key → authenticated as local mock identity (expected when "
            "ENV=LOCAL/MOCK_USER_DETAILS=true); ping requires no scope so this "
            "is not itself proof of a leak - see test_identity_scope_filtering"
        )
    else:
        result_fail("No API key", f"expected -32001 or mock-identity pong, got {data}")

    # Bad key: in mock-identity mode this also resolves to the mock user
    # (identity-path auth doesn't inspect X-API-Key at all when it succeeds
    # first), same caveat as above.
    status, _, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=jsonrpc_body("ping"),
        headers={"X-API-Key": "mcp_definitely_not_valid"},
    )
    data = safe_json(body) or {}
    dump("bad-key response", data, verbose)

    if data.get("error", {}).get("code") == -32001:
        result_ok("Bad API key → error -32001")
    elif data.get("result", {}).get("pong") is True:
        result_warn("Bad API key → authenticated as local mock identity (expected in mock mode)")
    else:
        result_fail("Bad API key", f"expected -32001 or mock-identity pong, got {data}")


def test_bad_json(base: str, token: str, verbose: bool):
    section("Parse Error – malformed JSON")
    status, _, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=b"this is not json",
        headers={"X-API-Key": token},
    )
    data = safe_json(body) or {}
    dump("response", data, verbose)

    if data.get("error", {}).get("code") == -32700:
        result_ok("Malformed JSON → error -32700")
    elif status == 422:
        result_ok("Malformed JSON → HTTP 422 (framework-level rejection)")
    else:
        result_fail("Malformed JSON", f"expected -32700, got HTTP {status}: {data}")


def test_initialize(base: str, token: str, verbose: bool) -> Optional[str]:
    section("Initialize")
    status, headers, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=jsonrpc_body("initialize", {
            "clientInfo": {"name": "test-mcp-endpoint", "version": "1.0"},
            "protocolVersion": "2024-11-05",
        }),
        headers={"X-API-Key": token},
    )
    data = safe_json(body)
    if data is None:
        result_fail("initialize", f"HTTP {status}, non-JSON response")
        return None
    dump("response", data, verbose)

    session_id = headers.get("mcp-session-id")

    if data.get("error"):
        result_fail("initialize", data["error"].get("message", str(data["error"])))
        return None

    result_data = data.get("result", {})
    if result_data.get("protocolVersion"):
        result_ok("protocolVersion returned", result_data["protocolVersion"])
    else:
        result_fail("protocolVersion missing")

    server_info = result_data.get("serverInfo", {})
    if server_info.get("name"):
        result_ok("serverInfo.name", server_info["name"])
    else:
        result_warn("serverInfo.name missing")

    if "capabilities" in result_data:
        result_ok("capabilities present", str(list(result_data["capabilities"].keys())))
    else:
        result_warn("capabilities missing")

    if session_id:
        result_ok("MCP-Session-Id header set", session_id[:16] + "…")
    else:
        result_warn("MCP-Session-Id header not returned")

    return session_id


def test_ping(base: str, token: str, session_id: Optional[str], verbose: bool):
    section("Ping")
    hdrs: Dict[str, str] = {"X-API-Key": token}
    if session_id:
        hdrs["MCP-Session-Id"] = session_id

    status, _, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=jsonrpc_body("ping", req_id=2),
        headers=hdrs,
    )
    data = safe_json(body) or {}
    dump("response", data, verbose)

    result = data.get("result", {}) or {}
    if result.get("pong") is True:
        result_ok("pong: true")
    else:
        result_fail("pong", f"got {result}")

    if result.get("timestamp"):
        result_ok("timestamp present", result["timestamp"])
    else:
        result_warn("timestamp missing")


# Tool-name prefixes with no entry in common/mcp_permissions.SCOPE_FEATURE_MAP
# as of this writing. Identity-path (OBO) callers must never see these
# regardless of which mock role/groups the local server is configured with -
# unmapped scopes fail closed by design (see docs/notes/MCP_AUTH_REWORK_PRD.md
# §4.1). Only "contracts:*"-scoped tools are currently mapped.
_UNMAPPED_SCOPE_TOOL_PREFIXES = (
    "list_catalogs", "get_catalog_details", "list_schemas",  # analytics:*
    "search_glossary_terms", "add_semantic_link", "list_semantic_links",
    "remove_semantic_link", "find_entities_by_concept", "execute_sparql_query",
    "get_concept_hierarchy", "get_concept_neighbors",  # semantic:*, sparql:query
    "get_current_user",  # user:read
    "global_search",  # search:read
)


def test_identity_unmapped_scopes_denied(base: str, verbose: bool):
    """Assert unmapped scopes never leak to an identity-path caller.

    Sends a credential-free request. If the local server has ENV=LOCAL or
    MOCK_USER_DETAILS=true, this resolves via the identity path to the
    configured mock user (see resolve_identity_caller); if not, it's an auth
    failure and this test is skipped (nothing to check). Either way, no tool
    backed by an unmapped scope (analytics:*, semantic:*, user:read,
    search:read, sparql:query) should ever appear - regardless of the mock
    user's groups/role - since those scopes have no SCOPE_FEATURE_MAP entry
    and must fail closed.
    """
    section("Identity Path – unmapped scopes fail closed")
    status, _, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=jsonrpc_body("tools/list", req_id=100),
    )
    data = safe_json(body) or {}
    dump("response", data, verbose)

    if data.get("error"):
        result_warn("Skipped - no identity-path auth active on this server (credential-free request was rejected)")
        return

    tools = data.get("result", {}).get("tools", [])
    tool_names = {t.get("name") for t in tools}
    leaked = tool_names & set(_UNMAPPED_SCOPE_TOOL_PREFIXES)

    if leaked:
        result_fail("Unmapped-scope tools visible to identity caller", ", ".join(sorted(leaked)))
    else:
        result_ok(f"No unmapped-scope tools visible ({len(tools)} total tools returned)")


def test_tools_list(base: str, token: str, session_id: Optional[str], verbose: bool) -> list:
    section("Tools List")
    hdrs: Dict[str, str] = {"X-API-Key": token}
    if session_id:
        hdrs["MCP-Session-Id"] = session_id

    status, _, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=jsonrpc_body("tools/list", req_id=3),
        headers=hdrs,
    )
    data = safe_json(body) or {}

    if data.get("error"):
        result_fail("tools/list", data["error"].get("message", str(data["error"])))
        return []

    tools = data.get("result", {}).get("tools", [])
    if verbose:
        for t in tools:
            print(f"  {C.DIM}  - {t['name']}{C.RESET}")

    if len(tools) > 0:
        result_ok(f"{len(tools)} tools returned")
    else:
        result_warn("No tools returned (token may lack scopes)")

    # Spot-check schema conformance
    bad_schema = [t["name"] for t in tools if "inputSchema" not in t]
    if not bad_schema:
        result_ok("All tools have inputSchema")
    else:
        result_fail("Missing inputSchema", ", ".join(bad_schema))

    return tools


def test_tools_call(
    base: str, token: str, session_id: Optional[str],
    tools: list, verbose: bool,
):
    section("Tools Call")
    hdrs: Dict[str, str] = {"X-API-Key": token}
    if session_id:
        hdrs["MCP-Session-Id"] = session_id

    # Pick a safe read-only tool to call
    read_tools = [
        ("search_data_products", {"query": "test"}),
        ("search_data_contracts", {"query": "test"}),
        ("search_domains", {"query": "test"}),
        ("global_search", {"query": "test"}),
    ]
    tool_names = {t["name"] for t in tools}
    chosen = None
    for name, args in read_tools:
        if name in tool_names:
            chosen = (name, args)
            break

    if not chosen:
        result_warn("No known read-only tool available — skipping tools/call test")
        return

    tool_name, tool_args = chosen

    # Successful call
    status, _, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=jsonrpc_body("tools/call", {"name": tool_name, "arguments": tool_args}, req_id=4),
        headers=hdrs,
    )
    data = safe_json(body) or {}
    dump(f"tools/call {tool_name}", data, verbose)

    if data.get("error"):
        result_fail(f"tools/call {tool_name}", data["error"].get("message"))
    else:
        result_data = data.get("result", {}) or {}
        content = result_data.get("content", [])
        is_error = result_data.get("isError", False)

        if is_error:
            err_text = content[0].get("text", "") if content else "unknown"
            result_fail(f"tools/call {tool_name} returned isError=true", err_text)
        elif content:
            text_len = len(content[0].get("text", ""))
            result_ok(f"tools/call {tool_name}", f"returned {len(content)} content block(s), {text_len} chars")
        else:
            result_warn(f"tools/call {tool_name}", "empty content")

    # Non-existent tool
    status, _, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=jsonrpc_body("tools/call", {"name": "nonexistent_tool_xyz", "arguments": {}}, req_id=5),
        headers=hdrs,
    )
    data = safe_json(body) or {}
    dump("nonexistent tool", data, verbose)

    err = data.get("error", {})
    if err.get("code") == -32601:
        result_ok("Nonexistent tool → error -32601")
    elif data.get("result", {}).get("isError"):
        result_ok("Nonexistent tool → isError response")
    else:
        result_fail("Nonexistent tool", f"unexpected: {data}")


def test_unknown_method(base: str, token: str, session_id: Optional[str], verbose: bool):
    section("Unknown Method")
    hdrs: Dict[str, str] = {"X-API-Key": token}
    if session_id:
        hdrs["MCP-Session-Id"] = session_id

    status, _, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=jsonrpc_body("resources/list", req_id=6),
        headers=hdrs,
    )
    data = safe_json(body) or {}
    dump("response", data, verbose)

    if data.get("error", {}).get("code") == -32601:
        result_ok("Unknown method → error -32601")
    else:
        result_fail("Unknown method", f"expected -32601, got {data}")


def test_invalid_session(base: str, token: str, verbose: bool):
    section("Invalid Session")
    status, _, body = http_request(
        f"{base}/api/mcp", method="POST",
        body=jsonrpc_body("ping", req_id=7),
        headers={"X-API-Key": token, "MCP-Session-Id": "bogus-session-id"},
    )
    data = safe_json(body) or {}
    dump("response", data, verbose)

    err = data.get("error", {})
    if err.get("code") in (-32600, -32001):
        result_ok("Invalid session → error", f"code {err['code']}")
    else:
        result_fail("Invalid session", f"expected error, got {data}")


def test_delete_session(base: str, token: str, session_id: Optional[str], verbose: bool):
    section("Delete Session")
    if not session_id:
        result_warn("No session to delete — skipped")
        return

    status, _, body = http_request(
        f"{base}/api/mcp", method="DELETE",
        headers={"X-API-Key": token, "MCP-Session-Id": session_id},
    )
    if verbose:
        print(f"  {C.DIM}HTTP {status}{C.RESET}")

    if status == 204:
        result_ok("DELETE session → 204 No Content")
    else:
        result_fail("DELETE session", f"HTTP {status}")

    # Verify session is gone
    status2, _, body2 = http_request(
        f"{base}/api/mcp", method="DELETE",
        headers={"X-API-Key": token, "MCP-Session-Id": session_id},
    )
    if status2 in (404, 400):
        result_ok("Re-delete → 404 (session cleaned up)")
    else:
        result_warn("Re-delete", f"expected 404, got HTTP {status2}")


# ---------------------------------------------------------------------------
# Bearer token helpers
# ---------------------------------------------------------------------------

def _resolve_bearer_from_cli(base_url: str, quiet: bool = False) -> Optional[str]:
    """
    Try to get a Databricks access token from the Databricks CLI.

    Runs `databricks auth token --host <workspace-host>`.  The CLI resolves
    the workspace host from the app URL (*.databricksapps.com → workspace).
    Falls back to the raw host if that doesn't work.
    """
    from urllib.parse import urlparse
    host = urlparse(base_url).hostname or base_url

    # Databricks Apps URLs look like <app>-<id>.aws.databricksapps.com
    # The workspace host is not directly derivable, so we try without --host
    # first (uses the default profile) and then with the app host.
    for cmd in [
        ["databricks", "auth", "token", "--host", f"https://{host}"],
        ["databricks", "auth", "token"],
    ]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                tok = data.get("access_token") or data.get("token_value", "")
                if tok:
                    if not quiet:
                        print(f"  {C.DIM}Bearer token resolved via: {' '.join(cmd)}{C.RESET}")
                    return tok
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            continue

    if not quiet:
        print(f"  {C.WARN}Could not resolve bearer token from Databricks CLI.{C.RESET}")
        print(f"  {C.WARN}Use -b/--bearer to pass a PAT manually.{C.RESET}")
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global C

    parser = argparse.ArgumentParser(
        description="End-to-end test for the Ontos MCP server endpoint.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-e", "--endpoint",
        default="http://localhost:8000",
        help="Base URL of the server (default: http://localhost:8000)",
    )
    parser.add_argument(
        "-t", "--token",
        required=True,
        help="MCP API token (X-API-Key value, starts with mcp_)",
    )
    parser.add_argument(
        "-b", "--bearer",
        default=None,
        help="Databricks PAT / OAuth token for app-level auth (Authorization: Bearer)",
    )
    parser.add_argument(
        "--bearer-from-cli",
        action="store_true",
        help="Auto-read bearer token from `databricks auth token` for the endpoint host",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print full response bodies",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    args = parser.parse_args()

    if args.no_color:
        C = NO_COLOR

    base = args.endpoint.rstrip("/")
    token = args.token
    verbose = args.verbose

    is_remote = not any(h in base for h in ("localhost", "127.0.0.1", "0.0.0.0"))

    # Resolve bearer token for app-level auth
    bearer = args.bearer
    if not bearer and args.bearer_from_cli:
        bearer = _resolve_bearer_from_cli(base)
    if not bearer and is_remote:
        # Automatically try the CLI if targeting a remote endpoint
        bearer = _resolve_bearer_from_cli(base, quiet=True)

    if bearer:
        _base_headers["Authorization"] = f"Bearer {bearer}"

    print(f"{C.BOLD}Ontos MCP Endpoint Test Suite{C.RESET}")
    print(f"  endpoint : {base}")
    print(f"  token    : {token[:12]}…")
    print(f"  bearer   : {'set' if bearer else 'none'}")
    print(f"  remote   : {is_remote}")
    t0 = time.time()

    # -- run tests --
    if not test_health(base, token, verbose):
        print(f"\n{C.FAIL}Health check failed — server may be down. Aborting.{C.RESET}")
        sys.exit(2)

    test_no_auth(base, is_remote, verbose)
    if not is_remote:
        test_identity_unmapped_scopes_denied(base, verbose)
    test_bad_json(base, token, verbose)
    test_invalid_session(base, token, verbose)
    session_id = test_initialize(base, token, verbose)
    test_ping(base, token, session_id, verbose)
    tools = test_tools_list(base, token, session_id, verbose)
    test_tools_call(base, token, session_id, tools, verbose)
    test_unknown_method(base, token, session_id, verbose)
    test_delete_session(base, token, session_id, verbose)

    # -- summary --
    elapsed = time.time() - t0
    section("Summary")
    total = passed + failed
    print(f"  {C.PASS}{passed} passed{C.RESET}, ", end="")
    print(f"{C.FAIL}{failed} failed{C.RESET}, ", end="")
    print(f"{C.WARN}{warnings} warnings{C.RESET}  ", end="")
    print(f"{C.DIM}({elapsed:.1f}s){C.RESET}")

    if failed:
        print(f"\n{C.FAIL}Some tests failed.{C.RESET}")
        sys.exit(1)
    else:
        print(f"\n{C.PASS}All tests passed!{C.RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
