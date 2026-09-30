# qwenpaw-openviking

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

A QwenPaw plugin that connects QwenPaw agents to [OpenViking](https://github.com/volcengine/OpenViking) — Volcengine's open-source long-term semantic memory engine for agents.

## Features

- **Seven native QwenPaw tools** for OpenViking memory operations: `openviking_find`, `openviking_search`, `openviking_read`, `openviking_remember`, `openviking_write`, `openviking_add_skill`, `openviking_health`.
- **Five bundled skills** (adapted from the upstream `agent-plugins` package): `openviking-memory`, `ov-experience-memory`, `ov-memory-troubleshoot`, `openviking-skills`, `ov-kanban`.
- **Pure Python standard library** — zero third-party dependencies. Credential resolution and the MCP streamable-HTTP client are implemented from scratch (Python 3.12+).
- **Credential resolution chain identical to the upstream `ov` CLI / agent-plugins** — environment variables, `~/.openviking/ovcli.conf`, `~/.openviking/ov.conf`, local defaults.
- **Hot-installable**: QwenPaw runs the plugin's startup hook on install; no host restart needed.

## Relationship to upstream `agent-plugins`

This project mirrors the official [`agent-plugins`](https://github.com/volcengine/OpenViking/blob/main/agent-plugins/README.md) package in the OpenViking repository, targeting a different host:

| Aspect | Upstream `agent-plugins` (Agent Plugins 1.0) | This project (qwenpaw-openviking) |
| --- | --- | --- |
| Target host | Any Agent-Plugins-1.0-conforming client (Cursor, VS Code, ...) | QwenPaw (Python host) |
| Transport | stdio MCP proxy written in Node.js (`servers/mcp-proxy.mjs`) | Pure-Python stdlib MCP streamable-HTTP client (`openviking_client/`) |
| Tool surface | MCP tools exposed through the `openviking` server entry | Registered as native QwenPaw tools, prefixed `openviking_` |
| Manifest | `plugin.json` per the Agent Plugins 1.0 spec | QwenPaw `plugin.json` (`id: openviking-memory`, `entry.backend: plugin.py`) |
| Credential chain | env vars → `ovcli.conf` → `ov.conf` → local defaults | Same chain, reimplemented in Python |
| Skills | `openviking-memory`, `ov-memory-troubleshoot`, `ov-experience-memory`, `openviking-skills`, `ov-kanban` | Same five skills, adapted for QwenPaw |
| Runtime deps | Node.js 18+ | Python 3.12+, no third-party packages |

## Repository layout

```
plugin.json                  # QwenPaw plugin manifest (id/name: openviking-memory, v0.1.0)
plugin.py                    # Plugin entry: startup hook, tool registration
openviking_client/           # Credential resolution chain + MCP streamable-HTTP client (stdlib only)
skills/
  openviking-memory/         # Teaches the model the recall + persist loop
  ov-experience-memory/      # Retrieve and apply prior task Experience
  ov-memory-troubleshoot/    # Read-only extraction troubleshooting
  openviking-skills/         # Find, use, create, and share OpenViking skills
  ov-kanban/                 # Kanban board over OpenViking markdown files
tests/                       # unittest-based test suite
```

## Installation

1. Make sure an OpenViking server is reachable (default local endpoint: `http://127.0.0.1:1933`). See the upstream [quickstart](https://github.com/volcengine/OpenViking/tree/main/docs) for how to run one.
2. Copy this repository (or a packaged zip of it) into QwenPaw's plugin directory, e.g.:

   ```
   ~/.qwenpaw/plugins/openviking-memory/
   ```

   Alternatively, install it through QwenPaw's plugin install interface. QwenPaw hot-installs the plugin and runs its startup hook immediately — no restart required.
3. Configure credentials (below) if the defaults don't match your deployment, then start a QwenPaw session. The `openviking_*` tools and the five skills become available to the agent.

## Configuration

### Credential resolution chain

Highest to lowest priority (same chain as the upstream `ov` CLI and `agent-plugins`):

| Priority | Source | Values read |
| --- | --- | --- |
| 1 | Environment variables | `OPENVIKING_URL` (or `OPENVIKING_BASE_URL`), `OPENVIKING_API_KEY` (or `OPENVIKING_BEARER_TOKEN`), `OPENVIKING_ACCOUNT`, `OPENVIKING_USER`, `OPENVIKING_PEER_ID` |
| 2 | `~/.openviking/ovcli.conf` | `url`, `api_key`, `account`, `user`, and plugin keys |
| 3 | `~/.openviking/ov.conf` | plugin section, then `server` section (`url` or `host`/`port`, `root_api_key`) |
| 4 | Defaults | `http://127.0.0.1:1933`, no auth (local mode) |

Additional environment variables:

| Variable | Effect |
| --- | --- |
| `OPENVIKING_CREDENTIAL_SOURCE` | Pin the credential source (skip higher-priority layers) |
| `OPENVIKING_TIMEOUT_MS` | Request timeout in milliseconds |
| `OPENVIKING_DEBUG` | Enable debug logging |

## Tools and skills

**Tools** (registered with QwenPaw at plugin startup):

| Tool | Purpose |
| --- | --- |
| `openviking_find` | Find memories / files by query (supports `context_type` filters) |
| `openviking_search` | Search OpenViking, including server-assembled context mode |
| `openviking_read` | Read a memory / file by its `viking://` URI |
| `openviking_remember` | Persist a durable fact into long-term memory |
| `openviking_write` | Write a file into OpenViking |
| `openviking_add_skill` | Create or replace a skill stored in OpenViking |
| `openviking_health` | Check connectivity / credentials against the server |

**Skills** (under `skills/`, adapted from upstream): `openviking-memory`, `ov-experience-memory`, `ov-memory-troubleshoot`, `openviking-skills`, `ov-kanban`.

## Development

Requirements: Python 3.12+. No third-party packages — the plugin, client, and tests use only the standard library.

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

CI (GitHub Actions, `.github/workflows/ci.yml`) runs the same tests plus a compile check over all `.py` files on every push and pull request.

Status: this is a 0.1.0 release. Behavior against the full matrix of OpenViking server deployments has not been exhaustively verified; please report issues.

## License and acknowledgements

[AGPL-3.0](LICENSE). The skills under `skills/` and the credential/transport logic are adapted from [volcengine/OpenViking](https://github.com/volcengine/OpenViking) (AGPL-3.0); this project keeps the same license. Thanks to the OpenViking authors at Volcengine.

Author: [CallMeHFK](https://github.com/CallMeHFK)

---

## 简体中文

### 功能

QwenPaw 插件，接入火山引擎开源的 agent 长期语义记忆引擎 [OpenViking](https://github.com/volcengine/OpenViking)。注册 7 个 QwenPaw 原生工具（`openviking_find` / `openviking_search` / `openviking_read` / `openviking_remember` / `openviking_write` / `openviking_add_skill` / `openviking_health`），并自带 5 个技能（`openviking-memory`、`ov-experience-memory`、`ov-memory-troubleshoot`、`openviking-skills`、`ov-kanban`，适配自上游 agent-plugins）。纯 Python 标准库实现（3.12+），零第三方依赖；凭证解析链与上游 `ov` CLI 一致。

### 安装

1. 确保有一个可达的 OpenViking server（默认本地地址 `http://127.0.0.1:1933`）。
2. 将本仓库（或打包 zip）放入 QwenPaw 的插件目录，例如 `~/.qwenpaw/plugins/openviking-memory/`；或通过 QwenPaw 的插件安装接口安装。QwenPaw 热装后会立即运行 startup hook，无需重启。
3. 按需配置凭证（见下），新开会话即可使用。

### 配置

凭证解析链（优先级从高到低，与上游一致）：

1. 环境变量：`OPENVIKING_URL`（或 `OPENVIKING_BASE_URL`）、`OPENVIKING_API_KEY`（或 `OPENVIKING_BEARER_TOKEN`）、`OPENVIKING_ACCOUNT`、`OPENVIKING_USER`、`OPENVIKING_PEER_ID`
2. `~/.openviking/ovcli.conf`
3. `~/.openviking/ov.conf`
4. 默认值：`http://127.0.0.1:1933`，无鉴权（本地模式）

其他环境变量：`OPENVIKING_CREDENTIAL_SOURCE`（固定凭证来源）、`OPENVIKING_TIMEOUT_MS`（超时毫秒数）、`OPENVIKING_DEBUG`（调试日志）。
