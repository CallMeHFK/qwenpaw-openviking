import unittest
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

    def test_health_check_never_raises_without_server(self):
        api = FakeApi()
        p = plugin_module.OpenVikingMemoryPlugin()
        p.register(api)
        api.startup_hooks["openviking_health_check"]()  # server unreachable: warn only
        api.shutdown_hooks["openviking_close_session"]()

    def test_tool_error_becomes_string(self):
        api = FakeApi()
        plugin_module.OpenVikingMemoryPlugin().register(api)
        out = api.tools["openviking_health"]["func"]()
        self.assertIsInstance(out, str)
        self.assertIn("OpenViking", out)

    def test_health_check_timeout_is_capped(self):
        import urllib.request as urllib_request

        api = FakeApi()
        p = plugin_module.OpenVikingMemoryPlugin()
        p.register(api)
        with mock.patch.object(urllib_request, "urlopen", side_effect=OSError("down")) as m:
            p._startup_health_check()
        self.assertLessEqual(m.call_args.kwargs["timeout"], 3.0)

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


if __name__ == "__main__":
    unittest.main()
