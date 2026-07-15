from typing import Any

import pytest
from aioresponses import aioresponses
from yarl import URL

from mcp_tracker.tracker.custom.client import TrackerClient
from mcp_tracker.tracker.proto.types.boards import Board, BoardColumn, Sprint


class TestBoards:
    @pytest.fixture
    def sample_board_data(self) -> dict[str, Any]:
        return {
            "self": "https://api.tracker.yandex.net/v3/boards/73",
            "id": 73,
            "version": 10,
            "name": "My Board",
            "createdAt": "2023-01-01T12:00:00.000+0000",
            "updatedAt": "2023-05-01T10:00:00.000+0000",
            "createdBy": {
                "self": "https://api.tracker.yandex.net/v3/users/1",
                "id": "user-1",
                "display": "User One",
            },
            "columns": [
                {
                    "self": "https://api.tracker.yandex.net/v3/boards/73/columns/1",
                    "id": 1,
                    "name": "Open",
                    "statuses": [
                        {
                            "self": "https://api.tracker.yandex.net/v3/statuses/1",
                            "id": "1",
                            "key": "open",
                            "display": "Open",
                        }
                    ],
                }
            ],
        }

    @pytest.fixture
    def sample_sprint_data(self) -> dict[str, Any]:
        return {
            "self": "https://api.tracker.yandex.net/v3/sprints/44",
            "id": 44,
            "version": 3,
            "name": "Sprint 1",
            "status": "in_progress",
            "archived": False,
            "startDate": "2024-06-01",
            "endDate": "2024-06-14",
            "startDateTime": "2024-06-01T07:00:00.000+0000",
            "endDateTime": "2024-06-14T07:00:00.000+0000",
            "board": {
                "self": "https://api.tracker.yandex.net/v3/boards/3",
                "id": 3,
                "display": "Board 3",
            },
            "createdBy": {
                "self": "https://api.tracker.yandex.net/v3/users/2",
                "id": "user-2",
                "display": "Creator",
            },
            "createdAt": "2024-05-30T10:00:00.000+0000",
        }

    async def test_boards_list(
        self, tracker_client: TrackerClient, sample_board_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/boards",
                payload=[sample_board_data],
            )
            result = await tracker_client.boards_list()

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Board)
        assert result[0].id == 73
        assert result[0].name == "My Board"
        assert result[0].columns is not None
        assert result[0].columns[0].name == "Open"

    async def test_board_get(
        self, tracker_client: TrackerClient, sample_board_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/boards/73",
                payload=sample_board_data,
            )
            result = await tracker_client.board_get(73)

        assert isinstance(result, Board)
        assert result.id == 73
        assert result.name == "My Board"

    async def test_board_get_columns(self, tracker_client: TrackerClient) -> None:
        payload = [
            {
                "self": "https://api.tracker.yandex.net/v3/boards/73/columns/1",
                "id": 1,
                "name": "Open",
                "statuses": [
                    {
                        "self": "https://api.tracker.yandex.net/v3/statuses/1",
                        "id": "1",
                        "key": "open",
                        "display": "Open",
                    }
                ],
            }
        ]

        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/boards/73/columns",
                payload=payload,
            )
            result = await tracker_client.board_get_columns(73)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], BoardColumn)
        assert result[0].id == 1
        assert result[0].statuses is not None
        assert result[0].statuses[0].key == "open"

    async def test_board_get_sprints(
        self, tracker_client: TrackerClient, sample_sprint_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/boards/3/sprints",
                payload=[sample_sprint_data],
            )
            result = await tracker_client.board_get_sprints(3)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Sprint)
        assert result[0].id == 44
        assert result[0].status == "in_progress"
        assert result[0].board is not None
        assert result[0].board.id == 3

    async def test_sprint_get(
        self, tracker_client: TrackerClient, sample_sprint_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.get(
                "https://api.tracker.yandex.net/v3/sprints/44",
                payload=sample_sprint_data,
            )
            result = await tracker_client.sprint_get("44")

        assert isinstance(result, Sprint)
        assert result.id == 44
        assert result.name == "Sprint 1"

    async def test_board_create_uses_live_boards_api(
        self, tracker_client: TrackerClient, sample_board_data: dict[str, Any]
    ) -> None:
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/liveBoards/",
                payload=sample_board_data,
                status=201,
            )
            result = await tracker_client.board_create(
                name="My Board",
                filter={"queue": "TEST"},
                columns=[{"name": "Open", "statuses": ["open"]}],
            )

        assert result.id == 73
        request = m.requests[
            ("POST", URL("https://api.tracker.yandex.net/v3/liveBoards/"))
        ][0]
        payload = request.kwargs["json"]
        assert payload["autoFilters"] == {
            "addFilter": {
                "liveFilter": {"fieldValues": {"queue": [{"fixed": "TEST"}]}},
                "enabled": True,
            }
        }
        assert "filter" not in payload

    async def test_board_create_accepts_native_auto_filters(
        self, tracker_client: TrackerClient, sample_board_data: dict[str, Any]
    ) -> None:
        auto_filters = {
            "addFilter": {
                "liveFilter": {"fieldValues": {"assignee": [{"fixed": "user"}]}},
                "enabled": True,
            }
        }
        with aioresponses() as m:
            m.post(
                "https://api.tracker.yandex.net/v3/liveBoards/",
                payload=sample_board_data,
                status=201,
            )
            await tracker_client.board_create(
                name="My Board",
                filter={"queue": "IGNORED"},
                auto_filters=auto_filters,
                backlog_available=True,
                sprints_available=True,
            )

        request = m.requests[
            ("POST", URL("https://api.tracker.yandex.net/v3/liveBoards/"))
        ][0]
        payload = request.kwargs["json"]
        assert payload["autoFilters"] == auto_filters
        assert payload["backlogAvailable"] is True
        assert payload["sprintsAvailable"] is True
