"""HTTP tests for filters/components/entities/dashboards/automations/bulk/issue-extras."""

import os
import tempfile
from typing import Any

import pytest
from aioresponses import aioresponses

from mcp_tracker.tracker.custom.client import TrackerClient, _order_to_yql_sort_by
from mcp_tracker.tracker.custom.errors import TrackerAPIError
from mcp_tracker.tracker.proto.types.boards import Board, BoardColumn, Sprint
from mcp_tracker.tracker.proto.types.issues import (
    ChecklistItem,
    Issue,
    IssueAttachment,
    IssueLink,
)
from mcp_tracker.tracker.proto.types.misc import (
    Autoaction,
    BulkChangeResult,
    Component,
    Dashboard,
    DashboardWidget,
    IssueFilter,
    Macro,
    Trigger,
    Workflow,
)
from tests.aioresponses_utils import RequestCapture


class TestFilters:
    async def test_filters_list(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/filters/_search",
                payload=[{"id": "1", "name": "My filter", "query": "queue: TEST"}],
            )
            result = await tracker_client.filters_list()
        assert len(result) == 1
        assert isinstance(result[0], IssueFilter)

    async def test_filters_list_unwraps_values(
        self, tracker_client: TrackerClient
    ) -> None:
        """Tracker may wrap the result in {hits, pages, values}."""
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/filters/_search",
                payload={
                    "hits": 2,
                    "pages": 1,
                    "values": [
                        {"id": "1", "name": "A", "query": "queue: TEST"},
                        {"id": "2", "name": "B", "query": "queue: DEV"},
                    ],
                },
            )
            result = await tracker_client.filters_list()
        assert len(result) == 2
        assert result[1].id == "2"

    async def test_filter_create(self, tracker_client: TrackerClient) -> None:
        payload = {"id": "42", "name": "New", "query": "queue: TEST"}
        with aioresponses() as m:
            m.post("https://api.tracker.yandex.net/v3/filters", payload=payload)
            result = await tracker_client.filter_create(name="New", query="queue: TEST")
        assert result.id == "42"

    async def test_filter_delete(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.delete("https://api.tracker.yandex.net/v3/filters/1", status=204)
            await tracker_client.filter_delete("1")


class TestComponents:
    async def test_components_list(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/components?perPage=50&page=1",
                payload=[{"id": 1, "name": "Core"}],
            )
            result = await tracker_client.components_list()
        assert len(result) == 1
        assert isinstance(result[0], Component)

    async def test_component_create(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/components",
                payload={"id": 5, "name": "Back"},
            )
            result = await tracker_client.component_create(name="Back", queue="TEST")
        assert result.id == 5


class TestEntities:
    async def test_projects_search(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/entities/project/_search?perPage=50&page=1",
                payload=[{"id": "p1", "name": "Project 1"}],
            )
            result = await tracker_client.projects_search()
        assert len(result) == 1
        assert result[0].id == "p1"

    async def test_entity_create(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/entities/goal",
                payload={"id": "g1", "fields": {"summary": "Q1"}},
            )
            result = await tracker_client.entity_create(
                "goal", fields={"summary": "Q1"}
            )
        assert result["id"] == "g1"


class TestDashboards:
    async def test_dashboards_list(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/dashboards/_search?perPage=50&page=1",
                payload=[{"id": "d1", "name": "Home"}],
            )
            result = await tracker_client.dashboards_list()
        assert len(result) == 1
        assert isinstance(result[0], Dashboard)

    async def test_dashboard_widgets(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/dashboards/d1",
                payload={
                    "id": "d1",
                    "name": "Home",
                    "widgets": [{"id": "w1", "type": "issueList"}],
                },
            )
            result = await tracker_client.dashboard_get_widgets("d1")
        assert len(result) == 1
        assert isinstance(result[0], DashboardWidget)


class TestAutomations:
    async def test_triggers_list(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/queues/TEST/triggers",
                payload=[{"id": 1, "name": "onCreate"}],
            )
            result = await tracker_client.triggers_list("TEST")
        assert isinstance(result[0], Trigger)

    async def test_autoactions_list(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/queues/TEST/autoactions",
                payload=[{"id": 2, "name": "nightly"}],
            )
            result = await tracker_client.autoactions_list("TEST")
        assert isinstance(result[0], Autoaction)

    async def test_macros_list(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/queues/TEST/macros",
                payload=[{"id": 3, "name": "close"}],
            )
            result = await tracker_client.macros_list("TEST")
        assert isinstance(result[0], Macro)

    async def test_workflows_list(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/workflows",
                payload=[{"id": "wf1", "name": "Kanban"}],
            )
            result = await tracker_client.workflows_list()
        assert isinstance(result[0], Workflow)

    async def test_queue_workflow_get(self, tracker_client: TrackerClient) -> None:
        # The client fetches all workflows and filters by queue key/id client-side
        # because Tracker has no /queues/<id>/workflow endpoint.
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/workflows",
                payload=[
                    {"id": "wf1", "name": "Kanban", "queue": {"key": "TEST"}},
                    {"id": "wf2", "name": "Other", "queue": {"key": "OTHER"}},
                ],
            )
            result = await tracker_client.queue_workflow_get("TEST")
        assert isinstance(result, Workflow)
        assert result.id == "wf1"

    async def test_queue_workflow_get_returns_none_when_absent(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/workflows",
                payload=[{"id": "wf1", "queue": {"key": "OTHER"}}],
            )
            result = await tracker_client.queue_workflow_get("TEST")
        assert result is None


