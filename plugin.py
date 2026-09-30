"""QwenPaw plugin entry: OpenViking semantic long-term memory."""

import json
import logging
import urllib.request
from pathlib import Path

from openviking_client import credentials, tools
from openviking_client.mcp_client import build_ov_headers

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(__file__).resolve().parent
HARNESS = "qwenpaw"
TOOL_ICON = "🧠"


def _plugin_version():
    try:
        with open(PLUGIN_DIR / "plugin.json", "r", encoding="utf-8") as f:
            return str(json.load(f).get("version", ""))
    except Exception:
        return ""


def _host_input_from_config(config):
    """Plugin config (plugin settings UI) acts as the highest-priority layer."""
    if not isinstance(config, dict):
        return {}
    return {
        "baseUrl": config.get("base_url") or config.get("baseUrl") or "",
        "apiKey": config.get("api_key") or config.get("apiKey") or "",
        "account": config.get("account") or "",
        "user": config.get("user") or "",
    }


class OpenVikingMemoryPlugin:
    def __init__(self):
        self._connection = None

    def register(self, api):
        try:
            connection = credentials.resolve_connection(
                HARNESS, host_input=_host_input_from_config(getattr(api, "config", None))
            )
            proxy = credentials.build_proxy_connection(HARNESS, version=_plugin_version())
            # resolve_connection honours host input; build_proxy_connection does
            # not, so merge host overrides into the proxy view.
            if connection["base_url"] != proxy["base_url"]:
                proxy["base_url"] = connection["base_url"]
                proxy["mcp_url"] = connection["mcp_url"]
            for key in ("api_key", "account", "user", "peer_id", "auth_mode",
                        "send_identity_headers", "has_api_key"):
                proxy[key] = connection[key]
            self._connection = proxy
            tools.configure(proxy)
            logger.info(
                "openviking-memory: server=%s credential_source=%s auth_mode=%s has_api_key=%s",
                proxy["mcp_url"], proxy["credential_source"], proxy["auth_mode"], proxy["has_api_key"],
            )
        except Exception as exc:
            logger.error("openviking-memory: credential resolution failed: %s", exc, exc_info=True)

        for tool_name, (tool_func, description) in tools.TOOLS.items():
            try:
                api.register_tool(
                    tool_name=tool_name,
                    tool_func=tool_func,
                    description=description,
                    icon=TOOL_ICON,
                    enabled=True,
                    tool_type="network",
                )
            except Exception as exc:
                logger.error("openviking-memory: failed to register tool %s: %s", tool_name, exc)

        try:
            api.register_skill_provider(PLUGIN_DIR / "skills", enabled_by_default=True)
        except Exception as exc:
            logger.error("openviking-memory: failed to register skill provider: %s", exc)

        try:
            api.register_startup_hook(
                hook_name="openviking_health_check",
                callback=self._startup_health_check,
                priority=90,
            )
        except Exception as exc:
            logger.error("openviking-memory: failed to register startup hook: %s", exc)

        try:
            api.register_shutdown_hook(
                hook_name="openviking_close_session",
                callback=self._shutdown,
                priority=100,
            )
        except Exception as exc:
            logger.error("openviking-memory: failed to register shutdown hook: %s", exc)

    def _startup_health_check(self):
        """One /api/v1/system/status probe; warns on failure, never raises."""
        conn = self._connection
        if not conn:
            logger.warning("openviking-memory: no connection configured; skipping health check")
            return
        url = f"{conn['base_url']}/api/v1/system/status"
        try:
            request = urllib.request.Request(
                url,
                headers=build_ov_headers(conn, actor_peer_id=conn.get("peer_id", "")),
                method="GET",
            )
            timeout_s = max(1.0, float(conn.get("timeout_ms", 15000)) / 1000.0)
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                body = response.read().decode("utf-8", errors="replace")
            logger.info("openviking-memory: server healthy at %s: %s", url, body[:300])
        except Exception as exc:
            logger.warning(
                "openviking-memory: health check failed for %s: %s "
                "(tools will still retry lazily; check the server and credentials)",
                url, exc,
            )

    def _shutdown(self):
        try:
            tools.close_client()
        except Exception as exc:
            logger.debug("openviking-memory: shutdown cleanup failed: %s", exc)


plugin = OpenVikingMemoryPlugin()
