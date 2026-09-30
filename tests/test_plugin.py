import unittest

import plugin as plugin_module
from openviking_client import tools


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
        tools.configure({"mcp_url": "http://unused.test/mcp"})

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


if __name__ == "__main__":
    unittest.main()