class TestBulkChange:
    async def test_bulk_update(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/bulkchange/_update",
                payload={"id": "op1", "status": "CREATED"},
            )
            result = await tracker_client.bulk_update(
                issues=["TEST-1"], values={"priority": "high"}
            )
        assert isinstance(result, BulkChangeResult)
        assert result.id == "op1"

    async def test_bulk_move(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/bulkchange/_move",
                payload={"id": "op2", "status": "IN_PROGRESS"},
            )
            result = await tracker_client.bulk_move(issues=["TEST-1"], queue="DEV")
        assert result.id == "op2"

    async def test_bulk_transition(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/bulkchange/_transition",
                payload={"id": "op3", "status": "COMPLETED"},
            )
            result = await tracker_client.bulk_transition(
                issues=["TEST-1"], transition="close"
            )
        assert result.id == "op3"

    async def test_bulk_transition_resolution_goes_into_values(
        self, tracker_client: TrackerClient
    ) -> None:
        capture = RequestCapture(payload={"id": "op4", "status": "CREATED"})
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/bulkchange/_transition",
                callback=capture.callback,
            )
            await tracker_client.bulk_transition(
                issues=["TEST-1"],
                transition="close",
                resolution="fixed",
                fields={"assignee": "user1"},
            )
        request = capture.last_request
        request.assert_json_field(
            "values", {"assignee": "user1", "resolution": "fixed"}
        )
        body = request.get_json_body()
        assert "resolution" not in body  # must not leak to the top level


