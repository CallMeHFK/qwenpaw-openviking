"""QwenPaw plugin entry: OpenViking semantic long-term memory."""

import json
import logging
import os
import urllib.request
from pathlib import Path

from openviking_client import credentials, tools
from openviking_client import proxy as proxy_policy
from openviking_client.mcp_client import build_ov_headers, build_ov_opener

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(__file__).resolve().parent
HARNESS = "qwenpaw"
TOOL_ICON = "🧠"


def _plugin_version():
    try:
        with open(PLUGIN_DIR / "plugin.json", encoding="utf-8") as f:
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
            # Resolve once with root_key_fallback=True (the proxy-side semantic):
            # a pinned ovcli.conf that names only a url still falls back to
            # ov.conf's server.root_api_key. Merging two differently-resolved
            # views used to overwrite that key with an empty one.
            host_config = getattr(api, "config", None)
            if not isinstance(host_config, dict):
                host_config = {}
            proxy = credentials.resolve_connection(
                HARNESS,
                host_input=_host_input_from_config(host_config),
                root_key_fallback=True,
            )
            proxy["proxy_bypass"] = host_config.get("proxy_bypass")
            proxy["no_proxy_extra"] = host_config.get("no_proxy_extra")
            proxy["user_agent"] = credentials.build_user_agent(HARNESS, _plugin_version())
            proxy["timeout_ms"] = credentials._clamp_timeout(
                os.environ.get("OPENVIKING_TIMEOUT_MS")
            )
            proxy["debug"] = credentials._env_flag(os.environ, "OPENVIKING_DEBUG")
            self._connection = proxy
            tools.configure(proxy)
            logger.info(
                "openviking-memory: server=%s credential_source=%s auth_mode=%s has_api_key=%s",
                proxy["mcp_url"],
                proxy["credential_source"],
                proxy["auth_mode"],
                proxy["has_api_key"],
            )
        except Exception as exc:
            logger.exception("openviking-memory: credential resolution failed: %s", exc)

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
        # Startup hooks run on the install path: a hanging server must not
        # stall plugin installation, so this probe gets a hard short budget
        # regardless of the (much longer) per-request tool timeout.
        timeout_s = min(3.0, max(1.0, float(conn.get("timeout_ms", 15000)) / 1000.0))
        try:
            body = self._probe(url, conn, timeout_s)
        except Exception as exc:
            logger.warning(
                "openviking-memory: health check failed for %s: %s "
                "(tools will still retry lazily; check the server and credentials)%s",
                url,
                exc,
                self._proxy_diagnosis(url, conn, timeout_s),
            )
            return
        logger.info("openviking-memory: server healthy at %s: %s", url, body[:300])

    @staticmethod
    def _probe(url, conn, timeout_s):
        request = urllib.request.Request(
            url,
            headers=build_ov_headers(conn, actor_peer_id=conn.get("peer_id", "")),
            method="GET",
        )
        with build_ov_opener(conn).open(request, timeout=timeout_s) as response:
            return response.read().decode("utf-8", errors="replace")

    def _proxy_diagnosis(self, url, conn, timeout_s):
        """Counter-probe with the proxy policy flipped; '' when inconclusive."""
        summary = proxy_policy.describe_proxy_env()
        if not summary:
            return ""
        flipped = dict(conn, proxy_bypass=not proxy_policy.resolve_proxy_bypass(conn)["enabled"])
        try:
            self._probe(url, flipped, timeout_s)
        except Exception:
            return ""
        if flipped["proxy_bypass"]:
            return (
                f" | diagnosis: direct connection succeeds — the environment proxy "
                f"({summary}) is breaking this request; add the OpenViking host to "
                f"no_proxy or set OPENVIKING_PROXY_BYPASS=1"
            )
        return (
            f" | diagnosis: the request succeeds through the environment proxy "
            f"({summary}) but the direct connection fails; set OPENVIKING_PROXY_BYPASS=0"
        )

    def _shutdown(self):
        try:
            tools.close_client()
        except Exception as exc:
            logger.debug("openviking-memory: shutdown cleanup failed: %s", exc)


plugin = OpenVikingMemoryPlugin()
