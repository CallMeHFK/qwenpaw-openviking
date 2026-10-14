import os
import unittest
from typing import ClassVar
from unittest import mock

import plugin as plugin_module
from openviking_client import tools

DUMMY_CONNECTION = {
    "base_url": "http://127.0.0.1:1",
    "mcp_url": "http://127.0.0.1:1/mcp",
    "api_key": "",
    "account": "",
    "user": "",
    "peer_id": "",
    "auth_mode": "api_key",
    "send_identity_headers": False,
    "has_api_key": False,
    "credential_source": "env",
    "timeout_ms": 15000,
}


class FakeApi:
    def __init__(self):
        self.config = {}
        self.tools = {}
        self.skill_providers = []
        self.startup_hooks = {}
        self.shutdown_hooks = {}

    def register_tool(self, tool_name, tool_func, description="", icon="", enabled=False,
                      tool_type="", target_param=""):
        self.tools[tool_name] = {
            "func": tool_func, "enabled": enabled, "tool_type": tool_type, "icon": icon,
        }

    def register_skill_provider(self, skills_dir, *, enabled_by_default=True, channels=None):
        self.skill_providers.append((skills_dir, enabled_by_default))

    def register_startup_hook(self, hook_name, callback, priority=100):
        self.startup_hooks[hook_name] = callback

    def register_shutdown_hook(self, hook_name, callback, priority=100):
        self.shutdown_hooks[hook_name] = callback


class FakeHttpResponse:
    def __init__(self, body=b"{}"):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """script: FakeHttpResponse | Exception, consumed one per open()."""

    def __init__(self, script):
        self._queue = list(script)
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append({"url": request.full_url, "timeout": timeout})
        if not self._queue:
            raise AssertionError("unexpected extra open()")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class RegisterTest(unittest.TestCase):
    def setUp(self):
        # register() must never resolve the host's real credential files: they
        # point at a live server and the startup health check would hit it for
        # real. Patch the chain to a fixed loopback dummy.
        # 127.0.0.1:1 refuses instantly; a DNS name would make the suite
        # wait on real resolver timeouts.
        self._resolve_patcher = mock.patch.object(
            plugin_module.credentials, "resolve_connection", return_value=dict(DUMMY_CONNECTION)
        )
        self._proxy_patcher = mock.patch.object(
            plugin_module.credentials, "build_proxy_connection", return_value=dict(DUMMY_CONNECTION)
        )
        self._resolve_patcher.start()
        self._proxy_patcher.start()
        self.addCleanup(self._resolve_patcher.stop)
        self.addCleanup(self._proxy_patcher.stop)
        tools.configure({"mcp_url": "http://127.0.0.1:1/mcp"})

    def test_registers_full_surface(self):
        api = FakeApi()
        plugin_module.OpenVikingMemoryPlugin().register(api)

        expected = set(tools.TOOLS)
        self.assertEqual(set(api.tools), expected)
        self.assertEqual(len(expected), 7)
        for name, spec in api.tools.items():
            self.assertTrue(spec["enabled"], name)
            self.assertEqual(spec["tool_type"], "network", name)
            self.assertTrue(callable(spec["func"]), name)

        self.assertEqual(len(api.skill_providers), 1)
        skills_dir, enabled = api.skill_providers[0]
        self.assertTrue(skills_dir.is_dir())
        self.assertTrue(enabled)
        self.assertEqual(
            sorted(p.name for p in skills_dir.iterdir() if p.is_dir()),
            ["openviking-memory", "openviking-skills", "ov-experience-memory",
             "ov-kanban", "ov-memory-troubleshoot"],
        )

        self.assertIn("openviking_health_check", api.startup_hooks)
        self.assertIn("openviking_close_session", api.shutdown_hooks)

    def test_register_passes_proxy_config_into_connection(self):
        api = FakeApi()
        api.config = {
            "base_url": "https://ov.internal",
            "proxy_bypass": False,
            "no_proxy_extra": ["a.example"],
        }
        p = plugin_module.OpenVikingMemoryPlugin()
        p.register(api)
        self.assertFalse(p._connection["proxy_bypass"])
        self.assertEqual(p._connection["no_proxy_extra"], ["a.example"])

    def test_register_proxy_config_defaults_to_none(self):
        api = FakeApi()
        p = plugin_module.OpenVikingMemoryPlugin()
        p.register(api)
        self.assertIsNone(p._connection["proxy_bypass"])
        self.assertIsNone(p._connection["no_proxy_extra"])

    def test_health_check_never_raises_without_server(self):
        api = FakeApi()
        p = plugin_module.OpenVikingMemoryPlugin()
        p.register(api)
        with mock.patch.dict(os.environ, {}, clear=True):
            api.startup_hooks["openviking_health_check"]()  # server unreachable: warn only
        api.shutdown_hooks["openviking_close_session"]()

    def test_tool_error_becomes_string(self):
        api = FakeApi()
        plugin_module.OpenVikingMemoryPlugin().register(api)
        out = api.tools["openviking_health"]["func"]()
        self.assertIsInstance(out, str)
        self.assertIn("OpenViking", out)

    def test_health_check_timeout_is_capped(self):
        api = FakeApi()
        p = plugin_module.OpenVikingMemoryPlugin()
        p.register(api)
        opener = FakeOpener([OSError("down")])
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(plugin_module, "build_ov_opener", return_value=opener),
        ):
            p._startup_health_check()
        self.assertLessEqual(opener.calls[0]["timeout"], 3.0)

    def test_add_skill_wire_args_match_server_schema(self):
        from unittest import mock

        sent = {}

        class FakeClient:
            def call_tool(self, name, arguments):
                sent["name"] = name
                sent["arguments"] = arguments
                return {"content": [{"type": "text", "text": "ok"}]}

        tools.configure({"mcp_url": "http://127.0.0.1:1/mcp"})
        with mock.patch.object(tools, "_get_client", return_value=FakeClient()):
            tools.openviking_add_skill(
                content="---\nname: x\n---\nbody", target_uri="viking://agent/skills"
            )
        self.assertEqual(sent["name"], "add_skill")
        # Server schema (add_skillArguments) has data/path/skills/target_uri/
        # list_only — no "name"; the name lives in the SKILL.md frontmatter.
        self.assertEqual(set(sent["arguments"]), {"data", "target_uri"})
        self.assertNotIn("name", sent["arguments"])


