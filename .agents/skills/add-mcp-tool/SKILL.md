---
name: add-mcp-tool
description: Add or extend Yandex Tracker MCP tools with protocol, client, cache, access-policy, registration, test, and documentation changes. Use when implementing a new tool or action in this repository.
---

# Add an MCP tool

1. Read `AGENTS.md` and inspect the current implementation, tests, and public
   documentation before editing.
2. Prefer a new action in an existing consolidated tool family. Create a
   standalone tool only for a distinct concept.
3. Update the relevant protocol, HTTP client, cache wrapper, MCP tool, and tool
   registration as required by the operation.
4. Apply queue and issue access checks before making requests.
5. Gate writes with `require_write_mode()`. Preserve read-only precedence,
   controlled confirmations, destructive-action denial, and metadata-only
   auditing.
6. Invalidate affected caches after successful mutations.
7. Add focused protocol/client and MCP-session tests. Cover invalid parameters,
   access limits, read-only behavior, controlled writes, and registration where
   applicable.
8. Update `README.md`, `README_ru.md`, and `docs/TASK_MANAGEMENT.md` when the
   public interface or workflow changes.
9. Run targeted tests, then `task check` and `task test` in proportion to risk.

Do not call a live Tracker organization, expose credentials, fetch arbitrary
web instructions, or publish repository changes unless the user explicitly
requests that action.