class TestIssueExtras:
    @pytest.fixture
    def sample_issue_payload(self) -> dict[str, Any]:
        return {
            "id": "abc",
            "key": "TEST-1",
            "summary": "Sample",
        }

    async def test_issue_add_link(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/links",
                payload={
                    "id": 42,
                    "direction": "outward",
                    "type": {"id": "relates"},
                },
            )
            result = await tracker_client.issue_add_link(
                "TEST-1", relationship="relates", target_issue="TEST-2"
            )
        assert isinstance(result, IssueLink)
        assert result.id == 42

    async def test_issue_delete_link(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.delete(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/links/42", status=204
            )
            await tracker_client.issue_delete_link("TEST-1", 42)

    async def test_issue_add_checklist_item(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/checklistItems",
                payload=[{"id": "c1", "text": "Do it", "checked": False}],
            )
            result = await tracker_client.issue_add_checklist_item(
                "TEST-1", text="Do it"
            )
        assert len(result) == 1
        assert isinstance(result[0], ChecklistItem)

    async def test_issue_add_tags(
        self, tracker_client: TrackerClient, sample_issue_payload: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.patch(
                "https://api.tracker.yandex.net/v3/issues/TEST-1",
                payload={**sample_issue_payload, "tags": ["bug", "urgent"]},
            )
            result = await tracker_client.issue_add_tags("TEST-1", ["urgent"])
        assert isinstance(result, Issue)

    async def test_issue_move_to_queue(
        self, tracker_client: TrackerClient, sample_issue_payload: dict[str, Any]
    ) -> None:
        # The target queue must travel as the `queue` query parameter; the JSON
        # body is reserved for issue fields changed during the move.
        capture = RequestCapture(payload={**sample_issue_payload, "key": "DEV-1"})
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/_move?queue=DEV",
                callback=capture.callback,
            )
            result = await tracker_client.issue_move_to_queue("TEST-1", "DEV")
        assert result.key == "DEV-1"
        assert capture.last_request.get_json_body() == {}

    async def test_issue_move_to_queue_with_options(
        self, tracker_client: TrackerClient, sample_issue_payload: dict[str, Any]
    ) -> None:
        capture = RequestCapture(payload={**sample_issue_payload, "key": "DEV-1"})
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/_move"
                "?queue=DEV&moveAllFields=true&initialStatus=true"
                "&notify=false&notifyAuthor=true",
                callback=capture.callback,
            )
            result = await tracker_client.issue_move_to_queue(
                "TEST-1",
                "DEV",
                move_all_fields=True,
                initial_status=True,
                notify=False,
                notify_author=True,
                extra={"summary": "Moved"},
            )
        assert result.key == "DEV-1"
        capture.last_request.assert_json_field("summary", "Moved")

    async def test_issue_upload_attachment(self, tracker_client: TrackerClient) -> None:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as fh:
            fh.write("hello")
            tmp_path = fh.name
        try:
            with aioresponses() as m:
                m.post(
                    "https://api.tracker.yandex.net/v3/issues/TEST-1/attachments",
                    payload={"id": "a1", "name": os.path.basename(tmp_path)},
                )
                result = await tracker_client.issue_upload_attachment(
                    "TEST-1", file_path=tmp_path
                )
            assert isinstance(result, IssueAttachment)
            assert result.id == "a1"
        finally:
            os.unlink(tmp_path)

    async def test_issue_download_attachment(
        self, tracker_client: TrackerClient
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with aioresponses() as m:
                m.get(
                    "https://api.tracker.yandex.net/v3/issues/TEST-1/attachments/a1/hello.txt",
                    body=b"hello world",
                    headers={"Content-Type": "application/octet-stream"},
                )
                result = await tracker_client.issue_download_attachment(
                    "TEST-1", "a1", "hello.txt", dest_path=tmp_dir
                )
            dest = result["path"]
            assert dest.endswith("hello.txt")
            with open(dest, "rb") as fh:
                assert fh.read() == b"hello world"


class TestBoardsWrite:
    async def test_board_create(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/liveBoards/",
                payload={"id": 11, "name": "New"},
                status=201,
            )
            result = await tracker_client.board_create(name="New")
        assert isinstance(result, Board)

    async def test_board_update(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.patch(
                "https://api.tracker.yandex.net/v3/boards/7",
                payload={"id": 7, "name": "Renamed"},
            )
            result = await tracker_client.board_update(7, fields={"name": "Renamed"})
        assert result.name == "Renamed"

    async def test_board_delete(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.delete("https://api.tracker.yandex.net/v3/boards/7", status=204)
            await tracker_client.board_delete(7)

    async def test_column_create(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/boards/7/columns/",
                payload={"id": 1, "name": "Open"},
            )
            result = await tracker_client.board_column_create(
                7, name="Open", statuses=["open"]
            )
        assert isinstance(result, BoardColumn)

    async def test_sprint_create(self, tracker_client: TrackerClient) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v2/sprints",
                payload={"id": 55, "name": "Sprint A", "status": "draft"},
            )
            result = await tracker_client.sprint_create(7, name="Sprint A")
        assert isinstance(result, Sprint)
        assert result.id == 55


class TestComponentIfMatch:
    """Regression for 0.8.2: component mutations need If-Match from `version`."""

    async def test_component_update_sends_if_match(
        self, tracker_client: TrackerClient
    ) -> None:
        captured_headers: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_headers.update(kwargs.get("headers") or {})
            return CallbackResult(status=200, body='{"id": 1, "name": "New"}')

        with aioresponses() as m:
            m.patch(
                "https://api.tracker.yandex.net/v3/components/1",
                callback=callback,
            )
            await tracker_client.component_update(1, fields={"name": "New"}, version=3)

        assert captured_headers.get("If-Match") == '"3"'

    async def test_component_delete_sends_if_match(
        self, tracker_client: TrackerClient
    ) -> None:
        captured_headers: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_headers.update(kwargs.get("headers") or {})
            return CallbackResult(status=204)

        with aioresponses() as m:
            m.delete(
                "https://api.tracker.yandex.net/v3/components/1",
                callback=callback,
            )
            await tracker_client.component_delete(1, version=3)

        assert captured_headers.get("If-Match") == '"3"'


class TestWorklogStartAutofill:
    """Regression for 0.8.1: Tracker requires `start` even when docs mark it optional."""

    async def test_adds_start_when_omitted(self, tracker_client: TrackerClient) -> None:
        captured_body: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_body.update(kwargs.get("json") or {})
            return CallbackResult(
                status=201,
                body='{"id": 1, "duration": "PT1H"}',
            )

        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/worklog",
                callback=callback,
            )
            await tracker_client.issue_add_worklog("TEST-1", duration="PT1H")

        assert "start" in captured_body
        assert captured_body["start"].endswith("+0000")


class TestRegressions:
    """Regressions fixed in 0.7.1 after MCP user report."""

    async def test_board_get_sprints_returns_empty_on_400(
        self, tracker_client: TrackerClient
    ) -> None:
        """Boards without a sprint setup respond 400 — we should translate that to []."""
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/boards/9/sprints",
                status=400,
                payload={"errorMessages": ["board has no sprints"]},
            )
            result = await tracker_client.board_get_sprints(9)
        assert result == []

    async def test_board_get_sprints_returns_empty_on_404(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/boards/9/sprints",
                status=404,
                payload={"errorMessages": ["not found"]},
            )
            result = await tracker_client.board_get_sprints(9)
        assert result == []

    async def test_issues_find_converts_order_to_yql_sort_by(
        self, tracker_client: TrackerClient
    ) -> None:
        """`order` alongside YQL `query` must be folded into a Sort By clause."""
        captured_body: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_body.update(kwargs.get("json") or {})
            return CallbackResult(status=200, body="[]")

        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/_search?perPage=15&page=1",
                callback=callback,
            )
            await tracker_client.issues_find(
                "Queue: TEST", order=["-updated_at", "+priority"]
            )

        assert "order" not in captured_body
        assert captured_body["query"] == (
            'Queue: TEST "Sort By": Updated DESC, Priority ASC'
        )

    async def test_issues_find_leaves_existing_sort_by_alone(
        self, tracker_client: TrackerClient
    ) -> None:
        captured_body: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_body.update(kwargs.get("json") or {})
            return CallbackResult(status=200, body="[]")

        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/_search?perPage=15&page=1",
                callback=callback,
            )
            await tracker_client.issues_find(
                'Queue: TEST "Sort By": Key ASC', order=["-updated_at"]
            )

        # Existing Sort By preserved, not duplicated
        assert captured_body["query"] == 'Queue: TEST "Sort By": Key ASC'

    async def test_issues_find_passes_order_with_filter(
        self, tracker_client: TrackerClient
    ) -> None:
        """With structured `filter`, order goes in the body as-is."""
        captured_body: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_body.update(kwargs.get("json") or {})
            return CallbackResult(status=200, body="[]")

        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/_search?perPage=15&page=1",
                callback=callback,
            )
            await tracker_client.issues_find(
                filter={"queue": "TEST"}, order=["-updated_at"]
            )

        assert captured_body["filter"] == {"queue": "TEST"}
        assert captured_body["order"] == ["-updated_at"]
        assert "query" not in captured_body

    async def test_issues_find_surfaces_tracker_error_body(
        self, tracker_client: TrackerClient
    ) -> None:
        """4xx should raise TrackerAPIError with parsed errorMessages."""
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/_search?perPage=15&page=1",
                status=422,
                payload={
                    "errorMessages": ["unknown field: Board"],
                    "errors": {"query": "invalid YQL"},
                },
            )
            with pytest.raises(TrackerAPIError) as exc_info:
                await tracker_client.issues_find("Board: 9")

        err = exc_info.value
        assert err.status == 422
        assert "unknown field: Board" in err.error_messages
        assert err.errors == {"query": "invalid YQL"}
        assert "unknown field: Board" in str(err)

    async def test_issues_count_surfaces_tracker_error_body(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/_count",
                status=422,
                payload={"errorMessages": ["invalid query"]},
            )
            with pytest.raises(TrackerAPIError):
                await tracker_client.issues_count("Board: 9")


