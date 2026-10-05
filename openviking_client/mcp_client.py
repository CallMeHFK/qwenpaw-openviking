"""Synchronous MCP streamable-HTTP client for OpenViking, stdlib only.

Port of agent-plugins/servers/shared/mcp-proxy-core.mjs transport semantics:
POST {mcp_url} with JSON-RPC, JSON or SSE responses, session capture from the
mcp-session-id response header, protocol-version negotiation on initialize,
one re-initialize-and-retry on 400/404 (expired session).
"""

import contextlib
import http.client
import json
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_PROTOCOL_VERSION = "2025-06-18"
DELETE_TIMEOUT_S = 2.0

_SENSITIVE_HEADERS = (
    "Authorization",
    "X-OpenViking-Account",
    "X-OpenViking-User",
    "X-OpenViking-Actor-Peer",
)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip credentials on cross-origin redirects (fetch-spec parity).

    urllib forwards Authorization verbatim on 30x; Node's fetch strips it
    cross-origin, and the upstream proxy relies on that behavior.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is None:
            return None
        origin = urllib.parse.urlsplit(req.full_url).netloc
        if urllib.parse.urlsplit(newurl).netloc != origin:
            for header in _SENSITIVE_HEADERS:
                new_req.headers.pop(header, None)
                new_req.unredirected_hdrs.pop(header, None)
        return new_req


_opener = urllib.request.build_opener(_SafeRedirectHandler)


def _urlopen(request, timeout):
    return _opener.open(request, timeout=timeout)


class OpenVikingError(Exception):
    """Base class for all OpenViking client failures."""


class McpHttpError(OpenVikingError):
    def __init__(self, status, body_text=""):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body_text = body_text


class McpAuthError(McpHttpError):
    """401/403: credentials rejected, retrying will not help."""


class McpTimeoutError(OpenVikingError):
    """Client-side timeout; the server may still be processing."""


class McpConnectionError(OpenVikingError):
    """Connection failed; the server is likely unreachable."""


class McpProtocolError(OpenVikingError):
    """JSON-RPC error or malformed response from the server."""


def parse_sse_messages(text):
    messages = []
    data_lines = []

    def flush():
        if not data_lines:
            return
        data = "\n".join(data_lines).strip()
        data_lines.clear()
        if not data or data == "[DONE]":
            return
        try:
            messages.append(json.loads(data))
        except json.JSONDecodeError as exc:
            raise McpProtocolError(f"malformed SSE event data: {exc}") from exc

    for raw_line in str(text or "").splitlines():
        if raw_line == "":
            flush()
            continue
        if raw_line.startswith(":"):
            continue
        field, sep, value = raw_line.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if field == "data":
            data_lines.append(value if sep else "")
    flush()
    return messages


def _parse_http_body(content_type, text):
    if not str(text or "").strip():
        return []
    if "text/event-stream" in str(content_type or "").lower():
        return parse_sse_messages(text)
    try:
        return [json.loads(text)]
    except Exception:
        return []


def serialize_body_for_error(body_text):
    try:
        parsed = json.loads(body_text)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        err = parsed.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        detail = parsed.get("detail")
        if isinstance(detail, str):
            return detail
        if detail is not None:
            return json.dumps(detail)
    return " ".join(str(body_text or "").split())[:500]


def build_ov_headers(config, actor_peer_id="", identity_headers=None, extra_headers=None):
    identity = (
        bool(config.get("send_identity_headers"))
        if identity_headers is None
        else bool(identity_headers)
    )
    headers = {"Content-Type": "application/json"}
    if config.get("api_key"):
        headers["Authorization"] = f"Bearer {config['api_key']}"
    if identity and config.get("account"):
        headers["X-OpenViking-Account"] = config["account"]
    if identity and config.get("user"):
        headers["X-OpenViking-User"] = config["user"]
    if actor_peer_id:
        headers["X-OpenViking-Actor-Peer"] = actor_peer_id
    if config.get("user_agent"):
        headers["User-Agent"] = config["user_agent"]
    if extra_headers:
        headers.update(extra_headers)
    return headers


