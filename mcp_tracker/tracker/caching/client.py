import datetime
import hashlib
from dataclasses import dataclass
from typing import Any

from aiocache import cached

from mcp_tracker.tracker.proto.boards import BoardsProtocolWrap
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.extras import (
    AutomationsProtocolWrap,
    BulkChangeProtocolWrap,
    ComponentsProtocolWrap,
    DashboardsProtocolWrap,
    EntitiesProtocolWrap,
    FiltersProtocolWrap,
)
from mcp_tracker.tracker.proto.fields import GlobalDataProtocolWrap
from mcp_tracker.tracker.proto.issues import IssueProtocolWrap
from mcp_tracker.tracker.proto.queues import QueuesProtocolWrap
from mcp_tracker.tracker.proto.types.boards import Board, BoardColumn, Sprint
from mcp_tracker.tracker.proto.types.fields import GlobalField, LocalField
from mcp_tracker.tracker.proto.types.inputs import (
    IssueUpdateFollower,
    IssueUpdateParent,
    IssueUpdatePriority,
    IssueUpdateProject,
    IssueUpdateSprint,
    IssueUpdateType,
)
from mcp_tracker.tracker.proto.types.issue_types import IssueType
from mcp_tracker.tracker.proto.types.issues import (
    ChecklistItem,
    Issue,
    IssueAttachment,
    IssueComment,
    IssueLink,
    IssueSearchPage,
    IssueTransition,
    Worklog,
)
from mcp_tracker.tracker.proto.types.misc import (
    Autoaction,
    BulkChangeResult,
    Component,
    Dashboard,
    DashboardWidget,
    Goal,
    IssueFilter,
    Macro,
    Portfolio,
    Project,
    ProjectLegacy,
    Trigger,
    Workflow,
)
from mcp_tracker.tracker.proto.types.priorities import Priority
from mcp_tracker.tracker.proto.types.queues import (
    Queue,
    QueueExpandOption,
    QueueVersion,
)
from mcp_tracker.tracker.proto.types.resolutions import Resolution
from mcp_tracker.tracker.proto.types.statuses import Status
from mcp_tracker.tracker.proto.types.users import User
from mcp_tracker.tracker.proto.users import UsersProtocolWrap


def _auth_fingerprint(auth: YandexAuth | None) -> str:
    """Stable per-identity cache-key fragment.

    Tokens are hashed so raw OAuth credentials never end up inside Redis keys
    (they are visible via KEYS/MONITOR and persist in RDB/AOF dumps).
    """
    if auth is None:
        return "-"
    token_part = (
        hashlib.sha256(auth.token.encode()).hexdigest()[:16] if auth.token else "-"
    )
    return f"{token_part}:{auth.org_id or '-'}:{auth.cloud_org_id or '-'}"


def _build_key(name: str, *args: Any, **kwargs: Any) -> str:
    """Deterministic cache key shared by the @cached decorator and invalidation.

    `auth` is always folded in (defaulting to the anonymous fingerprint) so an
    omitted kwarg and an explicit `auth=None` yield the same key.
    """
    rest = dict(kwargs)
    auth = rest.pop("auth", None)
    parts: list[str] = [name]
    parts.extend(repr(a) for a in args)
    parts.extend(f"{k}={rest[k]!r}" for k in sorted(rest))
    parts.append(f"auth={_auth_fingerprint(auth)}")
    return "|".join(parts)


def _key_builder(f: Any, _self: Any, *args: Any, **kwargs: Any) -> str:
    return _build_key(f.__name__, *args, **kwargs)


@dataclass
class CacheCollection:
    queues: type[QueuesProtocolWrap]
    issues: type[IssueProtocolWrap]
    global_data: type[GlobalDataProtocolWrap]
    users: type[UsersProtocolWrap]
    boards: type[BoardsProtocolWrap]
    filters: type[FiltersProtocolWrap]
    components: type[ComponentsProtocolWrap]
    entities: type[EntitiesProtocolWrap]
    dashboards: type[DashboardsProtocolWrap]
    automations: type[AutomationsProtocolWrap]
    bulkchange: type[BulkChangeProtocolWrap]