class TestTransitionReferenceWrapping:
    """Regressions for 0.7.2: bare strings for reference fields got 422."""

    async def test_issue_execute_transition_wraps_resolution_string(
        self, tracker_client: TrackerClient
    ) -> None:
        captured_body: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_body.update(kwargs.get("json") or {})
            return CallbackResult(status=200, body="[]")

        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/transitions/close/_execute",
                callback=callback,
            )
            await tracker_client.issue_execute_transition(
                "TEST-1", "close", fields={"resolution": "wontFix"}
            )

        assert captured_body["resolution"] == {"key": "wontFix"}

    async def test_issue_execute_transition_keeps_dict_resolution(
        self, tracker_client: TrackerClient
    ) -> None:
        """Already-wrapped values must pass through unchanged."""
        captured_body: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_body.update(kwargs.get("json") or {})
            return CallbackResult(status=200, body="[]")

        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/transitions/close/_execute",
                callback=callback,
            )
            await tracker_client.issue_execute_transition(
                "TEST-1",
                "close",
                fields={"resolution": {"key": "fixed", "display": "Fixed"}},
            )

        assert captured_body["resolution"] == {"key": "fixed", "display": "Fixed"}

    async def test_issue_execute_transition_does_not_wrap_nonreference_fields(
        self, tracker_client: TrackerClient
    ) -> None:
        captured_body: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_body.update(kwargs.get("json") or {})
            return CallbackResult(status=200, body="[]")

        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/transitions/close/_execute",
                callback=callback,
            )
            await tracker_client.issue_execute_transition(
                "TEST-1", "close", fields={"customField": "value", "tags": ["a", "b"]}
            )

        # Non-reference fields passed through unchanged.
        assert captured_body["customField"] == "value"
        assert captured_body["tags"] == ["a", "b"]


