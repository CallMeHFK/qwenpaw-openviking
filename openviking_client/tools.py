"""QwenPaw tool functions: thin wrappers over OpenViking MCP tools/call.

Every wrapper returns a plain string for the model. Argument names mirror the
upstream MCP tools; the server-side schema is authoritative, so unknown or
missing parameters surface as server validation errors, not client inventions.
"""

import json
import threading

from . import proxy as _proxy
from .mcp_client import (
    McpAuthError,
    McpClient,
    McpConnectionError,
    McpHttpError,
    McpTimeoutError,
    OpenVikingError,
    serialize_body_for_error,
)

_config = None
_client = None
_state_lock = threading.Lock()


def configure(config):
    """Store the resolved proxy connection; the client is built lazily."""
    global _config, _client
    with _state_lock:
        _config = dict(config or {})
        _client = None


def close_client():
    global _client
    with _state_lock:
        client, _client = _client, None
    if client is not None:
        client.close()


def _get_client():
    global _client
    with _state_lock:
        if _config is None:
            raise OpenVikingError("OpenViking plugin is not configured yet")
        if _client is None:
            _client = McpClient(_config)
        return _client


def _error_string(exc):
    mcp_url = (_config or {}).get("mcp_url", "")
    if isinstance(exc, McpAuthError):
        detail = serialize_body_for_error(exc.body_text)
        return (
            f"OpenViking authentication failed (HTTP {exc.status}). Check "
            f"~/.openviking/ovcli.conf or OPENVIKING_API_KEY, and verify the "
            f"configured account/user for trusted mode."
            + (f" Server said: {detail}" if detail else "")
        )
    if isinstance(exc, McpHttpError):
        detail = serialize_body_for_error(exc.body_text)
        return (f"OpenViking MCP upstream returned HTTP {exc.status}."
                + (f" Server said: {detail}" if detail else ""))
    if isinstance(exc, McpTimeoutError):
        timeout_ms = (_config or {}).get("timeout_ms", 15000)
        msg = (
            f"OpenViking MCP request timed out after {timeout_ms}ms ({mcp_url}). "
            f"The server may still be processing (rerank can be slow) — check "
            f"/health or raise OPENVIKING_TIMEOUT_MS."
        )
        return msg + _proxy.proxy_hint(_config or {})
    if isinstance(exc, McpConnectionError):
        msg = (
            f"OpenViking MCP request failed: cannot reach {mcp_url}. Check the "
            f"configured URL and that the OpenViking server is running. ({exc})"
        )
        return msg + _proxy.proxy_hint(_config or {})
    return f"OpenViking MCP error: {exc}"


def _unwrap(result):
    if not isinstance(result, dict):
        return str(result)
    content = result.get("content")
    texts = []
    if isinstance(content, list):
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ):
                texts.append(block["text"])
    body = "\n".join(t for t in texts if t)
    if not body:
        body = json.dumps(result.get("structuredContent", result), ensure_ascii=False, default=str)
    if result.get("isError"):
        return f"OpenViking tool error: {body}"
    return body


def _call(tool_name, arguments):
    try:
        return _unwrap(_get_client().call_tool(tool_name, arguments))
    except Exception as exc:  # never propagate into the host runtime
        if isinstance(exc, OpenVikingError):
            return _error_string(exc)
        return f"OpenViking error: {exc}"


def _clean(arguments):
    return {k: v for k, v in arguments.items() if v is not None and v != ""}


def openviking_find(query: str, target_uri: str = "", limit: int = 10) -> str:
    """Ranked semantic search over OpenViking memory: URIs, abstracts, scores.

    Use at the start of substantive work to recall prior knowledge. Scope with
    target_uri (e.g. viking://~/memories/experiences) when you know where to look.
    """
    return _call("find", _clean({"query": query, "target_uri": target_uri, "limit": limit}))


def openviking_search(
    query: str, target_uri: str = "", limit: int = 10, session_id: str = ""
) -> str:
    """Deeper intent-aware search over OpenViking memory (optionally session-scoped)."""
    return _call("search", _clean({
        "query": query, "target_uri": target_uri, "limit": limit, "session_id": session_id,
    }))


def openviking_read(uri: str) -> str:
    """Read the exact text of one viking:// URI (e.g. a memory or SKILL.md)."""
    return _call("read", _clean({"uris": [uri]}))


def openviking_remember(content: str) -> str:
    """Persist a durable fact, preference, decision, or lesson into OpenViking.

    Pass a short factual summary; the server extracts and files memories.
    """
    # Upstream remember takes role-tagged messages; wrap the summary as one.
    messages = [{"role": "user", "content": content}]
    return _call("remember", {"messages": messages})


def openviking_write(uri: str, content: str) -> str:
    """Write exact content to a known viking:// URI (parent must exist)."""
    return _call("write", {"uri": uri, "content": content})


def openviking_add_skill(
    content: str = "", path: str = "", target_uri: str = ""
) -> str:
    """Install an agent skill into OpenViking from SKILL.md text or a source path/URL.

    `content` is the full SKILL.md text (the name comes from its frontmatter);
    `path` is a local folder/zip or Git URL. `target_uri` defaults to the user's
    own skills root; viking://agent/skills shares account-wide.
    """
    return _call("add_skill", _clean({
        "data": content, "path": path, "target_uri": target_uri,
    }))


def openviking_health() -> str:
    """Check the OpenViking server connection and report status."""
    return _call("health", {})


TOOLS = {
    "openviking_find": (
        openviking_find,
        (
            "Ranked semantic recall from OpenViking long-term memory (URI + abstract + score). "
            "Call at the start of substantive tasks before doing the work."
        ),
    ),
    "openviking_search": (
        openviking_search,
        (
            "Deeper intent-aware search over OpenViking long-term memory; "
            "use when find is too shallow."
        ),
    ),
    "openviking_read": (
        openviking_read,
        "Read the exact text stored at one viking:// URI.",
    ),
    "openviking_remember": (
        openviking_remember,
        "Persist a durable fact, preference, decision, or hard-won lesson into OpenViking memory.",
    ),
    "openviking_write": (
        openviking_write,
        "Write exact content to a known viking:// URI (curated notes, shared references).",
    ),
    "openviking_add_skill": (
        openviking_add_skill,
        (
            "Install an agent skill into OpenViking from SKILL.md text, "
            "a local folder/zip, or a Git URL."
        ),
    ),
    "openviking_health": (
        openviking_health,
        "Check connectivity and authentication against the configured OpenViking server.",
    ),
}
