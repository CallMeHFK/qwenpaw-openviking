# Optional OpenViking tools

Tools listed here are not part of the set registered by the QwenPaw plugin
(`openviking_find`, `openviking_search`, `openviking_read`,
`openviking_remember`, `openviking_write`, `openviking_add_skill`,
`openviking_health`). 除 `write`（已注册为 `openviking_write`）外，本节列出的工具
当前 QwenPaw 插件均未注册，若需要请先确认工具存在（例如客户端扩展了注册列表），
并只对确实出现在当前会话已注册工具列表中的工具阅读对应小节 — SKILL.md 的核心流程
不依赖它们中的任何一个。

Upstream availability summary (server side):

| Tool | Server requirement | Managed cloud service | QwenPaw 插件 |
|---|---|---|---|
| `tree` | ≥ 0.4.14 | after the cloud rolls to 0.4.14 | 未注册 |
| `write` (`openviking_write`) | ≥ 0.4.14 | after the cloud rolls to 0.4.14 | 已注册 |
| `edit` | ≥ 0.4.14 | after the cloud rolls to 0.4.14 | 未注册 |
| `list_watches`, `cancel_watch` | ≥ 0.3.18, self-hosted / private | not exposed | 未注册 |

The managed cloud runs stateless multi-instance serving, so account-level
stateful tools (`list_watches`, `cancel_watch`) are trimmed there even when
the underlying version has them.

## `tree(uri, level_limit?)`

Directory tree of a `viking://` scope, deeper than one `list` level. Use it to
orient inside an unfamiliar scope before deciding what to read; prefer `list`
for a single known directory — it is cheaper. 当前 QwenPaw 插件未注册
`tree`/`list`，若需要请先确认工具存在；否则用 `openviking_find`/`openviking_search`
按语义定位。

## `openviking_write(uri, content, mode?)` and `edit(uri, ...)`

Exact-document persistence at a known URI, complementing
`openviking_remember` (which lets the server file extracted memories on its
own):

- `openviking_write` replaces, appends to, or creates a file. Creating
  requires the parent directory to exist.
- `edit` performs targeted string replacement inside an existing file. Prefer
  `edit` over rewriting whole files, and re-read the file first if your copy
  of its content might be stale. 当前 QwenPaw 插件未注册 `edit`，若需要请先确认
  工具存在；否则先 `openviking_read` 再用 `openviking_write` 写回完整内容。

Use them for curated notes under `viking://~/` (your own user root) and shared
reference material under `viking://resources/`. When neither is registered,
fall back to `openviking_remember` as SKILL.md describes.

## `list_watches()` and `cancel_watch(to_uri)`

Manage auto-refresh subscriptions created by `add_resource` with a watch
interval (private / self-hosted deployments only). `list_watches` shows the
account's active subscriptions; `cancel_watch` stops one by its target URI.
Only touch watches the user asked about — cancelling someone's subscription is
destructive. 当前 QwenPaw 插件未注册这两个工具（`add_resource` 也未注册），若需要
请先确认工具存在。
