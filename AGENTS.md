# Repository guidance

## Project

This repository contains a FastMCP server for Yandex Tracker. It exposes
read and write tools, optional Redis caching, OAuth support, queue access
limits, controlled write policies, write auditing, and an idempotent workflow
for creating development tasks from stable source identifiers.

## Safety and scope

- Preserve unrelated user changes. Do not rewrite history or discard work.
- Never commit tokens, service-account keys, `.env` files, audit logs, or task
  content captured from a live Tracker organization.
- Do not create commits, tags, pushes, releases, or external Tracker mutations
  unless the user explicitly requests them.
- Treat `TRACKER_READ_ONLY=true` as the strongest restriction.
- Under `TRACKER_WRITE_POLICY=controlled`, require `confirmed=true` for ordinary
  mutations and keep destructive actions disabled unless
  `TRACKER_ALLOW_DESTRUCTIVE=true` was deliberately configured.
- Keep audit events metadata-only. Do not add headers, query strings, request
  bodies, tokens, or issue text to audit output.

## Commands

```bash
uv sync --dev                  # Install development dependencies
uv run yandex-tracker-mcp      # Run the server
task check                     # Ruff, formatting, mypy, and ty checks
task test                      # Test suite
task format                    # Mutates files: format and fix imports
task lock                      # Mutates uv.lock and syncs dependencies
```

The default `task` command runs `task lock`, `task format`, `task check`, and
`task test`. Do not use it as a read-only validation command. Run dependency
or lock-file updates only when the task requires them.

## Architecture

- `mcp_tracker/tracker/proto/`: Tracker API protocols and shared types.
- `mcp_tracker/tracker/custom/client.py`: HTTP client implementing the
  protocols, including retry and write-audit behavior.
- `mcp_tracker/tracker/caching/client.py`: Redis-backed protocol wrappers.
- `mcp_tracker/mcp/server.py`: FastMCP server construction and lifespan.
- `mcp_tracker/mcp/tools/`: MCP tool definitions and registration.
  - `_access.py`: queue/issue access checks and write-policy enforcement.
  - `field.py`, `queue.py`, `user.py`: reference, queue, and user tools.
  - `issue_read.py`, `issue_write.py`, `issue_extras.py`, `issue_parts.py`:
    issue lifecycle and related resources.
  - `crud.py`, `board.py`, `automation.py`, `bulkchange.py`, `project.py`:
    consolidated Tracker object and workflow tools.
  - `task_management.py`: idempotent source-tagged task creation and
    reconciliation.
  - `__init__.py`: `register_all_tools()` orchestration.
- `mcp_tracker/settings.py`: environment-backed Pydantic settings.
- `tests/`: mirrors the client, caching, OAuth, server, and tool layers.

All protocol methods accept an optional `auth: YandexAuth | None`. Tracker
entity models inherit from `BaseTrackerEntity`.

## Implementing tools

1. Add or update the relevant protocol in `mcp_tracker/tracker/proto/`.
2. Implement the Tracker API call in `mcp_tracker/tracker/custom/client.py`.
3. Add or update the caching wrapper when the protocol is cached.
4. Prefer a new `action` on an existing consolidated tool when the operation
   belongs to that family. Add a standalone tool only for a distinct concept.
5. Apply queue/issue access checks and `require_write_mode()` before writes.
6. Invalidate affected caches after mutations.
7. Register the tool in `mcp_tracker/mcp/tools/__init__.py` when necessary.
8. Add focused tests and update both README variants when the public surface
   or configuration changes.

## Testing conventions

- Use pytest with asyncio mode `auto`.
- Use `aioresponses` for `TrackerClient` HTTP tests.
- Use `AsyncMock(spec=...)` for protocol mocks in MCP tool tests.
- Put imports at module scope and type-hint parameters, including fixtures.
- Prefer `pytest.mark.parametrize` over loops for data-driven cases.
- Use `model_construct()` for Pydantic fixtures when validation is irrelevant.
- Exercise MCP tools through `ClientSession.call_tool()` against a real test
  FastMCP server with mocked protocols.
- Test required parameters, read-only behavior, controlled confirmation,
  destructive-action denial, queue restrictions, cache invalidation, and
  server registration as applicable.

## Documentation and releases

- Keep `README.md` and `README_ru.md` synchronized.
- Keep `docs/TASK_MANAGEMENT.md` aligned with controlled workflow behavior.
- Document environment-variable changes in both README files.
- Add current changes under `Unreleased` in `CHANGELOG.md`; never rewrite old
  release entries merely to update terminology.
- Keep versions in `pyproject.toml` and `server.json` aligned during a release,
  including the OCI image tag in `server.json`.
