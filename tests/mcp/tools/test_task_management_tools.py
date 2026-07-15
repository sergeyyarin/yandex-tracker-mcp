from unittest.mock import AsyncMock

from mcp.client.session import ClientSession

from mcp_tracker.tracker.proto.types.issues import Issue, IssueSearchPage
from tests.mcp.conftest import get_tool_result_content


class TestManagedIssueCreate:
    async def test_creates_full_workflow_idempotently(
        self,
        client_session: ClientSession,
        mock_issues_protocol: AsyncMock,
        sample_issue: Issue,
        sample_checklist: list,
        sample_links: list,
    ) -> None:
        mock_issues_protocol.issues_find.return_value = IssueSearchPage(issues=[])
        mock_issues_protocol.issue_create.return_value = sample_issue
        mock_issues_protocol.issue_get_checklist.return_value = []
        mock_issues_protocol.issue_add_checklist_item.return_value = sample_checklist
        mock_issues_protocol.issues_get_links.return_value = []
        mock_issues_protocol.issue_add_link.return_value = sample_links[0]

        result = await client_session.call_tool(
            "tracker_issue_create_idempotent",
            {
                "queue": "TEST",
                "summary": "Runtime controller",
                "source_id": "roadmap/runtime/controller",
                "epic": "TEST-10",
                "dependencies": ["TEST-11"],
                "checklist": ["Unit tests"],
            },
        )

        assert not result.isError
        content = get_tool_result_content(result)
        assert content["created"] is True
        assert content["source_tag"].startswith("tracker-source-")
        create_kwargs = mock_issues_protocol.issue_create.call_args.kwargs
        assert create_kwargs["tags"] == [content["source_tag"]]
        assert mock_issues_protocol.issue_add_link.call_count == 2

    async def test_retry_reuses_existing_issue_and_reconciles_parts(
        self,
        client_session: ClientSession,
        mock_issues_protocol: AsyncMock,
        sample_issue: Issue,
        sample_checklist: list,
    ) -> None:
        mock_issues_protocol.issues_find.return_value = IssueSearchPage(
            issues=[sample_issue]
        )
        mock_issues_protocol.issue_get_checklist.return_value = sample_checklist
        mock_issues_protocol.issues_get_links.return_value = []

        result = await client_session.call_tool(
            "tracker_issue_create_idempotent",
            {
                "queue": "TEST",
                "summary": "Runtime controller",
                "source_id": "roadmap/runtime/controller",
                "checklist": [sample_checklist[0].text],
            },
        )

        assert not result.isError
        content = get_tool_result_content(result)
        assert content["created"] is False
        mock_issues_protocol.issue_create.assert_not_called()
        mock_issues_protocol.issue_add_checklist_item.assert_not_called()

    async def test_duplicate_source_marker_fails_closed(
        self,
        client_session: ClientSession,
        mock_issues_protocol: AsyncMock,
        sample_issue: Issue,
    ) -> None:
        duplicate = sample_issue.model_copy(update={"key": "TEST-999"})
        mock_issues_protocol.issues_find.return_value = IssueSearchPage(
            issues=[sample_issue, duplicate]
        )

        result = await client_session.call_tool(
            "tracker_issue_create_idempotent",
            {
                "queue": "TEST",
                "summary": "Runtime controller",
                "source_id": "same-source",
            },
        )

        assert result.isError
        mock_issues_protocol.issue_create.assert_not_called()


class TestControlledWritePolicy:
    async def test_transition_requires_confirmation(
        self,
        client_session_controlled: ClientSession,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_controlled.call_tool(
            "issue_execute_transition",
            {"issue_id": "TEST-1", "transition_id": "inProgressMeta"},
        )
        assert result.isError
        mock_issues_protocol.issue_execute_transition.assert_not_called()

    async def test_transition_accepts_human_confirmation(
        self,
        client_session_controlled: ClientSession,
        mock_issues_protocol: AsyncMock,
        sample_transitions: list,
    ) -> None:
        mock_issues_protocol.issue_execute_transition.return_value = sample_transitions
        result = await client_session_controlled.call_tool(
            "issue_execute_transition",
            {
                "issue_id": "TEST-1",
                "transition_id": "inProgressMeta",
                "confirmed": True,
            },
        )
        assert not result.isError

    async def test_close_remains_disabled_by_default(
        self,
        client_session_controlled: ClientSession,
        mock_issues_protocol: AsyncMock,
    ) -> None:
        result = await client_session_controlled.call_tool(
            "issue_close",
            {
                "issue_id": "TEST-1",
                "resolution_id": "fixed",
                "confirmed": True,
            },
        )
        assert result.isError
        mock_issues_protocol.issue_close.assert_not_called()
