"""Credential resolution chain for OpenViking harness plugins.

Port of agent-plugins/servers/shared/credentials.mjs: host input > env >
~/.openviking/ovcli.conf (with plugin.<harness> overrides) >
~/.openviking/ov.conf (harness section, then server defaults).
"""

import json
import os
from pathlib import Path

DEFAULT_OVCLI_CONF_PATH = str(Path.home() / ".openviking" / "ovcli.conf")
DEFAULT_OV_CONF_PATH = str(Path.home() / ".openviking" / "ov.conf")
DEFAULT_TIMEOUT_MS = 15000
MIN_TIMEOUT_MS = 1000

CREDENTIAL_ENV_VARS = [
    "OPENVIKING_URL",
    "OPENVIKING_BASE_URL",
    "OPENVIKING_MCP_URL",
    "OPENVIKING_BEARER_TOKEN",
    "OPENVIKING_API_KEY",
    "OPENVIKING_ACCOUNT",
    "OPENVIKING_USER",
    "OPENVIKING_PEER_ID",
]

CONNECTION_ENV_VARS = CREDENTIAL_ENV_VARS + [
    "OPENVIKING_AUTH_MODE",
    "OPENVIKING_CREDENTIAL_SOURCE",
    "OPENVIKING_CREDENTIALS_SOURCE",
    "OPENVIKING_CLI_CONFIG_FILE",
    "OPENVIKING_CONFIG_FILE",
]

AUTH_MODES = ("trusted", "api_key")


def _str(val, fallback=""):
    if isinstance(val, str) and val.strip():
        return val.strip()
    return fallback


def _normalize_path(value):
    raw = _str(value, "")
    if not raw:
        return ""
    if raw == "~":
        return str(Path.home())
    if raw.startswith("~/"):
        return str(Path.home() / raw[2:])
    return os.path.abspath(raw)


def _try_load_json(path):
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def build_user_agent(harness, version):
    return f"openviking-memory-{harness}/{_str(version, '') or '0.0.0'}"


def read_manifest_version(manifest_path):
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return _str(json.load(f).get("version"), "")
    except Exception:
        return ""


def _looks_like_ovcli(obj):
    if not isinstance(obj, dict):
        return False
    if isinstance(obj.get("server"), dict):
        return False
    return any(
        isinstance(obj.get(k), str)
        for k in ("url", "api_key", "account", "account_id", "user", "user_id", "actor_peer_id")
    )


def _has_credential_fields(obj):
    if not isinstance(obj, dict):
        return False
    return any(
        isinstance(obj.get(k), str)
        for k in ("url", "api_key", "account", "account_id", "user", "user_id", "actor_peer_id", "peer_id")
    )


def load_credential_files(env=None):
    env = os.environ if env is None else env
    cli_path_candidate = _normalize_path(env.get("OPENVIKING_CLI_CONFIG_FILE")) or DEFAULT_OVCLI_CONF_PATH
    ov_path_candidate = _normalize_path(env.get("OPENVIKING_CONFIG_FILE")) or DEFAULT_OV_CONF_PATH
    cli_path_env = bool(_str(env.get("OPENVIKING_CLI_CONFIG_FILE"), ""))
    ov_path_env = bool(_str(env.get("OPENVIKING_CONFIG_FILE"), ""))

    cli_file = _try_load_json(cli_path_candidate)
    cli_path = cli_path_candidate if cli_file else ""
    ov_file = _try_load_json(ov_path_candidate)
    ov_path = ov_path_candidate if ov_file else ""

    # Backward compat: older installs pointed OPENVIKING_CONFIG_FILE at an
    # ovcli-shaped file; treat it as ovcli.conf when no CLI path was given.
    if ov_path_env and not cli_path_env and _looks_like_ovcli(ov_file):
        cli_file, cli_path = ov_file, ov_path
        ov_file, ov_path = None, ""

    return {
        "cli_file": cli_file or {},
        "cli_path": cli_path,
        "cli_path_candidate": cli_path_candidate,
        "ov_file": ov_file or {},
        "ov_path": ov_path,
    }


def _is_section(value):
    return isinstance(value, dict)