class HealthCheckProxyDiagnosisTest(unittest.TestCase):
    CONN: ClassVar[dict] = dict(DUMMY_CONNECTION, base_url="https://ov.internal")
    ENV_PROXY: ClassVar[dict] = {"https_proxy": "http://127.0.0.1:7890"}
    DOWN = OSError("SSL: UNEXPECTED_EOF_WHILE_READING")

    def _plugin(self, **overrides):
        p = plugin_module.OpenVikingMemoryPlugin()
        p._connection = dict(self.CONN, **overrides)
        return p

    def _run_with_openers(self, p, openers, env):
        built = []

        def fake_build(conn):
            built.append(conn)
            return openers[len(built) - 1]

        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(plugin_module, "build_ov_opener", side_effect=fake_build),
            self.assertLogs("plugin", level="INFO") as logs,
        ):
            p._startup_health_check()
        return "\n".join(logs.output), built

    def test_proxy_path_works_when_direct_fails(self):
        # Default bypass on: primary probe is direct (fails), counter-probe uses
        # the environment proxy (succeeds).
        p = self._plugin()
        text, built = self._run_with_openers(
            p,
            [FakeOpener([self.DOWN]), FakeOpener([FakeHttpResponse(b'{"status":"ok"}')])],
            self.ENV_PROXY,
        )
        self.assertIn("health check failed", text)
        self.assertIn("succeeds through the environment proxy", text)
        self.assertIn("OPENVIKING_PROXY_BYPASS=0", text)
        self.assertEqual(len(built), 2)
        self.assertFalse(built[1]["proxy_bypass"])  # counter-probe flipped the policy

    def test_direct_path_works_when_proxy_fails(self):
        p = self._plugin(proxy_bypass=False)
        text, built = self._run_with_openers(
            p,
            [FakeOpener([self.DOWN]), FakeOpener([FakeHttpResponse(b'{"status":"ok"}')])],
            self.ENV_PROXY,
        )
        self.assertIn("direct connection succeeds", text)
        self.assertIn("OPENVIKING_PROXY_BYPASS=1", text)
        self.assertTrue(built[1]["proxy_bypass"])

    def test_no_diagnosis_when_both_paths_fail(self):
        p = self._plugin()
        text, _built = self._run_with_openers(
            p,
            [FakeOpener([self.DOWN]), FakeOpener([self.DOWN])],
            self.ENV_PROXY,
        )
        self.assertIn("health check failed", text)
        self.assertNotIn("diagnosis", text)

    def test_no_counter_probe_without_env_proxy(self):
        p = self._plugin()
        text, built = self._run_with_openers(p, [FakeOpener([self.DOWN])], {})
        self.assertIn("health check failed", text)
        self.assertEqual(len(built), 1)

    def test_healthy_primary_probe_skips_counter_probe(self):
        p = self._plugin()
        text, built = self._run_with_openers(
            p,
            [FakeOpener([FakeHttpResponse(b'{"status":"ok"}')])],
            self.ENV_PROXY,
        )
        self.assertIn("server healthy", text)
        self.assertEqual(len(built), 1)


if __name__ == "__main__":
    unittest.main()
