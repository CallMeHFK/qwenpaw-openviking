import io
import json
import unittest
import urllib.error
from unittest import mock

from openviking_client import mcp_client
from openviking_client.mcp_client import McpClient


class FakeResponse:
    def __init__(self, payload, headers=None, content_type="application/json"):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        self._body = payload.encode()
        self.headers = headers or {}
        self.headers.setdefault("content-type", content_type)

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_urlopen(script):
    """script: list of FakeResponse | Exception, consumed one per POST/DELETE."""
    calls = []
    queue = list(script)

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        if not queue:
            raise AssertionError("unexpected extra request")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    fake_urlopen.calls = calls
    return fake_urlopen


def init_response(session="sess-1", protocol="2025-06-18"):
    return FakeResponse(
        {"jsonrpc": "2.0", "id": "qwenpaw-1",
         "result": {"protocolVersion": protocol, "capabilities": {},
                    "serverInfo": {"name": "openviking", "version": "0.4.16"}}},
        headers={"mcp-session-id": session},
    )


CFG = {"mcp_url": "http://ov.test/mcp", "api_key": "k", "user_agent": "openviking-memory-qwenpaw/0.1.0"}


class ParseSseTest(unittest.TestCase):
    def test_single_data(self):
        msgs = mcp_client.parse_sse_messages('data: {"a": 1}\n\n')
        self.assertEqual(msgs, [{"a": 1}])

    def test_multiline_data_and_comments(self):
        text = ': keep-alive\ndata: {"a":\ndata: 1}\n\ndata: [DONE]\n\n'
        self.assertEqual(mcp_client.parse_sse_messages(text), [{"a": 1}])

    def test_empty(self):
        self.assertEqual(mcp_client.parse_sse_messages(""), [])


class HeadersTest(unittest.TestCase):
    def test_bearer_and_identity(self):
        h = mcp_client.build_ov_headers({"api_key": "k", "account": "a", "user": "u",
                                         "send_identity_headers": True})
        self.assertEqual(h["Authorization"], "Bearer k")
        self.assertEqual(h["X-OpenViking-Account"], "a")
        self.assertEqual(h["X-OpenViking-User"], "u")

    def test_no_identity_unless_trusted(self):
        h = mcp_client.build_ov_headers({"api_key": "k", "account": "a",
                                         "send_identity_headers": False})
        self.assertNotIn("X-OpenViking-Account", h)

    def test_no_bearer_without_key(self):
        self.assertNotIn("Authorization", mcp_client.build_ov_headers({}))


class CallToolTest(unittest.TestCase):
    def test_happy_path_json_response(self):
        urlopen = make_urlopen([
            init_response(),
            FakeResponse({}, content_type="application/json"),  # notifications/initialized 202-ish
            FakeResponse({"jsonrpc": "2.0", "id": "qwenpaw-2",
                          "result": {"content": [{"type": "text", "text": "hit"}]}}),
        ])
        with mock.patch.object(mcp_client.urllib.request, "urlopen", urlopen):
            client = McpClient(CFG)
            result = client.call_tool("find", {"query": "q"})
        self.assertEqual(result["content"][0]["text"], "hit")
        # session id captured and sent on subsequent requests
        self.assertEqual(urlopen.calls[-1].headers.get("Mcp-session-id"), "sess-1")

    def test_sse_response(self):
        sse = 'data: {"jsonrpc":"2.0","id":"qwenpaw-2","result":{"content":[{"type":"text","text":"ok"}]}}\n\n'
        urlopen = make_urlopen([
            init_response(),
            FakeResponse({}),
            FakeResponse(sse, content_type="text/event-stream"),
        ])
        with mock.patch.object(mcp_client.urllib.request, "urlopen", urlopen):
            result = McpClient(CFG).call_tool("health", {})
        self.assertEqual(result["content"][0]["text"], "ok")

    def test_reinitialize_on_400_then_retry(self):
        urlopen = make_urlopen([
            init_response(),
            FakeResponse({}),
            urllib.error.HTTPError("http://ov.test/mcp", 400, "Bad Request", {}, io.BytesIO(b"")),
            init_response(session="sess-2"),
            FakeResponse({}),
            FakeResponse({"jsonrpc": "2.0", "id": "qwenpaw-4",
                          "result": {"content": [{"type": "text", "text": "after-reinit"}]}}),
        ])
        with mock.patch.object(mcp_client.urllib.request, "urlopen", urlopen):
            result = McpClient(CFG).call_tool("find", {"query": "q"})
        self.assertEqual(result["content"][0]["text"], "after-reinit")

    def test_auth_error_not_retried(self):
        urlopen = make_urlopen([
            urllib.error.HTTPError("http://ov.test/mcp", 401, "Unauthorized", {},
                                   io.BytesIO(b'{"error": {"message": "bad key"}}')),
        ])
        with mock.patch.object(mcp_client.urllib.request, "urlopen", urlopen):
            with self.assertRaises(mcp_client.McpAuthError):
                McpClient(CFG).call_tool("find", {"query": "q"})
        self.assertEqual(len(urlopen.calls), 1)

    def test_connection_refused(self):
        urlopen = make_urlopen([urllib.error.URLError("Connection refused")])
        with mock.patch.object(mcp_client.urllib.request, "urlopen", urlopen):
            with self.assertRaises(mcp_client.McpConnectionError):
                McpClient(CFG).call_tool("find", {"query": "q"})

    def test_jsonrpc_error_raises_protocol_error(self):
        urlopen = make_urlopen([
            init_response(),
            FakeResponse({}),
            FakeResponse({"jsonrpc": "2.0", "id": "qwenpaw-2",
                          "error": {"code": -32602, "message": "unknown tool"}}),
        ])
        with mock.patch.object(mcp_client.urllib.request, "urlopen", urlopen):
            with self.assertRaises(mcp_client.McpProtocolError):
                McpClient(CFG).call_tool("nope", {})


if __name__ == "__main__":
    unittest.main()
