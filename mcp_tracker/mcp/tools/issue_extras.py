"""Remaining write tools for issues that did not fit the consolidated `issue_*` families."""

from typing import Annotated, Any

from mcp.server import FastMCP
from mcp.server.fastmcp import Context
from pydantic import Field

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.params import IssueID, QueueID
from mcp_tracker.mcp.tools._access import (
    check_issue_access,
    check_queue_access,
    require_write_mode,
)
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.proto.types.issues import Issue


def register_issue_extras_tools(settings: Settings, mcp: FastMCP[Any]) -> None:
    """Register write tools that don't belong to a consolidated issue family."""

    @mcp.tool(
        title="Move Issue to Queue",
        description="Move an issue to another queue. Optionally preserve all fields "
        "or set the initial status of the target queue.",
    )
    async def issue_move_to_queue(
        ctx: Context[Any, AppContext],
        issue_id: IssueID,
        queue: QueueID,
        move_all_fields: Annotated[
            bool | None,
            Field(description="Keep all fields including queue-specific ones"),
        ] = None,
        initial_status: Annotated[
            bool | None, Field(description="Set target queue initial status")
        ] = None,
        notify: Annotated[bool | None, Field(description="Send notifications")] = None,
        notify_author: Annotated[
            bool | None, Field(description="Notify the issue author")
        ] = None,
        expand: Annotated[
            list[str] | None,
            Field(
                description="Expand fields in response "
                "(attachments/comments/workflow/transitions)"
            ),
        ] = None,
        extra: Annotated[
            dict[str, Any] | None,
            Field(description="Additional body fields to override per move"),
        ] = None,
        confirmed: Annotated[
            bool, Field(description="Human approved moving this exact issue")
        ] = False,
    ) -> Issue:
        check_issue_access(settings, issue_id)
        check_queue_access(settings, queue)
        require_write_mode(settings, "move", confirmed=confirmed)
        return await ctx.request_context.lifespan_context.issues.issue_move_to_queue(
            issue_id,
            queue,
            move_all_fields=move_all_fields,
            initial_status=initial_status,
            expand=expand,
            notify=notify,
            notify_author=notify_author,
            extra=extra,
            auth=get_yandex_auth(ctx),
        )
