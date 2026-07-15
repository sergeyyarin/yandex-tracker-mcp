import pytest
from mcp.client.session import ClientSession

# Read-only tool names — always registered
READ_ONLY_TOOL_NAMES = [
    # Field tools (2)
    "tracker_reference",
    "issue_get_url",
    # Issue read tools (4)
    "issue_get",
    "issues_find",
    "issues_count",
    "issue_get_transitions",
    # Consolidated issue CRUD — always registered; write-actions gated by read-only mode (6)
    "issue_comments",
    "issue_links",
    "issue_worklogs",
    "issue_attachments",
    "issue_checklist",
    "issue_tags",
    # Consolidated queues (read+write, gated internally) — 1
    "queues",
    # Consolidated users — 1
    "users",
    # Consolidated bulk (read+write, gated internally) — 1
    "bulk",
    # Consolidated CRUD (components/filters/dashboards/sprints) — 4
    "components",
    "filters",
    "dashboards",
    "sprints",
    # Consolidated boards + columns — 2
    "boards",
    "board_columns",
    # Consolidated automations — 4
    "triggers",
    "autoactions",
    "macros",
    "workflows",
    # Project/entities tools (5)
    "projects_search",
    "portfolios_search",
    "goals_search",
    "entity_get",
    "projects_legacy_list",
]

# Write tool names — only registered when not in read-only mode
WRITE_TOOL_NAMES = [
    # Issue write (6)
    "tracker_issue_create_idempotent",
    "issue_execute_transition",
    "issue_close",
    "issue_create",
    "issue_update",
    "issue_move_to_queue",
    # Entity write (3)
    "entity_create",
    "entity_update",
    "entity_delete",
]

# All tool names that should be registered in normal mode
EXPECTED_TOOL_NAMES = READ_ONLY_TOOL_NAMES + WRITE_TOOL_NAMES


class TestToolRegistration:
    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    async def test_tool_is_registered(
        self,
        client_session: ClientSession,
        tool_name: str,
    ) -> None:
        result = await client_session.list_tools()

        tool_names = [tool.name for tool in result.tools]
        assert tool_name in tool_names, f"Tool '{tool_name}' is not registered"


class TestReadOnlyModeToolRegistration:
    """Test tool registration in read-only mode."""

    @pytest.mark.parametrize("tool_name", READ_ONLY_TOOL_NAMES)
    async def test_read_only_tools_are_registered(
        self,
        client_session_read_only: ClientSession,
        tool_name: str,
    ) -> None:
        """Read-only tools should be registered in read-only mode."""
        result = await client_session_read_only.list_tools()

        tool_names = [tool.name for tool in result.tools]
        assert tool_name in tool_names, (
            f"Read-only tool '{tool_name}' should be registered in read-only mode"
        )

    @pytest.mark.parametrize("tool_name", WRITE_TOOL_NAMES)
    async def test_write_tools_are_not_registered(
        self,
        client_session_read_only: ClientSession,
        tool_name: str,
    ) -> None:
        """Write tools should NOT be registered in read-only mode."""
        result = await client_session_read_only.list_tools()

        tool_names = [tool.name for tool in result.tools]
        assert tool_name not in tool_names, (
            f"Write tool '{tool_name}' should NOT be registered in read-only mode"
        )

    async def test_correct_tool_count_in_read_only_mode(
        self,
        client_session_read_only: ClientSession,
    ) -> None:
        """Read-only mode should have only read-only tools."""
        result = await client_session_read_only.list_tools()

        assert len(result.tools) == len(READ_ONLY_TOOL_NAMES), (
            f"Expected {len(READ_ONLY_TOOL_NAMES)} tools in read-only mode, "
            f"got {len(result.tools)}"
        )

    async def test_correct_tool_count_in_normal_mode(
        self,
        client_session: ClientSession,
    ) -> None:
        """Normal mode should have all tools (read-only + write)."""
        result = await client_session.list_tools()

        assert len(result.tools) == len(EXPECTED_TOOL_NAMES), (
            f"Expected {len(EXPECTED_TOOL_NAMES)} tools in normal mode, "
            f"got {len(result.tools)}"
        )


class TestResourceRegistration:
    async def test_configuration_resource_is_registered(
        self,
        client_session: ClientSession,
    ) -> None:
        result = await client_session.list_resources()

        resource_uris = [str(r.uri) for r in result.resources]
        assert "tracker-mcp://configuration" in resource_uris


class TestServerConfiguration:
    async def test_server_has_correct_name(
        self,
        client_session: ClientSession,
    ) -> None:
        result = await client_session.initialize()

        assert result.serverInfo.name == "Yandex Tracker MCP Server"

    async def test_server_has_instructions(
        self,
        client_session: ClientSession,
    ) -> None:
        result = await client_session.initialize()

        assert result.instructions is not None
        assert len(result.instructions) > 0