def make_cached_protocols(
    cache_config: dict[str, Any],
) -> CacheCollection:
    # Hash auth tokens out of cache keys and make keys deterministic so write
    # methods can invalidate the corresponding read entries.
    cache_config = {**cache_config, "key_builder": _key_builder}

    class _InvalidatingWrapMixin:
        async def _invalidate(self, name: str, *args: Any, **kwargs: Any) -> None:
            """Best-effort delete of a cached read entry after a write.

            Only the current identity's entry is dropped — in OAuth mode other
            users' entries live until the TTL expires.
            """
            method = getattr(self, name, None)
            cache = getattr(method, "cache", None)
            if cache is None:
                return
            try:
                await cache.delete(_build_key(name, *args, **kwargs))
            except Exception:  # noqa: BLE001 — cache failures must not break writes
                pass

    class CachingQueuesProtocol(QueuesProtocolWrap):
        @cached(**cache_config)
        async def queues_list(
            self, per_page: int = 100, page: int = 1, *, auth: YandexAuth | None = None
        ) -> list[Queue]:
            return await self._original.queues_list(
                per_page=per_page, page=page, auth=auth
            )

        @cached(**cache_config)
        async def queues_get_local_fields(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[LocalField]:
            return await self._original.queues_get_local_fields(queue_id, auth=auth)

        @cached(**cache_config)
        async def queues_get_tags(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[str]:
            return await self._original.queues_get_tags(queue_id, auth=auth)

        @cached(**cache_config)
        async def queues_get_versions(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[QueueVersion]:
            return await self._original.queues_get_versions(queue_id, auth=auth)

        @cached(**cache_config)
        async def queues_get_fields(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[GlobalField]:
            return await self._original.queues_get_fields(queue_id, auth=auth)

        @cached(**cache_config)
        async def queue_get(
            self,
            queue_id: str,
            *,
            expand: list[QueueExpandOption] | None = None,
            auth: YandexAuth | None = None,
        ) -> Queue:
            return await self._original.queue_get(queue_id, expand=expand, auth=auth)

        async def queue_create(
            self,
            *,
            key: str,
            name: str,
            lead: str,
            default_type: str,
            default_priority: str,
            issue_types_config: list[dict[str, Any]] | None = None,
            extra: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> Queue:
            return await self._original.queue_create(
                key=key,
                name=name,
                lead=lead,
                default_type=default_type,
                default_priority=default_priority,
                issue_types_config=issue_types_config,
                extra=extra,
                auth=auth,
            )

    class CachingIssuesProtocol(_InvalidatingWrapMixin, IssueProtocolWrap):
        @cached(**cache_config)
        async def issue_get(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> Issue:
            return await self._original.issue_get(issue_id, auth=auth)

        @cached(**cache_config)
        async def issues_get_links(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[IssueLink]:
            return await self._original.issues_get_links(issue_id, auth=auth)

        @cached(**cache_config)
        async def issue_get_comments(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[IssueComment]:
            return await self._original.issue_get_comments(issue_id, auth=auth)

        async def issue_add_comment(
            self,
            issue_id: str,
            *,
            text: str,
            summonees: list[str] | None = None,
            maillist_summonees: list[str] | None = None,
            markup_type: str | None = None,
            is_add_to_followers: bool = True,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            result = await self._original.issue_add_comment(
                issue_id,
                text=text,
                summonees=summonees,
                maillist_summonees=maillist_summonees,
                markup_type=markup_type,
                is_add_to_followers=is_add_to_followers,
                auth=auth,
            )
            await self._invalidate("issue_get_comments", issue_id, auth=auth)
            return result

        async def issue_update_comment(
            self,
            issue_id: str,
            comment_id: int,
            *,
            text: str,
            summonees: list[str] | None = None,
            maillist_summonees: list[str] | None = None,
            markup_type: str | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueComment:
            result = await self._original.issue_update_comment(
                issue_id,
                comment_id,
                text=text,
                summonees=summonees,
                maillist_summonees=maillist_summonees,
                markup_type=markup_type,
                auth=auth,
            )
            await self._invalidate("issue_get_comments", issue_id, auth=auth)
            return result

        async def issue_delete_comment(
            self,
            issue_id: str,
            comment_id: int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            await self._original.issue_delete_comment(issue_id, comment_id, auth=auth)
            await self._invalidate("issue_get_comments", issue_id, auth=auth)

        @cached(**cache_config)
        async def issues_find(
            self,
            query: str | None = None,
            *,
            filter: dict[str, Any] | None = None,
            order: list[str] | None = None,
            keys: list[str] | None = None,
            per_page: int = 15,
            page: int = 1,
            auth: YandexAuth | None = None,
        ) -> IssueSearchPage:
            return await self._original.issues_find(
                query=query,
                filter=filter,
                order=order,
                keys=keys,
                per_page=per_page,
                page=page,
                auth=auth,
            )

        @cached(**cache_config)
        async def issue_get_worklogs(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[Worklog]:
            return await self._original.issue_get_worklogs(issue_id, auth=auth)

        async def issue_add_worklog(
            self,
            issue_id: str,
            *,
            duration: str,
            comment: str | None = None,
            start: datetime.datetime | None = None,
            auth: YandexAuth | None = None,
        ) -> Worklog:
            result = await self._original.issue_add_worklog(
                issue_id,
                duration=duration,
                comment=comment,
                start=start,
                auth=auth,
            )
            await self._invalidate("issue_get_worklogs", issue_id, auth=auth)
            return result

        async def issue_update_worklog(
            self,
            issue_id: str,
            worklog_id: int,
            *,
            duration: str | None = None,
            comment: str | None = None,
            start: datetime.datetime | None = None,
            auth: YandexAuth | None = None,
        ) -> Worklog:
            result = await self._original.issue_update_worklog(
                issue_id,
                worklog_id,
                duration=duration,
                comment=comment,
                start=start,
                auth=auth,
            )
            await self._invalidate("issue_get_worklogs", issue_id, auth=auth)
            return result

        async def issue_delete_worklog(
            self,
            issue_id: str,
            worklog_id: int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            await self._original.issue_delete_worklog(
                issue_id,
                worklog_id,
                auth=auth,
            )
            await self._invalidate("issue_get_worklogs", issue_id, auth=auth)

        @cached(**cache_config)
        async def issue_get_attachments(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[IssueAttachment]:
            return await self._original.issue_get_attachments(issue_id, auth=auth)

        @cached(**cache_config)
        async def issues_count(
            self, query: str, *, auth: YandexAuth | None = None
        ) -> int:
            return await self._original.issues_count(query, auth=auth)

        @cached(**cache_config)
        async def issue_get_checklist(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[ChecklistItem]:
            return await self._original.issue_get_checklist(issue_id, auth=auth)

        async def issue_create(
            self,
            queue: str,
            summary: str,
            *,
            type: int | str | None = None,
            description: str | None = None,
            assignee: str | int | None = None,
            priority: str | None = None,
            parent: str | None = None,
            sprint: list[str] | None = None,
            auth: YandexAuth | None = None,
            **kwargs: dict[str, Any],
        ) -> Issue:
            return await self._original.issue_create(
                queue,
                summary,
                type=type,
                description=description,
                assignee=assignee,
                priority=priority,
                parent=parent,
                sprint=sprint,
                auth=auth,
                **kwargs,
            )

        @cached(**cache_config)
        async def issue_get_transitions(
            self, issue_id: str, *, auth: YandexAuth | None = None
        ) -> list[IssueTransition]:
            return await self._original.issue_get_transitions(issue_id, auth=auth)

        async def issue_execute_transition(
            self,
            issue_id: str,
            transition_id: str,
            *,
            comment: str | None = None,
            fields: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> list[IssueTransition]:
            result = await self._original.issue_execute_transition(
                issue_id,
                transition_id,
                comment=comment,
                fields=fields,
                auth=auth,
            )
            await self._invalidate("issue_get", issue_id, auth=auth)
            await self._invalidate("issue_get_transitions", issue_id, auth=auth)
            return result

        async def issue_close(
            self,
            issue_id: str,
            resolution_id: str,
            *,
            comment: str | None = None,
            fields: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> list[IssueTransition]:
            result = await self._original.issue_close(
                issue_id,
                resolution_id,
                comment=comment,
                fields=fields,
                auth=auth,
            )
            await self._invalidate("issue_get", issue_id, auth=auth)
            await self._invalidate("issue_get_transitions", issue_id, auth=auth)
            return result

        async def issue_update(
            self,
            issue_id: str,
            *,
            summary: str | None = None,
            description: str | None = None,
            markup_type: str | None = None,
            parent: IssueUpdateParent | None = None,
            sprint: list[IssueUpdateSprint] | None = None,
            type: IssueUpdateType | None = None,
            priority: IssueUpdatePriority | None = None,
            followers: list[IssueUpdateFollower] | None = None,
            project: IssueUpdateProject | None = None,
            attachment_ids: list[str] | None = None,
            description_attachment_ids: list[str] | None = None,
            tags: list[str] | None = None,
            version: int | None = None,
            auth: YandexAuth | None = None,
            **kwargs: Any,
        ) -> Issue:
            result = await self._original.issue_update(
                issue_id,
                summary=summary,
                description=description,
                markup_type=markup_type,
                parent=parent,
                sprint=sprint,
                type=type,
                priority=priority,
                followers=followers,
                project=project,
                attachment_ids=attachment_ids,
                description_attachment_ids=description_attachment_ids,
                tags=tags,
                version=version,
                auth=auth,
                **kwargs,
            )
            await self._invalidate("issue_get", issue_id, auth=auth)
            await self._invalidate("issue_get_transitions", issue_id, auth=auth)
            return result

        async def issue_add_link(
            self,
            issue_id: str,
            *,
            relationship: str,
            target_issue: str,
            auth: YandexAuth | None = None,
        ) -> IssueLink:
            result = await self._original.issue_add_link(
                issue_id,
                relationship=relationship,
                target_issue=target_issue,
                auth=auth,
            )
            # A link is visible from both ends.
            await self._invalidate("issues_get_links", issue_id, auth=auth)
            await self._invalidate("issues_get_links", target_issue, auth=auth)
            return result

        async def issue_delete_link(
            self,
            issue_id: str,
            link_id: int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            await self._original.issue_delete_link(issue_id, link_id, auth=auth)
            await self._invalidate("issues_get_links", issue_id, auth=auth)

        async def issue_add_checklist_item(
            self,
            issue_id: str,
            *,
            text: str,
            checked: bool | None = None,
            assignee: str | int | None = None,
            deadline: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> list[ChecklistItem]:
            result = await self._original.issue_add_checklist_item(
                issue_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                auth=auth,
            )
            await self._invalidate("issue_get_checklist", issue_id, auth=auth)
            return result

        async def issue_update_checklist_item(
            self,
            issue_id: str,
            item_id: str,
            *,
            text: str | None = None,
            checked: bool | None = None,
            assignee: str | int | None = None,
            deadline: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> list[ChecklistItem]:
            result = await self._original.issue_update_checklist_item(
                issue_id,
                item_id,
                text=text,
                checked=checked,
                assignee=assignee,
                deadline=deadline,
                auth=auth,
            )
            await self._invalidate("issue_get_checklist", issue_id, auth=auth)
            return result

        async def issue_delete_checklist_item(
            self,
            issue_id: str,
            item_id: str,
            *,
            auth: YandexAuth | None = None,
        ) -> list[ChecklistItem] | None:
            result = await self._original.issue_delete_checklist_item(
                issue_id, item_id, auth=auth
            )
            await self._invalidate("issue_get_checklist", issue_id, auth=auth)
            return result

        async def issue_clear_checklist(
            self,
            issue_id: str,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            await self._original.issue_clear_checklist(issue_id, auth=auth)
            await self._invalidate("issue_get_checklist", issue_id, auth=auth)

        async def issue_upload_attachment(
            self,
            issue_id: str,
            *,
            file_path: str | None = None,
            content_base64: str | None = None,
            filename: str | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueAttachment:
            result = await self._original.issue_upload_attachment(
                issue_id,
                file_path=file_path,
                content_base64=content_base64,
                filename=filename,
                auth=auth,
            )
            await self._invalidate("issue_get_attachments", issue_id, auth=auth)
            return result

        async def issue_delete_attachment(
            self,
            issue_id: str,
            attachment_id: str,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            await self._original.issue_delete_attachment(
                issue_id, attachment_id, auth=auth
            )
            await self._invalidate("issue_get_attachments", issue_id, auth=auth)

        async def issue_download_attachment(
            self,
            issue_id: str,
            attachment_id: str,
            filename: str,
            *,
            dest_path: str | None = None,
            return_base64: bool = False,
            auth: YandexAuth | None = None,
        ) -> dict[str, str]:
            return await self._original.issue_download_attachment(
                issue_id,
                attachment_id,
                filename,
                dest_path=dest_path,
                return_base64=return_base64,
                auth=auth,
            )

        async def issue_add_tags(
            self,
            issue_id: str,
            tags: list[str],
            *,
            auth: YandexAuth | None = None,
        ) -> Issue:
            result = await self._original.issue_add_tags(issue_id, tags, auth=auth)
            await self._invalidate("issue_get", issue_id, auth=auth)
            return result

        async def issue_remove_tags(
            self,
            issue_id: str,
            tags: list[str],
            *,
            auth: YandexAuth | None = None,
        ) -> Issue:
            result = await self._original.issue_remove_tags(issue_id, tags, auth=auth)
            await self._invalidate("issue_get", issue_id, auth=auth)
            return result

        async def issue_move_to_queue(
            self,
            issue_id: str,
            queue: str,
            *,
            move_all_fields: bool | None = None,
            initial_status: bool | None = None,
            expand: list[str] | None = None,
            notify: bool | None = None,
            notify_author: bool | None = None,
            extra: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> Issue:
            result = await self._original.issue_move_to_queue(
                issue_id,
                queue,
                move_all_fields=move_all_fields,
                initial_status=initial_status,
                expand=expand,
                notify=notify,
                notify_author=notify_author,
                extra=extra,
                auth=auth,
            )
            await self._invalidate("issue_get", issue_id, auth=auth)
            await self._invalidate("issue_get_transitions", issue_id, auth=auth)
            return result

    class CachingGlobalDataProtocol(GlobalDataProtocolWrap):
        @cached(**cache_config)
        async def get_global_fields(
            self, *, auth: YandexAuth | None = None
        ) -> list[GlobalField]:
            return await self._original.get_global_fields(auth=auth)

        @cached(**cache_config)
        async def get_statuses(self, *, auth: YandexAuth | None = None) -> list[Status]:
            return await self._original.get_statuses(auth=auth)

        @cached(**cache_config)
        async def get_issue_types(
            self, *, auth: YandexAuth | None = None
        ) -> list[IssueType]:
            return await self._original.get_issue_types(auth=auth)

        @cached(**cache_config)
        async def get_priorities(
            self, *, auth: YandexAuth | None = None
        ) -> list[Priority]:
            return await self._original.get_priorities(auth=auth)

        @cached(**cache_config)
        async def get_resolutions(
            self, *, auth: YandexAuth | None = None
        ) -> list[Resolution]:
            return await self._original.get_resolutions(auth=auth)

    class CachingUsersProtocol(UsersProtocolWrap):
        @cached(**cache_config)
        async def users_list(
            self, per_page: int = 50, page: int = 1, *, auth: YandexAuth | None = None
        ) -> list[User]:
            return await self._original.users_list(
                per_page=per_page, page=page, auth=auth
            )

        @cached(**cache_config)
        async def user_get(
            self, user_id: str, *, auth: YandexAuth | None = None
        ) -> User | None:
            return await self._original.user_get(user_id, auth=auth)

        @cached(**cache_config)
        async def user_get_current(self, *, auth: YandexAuth | None = None) -> User:
            return await self._original.user_get_current(auth=auth)

    class CachingBoardsProtocol(BoardsProtocolWrap):
        @cached(**cache_config)
        async def boards_list(self, *, auth: YandexAuth | None = None) -> list[Board]:
            return await self._original.boards_list(auth=auth)

        @cached(**cache_config)
        async def board_get(
            self, board_id: int, *, auth: YandexAuth | None = None
        ) -> Board:
            return await self._original.board_get(board_id, auth=auth)

        @cached(**cache_config)
        async def board_get_columns(
            self, board_id: int, *, auth: YandexAuth | None = None
        ) -> list[BoardColumn]:
            return await self._original.board_get_columns(board_id, auth=auth)

        @cached(**cache_config)
        async def board_get_sprints(
            self, board_id: int, *, auth: YandexAuth | None = None
        ) -> list[Sprint]:
            return await self._original.board_get_sprints(board_id, auth=auth)

        @cached(**cache_config)
        async def sprint_get(
            self, sprint_id: str, *, auth: YandexAuth | None = None
        ) -> Sprint:
            return await self._original.sprint_get(sprint_id, auth=auth)

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
        ) -> Board:
            return await self._original.board_create(
                name=name,
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

        async def board_update(
            self,
            board_id: int,
            *,
            fields: dict[str, Any],
            auth: YandexAuth | None = None,
        ) -> Board:
            return await self._original.board_update(board_id, fields=fields, auth=auth)

        async def board_delete(
            self, board_id: int, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.board_delete(board_id, auth=auth)

        async def board_column_create(
            self,
            board_id: int,
            *,
            name: str,
            statuses: list[str],
            version: str | int | None = None,
            auth: YandexAuth | None = None,
        ) -> BoardColumn:
            return await self._original.board_column_create(
                board_id,
                name=name,
                statuses=statuses,
                version=version,
                auth=auth,
            )

        async def board_column_update(
            self,
            board_id: int,
            column_id: int,
            *,
            name: str | None = None,
            statuses: list[str] | None = None,
            version: str | int | None = None,
            auth: YandexAuth | None = None,
        ) -> BoardColumn:
            return await self._original.board_column_update(
                board_id,
                column_id,
                name=name,
                statuses=statuses,
                version=version,
                auth=auth,
            )

        async def board_column_delete(
            self,
            board_id: int,
            column_id: int,
            *,
            version: str | int | None = None,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.board_column_delete(
                board_id, column_id, version=version, auth=auth
            )

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
        ) -> Sprint:
            return await self._original.sprint_create(
                board_id,
                name=name,
                start_date=start_date,
                end_date=end_date,
                start_date_time=start_date_time,
                end_date_time=end_date_time,
                extra=extra,
                auth=auth,
            )

        async def sprint_update(
            self,
            sprint_id: str | int,
            *,
            fields: dict[str, Any],
            auth: YandexAuth | None = None,
        ) -> Sprint:
            return await self._original.sprint_update(
                sprint_id, fields=fields, auth=auth
            )

        async def sprint_delete(
            self,
            sprint_id: str | int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.sprint_delete(sprint_id, auth=auth)

        async def sprint_start(
            self,
            sprint_id: str | int,
            *,
            auth: YandexAuth | None = None,
        ) -> Sprint:
            return await self._original.sprint_start(sprint_id, auth=auth)

        async def sprint_finish(
            self,
            sprint_id: str | int,
            *,
            auth: YandexAuth | None = None,
        ) -> Sprint:
            return await self._original.sprint_finish(sprint_id, auth=auth)

    class CachingFiltersProtocol(FiltersProtocolWrap):
        @cached(**cache_config)
        async def filters_list(
            self, *, auth: YandexAuth | None = None
        ) -> list[IssueFilter]:
            return await self._original.filters_list(auth=auth)

        @cached(**cache_config)
        async def filter_get(
            self, filter_id: str, *, auth: YandexAuth | None = None
        ) -> IssueFilter:
            return await self._original.filter_get(filter_id, auth=auth)

        async def filter_create(
            self,
            *,
            name: str,
            query: str,
            owner: str | dict[str, Any] | None = None,
            extra: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> IssueFilter:
            return await self._original.filter_create(
                name=name, query=query, owner=owner, extra=extra, auth=auth
            )

        async def filter_update(
            self,
            filter_id: str,
            *,
            fields: dict[str, Any],
            auth: YandexAuth | None = None,
        ) -> IssueFilter:
            return await self._original.filter_update(
                filter_id, fields=fields, auth=auth
            )

        async def filter_delete(
            self, filter_id: str, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.filter_delete(filter_id, auth=auth)

    class CachingComponentsProtocol(ComponentsProtocolWrap):
        @cached(**cache_config)
        async def components_list(
            self,
            *,
            per_page: int = 50,
            page: int = 1,
            auth: YandexAuth | None = None,
        ) -> list[Component]:
            return await self._original.components_list(
                per_page=per_page, page=page, auth=auth
            )

        @cached(**cache_config)
        async def component_get(
            self, component_id: str | int, *, auth: YandexAuth | None = None
        ) -> Component:
            return await self._original.component_get(component_id, auth=auth)

        async def component_create(
            self,
            *,
            name: str,
            queue: str,
            description: str | None = None,
            lead: str | None = None,
            assign_auto: bool | None = None,
            extra: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> Component:
            return await self._original.component_create(
                name=name,
                queue=queue,
                description=description,
                lead=lead,
                assign_auto=assign_auto,
                extra=extra,
                auth=auth,
            )

        async def component_update(
            self,
            component_id: str | int,
            *,
            fields: dict[str, Any],
            version: str | int | None = None,
            auth: YandexAuth | None = None,
        ) -> Component:
            return await self._original.component_update(
                component_id, fields=fields, version=version, auth=auth
            )

        async def component_delete(
            self,
            component_id: str | int,
            *,
            version: str | int | None = None,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.component_delete(
                component_id, version=version, auth=auth
            )

    class CachingEntitiesProtocol(EntitiesProtocolWrap):
        @cached(**cache_config)
        async def entities_search(
            self,
            entity_type: str,
            *,
            filter: dict[str, Any] | None = None,
            order: list[str] | None = None,
            per_page: int = 50,
            page: int = 1,
            fields: list[str] | None = None,
            root_only: bool | None = None,
            expand: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> list[dict[str, Any]]:
            return await self._original.entities_search(
                entity_type,
                filter=filter,
                order=order,
                per_page=per_page,
                page=page,
                fields=fields,
                root_only=root_only,
                expand=expand,
                auth=auth,
            )

        @cached(**cache_config)
        async def entity_get(
            self,
            entity_type: str,
            entity_id: str,
            *,
            fields: list[str] | None = None,
            expand: list[str] | None = None,
            auth: YandexAuth | None = None,
        ) -> dict[str, Any]:
            return await self._original.entity_get(
                entity_type, entity_id, fields=fields, expand=expand, auth=auth
            )

        async def entity_create(
            self,
            entity_type: str,
            *,
            fields: dict[str, Any],
            auth: YandexAuth | None = None,
        ) -> dict[str, Any]:
            return await self._original.entity_create(
                entity_type, fields=fields, auth=auth
            )

        async def entity_update(
            self,
            entity_type: str,
            entity_id: str,
            *,
            fields: dict[str, Any],
            auth: YandexAuth | None = None,
        ) -> dict[str, Any]:
            return await self._original.entity_update(
                entity_type, entity_id, fields=fields, auth=auth
            )

        async def entity_delete(
            self,
            entity_type: str,
            entity_id: str,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.entity_delete(entity_type, entity_id, auth=auth)

        @cached(**cache_config)
        async def projects_search(
            self,
            *,
            filter: dict[str, Any] | None = None,
            order: list[str] | None = None,
            per_page: int = 50,
            page: int = 1,
            auth: YandexAuth | None = None,
        ) -> list[Project]:
            return await self._original.projects_search(
                filter=filter,
                order=order,
                per_page=per_page,
                page=page,
                auth=auth,
            )

        @cached(**cache_config)
        async def portfolios_search(
            self,
            *,
            filter: dict[str, Any] | None = None,
            order: list[str] | None = None,
            per_page: int = 50,
            page: int = 1,
            auth: YandexAuth | None = None,
        ) -> list[Portfolio]:
            return await self._original.portfolios_search(
                filter=filter,
                order=order,
                per_page=per_page,
                page=page,
                auth=auth,
            )

        @cached(**cache_config)
        async def goals_search(
            self,
            *,
            filter: dict[str, Any] | None = None,
            order: list[str] | None = None,
            per_page: int = 50,
            page: int = 1,
            auth: YandexAuth | None = None,
        ) -> list[Goal]:
            return await self._original.goals_search(
                filter=filter,
                order=order,
                per_page=per_page,
                page=page,
                auth=auth,
            )

        @cached(**cache_config)
        async def projects_legacy_list(
            self,
            *,
            per_page: int = 50,
            page: int = 1,
            auth: YandexAuth | None = None,
        ) -> list[ProjectLegacy]:
            return await self._original.projects_legacy_list(
                per_page=per_page, page=page, auth=auth
            )

    class CachingDashboardsProtocol(DashboardsProtocolWrap):
        @cached(**cache_config)
        async def dashboards_list(
            self,
            *,
            per_page: int = 50,
            page: int = 1,
            auth: YandexAuth | None = None,
        ) -> list[Dashboard]:
            return await self._original.dashboards_list(
                per_page=per_page, page=page, auth=auth
            )

        @cached(**cache_config)
        async def dashboard_get(
            self, dashboard_id: str, *, auth: YandexAuth | None = None
        ) -> Dashboard:
            return await self._original.dashboard_get(dashboard_id, auth=auth)

        @cached(**cache_config)
        async def dashboard_get_widgets(
            self, dashboard_id: str, *, auth: YandexAuth | None = None
        ) -> list[DashboardWidget]:
            return await self._original.dashboard_get_widgets(dashboard_id, auth=auth)

        async def dashboard_create(
            self,
            *,
            name: str,
            fields: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> Dashboard:
            return await self._original.dashboard_create(
                name=name, fields=fields, auth=auth
            )

        async def dashboard_update(
            self,
            dashboard_id: str,
            *,
            fields: dict[str, Any],
            version: str | int | None = None,
            auth: YandexAuth | None = None,
        ) -> Dashboard:
            return await self._original.dashboard_update(
                dashboard_id, fields=fields, version=version, auth=auth
            )

        async def dashboard_delete(
            self, dashboard_id: str, *, auth: YandexAuth | None = None
        ) -> None:
            return await self._original.dashboard_delete(dashboard_id, auth=auth)

    class CachingAutomationsProtocol(AutomationsProtocolWrap):
        @cached(**cache_config)
        async def triggers_list(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[Trigger]:
            return await self._original.triggers_list(queue_id, auth=auth)

        @cached(**cache_config)
        async def trigger_get(
            self,
            queue_id: str,
            trigger_id: str | int,
            *,
            auth: YandexAuth | None = None,
        ) -> Trigger:
            return await self._original.trigger_get(queue_id, trigger_id, auth=auth)

        async def trigger_create(
            self,
            queue_id: str,
            *,
            name: str,
            actions: list[dict[str, Any]],
            conditions: list[dict[str, Any]] | None = None,
            active: bool | None = None,
            extra: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> Trigger:
            return await self._original.trigger_create(
                queue_id,
                name=name,
                actions=actions,
                conditions=conditions,
                active=active,
                extra=extra,
                auth=auth,
            )

        async def trigger_update(
            self,
            queue_id: str,
            trigger_id: str | int,
            *,
            fields: dict[str, Any],
            auth: YandexAuth | None = None,
        ) -> Trigger:
            return await self._original.trigger_update(
                queue_id, trigger_id, fields=fields, auth=auth
            )

        async def trigger_delete(
            self,
            queue_id: str,
            trigger_id: str | int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.trigger_delete(queue_id, trigger_id, auth=auth)

        @cached(**cache_config)
        async def autoactions_list(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[Autoaction]:
            return await self._original.autoactions_list(queue_id, auth=auth)

        @cached(**cache_config)
        async def autoaction_get(
            self,
            queue_id: str,
            action_id: str | int,
            *,
            auth: YandexAuth | None = None,
        ) -> Autoaction:
            return await self._original.autoaction_get(queue_id, action_id, auth=auth)

        async def autoaction_create(
            self,
            queue_id: str,
            *,
            name: str,
            filter: dict[str, Any],
            actions: list[dict[str, Any]],
            cron_expression: str | None = None,
            active: bool | None = None,
            extra: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> Autoaction:
            return await self._original.autoaction_create(
                queue_id,
                name=name,
                filter=filter,
                actions=actions,
                cron_expression=cron_expression,
                active=active,
                extra=extra,
                auth=auth,
            )

        async def autoaction_update(
            self,
            queue_id: str,
            action_id: str | int,
            *,
            fields: dict[str, Any],
            auth: YandexAuth | None = None,
        ) -> Autoaction:
            return await self._original.autoaction_update(
                queue_id, action_id, fields=fields, auth=auth
            )

        async def autoaction_delete(
            self,
            queue_id: str,
            action_id: str | int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.autoaction_delete(
                queue_id, action_id, auth=auth
            )

        @cached(**cache_config)
        async def macros_list(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> list[Macro]:
            return await self._original.macros_list(queue_id, auth=auth)

        @cached(**cache_config)
        async def macro_get(
            self,
            queue_id: str,
            macro_id: str | int,
            *,
            auth: YandexAuth | None = None,
        ) -> Macro:
            return await self._original.macro_get(queue_id, macro_id, auth=auth)

        async def macro_create(
            self,
            queue_id: str,
            *,
            name: str,
            body: str | None = None,
            field_changes: list[dict[str, Any]] | None = None,
            extra: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> Macro:
            return await self._original.macro_create(
                queue_id,
                name=name,
                body=body,
                field_changes=field_changes,
                extra=extra,
                auth=auth,
            )

        async def macro_update(
            self,
            queue_id: str,
            macro_id: str | int,
            *,
            fields: dict[str, Any],
            auth: YandexAuth | None = None,
        ) -> Macro:
            return await self._original.macro_update(
                queue_id, macro_id, fields=fields, auth=auth
            )

        async def macro_delete(
            self,
            queue_id: str,
            macro_id: str | int,
            *,
            auth: YandexAuth | None = None,
        ) -> None:
            return await self._original.macro_delete(queue_id, macro_id, auth=auth)

        @cached(**cache_config)
        async def workflows_list(
            self, *, auth: YandexAuth | None = None
        ) -> list[Workflow]:
            return await self._original.workflows_list(auth=auth)

        @cached(**cache_config)
        async def queue_workflow_get(
            self, queue_id: str, *, auth: YandexAuth | None = None
        ) -> Workflow | None:
            return await self._original.queue_workflow_get(queue_id, auth=auth)

    class CachingBulkChangeProtocol(BulkChangeProtocolWrap):
        async def bulk_update(
            self,
            *,
            issues: list[str],
            values: dict[str, Any],
            comment: str | None = None,
            notify: bool | None = None,
            auth: YandexAuth | None = None,
        ) -> BulkChangeResult:
            return await self._original.bulk_update(
                issues=issues,
                values=values,
                comment=comment,
                notify=notify,
                auth=auth,
            )

        async def bulk_move(
            self,
            *,
            issues: list[str],
            queue: str,
            move_all_fields: bool | None = None,
            initial_status: bool | None = None,
            notify: bool | None = None,
            extra: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> BulkChangeResult:
            return await self._original.bulk_move(
                issues=issues,
                queue=queue,
                move_all_fields=move_all_fields,
                initial_status=initial_status,
                notify=notify,
                extra=extra,
                auth=auth,
            )

        async def bulk_transition(
            self,
            *,
            issues: list[str],
            transition: str,
            comment: str | None = None,
            resolution: str | None = None,
            fields: dict[str, Any] | None = None,
            auth: YandexAuth | None = None,
        ) -> BulkChangeResult:
            return await self._original.bulk_transition(
                issues=issues,
                transition=transition,
                comment=comment,
                resolution=resolution,
                fields=fields,
                auth=auth,
            )

        async def bulk_status_get(
            self, operation_id: str, *, auth: YandexAuth | None = None
        ) -> BulkChangeResult:
            return await self._original.bulk_status_get(operation_id, auth=auth)

    return CacheCollection(
        queues=CachingQueuesProtocol,
        issues=CachingIssuesProtocol,
        global_data=CachingGlobalDataProtocol,
        users=CachingUsersProtocol,
        boards=CachingBoardsProtocol,
        filters=CachingFiltersProtocol,
        components=CachingComponentsProtocol,
        entities=CachingEntitiesProtocol,
        dashboards=CachingDashboardsProtocol,
        automations=CachingAutomationsProtocol,
        bulkchange=CachingBulkChangeProtocol,
    )
