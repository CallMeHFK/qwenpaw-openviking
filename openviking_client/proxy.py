"""HTTP proxy policy for OpenViking traffic.

urllib reads http_proxy/https_proxy/no_proxy from the environment. On hosts
behind a local proxy whose no_proxy list misses the OpenViking server
(tailnet/LAN deployments hit this a lot), requests die inside the proxy
tunnel with a misleading TLS EOF. Openers built here bypass the environment
proxy for the configured server hosts by default; set OPENVIKING_PROXY_BYPASS=0
(or plugin config proxy_bypass: false) to route through the environment proxy.
"""

import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

PROXY_BYPASS_ENV = "OPENVIKING_PROXY_BYPASS"
NO_PROXY_EXTRA_ENV = "OPENVIKING_NO_PROXY_EXTRA"
_PROXY_ENV_NAMES = ("http_proxy", "https_proxy", "all_proxy")


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _host_of(url):
    return urllib.parse.urlsplit(str(url or "")).hostname or ""


def _bare_host(host):
    host = str(host or "").lower()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.split(":", 1)[0]


def _host_matches(host, entry):
    entry = str(entry or "").strip().lower()
    if not entry:
        return False
    if entry.startswith("."):
        return host.endswith(entry)
    return host == entry


def resolve_proxy_bypass(config=None, env=None):
    """Decide whether OpenViking hosts skip the environment proxy.

    Priority: config["proxy_bypass"] > OPENVIKING_PROXY_BYPASS > default True.
    Extra bypassed hosts come from config["no_proxy_extra"] (list) or
    OPENVIKING_NO_PROXY_EXTRA (comma-separated). A leading "." matches
    subdomains, mirroring no_proxy conventions.
    """
    config = config or {}
    env = os.environ if env is None else env
    raw = config.get("proxy_bypass")
    if raw is None or str(raw).strip() == "":
        raw = env.get(PROXY_BYPASS_ENV)
    enabled = True if raw is None or str(raw).strip() == "" else _truthy(raw)
    extra = config.get("no_proxy_extra")
    if extra is None or extra == "":
        extra = env.get(NO_PROXY_EXTRA_ENV, "")
    if isinstance(extra, str):
        extra = [e.strip() for e in extra.split(",") if e.strip()]
    hosts = []
    for key in ("base_url", "mcp_url"):
        host = _host_of(config.get(key))
        if host and host not in hosts:
            hosts.append(host)
    return {"enabled": enabled, "hosts": hosts, "extra": [str(e) for e in extra]}


class _SelectiveProxyHandler(urllib.request.ProxyHandler):
    """Env proxies for everything except the listed bypass hosts."""

    def __init__(self, bypass_hosts, proxies=None):
        super().__init__(proxies)
        self._bypass_hosts = [str(h) for h in (bypass_hosts or []) if str(h or "").strip()]

    def proxy_open(self, req, proxy, type):
        host = _bare_host(req.host)
        if any(_host_matches(host, entry) for entry in self._bypass_hosts):
            # Decline without set_proxy: the opener falls through to the
            # direct HTTP(S) handler for this request.
            return None
        return super().proxy_open(req, proxy, type)


def build_opener(config, extra_handlers=(), env=None):
    """Opener that bypasses env proxies for the configured hosts by default."""
    decision = resolve_proxy_bypass(config, env)
    handlers = list(extra_handlers)
    if decision["enabled"]:
        bypass = decision["hosts"] + decision["extra"]
        handlers.append(_SelectiveProxyHandler(bypass))
        logger.info("openviking proxy: bypassing environment proxy for %s", ", ".join(bypass))
    return urllib.request.build_opener(*handlers)


def _redact_userinfo(url):
    text = str(url)
    if "@" not in text:
        return text
    scheme, sep, rest = text.partition("://")
    rest = rest.rsplit("@", 1)[1]
    return f"{scheme}{sep}{rest}" if sep else rest


def describe_proxy_env(env=None):
    """Active proxy env vars as 'name=value' pairs (userinfo redacted)."""
    env = os.environ if env is None else env
    parts = []
    for name in _PROXY_ENV_NAMES:
        value = env.get(name) or env.get(name.upper())
        if value:
            parts.append(f"{name}={_redact_userinfo(value)}")
    return ", ".join(parts)


def proxy_hint(config, env=None):
    """Guidance for connection errors when the request goes through an env proxy."""
    env = os.environ if env is None else env
    summary = describe_proxy_env(env)
    if not summary:
        return ""
    if resolve_proxy_bypass(config, env)["enabled"]:
        # Already direct for the configured hosts; the proxy is not the cause.
        return ""
    return (
        f" Proxy env vars are set ({summary}) and this request goes through them; "
        f"if the OpenViking server is on a tailnet/LAN, add its host to no_proxy "
        f"or set {PROXY_BYPASS_ENV}=1."
    )