def _section_key(harness):
    return str(harness or "").strip().lower().replace("-", "_")


def _harness_section(ov_file, harness):
    section = ov_file.get(_section_key(harness))
    return section if _is_section(section) else {}


def _plugin_section(cli_file, harness):
    plugin = cli_file.get("plugin")
    plugin = plugin if _is_section(plugin) else {}
    merged = {k: v for k, v in plugin.items() if not _is_section(v)}
    key = _section_key(harness)
    for candidate in (key, key.replace("_", "-")):
        section = plugin.get(candidate)
        if candidate and _is_section(section):
            merged.update(section)
    return merged


def _scalar(value):
    return "" if value is None else str(value).strip()


def _normalize_auth_mode(value):
    mode = _str(value, "").lower()
    return mode if mode in AUTH_MODES else ""


def _auth_mode_in(section):
    return _normalize_auth_mode(section.get("authMode")) or _normalize_auth_mode(section.get("auth_mode"))


def _source_mode(env):
    raw = _str(env.get("OPENVIKING_CREDENTIAL_SOURCE"),
               _str(env.get("OPENVIKING_CREDENTIALS_SOURCE"), "auto")).lower()
    if raw in ("env", "environment"):
        return "env"
    if raw in ("cli", "ovcli", "file", "config"):
        return "cli"
    return "auto"


def _has_env_credential_fields(env):
    return any(_str(env.get(name), "") for name in CREDENTIAL_ENV_VARS)


def _trim_slash(value):
    return value.rstrip("/")


def _first_layer(layers):
    for layer in layers:
        value, source = layer[0], layer[1]
        path = layer[2] if len(layer) > 2 else ""
        if value:
            return {"value": value, "source": source, "path": path}
    return {"value": "", "source": "none", "path": ""}


def _server_address(server):
    host = _str(server.get("host"), "127.0.0.1").replace("0.0.0.0", "127.0.0.1")
    try:
        port = int(float(server.get("port")))
    except (TypeError, ValueError):
        port = 1933
    return f"http://{host}:{port}"


def _env_flag(env, name):
    return _str(env.get(name), "").lower() in ("1", "true", "yes")


def _clamp_timeout(value):
    raw = _str(value, "")
    try:
        parsed = int(float(raw)) if raw else DEFAULT_TIMEOUT_MS
    except ValueError:
        parsed = DEFAULT_TIMEOUT_MS
    return max(MIN_TIMEOUT_MS, parsed)