class McpClient:
    """Thread-safe synchronous MCP-over-HTTP client for one OpenViking server."""

    def __init__(self, config):
        self._config = dict(config)
        self._mcp_url = self._config.get("mcp_url") or f"{self._config.get('base_url', '')}/mcp"
        self._timeout_s = max(1.0, float(self._config.get("timeout_ms") or 15000) / 1000.0)
        self._session_id = ""
        self._protocol_version = DEFAULT_PROTOCOL_VERSION
        self._initialized = False
        self._request_counter = 0
        self._lock = threading.Lock()

    @property
    def mcp_url(self):
        return self._mcp_url

    def _next_id(self):
        self._request_counter += 1
        return f"qwenpaw-{self._request_counter}"

    def _headers(self, include_session=True):
        return build_ov_headers(
            self._config,
            actor_peer_id=self._config.get("peer_id", ""),
            extra_headers={
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": self._protocol_version,
                **(
                    {"Mcp-Session-Id": self._session_id}
                    if include_session and self._session_id
                    else {}
                ),
            },
        )

    def _post(self, message, include_session=True):
        body = json.dumps(message).encode("utf-8")
        request = urllib.request.Request(
            self._mcp_url,
            data=body,
            headers=self._headers(include_session),
            method="POST",
        )
        try:
            with _urlopen(request, timeout=self._timeout_s) as response:
                text = response.read().decode("utf-8", errors="replace")
                messages = _parse_http_body(response.headers.get("content-type"), text)
                next_session = response.headers.get("mcp-session-id")
                if next_session:
                    self._session_id = next_session
                if message.get("method") == "initialize":
                    for msg in messages:
                        negotiated = (
                            (msg.get("result") or {}).get("protocolVersion")
                            if isinstance(msg, dict)
                            else None
                        )
                        if isinstance(negotiated, str) and negotiated:
                            self._protocol_version = negotiated
                            break
                return messages
        except urllib.error.HTTPError as exc:
            text = ""
            with contextlib.suppress(Exception):
                text = exc.read().decode("utf-8", errors="replace")
            # Error responses can still carry a fresh session id.
            next_session = exc.headers.get("mcp-session-id") if exc.headers else None
            if next_session:
                self._session_id = next_session
            if exc.code in (401, 403):
                raise McpAuthError(exc.code, text) from exc
            raise McpHttpError(exc.code, text) from exc
        except TimeoutError as exc:
            raise McpTimeoutError(str(exc) or "timed out") from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise McpTimeoutError(str(reason)) from exc
            raise McpConnectionError(str(reason)) from exc
        except (OSError, http.client.HTTPException) as exc:
            # Server accepted then dropped the connection (RemoteDisconnected,
            # ConnectionResetError) or truncated the body (IncompleteRead) —
            # urllib lets these through unwrapped.
            raise McpConnectionError(str(exc) or exc.__class__.__name__) from exc

    def _initialize(self):
        self._session_id = ""
        self._protocol_version = DEFAULT_PROTOCOL_VERSION
        user_agent = self._config.get("user_agent") or "openviking-memory-qwenpaw/0.0.0"
        client_name, _, client_version = user_agent.partition("/")
        messages = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": client_name,
                    "version": client_version or "0.0.0",
                },
            },
        }, include_session=False)
        self._initialized = True
        with contextlib.suppress(OpenVikingError):
            self._post(
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                include_session=True,
            )
        return messages

    def _request_once(self, method, params):
        if not self._initialized:
            self._initialize()
        request_id = self._next_id()
        messages = self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            include_session=True,
        )
        for msg in messages:
            if not isinstance(msg, dict) or msg.get("id") != request_id:
                continue
            if "error" in msg:
                err = msg["error"] or {}
                raise McpProtocolError(str(err.get("message") or err))
            return msg.get("result") if "result" in msg else {}
        raise McpProtocolError("OpenViking MCP upstream returned no response for the request id")

    def call_tool(self, name, arguments):
        """tools/call with one re-initialize retry on an expired session (400/404)."""
        with self._lock:
            try:
                return self._call_tool_once(name, arguments)
            except McpHttpError as exc:
                # Retry only when the session expired mid-call; a 400/404 from
                # _initialize itself leaves _initialized False and re-running
                # it would just fail the same way (upstream retries only
                # non-initialize messages).
                if exc.status not in (400, 404) or not self._initialized:
                    raise
                self._initialized = False
                self._initialize()
                return self._call_tool_once(name, arguments)

    def _call_tool_once(self, name, arguments):
        return self._request_once("tools/call", {"name": name, "arguments": arguments or {}})

    def list_tools(self):
        with self._lock:
            try:
                return self._request_once("tools/list", {})
            except McpHttpError as exc:
                if exc.status not in (400, 404):
                    raise
                self._initialized = False
                self._initialize()
                return self._request_once("tools/list", {})

    def close(self):
        """Best-effort session DELETE; never raises."""
        with self._lock:
            if not self._session_id:
                return
            request = urllib.request.Request(
                self._mcp_url, headers=self._headers(True), method="DELETE",
            )
            with contextlib.suppress(Exception), _urlopen(request, timeout=DELETE_TIMEOUT_S):
                pass
            self._session_id = ""
            self._initialized = False
