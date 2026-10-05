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
  -d '{"source": "https://github.com/CallMeHFK/qwenpaw-openviking/releases/latest/download/openviking-memory-0.1.0.zip"}'
```

Or copy the repository into QwenPaw's plugin directory (`~/.qwenpaw/plugins/openviking-memory/`) and install from that path. Either way the plugin loads immediately and runs its startup hook.

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
