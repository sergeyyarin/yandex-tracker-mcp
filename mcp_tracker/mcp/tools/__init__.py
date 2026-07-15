"""MCP tools package for Yandex Tracker."""

from typing import Any

from mcp.server import FastMCP

from mcp_tracker.mcp.tools.automation import register_automation_tools
from mcp_tracker.mcp.tools.board import register_board_tools
from mcp_tracker.mcp.tools.bulkchange import register_bulkchange_tools
from mcp_tracker.mcp.tools.crud import register_crud_tools
from mcp_tracker.mcp.tools.field import register_field_tools
from mcp_tracker.mcp.tools.issue_extras import register_issue_extras_tools
from mcp_tracker.mcp.tools.issue_parts import register_issue_parts_tools
from mcp_tracker.mcp.tools.issue_read import register_issue_read_tools
from mcp_tracker.mcp.tools.issue_write import register_issue_write_tools
from mcp_tracker.mcp.tools.project import (
    register_project_tools,
    register_project_write_tools,
)
from mcp_tracker.mcp.tools.queue import register_queue_tools
from mcp_tracker.mcp.tools.task_management import register_task_management_tools
from mcp_tracker.mcp.tools.user import register_user_tools
from mcp_tracker.settings import Settings


def register_all_tools(settings: Settings, mcp: FastMCP[Any]) -> None:
    """Register all MCP tools based on settings."""
    # Pure read-only tools — always registered
    register_field_tools(settings, mcp)
    register_issue_read_tools(settings, mcp)
    register_user_tools(settings, mcp)
    register_project_tools(settings, mcp)
    # Consolidated tools (read+write in one tool, gated internally)
    register_queue_tools(settings, mcp)
    register_issue_parts_tools(settings, mcp)
    register_crud_tools(settings, mcp)
    register_board_tools(settings, mcp)
    register_automation_tools(settings, mcp)
    register_bulkchange_tools(settings, mcp)

    # Write tools — only in non read-only mode
    if not settings.tracker_read_only:
        register_task_management_tools(settings, mcp)
        register_issue_write_tools(settings, mcp)
        register_issue_extras_tools(settings, mcp)
        register_project_write_tools(settings, mcp)


__all__ = ["register_all_tools"]
