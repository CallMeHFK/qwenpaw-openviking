# Contributing to qwenpaw-openviking

Thanks for your interest in qwenpaw-openviking! This document covers the dev
setup, the conventions this codebase follows, and the rules for submitting
contributions.

## Legal

By submitting a contribution you agree that it is licensed under the project's
[AGPL-3.0 License](LICENSE) — the same license as the upstream
[volcengine/OpenViking](https://github.com/volcengine/OpenViking) project this
plugin is adapted from.

## Development setup

Prerequisites: Python ≥ 3.12 and a QwenPaw installation for live testing. The
runtime and test code use **only the standard library** — there is nothing to
install.

```bash
git clone https://github.com/CallMeHFK/qwenpaw-openviking.git
cd qwenpaw-openviking
```

Run the same checks as CI:

```bash
python3 -m unittest discover -s tests -v
ruff check .
```

Live-test against a real QwenPaw host by hot-installing from the working tree:

```bash
curl -X POST http://127.0.0.1:19999/api/plugins/install \
  -H 'Content-Type: application/json' \
  -d "{\"source\": \"$PWD\"}"
```

QwenPaw loads the plugin immediately and runs its startup hook; no restart is
required. Point the plugin at an OpenViking server via the credential chain
(env vars, `~/.openviking/ovcli.conf`, or `~/.openviking/ov.conf` — see the
README for the full resolution order).

## Repository layout

- `plugin.json` — QwenPaw plugin manifest (`id: openviking-memory`)
- `plugin.py` — entry point: credential resolution, tool registration, startup
  health check, shutdown hook
- `openviking_client/`
  - `credentials.py` — the env → `ovcli.conf` → `ov.conf` resolution chain,
    ported from the upstream `agent-plugins/servers/shared/credentials.mjs`
  - `mcp_client.py` — synchronous MCP streamable-HTTP client (stdlib `urllib`),
    ported from `mcp-proxy-core.mjs`
  - `tools.py` — the seven `openviking_*` tool wrappers registered into QwenPaw
- `skills/` — the five skills adapted from upstream `agent-plugins/skills/`
- `tests/` — unittest suite (offline; no real network calls or API keys)
- `.github/workflows/ci.yml` — CI: compile check, unittest, `ruff check`

## Conventions

- **Standard library only.** Zero third-party runtime and test dependencies;
  do not add any. A dependency is a reason to open an issue first, not a PR.
- Target Python 3.12+.
- When porting behavior from upstream `agent-plugins`, match the upstream
  semantics (layering order, retry rules, error taxonomy) rather than inventing
  local variants — divergences must be called out in code and in the PR.
- Tool wrappers never raise into the QwenPaw runtime: every failure path
  returns a structured error string for the model.
- Comments only where the *why* is non-obvious.

## Tests

- Every bug fix must ship with a regression test (reproduce the failure first,
  then fix it).
- The suite must run offline: mock `urllib` or fake the HTTP layer, never a
  real endpoint or API key.
- CI must be green before requesting review.

## Commit & pull request guidelines

- Branch names: `fix/<topic>`, `feat/<topic>`, `docs/<topic>`.
- Commit messages: imperative mood, one-line summary, body for the why. Keep one
  logical change per commit.
- PRs: explain what and why, name the affected area, and describe how you
  tested. Use the provided template.
- Keep diffs small. For large refactors or new architecture, open an issue first
  and agree on the direction before writing code.

## Secrets (strict rule)

- **Never commit real API keys** — not in code, config samples, docs, tests, or
  commit messages.
- Use dummy values (e.g. `api_key="k"`) in tests.
- All runtime state lives outside the repository and must never be committed:
  `~/.openviking/`, `~/.qwenpaw/`, `.env`, etc. (see `.gitignore`).

## Code of conduct

All contributions and interactions must follow our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Where to ask

- Questions / bugs: GitHub Issues (`bug` label)
- Ideas / design: GitHub Issues (`enhancement` label) — or open a draft PR
