import os
import unittest
import urllib.request
from unittest import mock

from openviking_client import proxy as proxy_module

ENV_PROXIES = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
BASE = {"base_url": "https://ov.internal", "mcp_url": "https://ov.internal/mcp"}


def clean_env(**overrides):
    return mock.patch.dict(os.environ, overrides, clear=True)


class ResolveProxyBypassTest(unittest.TestCase):
    def test_default_bypasses_configured_hosts(self):
        d = proxy_module.resolve_proxy_bypass(BASE, env={})
        self.assertTrue(d["enabled"])
        self.assertEqual(d["hosts"], ["ov.internal"])
        self.assertEqual(d["extra"], [])

    def test_mcp_url_host_added_when_different(self):
        d = proxy_module.resolve_proxy_bypass(
            {"base_url": "https://ov.internal", "mcp_url": "https://mcp.other.example/mcp"},
            env={},
        )
        self.assertEqual(d["hosts"], ["ov.internal", "mcp.other.example"])

    def test_host_lowercased_and_port_stripped(self):
        d = proxy_module.resolve_proxy_bypass({"base_url": "https://OV.Internal:8443"}, env={})
        self.assertEqual(d["hosts"], ["ov.internal"])

    def test_config_false_wins_over_env_true(self):
        d = proxy_module.resolve_proxy_bypass(
            dict(BASE, proxy_bypass=False), env={"OPENVIKING_PROXY_BYPASS": "1"}
        )
        self.assertFalse(d["enabled"])

    def test_config_true_wins_over_env_false(self):
        d = proxy_module.resolve_proxy_bypass(
            dict(BASE, proxy_bypass=True), env={"OPENVIKING_PROXY_BYPASS": "0"}
        )
        self.assertTrue(d["enabled"])

    def test_env_disables_when_config_absent(self):
        for raw in ("0", "false", "no", "off", "False"):
            d = proxy_module.resolve_proxy_bypass(BASE, env={"OPENVIKING_PROXY_BYPASS": raw})
            self.assertFalse(d["enabled"], raw)

    def test_extra_hosts_from_config_list(self):
        d = proxy_module.resolve_proxy_bypass(
            dict(BASE, no_proxy_extra=["a.example", ".b.example"]), env={}
        )
        self.assertEqual(d["extra"], ["a.example", ".b.example"])

    def test_extra_hosts_from_env_string(self):
        d = proxy_module.resolve_proxy_bypass(
            BASE, env={"OPENVIKING_NO_PROXY_EXTRA": "a.example, .b.example "}
        )
        self.assertEqual(d["extra"], ["a.example", ".b.example"])


class SelectiveProxyHandlerTest(unittest.TestCase):
    def test_bypassed_host_stays_direct(self):
        handler = proxy_module._SelectiveProxyHandler(["ov.internal"], proxies=dict(ENV_PROXIES))
        req = urllib.request.Request("https://ov.internal/mcp")
        # proxy_open returning None without set_proxy = opener falls through to
        # the direct HTTP(S) handler.
        self.assertIsNone(handler.proxy_open(req, ENV_PROXIES["https"], "https"))
        self.assertEqual(req.host, "ov.internal")
        self.assertIsNone(getattr(req, "_tunnel_host", None))

    def test_bypassed_host_with_port_still_direct(self):
        handler = proxy_module._SelectiveProxyHandler(["ov.internal"], proxies=dict(ENV_PROXIES))
        req = urllib.request.Request("https://ov.internal:8443/mcp")
        handler.proxy_open(req, ENV_PROXIES["https"], "https")
        self.assertEqual(req.host, "ov.internal:8443")
        self.assertIsNone(getattr(req, "_tunnel_host", None))

    def test_other_hosts_use_env_proxy(self):
        with clean_env():
            handler = proxy_module._SelectiveProxyHandler(
                ["ov.internal"], proxies=dict(ENV_PROXIES)
            )
            req = urllib.request.Request("https://other.example/mcp")
            handler.proxy_open(req, ENV_PROXIES["https"], "https")
            # set_proxy redirected the request at the proxy, tunneling the origin.
            self.assertEqual(req.host, "127.0.0.1:7890")
            self.assertEqual(req._tunnel_host, "other.example")

    def test_dot_entry_matches_subdomain_only(self):
        handler = proxy_module._SelectiveProxyHandler([".tail.example"], proxies=dict(ENV_PROXIES))
        sub = urllib.request.Request("https://ov.tail.example/mcp")
        handler.proxy_open(sub, ENV_PROXIES["https"], "https")
        self.assertEqual(sub.host, "ov.tail.example")
        with clean_env():
            bare = urllib.request.Request("https://tail.example/mcp")
            handler.proxy_open(bare, ENV_PROXIES["https"], "https")
            self.assertEqual(bare.host, "127.0.0.1:7890")


