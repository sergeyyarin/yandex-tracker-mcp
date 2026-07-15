# Controlled Tracker operations

This fork is intended to manage development work derived from roadmaps and engineering backlogs.

## Recommended safety profile

```dotenv
TRACKER_WRITE_POLICY=controlled
TRACKER_ALLOW_DESTRUCTIVE=false
TRACKER_AUDIT_LOG_PATH=/var/log/tracker-mcp/tracker-writes.jsonl
TRACKER_LIMIT_QUEUES=PROJECT
```

With this profile:

- issue creation and other additive actions are allowed;
- issue updates, priority changes, transitions, board updates and bulk operations require `confirmed=true` after a human reviews the exact mutation;
- close, delete and clear operations are denied by default;
- every mutating HTTP request is logged as JSONL without headers, request bodies or query parameters.

`TRACKER_ALLOW_DESTRUCTIVE=true` should only be used in a controlled maintenance window. Read-only mode (`TRACKER_READ_ONLY=true`) still takes precedence over every policy.

## Idempotent task creation

Use `tracker_issue_create_idempotent` for roadmap/backlog synchronization. Supply a stable `source_id`, such as `runtime/CTRL-01`. The tool hashes it into a non-sensitive Tracker tag, searches before creating, and reconciles missing checklist and relationship entries on retry.

The workflow can create:

- the issue with initial type, priority, assignee, parent and sprint;
- acceptance checklist entries;
- an epic relationship;
- dependency links (`depends on`).

If more than one issue has the same source marker, the tool fails closed so a human can resolve the duplicate.

## Boards

Board creation uses `POST /v3/liveBoards/`. The compatibility argument `filter={"queue": "PROJECT"}` is converted to the current `autoFilters.addFilter.liveFilter.fieldValues` structure. Native `auto_filters` can be supplied for multi-field filters.

## Integration test setup

Unit tests do not require Tracker credentials. Live tests should use a dedicated organization and queue. Store tokens only in repository/environment secrets; never commit them or put them in test fixtures.
