import unittest

from openviking_client import credentials


def conn(env=None, files=None, **kw):
    return credentials.resolve_connection("qwenpaw", env=env or {}, files=files, **kw)


def empty_files():
    return {"cli_file": {}, "cli_path": "", "cli_path_candidate": "", "ov_file": {}, "ov_path": ""}


class ResolveConnectionTest(unittest.TestCase):
    def test_defaults(self):
        c = conn(files=empty_files())
        self.assertEqual(c["base_url"], "http://127.0.0.1:1933")
        self.assertEqual(c["mcp_url"], "http://127.0.0.1:1933/mcp")
        self.assertFalse(c["has_api_key"])
        self.assertEqual(c["auth_mode"], "api_key")
        self.assertFalse(c["send_identity_headers"])

    def test_env_overrides_files(self):
        files = {
            **empty_files(),
            "cli_file": {"url": "http://file-host:1111", "api_key": "file-key"},
            "cli_path": "/x/ovcli.conf",
        }
        c = conn(env={"OPENVIKING_URL": "http://env-host:2222", "OPENVIKING_API_KEY": "env-key"},
                 files=files)
        self.assertEqual(c["base_url"], "http://env-host:2222")
        self.assertEqual(c["api_key"], "env-key")
        self.assertEqual(c["credential_source"], "env")

    def test_ovcli_pins_chain_when_env_is_silent(self):
        files = {
            **empty_files(),
            "cli_file": {"url": "http://cli-host:3333", "api_key": "cli-key",
                         "account": "acc", "user": "leo"},
            "cli_path": "/x/ovcli.conf",
        }
        c = conn(files=files)
        self.assertEqual(c["credential_source"], "ovcli")
        self.assertEqual(c["base_url"], "http://cli-host:3333")
        self.assertEqual(c["api_key"], "cli-key")
        self.assertEqual(c["auth_mode"], "trusted")
        self.assertTrue(c["send_identity_headers"])

    def test_plugin_harness_section_overrides_cli_scalars(self):
        # Top-level api_key outranks the whole plugin section (upstream order:
        # cliFile.api_key, then plugin.<harness>.apiKey, then plugin.apiKey).
        files = {
            **empty_files(),
            "cli_file": {"api_key": "shared-key",
                         "plugin": {"apiKey": "plugin-shared", "qwenpaw": {"apiKey": "paw-key"}}},
            "cli_path": "/x/ovcli.conf",
        }
        self.assertEqual(conn(files=files)["api_key"], "shared-key")

    def test_plugin_harness_beats_plugin_shared(self):
        base = {**empty_files(), "cli_path": "/x/ovcli.conf"}
        files = {**base, "cli_file": {"plugin": {"apiKey": "plugin-shared",
                                                 "qwenpaw": {"apiKey": "paw-key"}}}}
        self.assertEqual(conn(files=files)["api_key"], "paw-key")
        files = {**base, "cli_file": {"plugin": {"apiKey": "plugin-shared"}}}
        self.assertEqual(conn(files=files)["api_key"], "plugin-shared")

    def test_ov_conf_server_host_port(self):
        files = {**empty_files(), "ov_file": {"server": {"host": "0.0.0.0", "port": 9999}},
                 "ov_path": "/x/ov.conf"}
        c = conn(files=files)
        self.assertEqual(c["base_url"], "http://127.0.0.1:9999")

    def test_credential_source_env_ignores_files(self):
        files = {**empty_files(), "cli_file": {"api_key": "cli-key"}, "cli_path": "/x/ovcli.conf"}
        c = conn(env={"OPENVIKING_CREDENTIAL_SOURCE": "env"}, files=files)
        self.assertFalse(c["has_api_key"])
        self.assertEqual(c["credential_source"], "env")

    def test_mcp_url_env_wins_without_host_base(self):
        c = conn(env={"OPENVIKING_MCP_URL": "http://gw:8000/mcp"}, files=empty_files())
        self.assertEqual(c["mcp_url"], "http://gw:8000/mcp")

    def test_trailing_slash_trimmed(self):
        c = conn(env={"OPENVIKING_URL": "http://h:1933/"}, files=empty_files())
        self.assertEqual(c["base_url"], "http://h:1933")
        self.assertEqual(c["mcp_url"], "http://h:1933/mcp")

    def test_root_api_key_fallback(self):
        # Pinned ovcli.conf that names only a url: the key may still come from
        # ov.conf's server.root_api_key, but only with root_key_fallback=True.
        files = {
            **empty_files(),
            "cli_file": {"url": "http://cli-host:3333"},
            "cli_path": "/x/ovcli.conf",
            "ov_file": {"server": {"root_api_key": "root-key"}},
            "ov_path": "/x/ov.conf",
        }
        with_fallback = credentials.resolve_connection(
            "qwenpaw", env={}, files=files, root_key_fallback=True
        )
        without_fallback = conn(files=files)
        self.assertEqual(with_fallback["api_key"], "root-key")
        self.assertEqual(without_fallback["api_key"], "")

    def test_overflow_values_fall_back_to_defaults(self):
        self.assertEqual(credentials._clamp_timeout("inf"), credentials.DEFAULT_TIMEOUT_MS)
        files = {**empty_files(), "ov_file": {"server": {"port": "inf"}}, "ov_path": "/x/ov.conf"}
        self.assertEqual(conn(files=files)["base_url"], "http://127.0.0.1:1933")


class ProxyConnectionTest(unittest.TestCase):
    def test_timeout_clamped_to_minimum(self):
        c = credentials.build_proxy_connection("qwenpaw", env={"OPENVIKING_TIMEOUT_MS": "5"})
        self.assertEqual(c["timeout_ms"], 1000)

    def test_timeout_default(self):
        c = credentials.build_proxy_connection("qwenpaw", env={})
        self.assertEqual(c["timeout_ms"], 15000)

    def test_user_agent_shape(self):
        self.assertEqual(credentials.build_user_agent("qwenpaw", "0.1.0"),
                         "openviking-memory-qwenpaw/0.1.0")
        self.assertEqual(credentials.build_user_agent("qwenpaw", ""),
                         "openviking-memory-qwenpaw/0.0.0")


if __name__ == "__main__":
    unittest.main()
