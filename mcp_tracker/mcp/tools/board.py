"""Consolidated board + board_columns tools.

Replaces: boards_get_all, board_get, board_get_columns, board_get_sprints,
board_create, board_update, board_delete, board_column_create/update/delete.
"""

from typing import Annotated, Any, Literal, TypeVar

from mcp.server import FastMCP
from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field
from starlette.requests import Request

from mcp_tracker.mcp.context import AppContext
from mcp_tracker.mcp.tools._access import require_write_mode
from mcp_tracker.mcp.utils import get_yandex_auth
from mcp_tracker.settings import Settings

BoardID = Annotated[
    int,
    Field(description="Numeric Yandex Tracker board identifier, e.g. 42"),
]

BoardAction = Literal["list", "get", "columns", "sprints", "create", "update", "delete"]
ColumnAction = Literal["create", "update", "delete"]


_T = TypeVar("_T")


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, list):
        return [_dump(v) for v in value]
    return value


def _require(value: _T | None, name: str, action: str) -> _T:
    if value is None:
        raise ValueError(f"`{name}` is required for action `{action}`.")
    return value


def register_board_tools(settings: Settings, mcp: FastMCP[Any]) -> None:
    """Register consolidated boards + board_columns tools."""

    # ─── boards ────────────────────────────────────────────────
    @mcp.tool(
        title="Boards",
        description=(
            "Manage agile boards and query their nested resources.\n\n"
            "Actions:\n"
            "- `list` → `{boards: [...]}` — all boards in org\n"
            "- `get` → board; requires `board_id`\n"
            "- `columns` → `{columns: [...]}`; requires `board_id`\n"
            "- `sprints` → `{sprints: [...]}`; requires `board_id` "
            "(empty for kanban/filter-only boards)\n"
            "- `create` → board through the current Live Boards API; requires `name`; "
            "use `filter={'queue': 'TEST'}` for the common queue-bound case, or "
            "pass the native `auto_filters` structure\n"
            "- `update` → board; requires `board_id` and `fields`\n"
            "- `delete` → `{ok: true}`; requires `board_id`"
        ),
    )
    async def boards(
        ctx: Context[Any, AppContext, Request],
        action: BoardAction,
        board_id: Annotated[
            int | None,
            Field(description="Board id (get/columns/sprints/update/delete)"),
        ] = None,
        name: Annotated[str | None, Field(description="Board name (create)")] = None,
        owner: Annotated[
            str | int | None, Field(description="Owner login or uid (create)")
        ] = None,
        board_permissions_template: Annotated[
            Literal["private", "public"] | None,
            Field(description="Board access template (create)"),
        ] = None,
        backlog_available: Annotated[
            bool | None, Field(description="Enable backlog (create)")
        ] = None,
        sprints_available: Annotated[
            bool | None, Field(description="Enable sprints (create)")
        ] = None,
        filter: Annotated[
            dict[str, Any] | None,
            Field(description='Board filter, e.g. {"queue": "TEST"} (create)'),
        ] = None,
        auto_filters: Annotated[
            dict[str, Any] | None,
            Field(description="Native Live Boards autoFilters object (create)"),
        ] = None,
        non_parametrized_columns: Annotated[
            list[dict[str, Any]] | None,
            Field(description='Columns as [{"name": str, "statuses": [...]}] (create)'),
        ] = None,
        columns: Annotated[
            list[dict[str, Any]] | None,
            Field(description="Status-bound board columns (create)"),
        ] = None,
        backlog_columns: Annotated[
            list[dict[str, Any]] | None,
            Field(description="Backlog columns (create)"),
        ] = None,
        fields: Annotated[
            dict[str, Any] | None, Field(description="Fields to update (update)")
        ] = None,
        extra: Annotated[
            dict[str, Any] | None, Field(description="Extra body fields (create)")
        ] = None,
        confirmed: Annotated[
            bool,
            Field(description="Human approved this exact mutation (update/delete)"),
        ] = False,
    ) -> dict[str, Any]:
        boards_proto = ctx.request_context.lifespan_context.boards
        auth = get_yandex_auth(ctx)

        def _need_id() -> int:
            if board_id is None:
                raise ValueError(f"`board_id` is required for action `{action}`.")
            return board_id

        if action == "list":
            items = await boards_proto.boards_list(auth=auth)
            return {"boards": _dump(items)}
        if action == "get":
            item = await boards_proto.board_get(_need_id(), auth=auth)
            return {"board": _dump(item)}
        if action == "columns":
            cols = await boards_proto.board_get_columns(_need_id(), auth=auth)
            return {"columns": _dump(cols)}
        if action == "sprints":
            sprints = await boards_proto.board_get_sprints(_need_id(), auth=auth)
            return {"sprints": _dump(sprints)}

        require_write_mode(settings, action, confirmed=confirmed)

        if action == "create":
            name_ = _require(name, "name", action)
            item = await boards_proto.board_create(
                name=name_,
                owner=owner,
                board_permissions_template=board_permissions_template,
                backlog_available=backlog_available,
                sprints_available=sprints_available,
                filter=filter,
                auto_filters=auto_filters,
                non_parametrized_columns=non_parametrized_columns,
                backlog_columns=backlog_columns,
                columns=columns,
                extra=extra,
                auth=auth,
            )
            return {"board": _dump(item)}
        if action == "update":
            flds = _require(fields, "fields", action)
            item = await boards_proto.board_update(_need_id(), fields=flds, auth=auth)
            return {"board": _dump(item)}
        if action == "delete":
            await boards_proto.board_delete(_need_id(), auth=auth)
            return {"ok": True}
        raise ValueError(f"Unknown action: {action}")

    # ─── board_columns ────────────────────────────────────────────────
    @mcp.tool(
        title="Board Columns",
        description=(
            "Create/update/delete agile board columns. Use `boards(action='columns', ...)` "
            "to list existing columns.\n\n"
            "Actions:\n"
            "- `create` → column; requires `board_id`, `name`, `statuses`\n"
            "- `update` → column; requires `board_id` and `column_id`; any of "
            "`name`/`statuses`\n"
            "- `delete` → `{ok: true}`; requires `board_id` and `column_id`\n\n"
            "All actions accept optional `version` for If-Match optimistic lock."
        ),
    )
    async def board_columns(
        ctx: Context[Any, AppContext, Request],
        action: ColumnAction,
        board_id: BoardID,
        column_id: Annotated[
            int | None, Field(description="Column id (update/delete)")
        ] = None,
        name: Annotated[
            str | None, Field(description="Column name (create/update)")
        ] = None,
        statuses: Annotated[
            list[str] | None,
            Field(description="Status keys in column (create/update)"),
        ] = None,
        version: Annotated[
            str | int | None,
            Field(description="Board version for If-Match optimistic lock"),
        ] = None,
        confirmed: Annotated[
            bool,
            Field(description="Human approved this exact mutation (update/delete)"),
        ] = False,
    ) -> dict[str, Any]:
        require_write_mode(settings, action, confirmed=confirmed)
        boards_proto = ctx.request_context.lifespan_context.boards
        auth = get_yandex_auth(ctx)

        def _need_col() -> int:
            if column_id is None:
                raise ValueError(f"`column_id` is required for action `{action}`.")
            return column_id

        if action == "create":
            name_ = _require(name, "name", action)
            statuses_ = _require(statuses, "statuses", action)
            item = await boards_proto.board_column_create(
                board_id,
                name=name_,
                statuses=statuses_,
                version=version,
                auth=auth,
            )
            return {"column": _dump(item)}
        if action == "update":
            item = await boards_proto.board_column_update(
                board_id,
                _need_col(),
                name=name,
                statuses=statuses,
                version=version,
                auth=auth,
            )
            return {"column": _dump(item)}
        if action == "delete":
            await boards_proto.board_column_delete(
                board_id, _need_col(), version=version, auth=auth
            )
            return {"ok": True}
        raise ValueError(f"Unknown action: {action}")
