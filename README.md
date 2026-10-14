# qwenpaw-openviking

English | [简体中文](README.zh-CN.md)

[![CI](https://github.com/CallMeHFK/qwenpaw-openviking/actions/workflows/ci.yml/badge.svg)](https://github.com/CallMeHFK/qwenpaw-openviking/actions)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

A QwenPaw plugin that connects QwenPaw agents to [OpenViking](https://github.com/volcengine/OpenViking) — Volcengine's open-source long-term semantic memory engine for agents.

It ports the upstream [`agent-plugins`](https://github.com/volcengine/OpenViking/blob/main/agent-plugins/README.md) integration (Agent Plugins 1.0, Node.js stdio MCP proxy) to QwenPaw's native plugin API in pure Python: no Node runtime, no third-party packages.

## How it works

On install, the plugin resolves the OpenViking connection (same credential chain as the upstream `ov` CLI), then registers:

- **Seven native QwenPaw tools** (`openviking_find`, `openviking_search`, `openviking_read`, `openviking_remember`, `openviking_write`, `openviking_add_skill`, `openviking_health`) — thin wrappers over the server's MCP endpoint, speaking streamable HTTP with session re-initialization on expiry.
- **Five skills** (`openviking-memory`, `ov-experience-memory`, `ov-memory-troubleshoot`, `openviking-skills`, `ov-kanban`) that teach the agent the recall → work → persist loop.
- A **startup hook** that probes `/api/v1/system/status` once and a **shutdown hook** that closes the MCP session. Both are fail-open: a dead server degrades to warnings, never a broken host.

Tool wrappers never raise into the QwenPaw runtime — every failure (auth, timeout, unreachable server) comes back as a structured error string the model can act on.

## Install

Requires Python ≥ 3.12 (the QwenPaw host) and a reachable OpenViking server (default `http://127.0.0.1:1933`; see the upstream [docs](https://github.com/volcengine/OpenViking/tree/main/docs) for running one).

From the latest release zip, hot-installed without restarting QwenPaw:

```bash
curl -X POST http://127.0.0.1:19999/api/plugins/install \
  -H 'Content-Type: application/json' \
  -d '{"source": "https://github.com/CallMeHFK/qwenpaw-openviking/releases/latest/download/openviking-memory-0.2.0.zip"}'
```

Or copy the repository into QwenPaw's plugin directory (`~/.qwenpaw/plugins/openviking-memory/`) and install from that path. Either way the plugin loads immediately and runs its startup hook.

The seven tools are registered **disabled by default** — enable the ones you want in QwenPaw's tool settings after install. While the app is running you can also upload the release zip directly (multipart `POST /api/plugins/upload`); with the app stopped, the offline CLI accepts a directory or a zip URL only.

## Configuration

Credential resolution chain, highest to lowest priority (identical to upstream):

| Priority | Source | Values read |
| --- | --- | --- |
| 1 | Environment variables | `OPENVIKING_URL` (or `OPENVIKING_BASE_URL`), `OPENVIKING_API_KEY` (or `OPENVIKING_BEARER_TOKEN`), `OPENVIKING_ACCOUNT`, `OPENVIKING_USER`, `OPENVIKING_PEER_ID` |
| 2 | `~/.openviking/ovcli.conf` | `url`, `api_key`, `account`, `user`, plus `plugin.qwenpaw` overrides |
| 3 | `~/.openviking/ov.conf` | `qwenpaw` section, then `server` section (`url` or `host`/`port`, `root_api_key`) |
| 4 | Defaults | `http://127.0.0.1:1933`, no auth (local mode) |

Additional environment variables:

| Variable | Effect |
| --- | --- |
| `OPENVIKING_CREDENTIAL_SOURCE` | Pin the credential source to `env` or `cli` (default: `auto`) |
| `OPENVIKING_TIMEOUT_MS` | Request timeout in milliseconds (default 15000, minimum 1000) |
| `OPENVIKING_DEBUG` | Enable debug logging to `~/.openviking/logs/qwenpaw.log` |
| `OPENVIKING_PROXY_BYPASS` | Bypass `http_proxy`/`https_proxy` for the configured server host (default `1`; set `0` to route through the environment proxy) |
| `OPENVIKING_NO_PROXY_EXTRA` | Comma-separated extra hosts to bypass (a leading `.` matches subdomains) |

## Proxy environments

The plugin speaks HTTP via Python's `urllib`, which honors `http_proxy`/`https_proxy`/`no_proxy`. On hosts with a local proxy (e.g. `http://127.0.0.1:7890`) whose `no_proxy` list misses the OpenViking server — common when the server is reached over a tailnet (`100.64.0.0/10`) or LAN — every request dies inside the proxy tunnel with a misleading `SSL: UNEXPECTED_EOF_WHILE_READING`.

By default the plugin bypasses the environment proxy for the configured `base_url`/`mcp_url` host, so tailnet/LAN servers keep working with zero setup. Knobs for when you need them:

- Plugin setting `proxy_bypass: false` or `OPENVIKING_PROXY_BYPASS=0`: route through the environment proxy (e.g. a corporate egress proxy required to reach the server).
- Plugin setting `no_proxy_extra: ["host", ...]` or `OPENVIKING_NO_PROXY_EXTRA="host1,.domain2"`: bypass additional hosts.

Two diagnostics make proxy failures recognizable: connection errors carry a hint naming the active proxy variables, and the startup health check counter-probes with the policy flipped, logging which path (direct vs proxied) actually works.

The manual alternative is extending `no_proxy` yourself, e.g. `no_proxy=localhost,127.0.0.1,100.64.0.0/10,your-ov-host`.

## Tools

| Tool | Signature | Purpose |
| --- | --- | --- |
| `openviking_find` | `(query, target_uri="", limit=10)` | Ranked semantic recall; scope with `target_uri` (e.g. `viking://~/memories/experiences`) |
| `openviking_search` | `(query, target_uri="", limit=10, session_id="")` | Deeper intent-aware search when `find` is too shallow |
| `openviking_read` | `(uri)` | Read the exact text at one `viking://` URI |
| `openviking_remember` | `(content)` | Persist a durable fact, preference, decision, or lesson |
| `openviking_write` | `(uri, content)` | Write exact content to a known `viking://` URI |
| `openviking_add_skill` | `(content="", path="", target_uri="")` | Install a skill from SKILL.md text, a local folder/zip, or a Git URL |
| `openviking_health` | `()` | Check connectivity and credentials against the server |

Argument names mirror the upstream MCP tools; the server-side schema is authoritative, so an unknown parameter surfaces as a server validation error rather than a silent client-side drop.

## Repository layout

```
plugin.json                  # QwenPaw plugin manifest (id/name: openviking-memory)
plugin.py                    # Entry: credential resolution, tool registration, hooks
openviking_client/
  credentials.py             # env → ovcli.conf → ov.conf resolution chain
  proxy.py                   # env-proxy bypass policy + failure diagnostics
  mcp_client.py              # MCP streamable-HTTP client (stdlib urllib, thread-safe)
  tools.py                   # The seven openviking_* tool wrappers
skills/                      # Five skills adapted from upstream agent-plugins
tests/                       # unittest suite (offline, no network, no keys)
```

## Development

Zero third-party dependencies — runtime, client, and tests are all standard library.

```bash
python3 -m unittest discover -s tests -v   # test suite
ruff check .                               # lint gate (config in pyproject.toml)
```

CI (`.github/workflows/ci.yml`) runs a compile check, the test suite, and ruff on every push and pull request.

Status: 0.1.0. Loading, credential resolution, and the MCP transport are covered by offline tests and a real QwenPaw `PluginLoader` load check; end-to-end behavior against a live OpenViking server is exercised manually. Please report issues.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup, porting conventions (match upstream semantics, call out divergences), the offline-test rule, and the strict no-real-secrets rule. Interactions are governed by the [Code of Conduct](CODE_OF_CONDUCT.md).

## License and acknowledgements

[AGPL-3.0](LICENSE). The skills under `skills/` and the credential/transport logic are adapted from [volcengine/OpenViking](https://github.com/volcengine/OpenViking) (AGPL-3.0); this project keeps the same license. Thanks to the OpenViking authors at Volcengine.

Author: [CallMeHFK](https://github.com/CallMeHFK)
