# qwenpaw-openviking

[English](README.md) | 简体中文

[![CI](https://github.com/CallMeHFK/qwenpaw-openviking/actions/workflows/ci.yml/badge.svg)](https://github.com/CallMeHFK/qwenpaw-openviking/actions)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

QwenPaw 插件，把 QwenPaw agent 接入火山引擎开源的 agent 长期语义记忆引擎 [OpenViking](https://github.com/volcengine/OpenViking)。

本项目把上游 [`agent-plugins`](https://github.com/volcengine/OpenViking/blob/main/agent-plugins/README.md) 集成包（Agent Plugins 1.0 格式，Node.js stdio MCP proxy）移植为 QwenPaw 原生插件：纯 Python 标准库实现，不需要 Node 运行时，零第三方依赖。

## 工作原理

安装时，插件解析 OpenViking 连接（凭证链与上游 `ov` CLI 完全一致），然后注册：

- **7 个 QwenPaw 原生工具**（`openviking_find`、`openviking_search`、`openviking_read`、`openviking_remember`、`openviking_write`、`openviking_add_skill`、`openviking_health`）——对服务端 MCP 端点的薄封装，走 streamable HTTP，会话过期自动重新初始化。
- **5 个技能**（`openviking-memory`、`ov-experience-memory`、`ov-memory-troubleshoot`、`openviking-skills`、`ov-kanban`），教 agent 形成"召回→工作→沉淀"循环。
- 一个 **startup hook**（探测一次 `/api/v1/system/status`）和一个 **shutdown hook**（关闭 MCP 会话）。两者都是 fail-open：服务器不可用只会降级为警告，绝不会拖垮宿主。

工具封装绝不向 QwenPaw 运行时抛异常——所有失败（鉴权、超时、服务器不可达）都以结构化错误字符串返回给模型，由模型自行处置。

## 安装

要求 Python ≥ 3.12（QwenPaw 宿主）和一个可达的 OpenViking server（默认 `http://127.0.0.1:1933`，起服务见上游 [docs](https://github.com/volcengine/OpenViking/tree/main/docs)）。

用最新 release 的 zip 热装（无需重启 QwenPaw）：

```bash
curl -X POST http://127.0.0.1:19999/api/plugins/install \
  -H 'Content-Type: application/json' \
  -d '{"source": "https://github.com/CallMeHFK/qwenpaw-openviking/releases/latest/download/openviking-memory-0.1.0.zip"}'
```

也可以把本仓库拷贝到 QwenPaw 插件目录（`~/.qwenpaw/plugins/openviking-memory/`）后从该路径安装。两种方式都会立即加载插件并运行 startup hook。

## 配置

凭证解析链（优先级从高到低，与上游一致）：

| 优先级 | 来源 | 读取的值 |
| --- | --- | --- |
| 1 | 环境变量 | `OPENVIKING_URL`（或 `OPENVIKING_BASE_URL`）、`OPENVIKING_API_KEY`（或 `OPENVIKING_BEARER_TOKEN`）、`OPENVIKING_ACCOUNT`、`OPENVIKING_USER`、`OPENVIKING_PEER_ID` |
| 2 | `~/.openviking/ovcli.conf` | `url`、`api_key`、`account`、`user`，以及 `plugin.qwenpaw` 覆盖节 |
| 3 | `~/.openviking/ov.conf` | `qwenpaw` 节，然后 `server` 节（`url` 或 `host`/`port`、`root_api_key`） |
| 4 | 默认值 | `http://127.0.0.1:1933`，无鉴权（本地模式） |

其他环境变量：

| 变量 | 作用 |
| --- | --- |
| `OPENVIKING_CREDENTIAL_SOURCE` | 把凭证来源固定为 `env` 或 `cli`（默认 `auto`） |
| `OPENVIKING_TIMEOUT_MS` | 请求超时毫秒数（默认 15000，最小 1000） |
| `OPENVIKING_DEBUG` | 开启调试日志，写入 `~/.openviking/logs/qwenpaw.log` |
| `OPENVIKING_PROXY_BYPASS` | 对已配置的服务器主机绕过 `http_proxy`/`https_proxy`（默认 `1`；设为 `0` 改走环境代理） |
| `OPENVIKING_NO_PROXY_EXTRA` | 追加绕过的主机，逗号分隔（前导 `.` 匹配子域名） |

## 代理环境

插件通过 Python `urllib` 发起 HTTP 请求，会读取 `http_proxy`/`https_proxy`/`no_proxy` 环境变量。当本机挂着本地代理（如 `http://127.0.0.1:7890`）而 `no_proxy` 没有覆盖 OpenViking 服务器地址时——服务器走 tailnet 网段（`100.64.0.0/10`）或内网时很常见——所有请求都会死在代理隧道里，报极具误导性的 `SSL: UNEXPECTED_EOF_WHILE_READING`。

插件默认对配置中的 `base_url`/`mcp_url` 主机绕过环境代理，尾网/内网服务器开箱即用。需要时的开关：

- 插件设置 `proxy_bypass: false` 或 `OPENVIKING_PROXY_BYPASS=0`：改走环境代理（例如必须经公司出口代理才能访问服务器）。
- 插件设置 `no_proxy_extra: ["host", ...]` 或 `OPENVIKING_NO_PROXY_EXTRA="host1,.domain2"`：追加绕过更多主机。

两处诊断让代理类故障一眼可辨：连接报错附带代理提示（列出当前生效的代理变量）；启动健康检查在主探测失败时会用翻转后的策略补测一次，日志直接写明哪条路径（直连/代理）是通的。

也可以不改插件，手动扩展 `no_proxy`，例如 `no_proxy=localhost,127.0.0.1,100.64.0.0/10,your-ov-host`。

## 工具

| 工具 | 签名 | 用途 |
| --- | --- | --- |
| `openviking_find` | `(query, target_uri="", limit=10)` | 排序语义召回；用 `target_uri` 限定范围（如 `viking://~/memories/experiences`） |
| `openviking_search` | `(query, target_uri="", limit=10, session_id="")` | 更深的意图感知搜索，`find` 不够时用 |
| `openviking_read` | `(uri)` | 读取一个 `viking://` URI 的精确文本 |
| `openviking_remember` | `(content)` | 沉淀持久事实、偏好、决定或教训 |
| `openviking_write` | `(uri, content)` | 向已知 `viking://` URI 写入精确内容 |
| `openviking_add_skill` | `(content="", path="", target_uri="")` | 从 SKILL.md 文本、本地目录/zip 或 Git URL 安装技能 |
| `openviking_health` | `()` | 检查到服务器的连通性与凭证 |

参数名与上游 MCP 工具对齐；参数 schema 以服务端为准——未知参数会表现为服务端校验错误，而不是被客户端静默丢弃。

## 仓库结构

```
plugin.json                  # QwenPaw 插件 manifest（id/name: openviking-memory）
plugin.py                    # 入口：凭证解析、工具注册、hooks
openviking_client/
  credentials.py             # env → ovcli.conf → ov.conf 凭证解析链
  proxy.py                   # 环境代理绕过策略与故障诊断
  mcp_client.py              # MCP streamable-HTTP 客户端（stdlib urllib，线程安全）
  tools.py                   # 7 个 openviking_* 工具封装
skills/                      # 适配自上游 agent-plugins 的 5 个技能
tests/                       # unittest 测试套件（离线，不联网，不需要密钥）
```

## 开发

零第三方依赖——运行时、客户端、测试全部只用标准库。

```bash
python3 -m unittest discover -s tests -v   # 测试套件
ruff check .                               # lint 门禁（配置在 pyproject.toml）
```

CI（`.github/workflows/ci.yml`）在每次 push 和 PR 上跑编译检查、测试套件和 ruff。

状态：0.1.0。加载路径、凭证解析、MCP 传输有离线测试与真实 QwenPaw `PluginLoader` 加载验证覆盖；对活体 OpenViking server 的端到端行为为手动验证。欢迎报 issue。

## 贡献

欢迎贡献——开发环境、移植约定（对齐上游语义、显式标注分歧）、离线测试规则与严格的禁真实密钥规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。项目交互遵循[行为准则](CODE_OF_CONDUCT.md)。

## 许可证与致谢

[AGPL-3.0](LICENSE)。`skills/` 下的技能与凭证/传输逻辑适配自 [volcengine/OpenViking](https://github.com/volcengine/OpenViking)（AGPL-3.0），本项目保持同一许可证。感谢火山引擎的 OpenViking 作者们。

作者：[CallMeHFK](https://github.com/CallMeHFK)