class TestSprintCreateEndpoint:
    async def test_uses_v2_sprints_endpoint_with_board_in_body(
        self, tracker_client: TrackerClient
    ) -> None:
        captured_body: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_body.update(kwargs.get("json") or {})
            return CallbackResult(
                status=200,
                body='{"id": 77, "name": "Sprint", "status": "draft"}',
            )

        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v2/sprints",
                callback=callback,
            )
            result = await tracker_client.sprint_create(
                13,
                name="Sprint",
                start_date="2026-01-01",
                end_date="2026-01-14",
            )

        assert isinstance(result, Sprint)
        assert captured_body["board"] == {"id": 13}
        assert captured_body["name"] == "Sprint"
        assert captured_body["startDate"] == "2026-01-01"
        assert captured_body["endDate"] == "2026-01-14"


class TestEntitiesSearchWrapper:
    """Regressions for 0.8.0: Tracker returns `{hits, pages, values}` wrapper."""

    async def test_projects_search_unwraps_values(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/entities/project/_search?perPage=50&page=1",
                payload={
                    "hits": 2,
                    "pages": 1,
                    "values": [
                        {"id": "p1", "name": "Project 1"},
                        {"id": "p2", "name": "Project 2"},
                    ],
                },
            )
            result = await tracker_client.projects_search()
        assert len(result) == 2
        assert result[0].id == "p1"
        assert result[1].id == "p2"

    async def test_projects_search_accepts_bare_list(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/entities/project/_search?perPage=50&page=1",
                payload=[{"id": "p1", "name": "One"}],
            )
            result = await tracker_client.projects_search()
        assert len(result) == 1
        assert result[0].id == "p1"


