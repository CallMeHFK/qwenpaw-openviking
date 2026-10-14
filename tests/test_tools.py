import os
import unittest
from unittest import mock

from openviking_client import mcp_client, tools

PROXY_ENV = {"https_proxy": "http://127.0.0.1:7890"}
CFG = {"base_url": "https://ov.internal", "mcp_url": "https://ov.internal/mcp"}


class ErrorStringProxyHintTest(unittest.TestCase):
    def tearDown(self):
        tools.configure({})

    def _error_string(self, exc, config, env):
        tools.configure(config)
        with mock.patch.dict(os.environ, env, clear=True):
            return tools._error_string(exc)

    def test_connection_error_includes_proxy_hint_when_proxying(self):
        out = self._error_string(
            mcp_client.McpConnectionError("SSL: UNEXPECTED_EOF_WHILE_READING"),
            dict(CFG, proxy_bypass=False),
            PROXY_ENV,
        )
        self.assertIn("OPENVIKING_PROXY_BYPASS", out)
        self.assertIn("https_proxy=http://127.0.0.1:7890", out)

    def test_connection_error_no_hint_when_bypass_active(self):
        out = self._error_string(
            mcp_client.McpConnectionError("SSL: UNEXPECTED_EOF_WHILE_READING"), dict(CFG), PROXY_ENV
        )
        self.assertNotIn("OPENVIKING_PROXY_BYPASS", out)

    def test_connection_error_no_hint_without_env_proxy(self):
        out = self._error_string(
            mcp_client.McpConnectionError("connection refused"),
            dict(CFG, proxy_bypass=False),
            {},
        )
        self.assertNotIn("no_proxy", out)

    def test_timeout_error_includes_proxy_hint_when_proxying(self):
        out = self._error_string(
            mcp_client.McpTimeoutError("timed out"), dict(CFG, proxy_bypass=False), PROXY_ENV
        )
        self.assertIn("OPENVIKING_PROXY_BYPASS", out)


if __name__ == "__main__":
    unittest.main()
