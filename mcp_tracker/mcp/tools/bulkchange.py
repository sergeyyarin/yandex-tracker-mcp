"""Consolidated bulk tool (update/move/transition/status)."""

from typing import Annotated, Any, Literal

from mcp.server import FastMCP
from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import IssueIDs, QueueID
from mcp_tracker.mcp.tools._access import (
    check_issue_access,
    check_queue_access,
    require_write_mode,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings

BulkAction = Literal["update", "move", "transition", "status"]


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, list):
        return [_dump(v) for v in value]
    return value


def register_bulkchange_tools(settings: Settings, mcp: FastMCP[Any]) -> None:
    @mcp.tool(
        title="Bulk",
        description=(
            "Run or inspect long-running bulk operations on issues.\n\n"
            "Actions:\n"
            "- `update` — apply one `values` dict to many `issues`; "
            "optional `comment`, `notify`\n"
            "- `move` — move many `issues` to another `queue`; "
            "optional `move_all_fields`, `initial_status`, `notify`, `extra`\n"
            "- `transition` — execute the same `transition` across many `issues`; "
            "optional `comment`, `resolution`, `fields`\n"
            "- `status` — poll progress of a previously started operation; "
            "requires `operation_id`\n\n"
            "Write actions return an operation descriptor; use `status` to track."
        ),
    )
    async def bulk(
        ctx: Context[Any, AppContext],
        action: BulkAction,
        issues: Annotated[
            IssueIDs | None,
            Field(description="Issue keys (update/move/transition)"),
        ] = None,
        values: Annotated[
            dict[str, Any] | None,
            Field(description="Fields to set (update)"),
        ] = None,
        queue: Annotated[
            QueueID | None, Field(description="Target queue key (move)")
        ] = None,
        transition: Annotated[
            str | None, Field(description="Transition id (transition)")
        ] = None,
        resolution: Annotated[
            str | None, Field(description="Resolution for done-type transitions")
        ] = None,
        comment: Annotated[
            str | None, Field(description="Comment to add (update/transition)")
        ] = None,
        notify: Annotated[
            bool | None, Field(description="Send notifications (update/move)")
        ] = None,
        move_all_fields: Annotated[
            bool | None, Field(description="Preserve fields during move")
        ] = None,
        initial_status: Annotated[
            bool | None, Field(description="Use target queue initial status (move)")
        ] = None,
        fields: Annotated[
            dict[str, Any] | None, Field(description="Extra transition fields")
        ] = None,
        extra: Annotated[
            dict[str, Any] | None, Field(description="Extra body fields (move)")
        ] = None,
        operation_id: Annotated[
            str | None, Field(description="Bulk operation id (status)")
        ] = None,
        confirmed: Annotated[
            bool, Field(description="Human approved this exact bulk mutation")
        ] = False,
    ) -> dict[str, Any]:
        bulkchange = ctx.request_context.lifespan_context.bulkchange
        auth = get_yandex_auth(ctx)

        if action == "status":
            if operation_id is None:
                raise ValueError("`operation_id` is required for action `status`.")
            item = await bulkchange.bulk_status_get(operation_id, auth=auth)
            return {"operation": _dump(item)}

        require_write_mode(settings, "bulk", confirmed=confirmed)

        # Bulk operations must honor queue restrictions like single-issue tools.
        if issues:
            for issue_key in issues:
                check_issue_access(settings, issue_key)

        if action == "update":
            if issues is None:
                raise ValueError("`issues` is required for action `update`.")
            if values is None:
                raise ValueError("`values` is required for action `update`.")
            item = await bulkchange.bulk_update(
                issues=issues,
                values=values,
                comment=comment,
                notify=notify,
                auth=auth,
            )
            return {"operation": _dump(item)}

        if action == "move":
            if issues is None:
                raise ValueError("`issues` is required for action `move`.")
            if queue is None:
                raise ValueError("`queue` is required for action `move`.")
            check_queue_access(settings, queue)
            item = await bulkchange.bulk_move(
                issues=issues,
                queue=queue,
                move_all_fields=move_all_fields,
                initial_status=initial_status,
                notify=notify,
                extra=extra,
                auth=auth,
            )
            return {"operation": _dump(item)}

        if action == "transition":
            if issues is None:
                raise ValueError("`issues` is required for action `transition`.")
            if transition is None:
                raise ValueError("`transition` is required for action `transition`.")
            item = await bulkchange.bulk_transition(
                issues=issues,
                transition=transition,
                comment=comment,
                resolution=resolution,
                fields=fields,
                auth=auth,
            )
            return {"operation": _dump(item)}

        raise ValueError(f"Unknown action: {action}")