class TestChecklistIssueResponse:
    """Regressions for 0.8.0: checklist mutation returns the full Issue body."""

    async def test_add_checklist_item_extracts_items_from_issue(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/checklistItems",
                payload={
                    "self": "https://...",
                    "key": "TEST-1",
                    "checklistItems": [
                        {"id": "c1", "text": "First"},
                        {"id": "c2", "text": "Second"},
                    ],
                },
            )
            result = await tracker_client.issue_add_checklist_item(
                "TEST-1", text="Second"
            )
        assert len(result) == 2
        assert result[0].id == "c1"
        assert result[1].text == "Second"

    async def test_update_checklist_item_extracts_items(
        self, tracker_client: TrackerClient
    ) -> None:
        with aioresponses() as m:
            m.patch(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/checklistItems/c1",
                payload={
                    "key": "TEST-1",
                    "checklistItems": [{"id": "c1", "text": "Done", "checked": True}],
                },
            )
            result = await tracker_client.issue_update_checklist_item(
                "TEST-1", "c1", checked=True
            )
        assert len(result) == 1
        assert result[0].checked is True

    async def test_add_checklist_item_accepts_bare_list(
        self, tracker_client: TrackerClient
    ) -> None:
        """Older variants may return a bare array — we still accept it."""
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/issues/TEST-1/checklistItems",
                payload=[{"id": "c1", "text": "Only"}],
            )
            result = await tracker_client.issue_add_checklist_item(
                "TEST-1", text="Only"
            )
        assert len(result) == 1
        assert result[0].id == "c1"


class TestDashboardUpdateVersion:
    async def test_sends_if_match_header(self, tracker_client: TrackerClient) -> None:
        captured_headers: dict[str, Any] = {}

        def callback(url: Any, **kwargs: Any) -> Any:
            from aioresponses.core import CallbackResult

            captured_headers.update(kwargs.get("headers") or {})
            return CallbackResult(status=200, body='{"id": "d1", "name": "Renamed"}')

        with aioresponses() as m:
            m.patch(
                "https://api.tracker.yandex.net/v3/dashboards/d1",
                callback=callback,
            )
            await tracker_client.dashboard_update(
                "d1", fields={"name": "Renamed"}, version=5
            )

        assert captured_headers.get("If-Match") == '"5"'


class TestOrderToYqlSortBy:
    @pytest.mark.parametrize(
        "order,expected",
        [
            ([], ""),
            (["updated_at"], '"Sort By": Updated ASC'),
            (["-updated_at"], '"Sort By": Updated DESC'),
            (["+priority"], '"Sort By": Priority ASC'),
            (
                ["-updated_at", "+priority"],
                '"Sort By": Updated DESC, Priority ASC',
            ),
            (["story_points"], '"Sort By": StoryPoints ASC'),
            (["-customField"], '"Sort By": Customfield DESC'),
        ],
    )
    def test_mapping(self, order: list[str], expected: str) -> None:
        assert _order_to_yql_sort_by(order) == expected