def resolve_connection(harness, env=None, files=None, host_input=None, root_key_fallback=False):
    env = os.environ if env is None else env
    loaded = files or load_credential_files(env)
    cli_file, ov_file = loaded["cli_file"], loaded["ov_file"]
    cli_path, ov_path = loaded["cli_path"], loaded["ov_path"]
    host = host_input or {}
    name = _str(harness, "")
    mode = _source_mode(env)
    env_has_credentials = _has_env_credential_fields(env)
    pinned = mode == "cli" or (
        mode == "auto" and not env_has_credentials and bool(cli_path) and _has_credential_fields(cli_file)
    )
    unpinned = lambda layer: [] if pinned else [layer]  # noqa: E731
    from_files = mode != "env"
    filed = lambda *layers: layers if from_files else ()  # noqa: E731
    plugin = _plugin_section(cli_file, name)
    section = _harness_section(ov_file, name)
    server = ov_file.get("server") if _is_section(ov_file.get("server")) else {}

    key = _first_layer([
        (_str(host.get("apiKey"), ""), "host"),
        *unpinned((_str(env.get("OPENVIKING_BEARER_TOKEN"), _str(env.get("OPENVIKING_API_KEY"), "")), "env")),
        *filed(
            (_str(cli_file.get("api_key"), ""), "ovcli", cli_path),
            (_scalar(plugin.get("apiKey")), "ovcli", cli_path),
            (_scalar(section.get("apiKey")), "ov", ov_path),
        ),
        *(() if (pinned and not root_key_fallback) else filed(
            (_str(server.get("root_api_key"), ""), "ov", ov_path),
        )),
    ])

    def identity(host_value, env_name, cli_value, knob):
        return _first_layer([
            (_str(host_value, ""), "host"),
            *unpinned((_str(env.get(env_name), ""), "env")),
            *filed((cli_value, "ovcli", cli_path), (_scalar(plugin.get(knob)), "ovcli", cli_path)),
            *(() if pinned else filed((_str(section.get(knob), ""), "ov", ov_path))),
        ])["value"]

    account = identity(host.get("account"), "OPENVIKING_ACCOUNT",
                       _str(cli_file.get("account"), _str(cli_file.get("account_id"), "")), "accountId")
    user = identity(host.get("user"), "OPENVIKING_USER",
                    _str(cli_file.get("user"), _str(cli_file.get("user_id"), "")), "userId")

    peer_id = _first_layer([
        *unpinned((_str(env.get("OPENVIKING_PEER_ID"), ""), "env")),
        *filed((_str(cli_file.get("actor_peer_id"), _str(cli_file.get("peer_id"), "")), "ovcli")),
        *(() if pinned else filed((_str(section.get("peerId"), _str(section.get("peer_id"), "")), "ov"))),
    ])["value"]

    auth_mode = (
        _normalize_auth_mode(host.get("authMode"))
        or _normalize_auth_mode(env.get("OPENVIKING_AUTH_MODE"))
        or (from_files and (_auth_mode_in(plugin) or _auth_mode_in(section)
                            or _normalize_auth_mode(server.get("auth_mode"))))
        or ("trusted" if (account or user) else "api_key")
    )

    host_base_url = _trim_slash(_str(host.get("baseUrl"), ""))
    env_url = "" if pinned else _str(env.get("OPENVIKING_URL"), _str(env.get("OPENVIKING_BASE_URL"), ""))
    file_url = (_str(cli_file.get("url"), "") or _str(server.get("url"), "")) if from_files else ""
    base_url = host_base_url or _trim_slash(env_url or file_url) or _server_address(server if from_files else {})
    env_mcp_url = "" if pinned else _str(env.get("OPENVIKING_MCP_URL"), "")
    mcp_url = env_mcp_url if (not host_base_url and env_mcp_url) else f"{base_url}/mcp"

    return {
        "cli_file": cli_file,
        "cli_path": cli_path,
        "cli_path_candidate": loaded["cli_path_candidate"],
        "ov_file": ov_file,
        "ov_path": ov_path,
        "harness": name,
        "credential_source": "ovcli" if pinned else ("env" if (mode == "env" or env_has_credentials) else "auto"),
        "base_url": base_url,
        "mcp_url": mcp_url,
        "api_key": key["value"],
        "account": account,
        "user": user,
        "peer_id": peer_id,
        "auth_mode": auth_mode,
        "send_identity_headers": auth_mode == "trusted",
        "has_api_key": bool(key["value"]),
        "api_key_source": key["source"],
        "credential_path": key["path"],
    }


def build_proxy_connection(harness, env=None, manifest_path="", version=""):
    env = os.environ if env is None else env
    name = _str(harness)
    connection = resolve_connection(name, env=env, root_key_fallback=True)
    return {
        "harness": name,
        "user_agent": build_user_agent(
            name, _str(version) or (read_manifest_version(manifest_path) if manifest_path else "")
        ),
        "base_url": connection["base_url"],
        "mcp_url": connection["mcp_url"],
        "api_key": connection["api_key"],
        "account": connection["account"],
        "user": connection["user"],
        "peer_id": connection["peer_id"],
        "auth_mode": connection["auth_mode"],
        "send_identity_headers": connection["send_identity_headers"],
        "credential_source": connection["credential_source"],
        "api_key_source": connection["api_key_source"],
        "credential_path": connection["credential_path"],
        "has_api_key": connection["has_api_key"],
        "cli_path": connection["cli_path"],
        "ov_path": connection["ov_path"],
        "timeout_ms": _clamp_timeout(env.get("OPENVIKING_TIMEOUT_MS")),
        "debug": _env_flag(env, "OPENVIKING_DEBUG"),
        "debug_log_path": _str(env.get("OPENVIKING_DEBUG_LOG"))
        or str(Path.home() / ".openviking" / "logs" / f"{name}.log"),
    }
