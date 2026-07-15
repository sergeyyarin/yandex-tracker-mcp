"""High-level, idempotent workflow for managed development tasks."""

import hashlib
from typing import Annotated, Any

from mcp.server import FastMCP
from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.tools._access import (
    check_issue_access,
    check_queue_access,
    require_write_mode,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, list):
        return [_dump(item) for item in value]
    return value


def _source_tag(source_id: str) -> str:
    """Build a stable, non-sensitive Tracker tag for an external task id."""
    digest = hashlib.sha256(source_id.strip().encode()).hexdigest()[:24]
    return f"tracker-source-{digest}"


def _yql_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def register_task_management_tools(settings: Settings, mcp: FastMCP[Any]) -> None:
    @mcp.tool(
        title="Create Managed Tracker Task",
        description=(
            "Create or reconcile one development task as an idempotent "
            "workflow: issue, checklist, parent/epic and dependency links. "
            "Provide a stable `source_id` from the roadmap/backlog; retries search "
            "for its deterministic tag before creating a duplicate."
        ),
    )
    async def tracker_issue_create_idempotent(
        ctx: Context[Any, AppContext],
        queue: Annotated[str, Field(description="Target Tracker queue key")],
        summary: Annotated[str, Field(description="Task title")],
        source_id: Annotated[
            str | None,
            Field(description="Stable external backlog id used for idempotency"),
        ] = None,
        type: Annotated[
            int | str | None, Field(description="Issue type id or key")
        ] = "task",
        description: Annotated[
            str | None, Field(description="Task description in YFM/Markdown")
        ] = None,
        assignee: Annotated[
            str | int | None, Field(description="Assignee login or uid")
        ] = None,
        priority: Annotated[
            str | None, Field(description="Initial priority key")
        ] = None,
        parent: Annotated[str | None, Field(description="Parent issue key")] = None,
        epic: Annotated[str | None, Field(description="Epic issue key")] = None,
        dependencies: Annotated[
            list[str] | None,
            Field(description="Issues that must be completed before this task"),
        ] = None,
        sprint: Annotated[list[str] | None, Field(description="Sprint ids")] = None,
        checklist: Annotated[
            list[str] | None,
            Field(
                description="Acceptance/checklist items; duplicate texts are ignored"
            ),
        ] = None,
        fields: Annotated[
            dict[str, Any] | None,
            Field(description="Additional Tracker fields for issue creation"),
        ] = None,
    ) -> dict[str, Any]:
        require_write_mode(settings, "create")
        check_queue_access(settings, queue)
        for issue_key in [parent, epic, *(dependencies or [])]:
            if issue_key:
                check_issue_access(settings, issue_key)

        issues = ctx.request_context.lifespan_context.issues
        auth = get_yandex_auth(ctx)
        marker = _source_tag(source_id) if source_id else None
        issue = None
        created = False

        if marker:
            result = await issues.issues_find(
                query=(f"Queue: {_yql_string(queue)} AND Tags: {_yql_string(marker)}"),
                per_page=2,
                page=1,
                auth=auth,
            )
            if len(result.issues) > 1:
                raise ValueError(
                    "Idempotency conflict: more than one issue has the Tracker "
                    f"source marker `{marker}`. Resolve duplicates before retrying."
                )
            if result.issues:
                issue = result.issues[0]

        if issue is None:
            create_fields = dict(fields or {})
            tags = list(create_fields.pop("tags", []) or [])
            if marker and marker not in tags:
                tags.append(marker)
            if tags:
                create_fields["tags"] = tags

            issue = await issues.issue_create(
                queue=queue,
                summary=summary,
                type=type,
                description=description,
                assignee=assignee,
                priority=priority,
                parent=parent,
                sprint=sprint,
                auth=auth,
                **create_fields,
            )
            created = True

        if not issue.key:
            raise ValueError("Tracker returned an issue without a key.")
        issue_key = issue.key

        existing_checklist = await issues.issue_get_checklist(issue_key, auth=auth)
        known_texts = {item.text.strip() for item in existing_checklist}
        for text in checklist or []:
            normalized = text.strip()
            if normalized and normalized not in known_texts:
                existing_checklist = await issues.issue_add_checklist_item(
                    issue_key, text=normalized, auth=auth
                )
                known_texts.add(normalized)

        existing_links = await issues.issues_get_links(issue_key, auth=auth)
        known_targets = {
            link.object.key.upper()
            for link in existing_links
            if link.object and link.object.key
        }
        requested_links: list[tuple[str, str]] = []
        if epic:
            requested_links.append(("has epic", epic))
        requested_links.extend(
            ("depends on", dependency) for dependency in dependencies or []
        )
        for relationship, target in requested_links:
            if target.upper() not in known_targets:
                link = await issues.issue_add_link(
                    issue_key,
                    relationship=relationship,
                    target_issue=target,
                    auth=auth,
                )
                existing_links.append(link)
                known_targets.add(target.upper())

        return {
            "created": created,
            "source_tag": marker,
            "issue": _dump(issue),
            "checklist": _dump(existing_checklist),
            "links": _dump(existing_links),
        }
