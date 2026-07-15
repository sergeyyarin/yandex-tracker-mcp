from typing import Any, Protocol, runtime_checkable

from .common import YandexAuth
from .types.boards import Board, BoardColumn, Sprint


@runtime_checkable
class BoardsProtocol(Protocol):
    async def boards_list(self, *, auth: YandexAuth | None = None) -> list[Board]: ...

    async def board_get(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> Board: ...

    async def board_get_columns(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> list[BoardColumn]: ...

    async def board_get_sprints(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> list[Sprint]: ...

    async def sprint_get(
        self, sprint_id: str, *, auth: YandexAuth | None = None
    ) -> Sprint: ...

    # --- write ---
    async def board_create(
        self,
        *,
        name: str,
        owner: str | int | None = None,
        board_permissions_template: str | None = None,
        backlog_available: bool | None = None,
        sprints_available: bool | None = None,
        filter: dict[str, Any] | None = None,
        auto_filters: dict[str, Any] | None = None,
        non_parametrized_columns: list[dict[str, Any]] | None = None,
        backlog_columns: list[dict[str, Any]] | None = None,
        columns: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
        auth: YandexAuth | None = None,
    ) -> Board: ...

    async def board_update(
        self,
        board_id: int,
        *,
        fields: dict[str, Any],
        auth: YandexAuth | None = None,
    ) -> Board: ...

    async def board_delete(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> None: ...

    async def board_column_create(
        self,
        board_id: int,
        *,
        name: str,
        statuses: list[str],
        version: str | int | None = None,
        auth: YandexAuth | None = None,
    ) -> BoardColumn: ...

    async def board_column_update(
        self,
        board_id: int,
        column_id: int,
        *,
        name: str | None = None,
        statuses: list[str] | None = None,
        version: str | int | None = None,
        auth: YandexAuth | None = None,
    ) -> BoardColumn: ...

    async def board_column_delete(
        self,
        board_id: int,
        column_id: int,
        *,
        version: str | int | None = None,
        auth: YandexAuth | None = None,
    ) -> None: ...

    async def sprint_create(
        self,
        board_id: int,
        *,
        name: str,
        start_date: str | None = None,
        end_date: str | None = None,
        start_date_time: str | None = None,
        end_date_time: str | None = None,
        extra: dict[str, Any] | None = None,
        auth: YandexAuth | None = None,
    ) -> Sprint: ...

    async def sprint_update(
        self,
        sprint_id: str | int,
        *,
        fields: dict[str, Any],
        auth: YandexAuth | None = None,
    ) -> Sprint: ...

    async def sprint_delete(
        self,
        sprint_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> None: ...

    async def sprint_start(
        self,
        sprint_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> Sprint: ...

    async def sprint_finish(
        self,
        sprint_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> Sprint: ...


class BoardsProtocolWrap(BoardsProtocol):
    def __init__(self, original: BoardsProtocol):
        self._original = original