class BuildOpenerTest(unittest.TestCase):
    def test_bypass_adds_selective_handler(self):
        with clean_env(http_proxy=ENV_PROXIES["http"], https_proxy=ENV_PROXIES["https"]):
            opener = proxy_module.build_opener(BASE)
        self.assertTrue(
            any(isinstance(h, proxy_module._SelectiveProxyHandler) for h in opener.handlers)
        )

    def test_bypass_disabled_keeps_default_proxy_handler(self):
        with clean_env(http_proxy=ENV_PROXIES["http"], https_proxy=ENV_PROXIES["https"]):
            opener = proxy_module.build_opener(dict(BASE, proxy_bypass=False))
        self.assertFalse(
            any(isinstance(h, proxy_module._SelectiveProxyHandler) for h in opener.handlers)
        )
        self.assertTrue(any(isinstance(h, urllib.request.ProxyHandler) for h in opener.handlers))

    def test_extra_handlers_kept(self):
        # Must register at least one handler method: build_opener drops bare
        # BaseHandler subclasses that define no *_open hooks.
        class _Marker(urllib.request.HTTPRedirectHandler):
            pass

        with clean_env():
            opener = proxy_module.build_opener(BASE, extra_handlers=[_Marker()])
        self.assertTrue(any(isinstance(h, _Marker) for h in opener.handlers))

    def test_extra_hosts_reach_handler(self):
        with clean_env(https_proxy=ENV_PROXIES["https"]):
            opener = proxy_module.build_opener(dict(BASE, no_proxy_extra=["a.example"]))
        handler = next(
            h for h in opener.handlers if isinstance(h, proxy_module._SelectiveProxyHandler)
        )
        self.assertIn("a.example", handler._bypass_hosts)
        self.assertIn("ov.internal", handler._bypass_hosts)


class DescribeProxyEnvTest(unittest.TestCase):
    def test_empty_when_unset(self):
        self.assertEqual(proxy_module.describe_proxy_env({}), "")

    def test_lists_set_vars_with_lowercase_name(self):
        out = proxy_module.describe_proxy_env({"http_proxy": "http://127.0.0.1:7890"})
        self.assertEqual(out, "http_proxy=http://127.0.0.1:7890")
        out = proxy_module.describe_proxy_env({"HTTPS_PROXY": "http://p:1"})
        self.assertIn("https_proxy=http://p:1", out)

    def test_redacts_userinfo(self):
        out = proxy_module.describe_proxy_env({"http_proxy": "http://user:secret@127.0.0.1:7890"})
        self.assertNotIn("secret", out)
        self.assertIn("127.0.0.1:7890", out)


class ProxyHintTest(unittest.TestCase):
    def test_empty_without_env_proxy(self):
        self.assertEqual(proxy_module.proxy_hint(dict(BASE, proxy_bypass=False), env={}), "")

    def test_empty_when_bypass_active(self):
        out = proxy_module.proxy_hint(BASE, env={"http_proxy": "http://127.0.0.1:7890"})
        # Default bypass is on: the proxy is not on the path, so no hint.
        self.assertEqual(out, "")

    def test_hint_when_proxying_and_env_set(self):
        out = proxy_module.proxy_hint(
            dict(BASE, proxy_bypass=False), env={"https_proxy": "http://127.0.0.1:7890"}
        )
        self.assertIn("https_proxy=http://127.0.0.1:7890", out)
        self.assertIn("OPENVIKING_PROXY_BYPASS", out)
        self.assertIn("no_proxy", out)

    def test_hint_when_env_disables_bypass(self):
        out = proxy_module.proxy_hint(
            BASE,
            env={"https_proxy": "http://127.0.0.1:7890", "OPENVIKING_PROXY_BYPASS": "0"},
        )
        self.assertIn("OPENVIKING_PROXY_BYPASS", out)


if __name__ == "__main__":
    unittest.main()
