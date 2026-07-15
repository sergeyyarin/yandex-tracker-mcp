import asyncio
import datetime
import json
import logging
import os
import random
import time
from asyncio import CancelledError
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import jwt
import yandexcloud
from aiohttp import (
    ClientOSError,
    ClientPayloadError,
    ClientSession,
    ClientTimeout,
    FormData,
    ServerDisconnectedError,
    TraceConfig,
)
from pydantic import BaseModel, RootModel
from yandex.cloud.iam.v1.iam_token_service_pb2 import CreateIamTokenRequest
from yandex.cloud.iam.v1.iam_token_service_pb2_grpc import IamTokenServiceStub

from mcp_tracker.tracker.custom.errors import IssueNotFound, TrackerAPIError
from mcp_tracker.tracker.proto.boards import BoardsProtocol
from mcp_tracker.tracker.proto.common import YandexAuth
from mcp_tracker.tracker.proto.extras import (
    AutomationsProtocol,
    BulkChangeProtocol,
    ComponentsProtocol,
    DashboardsProtocol,
    EntitiesProtocol,
    FiltersProtocol,
)
from mcp_tracker.tracker.proto.fields import GlobalDataProtocol
from mcp_tracker.tracker.proto.issues import IssueProtocol
from mcp_tracker.tracker.proto.queues import QueuesProtocol
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
from mcp_tracker.tracker.proto.users import UsersProtocol

QueueList = RootModel[list[Queue]]
LocalFieldList = RootModel[list[LocalField]]
QueueTagList = RootModel[list[str]]
VersionList = RootModel[list[QueueVersion]]
IssueLinkList = RootModel[list[IssueLink]]
IssueList = RootModel[list[Issue]]
IssueCommentList = RootModel[list[IssueComment]]
WorklogList = RootModel[list[Worklog]]
IssueAttachmentList = RootModel[list[IssueAttachment]]
ChecklistItemList = RootModel[list[ChecklistItem]]
GlobalFieldList = RootModel[list[GlobalField]]
StatusList = RootModel[list[Status]]
IssueTypeList = RootModel[list[IssueType]]
PriorityList = RootModel[list[Priority]]
ResolutionList = RootModel[list[Resolution]]
UserList = RootModel[list[User]]
IssueTransitionList = RootModel[list[IssueTransition]]
BoardList = RootModel[list[Board]]
BoardColumnList = RootModel[list[BoardColumn]]
SprintList = RootModel[list[Sprint]]
FilterList = RootModel[list[IssueFilter]]
ComponentList = RootModel[list[Component]]
ProjectLegacyList = RootModel[list[ProjectLegacy]]
DashboardList = RootModel[list[Dashboard]]
DashboardWidgetList = RootModel[list[DashboardWidget]]
TriggerList = RootModel[list[Trigger]]
AutoactionList = RootModel[list[Autoaction]]
MacroList = RootModel[list[Macro]]
WorkflowList = RootModel[list[Workflow]]
EntityList = RootModel[list[dict[str, Any]]]


async def _raise_tracker_error(response: Any) -> None:
    """Read response body, parse Tracker-specific error fields, raise TrackerAPIError.

    The Yandex Tracker API usually returns `{"errorMessages": [...], "errors": {...}}`
    on 4xx responses. This helper surfaces those in the raised exception so callers
    can see the actual cause instead of a bare status code.
    """
    try:
        body = await response.text()
    except Exception:
        body = ""

    error_messages: list[str] | None = None
    errors: dict[str, Any] | None = None
    if body:
        try:
            import json as _json

            data = _json.loads(body)
            if isinstance(data, dict):
                raw_msgs = data.get("errorMessages")
                if isinstance(raw_msgs, list):
                    error_messages = [str(m) for m in raw_msgs]
                raw_err = data.get("errors")
                if isinstance(raw_err, dict):
                    errors = {str(k): v for k, v in raw_err.items()}
        except Exception:
            pass

    raise TrackerAPIError(
        status=response.status,
        url=str(response.url),
        error_messages=error_messages,
        errors=errors,
        raw_body=body,
    )


# Maps snake_case / friendly field names to YQL Sort By keys.
_SORT_FIELD_YQL: dict[str, str] = {
    "updated_at": "Updated",
    "updated": "Updated",
    "created_at": "Created",
    "created": "Created",
    "key": "Key",
    "summary": "Summary",
    "status": "Status",
    "assignee": "Assignee",
    "priority": "Priority",
    "type": "Type",
    "deadline": "Deadline",
    "start": "Start",
    "story_points": "StoryPoints",
    "storypoints": "StoryPoints",
    "resolution": "Resolution",
}


def _order_to_yql_sort_by(order: list[str]) -> str:
    """Convert ``['-updated_at', '+priority']`` -> ``'"Sort By": Updated DESC, Priority ASC'``.

    Prefix '-' → DESC, '+' or none → ASC. Unknown keys are passed as-is
    (title-cased). Returns empty string on empty input.
    """
    parts: list[str] = []
    for item in order:
        if not item:
            continue
        direction = "ASC"
        name = item
        if name.startswith("-"):
            direction = "DESC"
            name = name[1:]
        elif name.startswith("+"):
            name = name[1:]
        mapped = _SORT_FIELD_YQL.get(name.lower()) or "".join(
            part.capitalize() for part in name.replace("-", "_").split("_")
        )
        parts.append(f"{mapped} {direction}")
    if not parts:
        return ""
    return '"Sort By": ' + ", ".join(parts)


logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("mcp_tracker.audit")


class ServiceAccountSettings(BaseModel):
    key_id: str
    service_account_id: str
    private_key: str

    def to_yandexcloud_dict(self) -> dict[str, str]:
        return {
            "id": self.key_id,
            "service_account_id": self.service_account_id,
            "private_key": self.private_key,
        }


class IAMTokenInfo(BaseModel):
    token: str


class ServiceAccountStore:
    DEFAULT_REFRESH_INTERVAL: float = 3500.0
    DEFAULT_RETRY_INTERVAL: float = 10.0

    def __init__(
        self,
        settings: ServiceAccountSettings,
        *,
        refresh_interval: float | None = None,
        retry_interval: float | None = None,
    ):
        self._settings = settings
        self._refresh_interval = refresh_interval or self.DEFAULT_REFRESH_INTERVAL
        self._retry_interval = retry_interval or self.DEFAULT_RETRY_INTERVAL

        self._yc_sdk = yandexcloud.SDK(
            service_account_key=self._settings.to_yandexcloud_dict()
        )
        self._iam_service = self._yc_sdk.client(IamTokenServiceStub)
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._iam_token: IAMTokenInfo | None = None
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task[None] | None = None

    async def prepare(self):
        self._refresh_task = asyncio.create_task(self._refresher())

    async def close(self):
        try:
            if self._refresh_task is not None:
                self._refresh_task.cancel()
                await self._refresh_task
                self._refresh_task = None
        except CancelledError:
            return
        except Exception as e:  # pragma: no cover
            logger.error("error while closing ServiceAccountStore: %s", e)

    async def get_iam_token(self, *, force_refresh: bool = False) -> str:
        if force_refresh or self._iam_token is None:
            async with self._lock:
                if not force_refresh and self._iam_token is not None:
                    return self._iam_token.token

                iam_token = await asyncio.get_running_loop().run_in_executor(
                    self._executor, self._fetch_iam_token, self._settings
                )

                self._iam_token = iam_token
                logger.info("Successfully fetched new IAM token.")

        return self._iam_token.token

    async def _refresher(self):
        while True:
            try:
                await self.get_iam_token(force_refresh=True)
                interval = self._refresh_interval
            except asyncio.CancelledError:  # pragma: no cover
                return
            except Exception as e:
                logger.error("Error refreshing IAM token: %s", e)
                interval = self._retry_interval

            jitter = random.random() * min(interval * 0.1, 100)
            await asyncio.sleep(interval + jitter)

    def _fetch_iam_token(self, service_account: ServiceAccountSettings) -> IAMTokenInfo:
        now = int(time.time())
        payload = {
            "aud": "https://iam.api.cloud.yandex.net/iam/v1/tokens",
            "iss": service_account.service_account_id,
            "iat": now,
            "exp": now + 3600,
        }

        jwt_token = jwt.encode(
            payload=payload,
            key=service_account.private_key,
            algorithm="PS256",
            headers={"kid": service_account.key_id},
        )

        iam_token = self._iam_service.Create(CreateIamTokenRequest(jwt=jwt_token))
        return IAMTokenInfo(token=iam_token.iam_token)


class TrackerClient(
    QueuesProtocol,
    IssueProtocol,
    GlobalDataProtocol,
    UsersProtocol,
    BoardsProtocol,
    FiltersProtocol,
    ComponentsProtocol,
    EntitiesProtocol,
    DashboardsProtocol,
    AutomationsProtocol,
    BulkChangeProtocol,
):
    # Transient statuses worth retrying on idempotent GETs.
    _RETRY_STATUSES: frozenset[int] = frozenset({429, 502, 503, 504})

    def __init__(
        self,
        *,
        token: str | None,
        iam_token: str | None = None,
        token_type: Literal["Bearer", "OAuth"] | None = None,
        service_account: ServiceAccountSettings | None = None,
        org_id: str | None = None,
        cloud_org_id: str | None = None,
        base_url: str = "https://api.tracker.yandex.net",
        timeout: float = 30,
        get_retries: int = 2,
        audit_log_path: str | None = None,
    ):
        self._token = token
        self._token_type = token_type
        self._static_iam_token = iam_token
        self._service_account_store: ServiceAccountStore | None = (
            ServiceAccountStore(service_account) if service_account else None
        )
        self._org_id = org_id
        self._cloud_org_id = cloud_org_id
        self._get_retries = max(0, get_retries)
        self._audit_log_path = Path(audit_log_path) if audit_log_path else None
        self._audit_lock = asyncio.Lock()

        trace_config = TraceConfig()
        trace_config.on_request_end.append(self._on_request_end)
        trace_config.on_request_exception.append(self._on_request_exception)

        self._session = ClientSession(
            base_url=base_url,
            timeout=ClientTimeout(total=timeout),
            trace_configs=[trace_config],
        )

    async def _emit_write_audit(
        self,
        *,
        method: str,
        url: str,
        status: int | None,
        error: str | None = None,
    ) -> None:
        path = url.split("?", 1)[0]
        if method.upper() in {"GET", "HEAD", "OPTIONS"} or path.endswith(
            ("/_search", "/_count")
        ):
            return
        record = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "method": method.upper(),
            # Deliberately exclude query parameters, headers and bodies: audit
            # metadata must never leak tokens or potentially sensitive task text.
            "path": path,
            "status": status,
            "error": error,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        audit_logger.info("tracker_write %s", line)
        if self._audit_log_path is not None:
            async with self._audit_lock:
                self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
                with self._audit_log_path.open("a", encoding="utf-8") as stream:
                    stream.write(line + "\n")

    async def _on_request_end(self, _session: Any, _context: Any, params: Any) -> None:
        await self._emit_write_audit(
            method=params.method,
            url=str(params.url),
            status=params.response.status,
        )

    async def _on_request_exception(
        self, _session: Any, _context: Any, params: Any
    ) -> None:
        await self._emit_write_audit(
            method=params.method,
            url=str(params.url),
            status=None,
            error=type(params.exception).__name__,
        )

    @asynccontextmanager
    async def _request_idempotent(
        self, method: str, url: str, **kwargs: Any
    ) -> AsyncIterator[Any]:
        """Issue an idempotent request with retries on transient failures.

        Retries cover three failure classes (only safe for idempotent calls —
        all GETs plus POST-based search/count endpoints):
        - connection errors on send: a pooled keep-alive connection that the
          Tracker LB already closed (`ServerDisconnectedError`, `ClientOSError`)
        - truncated reads: `ClientPayloadError` ("Response payload is not
          completed" / TransferEncodingError) — the body is buffered here via
          `response.read()` so the error is caught inside the retry loop;
          callers re-read from the cache
        - retryable statuses 429/502/503/504, honoring `Retry-After`
        """
        attempt = 0
        while True:
            try:
                response = await self._session.request(method, url, **kwargs)
            except (ServerDisconnectedError, ClientOSError, ClientPayloadError):
                if attempt >= self._get_retries:
                    raise
                await asyncio.sleep(min(0.5 * (2**attempt), 10.0))
                attempt += 1
                continue

            if response.status in self._RETRY_STATUSES and attempt < self._get_retries:
                retry_after = response.headers.get("Retry-After", "")
                response.release()
                delay = (
                    float(retry_after) if retry_after.isdigit() else 0.5 * (2**attempt)
                )
                await asyncio.sleep(min(delay, 10.0))
                attempt += 1
                continue

            try:
                # Buffer the body so truncated keep-alive reads surface here,
                # where they can be retried; aiohttp caches it for callers.
                await response.read()
            except ClientPayloadError:
                response.release()
                if attempt >= self._get_retries:
                    raise
                await asyncio.sleep(min(0.5 * (2**attempt), 10.0))
                attempt += 1
                continue

            try:
                yield response
            finally:
                response.release()
            return

    def _get(self, url: str, **kwargs: Any) -> AbstractAsyncContextManager[Any]:
        return self._request_idempotent("GET", url, **kwargs)

    def _post_search(self, url: str, **kwargs: Any) -> AbstractAsyncContextManager[Any]:
        """POST that is semantically a read (search/count) — safe to retry."""
        return self._request_idempotent("POST", url, **kwargs)

    async def prepare(self):
        if self._service_account_store:
            await self._service_account_store.prepare()

    async def close(self):
        if self._service_account_store:
            await self._service_account_store.close()
        await self._session.close()

    async def _build_headers(self, auth: YandexAuth | None = None) -> dict[str, str]:
        # Priority: OAuth from auth > static OAuth > static IAM token > service account
        auth_header = None

        if auth and auth.token:
            token_type = self._token_type or "OAuth"
            auth_header = f"{token_type} {auth.token}"
        elif self._token:
            token_type = self._token_type or "OAuth"
            auth_header = f"{token_type} {self._token}"
        elif self._static_iam_token:
            auth_header = f"Bearer {self._static_iam_token}"
        elif self._service_account_store is not None:
            iam_token = await self._service_account_store.get_iam_token()
            auth_header = f"Bearer {iam_token}"

        if not auth_header:
            raise ValueError(
                "No authentication method provided. "
                "Provide either OAuth token, IAM token, or use OAuth flow."
            )

        headers = {"Authorization": auth_header}

        # Handle org_id logic
        org_id = auth.org_id if auth and auth.org_id else self._org_id
        cloud_org_id = (
            auth.cloud_org_id if auth and auth.cloud_org_id else self._cloud_org_id
        )

        if org_id and cloud_org_id:
            raise ValueError("Only one of org_id or cloud_org_id should be provided.")

        if org_id:
            headers["X-Org-ID"] = org_id
        elif cloud_org_id:
            headers["X-Cloud-Org-ID"] = cloud_org_id
        else:
            raise ValueError("Either org_id or cloud_org_id must be provided.")

        return headers

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
        body: dict[str, Any] = {
            "key": key,
            "name": name,
            "lead": lead,
            "defaultType": default_type,
            "defaultPriority": default_priority,
        }
        if issue_types_config is not None:
            body["issueTypesConfig"] = issue_types_config
        if extra:
            for k, v in extra.items():
                body.setdefault(k, v)

        async with self._session.post(
            "v3/queues",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Queue.model_validate_json(await response.read())

    async def queues_list(
        self, per_page: int = 100, page: int = 1, *, auth: YandexAuth | None = None
    ) -> list[Queue]:
        params = {
            "perPage": per_page,
            "page": page,
        }
        async with self._get(
            "v3/queues", headers=await self._build_headers(auth), params=params
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return QueueList.model_validate_json(await response.read()).root

    async def queues_get_local_fields(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[LocalField]:
        async with self._get(
            f"v3/queues/{queue_id}/localFields", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return LocalFieldList.model_validate_json(await response.read()).root

    async def queues_get_tags(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[str]:
        async with self._get(
            f"v3/queues/{queue_id}/tags", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return QueueTagList.model_validate_json(await response.read()).root

    async def queues_get_versions(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[QueueVersion]:
        async with self._get(
            f"v3/queues/{queue_id}/versions", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return VersionList.model_validate_json(await response.read()).root

    async def queues_get_fields(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[GlobalField]:
        async with self._get(
            f"v3/queues/{queue_id}/fields", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return GlobalFieldList.model_validate_json(await response.read()).root

    async def queue_get(
        self,
        queue_id: str,
        *,
        expand: list[QueueExpandOption] | None = None,
        auth: YandexAuth | None = None,
    ) -> Queue:
        params: dict[str, str] = {}
        if expand:
            params["expand"] = ",".join(expand)

        async with self._get(
            f"v3/queues/{queue_id}",
            headers=await self._build_headers(auth),
            params=params if params else None,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Queue.model_validate_json(await response.read())

    async def get_global_fields(
        self, *, auth: YandexAuth | None = None
    ) -> list[GlobalField]:
        async with self._get(
            "v3/fields", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return GlobalFieldList.model_validate_json(await response.read()).root

    async def get_statuses(self, *, auth: YandexAuth | None = None) -> list[Status]:
        async with self._get(
            "v3/statuses", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return StatusList.model_validate_json(await response.read()).root

    async def get_issue_types(
        self, *, auth: YandexAuth | None = None
    ) -> list[IssueType]:
        async with self._get(
            "v3/issuetypes", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueTypeList.model_validate_json(await response.read()).root

    async def get_priorities(self, *, auth: YandexAuth | None = None) -> list[Priority]:
        async with self._get(
            "v3/priorities", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return PriorityList.model_validate_json(await response.read()).root

    async def get_resolutions(
        self, *, auth: YandexAuth | None = None
    ) -> list[Resolution]:
        async with self._get(
            "v3/resolutions", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return ResolutionList.model_validate_json(await response.read()).root

    async def issue_get(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> Issue:
        async with self._get(
            f"v3/issues/{issue_id}", headers=await self._build_headers(auth)
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Issue.model_validate_json(await response.read())

    async def issues_get_links(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[IssueLink]:
        async with self._get(
            f"v3/issues/{issue_id}/links", headers=await self._build_headers(auth)
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueLinkList.model_validate_json(await response.read()).root

    async def issue_get_comments(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[IssueComment]:
        async with self._get(
            f"v3/issues/{issue_id}/comments", headers=await self._build_headers(auth)
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueCommentList.model_validate_json(await response.read()).root

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
        """Добавить комментарий к задаче."""
        body: dict[str, Any] = {"text": text}
        if summonees is not None:
            body["summonees"] = summonees
        if maillist_summonees is not None:
            body["maillistSummonees"] = maillist_summonees
        if markup_type is not None:
            body["markupType"] = markup_type

        # Параметр опциональный, по умолчанию true на стороне API.
        # Чтобы не менять URL (и поведение по умолчанию), передаём его только при false.
        params = {"isAddToFollowers": "false"} if not is_add_to_followers else None

        async with self._session.post(
            f"v3/issues/{issue_id}/comments",
            headers=await self._build_headers(auth),
            json=body,
            params=params,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueComment.model_validate_json(await response.read())

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
        """Изменить комментарий в задаче."""
        body: dict[str, Any] = {"text": text}
        if summonees is not None:
            body["summonees"] = summonees
        if maillist_summonees is not None:
            body["maillistSummonees"] = maillist_summonees
        if markup_type is not None:
            body["markupType"] = markup_type

        async with self._session.patch(
            f"v3/issues/{issue_id}/comments/{comment_id}",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueComment.model_validate_json(await response.read())

    async def issue_delete_comment(
        self,
        issue_id: str,
        comment_id: int,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        """Удалить комментарий из задачи."""
        async with self._session.delete(
            f"v3/issues/{issue_id}/comments/{comment_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return None

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
        params = {
            "perPage": per_page,
            "page": page,
        }

        body: dict[str, Any] = {}

        # The API forbids combining `queue`/`keys`/`filter`/`query` in one
        # request, so `keys` alongside a query is folded into the YQL instead.
        # Tracker's /v3/issues/_search accepts `order` only together with `filter`.
        # When using raw YQL `query`, sorting is expressed inline as `"Sort By": ...`.
        if query is not None:
            if keys:
                keys_clause = "Key: " + ", ".join(f'"{k}"' for k in keys)
                query = f"{keys_clause} AND ({query})"
            if order:
                sort_by = _order_to_yql_sort_by(order)
                if sort_by and '"Sort By"' not in query:
                    query = f"{query} {sort_by}".strip()
            body["query"] = query
        elif keys is not None:
            body["keys"] = keys
        else:
            if filter is not None:
                body["filter"] = filter
            if order is not None:
                body["order"] = order

        async with self._post_search(
            "v3/issues/_search",
            headers=await self._build_headers(auth),
            json=body,
            params=params,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

            def _int_header(name: str) -> int | None:
                raw = response.headers.get(name, "")
                return int(raw) if raw.isdigit() else None

            return IssueSearchPage(
                issues=IssueList.model_validate_json(await response.read()).root,
                total_count=_int_header("X-Total-Count"),
                total_pages=_int_header("X-Total-Pages"),
            )

    async def issue_get_worklogs(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[Worklog]:
        async with self._get(
            f"v3/issues/{issue_id}/worklog", headers=await self._build_headers(auth)
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return WorklogList.model_validate_json(await response.read()).root

    async def issue_add_worklog(
        self,
        issue_id: str,
        *,
        duration: str,
        comment: str | None = None,
        start: datetime.datetime | None = None,
        auth: YandexAuth | None = None,
    ) -> Worklog:
        """Добавить запись трудозатрат (worklog) к задаче.

        Args:
            issue_id: Ключ задачи (например, "QUEUE-123")
            duration: Длительность в формате ISO 8601 (например, "PT1H30M")
            comment: Комментарий к записи
            start: Время начала работ. Если не задано — подставляется текущее UTC время
                (Tracker API требует обязательный start и возвращает 422 без него).
            auth: Опциональная auth-структура (OAuth/Org) поверх конфигурации клиента
        """
        body: dict[str, Any] = {"duration": duration}
        if comment is not None:
            body["comment"] = comment
        # Tracker requires `start` even though older docs listed it as optional;
        # default to `now()` in UTC so callers don't have to remember to pass it.
        if start is None:
            start = datetime.datetime.now(tz=datetime.timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=datetime.timezone.utc)
        start_utc = start.astimezone(datetime.timezone.utc)
        # Формат "+0000" (без двоеточия) совместим с API Трекера.
        body["start"] = start_utc.strftime("%Y-%m-%dT%H:%M:%S.%f%z")

        async with self._session.post(
            f"v3/issues/{issue_id}/worklog",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Worklog.model_validate_json(await response.read())

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
        """Обновить запись трудозатрат (worklog) в задаче."""
        body: dict[str, Any] = {}
        if duration is not None:
            body["duration"] = duration
        if comment is not None:
            body["comment"] = comment
        if start is not None:
            if start.tzinfo is None:
                start = start.replace(tzinfo=datetime.timezone.utc)
            start_utc = start.astimezone(datetime.timezone.utc)
            body["start"] = start_utc.strftime("%Y-%m-%dT%H:%M:%S.%f%z")

        async with self._session.patch(
            f"v3/issues/{issue_id}/worklog/{worklog_id}",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Worklog.model_validate_json(await response.read())

    async def issue_delete_worklog(
        self,
        issue_id: str,
        worklog_id: int,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        """Удалить запись трудозатрат (worklog) из задачи."""
        async with self._session.delete(
            f"v3/issues/{issue_id}/worklog/{worklog_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return None

    async def issue_get_attachments(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[IssueAttachment]:
        async with self._get(
            f"v3/issues/{issue_id}/attachments", headers=await self._build_headers(auth)
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueAttachmentList.model_validate_json(await response.read()).root

    async def users_list(
        self, per_page: int = 50, page: int = 1, *, auth: YandexAuth | None = None
    ) -> list[User]:
        params: dict[str, str | int] = {
            "perPage": per_page,
            "page": page,
        }
        async with self._get(
            "v3/users", headers=await self._build_headers(auth), params=params
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return UserList.model_validate_json(await response.read()).root

    async def user_get(
        self, user_id: str, *, auth: YandexAuth | None = None
    ) -> User | None:
        async with self._get(
            f"v3/users/{user_id}", headers=await self._build_headers(auth)
        ) as response:
            if response.status == 404:
                return None
            if response.status >= 400:
                await _raise_tracker_error(response)
            return User.model_validate_json(await response.read())

    async def user_get_current(self, *, auth: YandexAuth | None = None) -> User:
        async with self._get(
            "v3/myself", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return User.model_validate_json(await response.read())

    async def issue_get_checklist(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[ChecklistItem]:
        async with self._get(
            f"v3/issues/{issue_id}/checklistItems",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            raw = await response.read()
        # Tracker may return either a bare list of items or an Issue object
        # with the checklist embedded — accept both shapes.
        return self._extract_checklist_from_issue(raw)

    async def issues_count(self, query: str, *, auth: YandexAuth | None = None) -> int:
        body: dict[str, Any] = {
            "query": query,
        }

        async with self._post_search(
            "v3/issues/_count", headers=await self._build_headers(auth), json=body
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return int(await response.text())

    async def issue_create(
        self,
        queue: str,
        summary: str,
        *,
        type: int | str | None = None,
        description: str | None = None,
        assignee: str | int | None = None,
        priority: str | int | None = None,
        parent: str | None = None,
        sprint: list[str] | None = None,
        auth: YandexAuth | None = None,
        **kwargs: dict[str, Any],
    ) -> Issue:
        body: dict[str, Any] = {
            "queue": queue,
            "summary": summary,
        }

        if type is not None:
            body["type"] = type
        if description is not None:
            body["description"] = description
        if assignee is not None:
            body["assignee"] = assignee
        if priority is not None:
            body["priority"] = priority
        if parent is not None:
            body["parent"] = parent
        if sprint is not None:
            body["sprint"] = sprint

        for k, v in kwargs.items():
            if k not in body:
                body[k] = v

        async with self._session.post(
            "v3/issues", headers=await self._build_headers(auth), json=body
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Issue.model_validate_json(await response.read())

    async def issue_get_transitions(
        self, issue_id: str, *, auth: YandexAuth | None = None
    ) -> list[IssueTransition]:
        async with self._get(
            f"v3/issues/{issue_id}/transitions", headers=await self._build_headers(auth)
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueTransitionList.model_validate_json(await response.read()).root

    # Fields that expect `{"key": value}` reference objects in Tracker API;
    # we auto-wrap plain strings to save callers from a frequent 422.
    _REFERENCE_FIELD_KEYS: frozenset[str] = frozenset(
        {
            "resolution",
            "priority",
            "type",
            "status",
            "queue",
            "assignee",
            "project",
            "parent",
            "epic",
        }
    )

    @classmethod
    def _normalize_transition_fields(
        cls, fields: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Wrap bare string values for reference-type fields into ``{"key": value}``."""
        if not fields:
            return {}
        normalized: dict[str, Any] = {}
        for key, value in fields.items():
            if key in cls._REFERENCE_FIELD_KEYS and isinstance(value, str) and value:
                normalized[key] = {"key": value}
            else:
                normalized[key] = value
        return normalized

    async def issue_execute_transition(
        self,
        issue_id: str,
        transition_id: str,
        *,
        comment: str | None = None,
        fields: dict[str, Any] | None = None,
        auth: YandexAuth | None = None,
    ) -> list[IssueTransition]:
        body: dict[str, Any] = {}
        if comment is not None:
            body["comment"] = comment
        if fields is not None:
            body.update(self._normalize_transition_fields(fields))

        async with self._session.post(
            f"v3/issues/{issue_id}/transitions/{transition_id}/_execute",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueTransitionList.model_validate_json(await response.read()).root

    async def issue_close(
        self,
        issue_id: str,
        resolution_id: str,
        *,
        comment: str | None = None,
        fields: dict[str, Any] | None = None,
        auth: YandexAuth | None = None,
    ) -> list[IssueTransition]:
        # Fetch transitions and statuses in parallel
        async with asyncio.TaskGroup() as tg:
            transitions_task = tg.create_task(
                self.issue_get_transitions(issue_id, auth=auth)
            )
            statuses_task = tg.create_task(self.get_statuses(auth=auth))

        transitions = transitions_task.result()
        statuses = statuses_task.result()

        # Build a map of status key -> status type
        status_type_map: dict[str, str | None] = {
            status.key: status.type for status in statuses
        }

        # Find a transition to a status with type="done"
        done_transition: IssueTransition | None = None
        for transition in transitions:
            if transition.to and transition.to.key:
                status_type = status_type_map.get(transition.to.key)
                if status_type == "done":
                    done_transition = transition
                    break

        if done_transition is None:
            raise ValueError(
                f"No transition to a 'done' status found for issue {issue_id}. "
                f"Available transitions: {[t.id for t in transitions]}."
            )

        if fields is None:
            fields = {}

        # Tracker expects reference objects here, not raw strings.
        # issue_execute_transition would wrap it too, but being explicit is cheaper to read.
        fields["resolution"] = {"key": resolution_id}

        return await self.issue_execute_transition(
            issue_id,
            done_transition.id,
            comment=comment,
            fields=fields,
            auth=auth,
        )

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
        body: dict[str, Any] = {}

        if summary is not None:
            body["summary"] = summary
        if description is not None:
            body["description"] = description
        if markup_type is not None:
            body["markupType"] = markup_type
        if parent is not None:
            body["parent"] = parent.model_dump(exclude_none=True)
        if sprint is not None:
            body["sprint"] = [s.model_dump(exclude_none=True) for s in sprint]
        if type is not None:
            body["type"] = type.model_dump(exclude_none=True)
        if priority is not None:
            body["priority"] = priority.model_dump(exclude_none=True)
        if followers is not None:
            body["followers"] = [f.model_dump(exclude_none=True) for f in followers]
        if project is not None:
            body["project"] = project.model_dump(exclude_none=True)
        if attachment_ids is not None:
            body["attachmentIds"] = attachment_ids
        if description_attachment_ids is not None:
            body["descriptionAttachmentIds"] = description_attachment_ids
        if tags is not None:
            body["tags"] = tags

        for k, v in kwargs.items():
            if k not in body:
                body[k] = v

        params: dict[str, int] = {}
        if version is not None:
            params["version"] = version

        async with self._session.patch(
            f"v3/issues/{issue_id}",
            headers=await self._build_headers(auth),
            json=body,
            params=params if params else None,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Issue.model_validate_json(await response.read())

    # --- issue links write ---
    async def issue_add_link(
        self,
        issue_id: str,
        *,
        relationship: str,
        target_issue: str,
        auth: YandexAuth | None = None,
    ) -> IssueLink:
        body = {"relationship": relationship, "issue": target_issue}
        async with self._session.post(
            f"v3/issues/{issue_id}/links",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            data = await response.read()
        try:
            return IssueLink.model_validate_json(data)
        except Exception:
            # Some deployments answer with the full link list; pick the link
            # pointing at the issue we just connected rather than guessing by
            # position (ordering is not guaranteed).
            links = IssueLinkList.model_validate_json(data).root
            if not links:
                raise
            target = target_issue.strip().lower()
            for link in links:
                if link.object and (link.object.key or "").lower() == target:
                    return link
            return links[-1]

    async def issue_delete_link(
        self,
        issue_id: str,
        link_id: int,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        async with self._session.delete(
            f"v3/issues/{issue_id}/links/{link_id}",
            headers=await self._build_headers(auth),
        ) as response:
            # 404 here can mean either a missing issue or a missing link —
            # surface the API error instead of blaming the issue.
            if response.status >= 400:
                await _raise_tracker_error(response)

    # --- checklist write ---
    @staticmethod
    def _extract_checklist_from_issue(raw: bytes) -> list[ChecklistItem]:
        """Parse Tracker's checklist-mutation response.

        Tracker returns the full Issue object with the updated checklist inside
        the `checklistItems` field; older variants may return a bare list.
        """
        import json as _json

        try:
            data = _json.loads(raw)
        except Exception:
            return []
        if isinstance(data, list):
            return [ChecklistItem.model_validate(item) for item in data]
        if isinstance(data, dict):
            items = data.get("checklistItems") or data.get("checklist") or []
            if isinstance(items, list):
                return [ChecklistItem.model_validate(item) for item in items]
        return []

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
        body: dict[str, Any] = {"text": text}
        if checked is not None:
            body["checked"] = checked
        if assignee is not None:
            body["assignee"] = assignee
        if deadline is not None:
            body["deadline"] = deadline

        async with self._session.post(
            f"v3/issues/{issue_id}/checklistItems",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            raw = await response.read()
        return self._extract_checklist_from_issue(raw)

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
        body: dict[str, Any] = {}
        if text is not None:
            body["text"] = text
        if checked is not None:
            body["checked"] = checked
        if assignee is not None:
            body["assignee"] = assignee
        if deadline is not None:
            body["deadline"] = deadline

        async with self._session.patch(
            f"v3/issues/{issue_id}/checklistItems/{item_id}",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            raw = await response.read()
        return self._extract_checklist_from_issue(raw)

    async def issue_delete_checklist_item(
        self,
        issue_id: str,
        item_id: str,
        *,
        auth: YandexAuth | None = None,
    ) -> list[ChecklistItem] | None:
        async with self._session.delete(
            f"v3/issues/{issue_id}/checklistItems/{item_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            raw = await response.read()
        if not raw:
            return None
        return self._extract_checklist_from_issue(raw)

    async def issue_clear_checklist(
        self,
        issue_id: str,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        async with self._session.delete(
            f"v3/issues/{issue_id}/checklistItems",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)

    # --- attachments CRUD ---
    async def issue_upload_attachment(
        self,
        issue_id: str,
        *,
        file_path: str | None = None,
        content_base64: str | None = None,
        filename: str | None = None,
        auth: YandexAuth | None = None,
    ) -> IssueAttachment:
        # Exactly one source must be given — either a server-side path or
        # base64-encoded bytes supplied directly by the caller (useful when
        # the MCP client has no access to the server's filesystem).
        if (file_path is None) == (content_base64 is None):
            raise ValueError(
                "Provide exactly one of `file_path` (server-side file) or "
                "`content_base64` (bytes supplied by the client)."
            )

        if file_path is not None:
            filename = filename or os.path.basename(file_path)
            with open(file_path, "rb") as fh:
                file_bytes = fh.read()
        else:
            if not filename:
                raise ValueError(
                    "`filename` is required when uploading via content_base64."
                )
            import base64 as _base64

            try:
                file_bytes = _base64.b64decode(content_base64 or "", validate=True)
            except Exception as exc:
                raise ValueError(f"content_base64 is not valid base64: {exc}") from exc

        form = FormData()
        form.add_field("file", file_bytes, filename=filename)
        async with self._session.post(
            f"v3/issues/{issue_id}/attachments",
            headers=await self._build_headers(auth),
            data=form,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueAttachment.model_validate_json(await response.read())

    async def issue_delete_attachment(
        self,
        issue_id: str,
        attachment_id: str,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        async with self._session.delete(
            f"v3/issues/{issue_id}/attachments/{attachment_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)

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
        """Download an attachment.

        Pass ``dest_path`` to save to the MCP server's filesystem, or
        ``return_base64=True`` to get the bytes back as base64 (useful when
        the caller has no access to the server's FS). Both can be combined.
        Returns a dict with optional ``path`` and ``content_base64`` keys.
        """
        if dest_path is None and not return_base64:
            raise ValueError(
                "Provide at least one of `dest_path` or `return_base64=True`."
            )

        async with self._get(
            f"v3/issues/{issue_id}/attachments/{attachment_id}/{filename}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            data = await response.read()

        result: dict[str, str] = {}
        if dest_path is not None:
            if os.path.isdir(dest_path):
                dest_path = os.path.join(dest_path, filename)
            with open(dest_path, "wb") as fh:
                fh.write(data)
            result["path"] = dest_path
        if return_base64:
            import base64 as _base64

            result["content_base64"] = _base64.b64encode(data).decode("ascii")
        return result

    # --- misc issue ops ---
    async def issue_add_tags(
        self,
        issue_id: str,
        tags: list[str],
        *,
        auth: YandexAuth | None = None,
    ) -> Issue:
        body = {"tags": {"add": tags}}
        async with self._session.patch(
            f"v3/issues/{issue_id}",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Issue.model_validate_json(await response.read())

    async def issue_remove_tags(
        self,
        issue_id: str,
        tags: list[str],
        *,
        auth: YandexAuth | None = None,
    ) -> Issue:
        body = {"tags": {"remove": tags}}
        async with self._session.patch(
            f"v3/issues/{issue_id}",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Issue.model_validate_json(await response.read())

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
        # The target queue is a query parameter; the JSON body is reserved for
        # issue fields to change during the move (issue-edit format).
        params: dict[str, Any] = {"queue": queue}
        if move_all_fields is not None:
            params["moveAllFields"] = str(move_all_fields).lower()
        if initial_status is not None:
            params["initialStatus"] = str(initial_status).lower()
        if expand:
            params["expand"] = ",".join(expand)
        if notify is not None:
            params["notify"] = str(notify).lower()
        if notify_author is not None:
            params["notifyAuthor"] = str(notify_author).lower()

        async with self._session.post(
            f"v3/issues/{issue_id}/_move",
            headers=await self._build_headers(auth),
            json=extra or {},
            params=params,
        ) as response:
            if response.status == 404:
                raise IssueNotFound(issue_id)
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Issue.model_validate_json(await response.read())

    async def boards_list(self, *, auth: YandexAuth | None = None) -> list[Board]:
        async with self._get(
            "v3/boards", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return BoardList.model_validate_json(await response.read()).root

    async def board_get(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> Board:
        async with self._get(
            f"v3/boards/{board_id}", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Board.model_validate_json(await response.read())

    async def board_get_columns(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> list[BoardColumn]:
        async with self._get(
            f"v3/boards/{board_id}/columns",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return BoardColumnList.model_validate_json(await response.read()).root

    async def board_get_sprints(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> list[Sprint]:
        async with self._get(
            f"v3/boards/{board_id}/sprints",
            headers=await self._build_headers(auth),
        ) as response:
            # Kanban boards (or boards without a sprint setup) respond with 400/404
            # instead of an empty list — treat that as "no sprints" rather than
            # an error, matching what callers typically want.
            if response.status in (400, 404):
                return []
            if response.status >= 400:
                await _raise_tracker_error(response)
            return SprintList.model_validate_json(await response.read()).root

    async def sprint_get(
        self, sprint_id: str, *, auth: YandexAuth | None = None
    ) -> Sprint:
        async with self._get(
            f"v3/sprints/{sprint_id}", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Sprint.model_validate_json(await response.read())

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
        body: dict[str, Any] = {"name": name}
        if owner is not None:
            body["owner"] = owner
        if board_permissions_template is not None:
            body["boardPermissionsTemplate"] = board_permissions_template
        if backlog_available is not None:
            body["backlogAvailable"] = backlog_available
        if sprints_available is not None:
            body["sprintsAvailable"] = sprints_available
        if auto_filters is not None:
            body["autoFilters"] = auto_filters
        elif filter is not None:
            # Compatibility with the old MCP argument. The current Live Boards
            # API represents board selection as autoFilters/liveFilter values.
            field_values: dict[str, list[dict[str, Any]]] = {}
            for key, raw_value in filter.items():
                values = raw_value if isinstance(raw_value, list) else [raw_value]
                field_values[key] = [
                    value if isinstance(value, dict) else {"fixed": value}
                    for value in values
                ]
            body["autoFilters"] = {
                "addFilter": {
                    "liveFilter": {"fieldValues": field_values},
                    "enabled": True,
                }
            }
        if non_parametrized_columns is not None:
            body["nonParametrizedColumns"] = non_parametrized_columns
        if backlog_columns is not None:
            body["backlogColumns"] = backlog_columns
        if columns is not None:
            body["columns"] = columns
        if extra:
            for k, v in extra.items():
                body.setdefault(k, v)

        async with self._session.post(
            "v3/liveBoards/", headers=await self._build_headers(auth), json=body
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Board.model_validate_json(await response.read())

    async def board_update(
        self,
        board_id: int,
        *,
        fields: dict[str, Any],
        auth: YandexAuth | None = None,
    ) -> Board:
        async with self._session.patch(
            f"v3/boards/{board_id}",
            headers=await self._build_headers(auth),
            json=fields,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Board.model_validate_json(await response.read())

    async def board_delete(
        self, board_id: int, *, auth: YandexAuth | None = None
    ) -> None:
        async with self._session.delete(
            f"v3/boards/{board_id}", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

    async def board_column_create(
        self,
        board_id: int,
        *,
        name: str,
        statuses: list[str],
        version: str | int | None = None,
        auth: YandexAuth | None = None,
    ) -> BoardColumn:
        headers = await self._build_headers(auth)
        if version is not None:
            headers["If-Match"] = f'"{version}"'

        async with self._session.post(
            f"v3/boards/{board_id}/columns/",
            headers=headers,
            json={"name": name, "statuses": statuses},
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return BoardColumn.model_validate_json(await response.read())

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
        headers = await self._build_headers(auth)
        if version is not None:
            headers["If-Match"] = f'"{version}"'

        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if statuses is not None:
            body["statuses"] = statuses

        async with self._session.patch(
            f"v3/boards/{board_id}/columns/{column_id}",
            headers=headers,
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return BoardColumn.model_validate_json(await response.read())

    async def board_column_delete(
        self,
        board_id: int,
        column_id: int,
        *,
        version: str | int | None = None,
        auth: YandexAuth | None = None,
    ) -> None:
        headers = await self._build_headers(auth)
        if version is not None:
            headers["If-Match"] = f'"{version}"'

        async with self._session.delete(
            f"v3/boards/{board_id}/columns/{column_id}",
            headers=headers,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

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
        # Yandex Tracker creates sprints via POST /v2/sprints with the target
        # board referenced in the body — not via /v3/boards/<id>/sprints
        # (which is read-only and returns 405 on POST).
        body: dict[str, Any] = {
            "name": name,
            "board": {"id": board_id},
        }
        if start_date is not None:
            body["startDate"] = start_date
        if end_date is not None:
            body["endDate"] = end_date
        if start_date_time is not None:
            body["startDateTime"] = start_date_time
        if end_date_time is not None:
            body["endDateTime"] = end_date_time
        if extra:
            for k, v in extra.items():
                body.setdefault(k, v)

        async with self._session.post(
            "v2/sprints",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Sprint.model_validate_json(await response.read())

    async def sprint_update(
        self,
        sprint_id: str | int,
        *,
        fields: dict[str, Any],
        auth: YandexAuth | None = None,
    ) -> Sprint:
        async with self._session.patch(
            f"v3/sprints/{sprint_id}",
            headers=await self._build_headers(auth),
            json=fields,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Sprint.model_validate_json(await response.read())

    async def sprint_delete(
        self,
        sprint_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        async with self._session.delete(
            f"v3/sprints/{sprint_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

    async def sprint_start(
        self,
        sprint_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> Sprint:
        async with self._session.post(
            f"v3/sprints/{sprint_id}/_start",
            headers=await self._build_headers(auth),
            json={},
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Sprint.model_validate_json(await response.read())

    async def sprint_finish(
        self,
        sprint_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> Sprint:
        async with self._session.post(
            f"v3/sprints/{sprint_id}/_finish",
            headers=await self._build_headers(auth),
            json={},
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Sprint.model_validate_json(await response.read())

    # --- filters ---
    async def filters_list(
        self, *, auth: YandexAuth | None = None
    ) -> list[IssueFilter]:
        # Yandex Tracker searches filters via POST /v3/filters/_search;
        # a bare GET /v3/filters returns 405.
        async with self._post_search(
            "v3/filters/_search",
            headers=await self._build_headers(auth),
            json={},
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            raw = await response.read()

        # API may wrap results in {hits, pages, values} or return a bare list.
        import json as _json

        data = _json.loads(raw)
        if isinstance(data, dict):
            values = data.get("values", [])
            if not isinstance(values, list):
                values = []
            return [IssueFilter.model_validate(v) for v in values]
        if isinstance(data, list):
            return [IssueFilter.model_validate(v) for v in data]
        return []

    async def filter_get(
        self, filter_id: str, *, auth: YandexAuth | None = None
    ) -> IssueFilter:
        async with self._get(
            f"v3/filters/{filter_id}", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueFilter.model_validate_json(await response.read())

    async def filter_create(
        self,
        *,
        name: str,
        query: str,
        owner: str | dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
        auth: YandexAuth | None = None,
    ) -> IssueFilter:
        body: dict[str, Any] = {"name": name, "query": query}
        if owner is not None:
            body["owner"] = owner
        if extra:
            for k, v in extra.items():
                body.setdefault(k, v)
        async with self._session.post(
            "v3/filters",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueFilter.model_validate_json(await response.read())

    async def filter_update(
        self,
        filter_id: str,
        *,
        fields: dict[str, Any],
        auth: YandexAuth | None = None,
    ) -> IssueFilter:
        async with self._session.patch(
            f"v3/filters/{filter_id}",
            headers=await self._build_headers(auth),
            json=fields,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return IssueFilter.model_validate_json(await response.read())

    async def filter_delete(
        self, filter_id: str, *, auth: YandexAuth | None = None
    ) -> None:
        async with self._session.delete(
            f"v3/filters/{filter_id}", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

    # --- components ---
    async def components_list(
        self,
        *,
        per_page: int = 50,
        page: int = 1,
        auth: YandexAuth | None = None,
    ) -> list[Component]:
        params = {"perPage": per_page, "page": page}
        async with self._get(
            "v3/components",
            headers=await self._build_headers(auth),
            params=params,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return ComponentList.model_validate_json(await response.read()).root

    async def component_get(
        self, component_id: str | int, *, auth: YandexAuth | None = None
    ) -> Component:
        async with self._get(
            f"v3/components/{component_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Component.model_validate_json(await response.read())

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
        body: dict[str, Any] = {"name": name, "queue": queue}
        if description is not None:
            body["description"] = description
        if lead is not None:
            body["lead"] = lead
        if assign_auto is not None:
            body["assignAuto"] = assign_auto
        if extra:
            for k, v in extra.items():
                body.setdefault(k, v)
        async with self._session.post(
            "v3/components",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Component.model_validate_json(await response.read())

    async def component_update(
        self,
        component_id: str | int,
        *,
        fields: dict[str, Any],
        version: str | int | None = None,
        auth: YandexAuth | None = None,
    ) -> Component:
        headers = await self._build_headers(auth)
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        async with self._session.patch(
            f"v3/components/{component_id}",
            headers=headers,
            json=fields,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Component.model_validate_json(await response.read())

    async def component_delete(
        self,
        component_id: str | int,
        *,
        version: str | int | None = None,
        auth: YandexAuth | None = None,
    ) -> None:
        headers = await self._build_headers(auth)
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        async with self._session.delete(
            f"v3/components/{component_id}",
            headers=headers,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

    # --- entities (projects/portfolios/goals, new API) ---
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
        body: dict[str, Any] = {}
        if filter is not None:
            body["filter"] = filter
        if order is not None:
            body["order"] = order

        params: dict[str, Any] = {"perPage": per_page, "page": page}
        if fields:
            params["fields"] = ",".join(fields)
        if root_only is not None:
            params["rootOnly"] = str(root_only).lower()
        if expand:
            params["expand"] = ",".join(expand)

        async with self._post_search(
            f"v3/entities/{entity_type}/_search",
            headers=await self._build_headers(auth),
            json=body,
            params=params,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            raw = await response.read()

        # Yandex Tracker wraps entity search results in `{hits, pages, values: [...]}`
        # when the collection is paginated, but may also return a bare list — accept both.
        import json as _json

        data = _json.loads(raw)
        if isinstance(data, dict):
            values = data.get("values", [])
            if not isinstance(values, list):
                values = []
            return [v if isinstance(v, dict) else {} for v in values]
        if isinstance(data, list):
            return [v if isinstance(v, dict) else {} for v in data]
        return []

    async def entity_get(
        self,
        entity_type: str,
        entity_id: str,
        *,
        fields: list[str] | None = None,
        expand: list[str] | None = None,
        auth: YandexAuth | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if fields:
            params["fields"] = ",".join(fields)
        if expand:
            params["expand"] = ",".join(expand)
        async with self._get(
            f"v3/entities/{entity_type}/{entity_id}",
            headers=await self._build_headers(auth),
            params=params if params else None,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            import json

            return json.loads(await response.read())

    async def entity_create(
        self,
        entity_type: str,
        *,
        fields: dict[str, Any],
        auth: YandexAuth | None = None,
    ) -> dict[str, Any]:
        async with self._session.post(
            f"v3/entities/{entity_type}",
            headers=await self._build_headers(auth),
            json={"fields": fields},
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            import json

            return json.loads(await response.read())

    async def entity_update(
        self,
        entity_type: str,
        entity_id: str,
        *,
        fields: dict[str, Any],
        auth: YandexAuth | None = None,
    ) -> dict[str, Any]:
        async with self._session.patch(
            f"v3/entities/{entity_type}/{entity_id}",
            headers=await self._build_headers(auth),
            json={"fields": fields},
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            import json

            return json.loads(await response.read())

    async def entity_delete(
        self,
        entity_type: str,
        entity_id: str,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        async with self._session.delete(
            f"v3/entities/{entity_type}/{entity_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

    async def projects_search(
        self,
        *,
        filter: dict[str, Any] | None = None,
        order: list[str] | None = None,
        per_page: int = 50,
        page: int = 1,
        auth: YandexAuth | None = None,
    ) -> list[Project]:
        raw = await self.entities_search(
            "project",
            filter=filter,
            order=order,
            per_page=per_page,
            page=page,
            auth=auth,
        )
        return [Project.model_validate(item) for item in raw]

    async def portfolios_search(
        self,
        *,
        filter: dict[str, Any] | None = None,
        order: list[str] | None = None,
        per_page: int = 50,
        page: int = 1,
        auth: YandexAuth | None = None,
    ) -> list[Portfolio]:
        raw = await self.entities_search(
            "portfolio",
            filter=filter,
            order=order,
            per_page=per_page,
            page=page,
            auth=auth,
        )
        return [Portfolio.model_validate(item) for item in raw]

    async def goals_search(
        self,
        *,
        filter: dict[str, Any] | None = None,
        order: list[str] | None = None,
        per_page: int = 50,
        page: int = 1,
        auth: YandexAuth | None = None,
    ) -> list[Goal]:
        raw = await self.entities_search(
            "goal",
            filter=filter,
            order=order,
            per_page=per_page,
            page=page,
            auth=auth,
        )
        return [Goal.model_validate(item) for item in raw]

    async def projects_legacy_list(
        self,
        *,
        per_page: int = 50,
        page: int = 1,
        auth: YandexAuth | None = None,
    ) -> list[ProjectLegacy]:
        params = {"perPage": per_page, "page": page}
        async with self._get(
            "v2/projects",
            headers=await self._build_headers(auth),
            params=params,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return ProjectLegacyList.model_validate_json(await response.read()).root

    # --- dashboards ---
    async def dashboards_list(
        self,
        *,
        per_page: int = 50,
        page: int = 1,
        auth: YandexAuth | None = None,
    ) -> list[Dashboard]:
        # Yandex Tracker searches dashboards via POST /v3/dashboards/_search.
        # A plain GET /v3/dashboards returns 405.
        params = {"perPage": per_page, "page": page}
        async with self._post_search(
            "v3/dashboards/_search",
            headers=await self._build_headers(auth),
            json={},
            params=params,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return DashboardList.model_validate_json(await response.read()).root

    async def dashboard_get(
        self, dashboard_id: str, *, auth: YandexAuth | None = None
    ) -> Dashboard:
        async with self._get(
            f"v3/dashboards/{dashboard_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Dashboard.model_validate_json(await response.read())

    async def dashboard_get_widgets(
        self, dashboard_id: str, *, auth: YandexAuth | None = None
    ) -> list[DashboardWidget]:
        # Tracker has no dedicated /widgets endpoint — widgets are embedded
        # in the dashboard body. We fetch the dashboard and extract them.
        async with self._get(
            f"v3/dashboards/{dashboard_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            raw = await response.read()

        import json as _json

        data = _json.loads(raw)
        widgets_data = data.get("widgets") or []
        return [DashboardWidget.model_validate(w) for w in widgets_data]

    async def dashboard_create(
        self,
        *,
        name: str,
        fields: dict[str, Any] | None = None,
        auth: YandexAuth | None = None,
    ) -> Dashboard:
        body: dict[str, Any] = {"name": name}
        if fields:
            for k, v in fields.items():
                body.setdefault(k, v)
        async with self._session.post(
            "v3/dashboards",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Dashboard.model_validate_json(await response.read())

    async def dashboard_update(
        self,
        dashboard_id: str,
        *,
        fields: dict[str, Any],
        version: str | int | None = None,
        auth: YandexAuth | None = None,
    ) -> Dashboard:
        headers = await self._build_headers(auth)
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        async with self._session.patch(
            f"v3/dashboards/{dashboard_id}",
            headers=headers,
            json=fields,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Dashboard.model_validate_json(await response.read())

    async def dashboard_delete(
        self, dashboard_id: str, *, auth: YandexAuth | None = None
    ) -> None:
        async with self._session.delete(
            f"v3/dashboards/{dashboard_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

    # --- automations ---
    async def triggers_list(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[Trigger]:
        async with self._get(
            f"v3/queues/{queue_id}/triggers",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return TriggerList.model_validate_json(await response.read()).root

    async def trigger_get(
        self,
        queue_id: str,
        trigger_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> Trigger:
        async with self._get(
            f"v3/queues/{queue_id}/triggers/{trigger_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Trigger.model_validate_json(await response.read())

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
        body: dict[str, Any] = {"name": name, "actions": actions}
        if conditions is not None:
            body["conditions"] = conditions
        if active is not None:
            body["active"] = active
        if extra:
            for k, v in extra.items():
                body.setdefault(k, v)
        async with self._session.post(
            f"v3/queues/{queue_id}/triggers",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Trigger.model_validate_json(await response.read())

    async def trigger_update(
        self,
        queue_id: str,
        trigger_id: str | int,
        *,
        fields: dict[str, Any],
        auth: YandexAuth | None = None,
    ) -> Trigger:
        async with self._session.patch(
            f"v3/queues/{queue_id}/triggers/{trigger_id}",
            headers=await self._build_headers(auth),
            json=fields,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Trigger.model_validate_json(await response.read())

    async def trigger_delete(
        self,
        queue_id: str,
        trigger_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        async with self._session.delete(
            f"v3/queues/{queue_id}/triggers/{trigger_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

    async def autoactions_list(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[Autoaction]:
        async with self._get(
            f"v3/queues/{queue_id}/autoactions",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return AutoactionList.model_validate_json(await response.read()).root

    async def autoaction_get(
        self,
        queue_id: str,
        action_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> Autoaction:
        async with self._get(
            f"v3/queues/{queue_id}/autoactions/{action_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Autoaction.model_validate_json(await response.read())

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
        body: dict[str, Any] = {
            "name": name,
            "filter": filter,
            "actions": actions,
        }
        if cron_expression is not None:
            body["cronExpression"] = cron_expression
        if active is not None:
            body["active"] = active
        if extra:
            for k, v in extra.items():
                body.setdefault(k, v)
        async with self._session.post(
            f"v3/queues/{queue_id}/autoactions",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Autoaction.model_validate_json(await response.read())

    async def autoaction_update(
        self,
        queue_id: str,
        action_id: str | int,
        *,
        fields: dict[str, Any],
        auth: YandexAuth | None = None,
    ) -> Autoaction:
        async with self._session.patch(
            f"v3/queues/{queue_id}/autoactions/{action_id}",
            headers=await self._build_headers(auth),
            json=fields,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Autoaction.model_validate_json(await response.read())

    async def autoaction_delete(
        self,
        queue_id: str,
        action_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        async with self._session.delete(
            f"v3/queues/{queue_id}/autoactions/{action_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

    async def macros_list(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> list[Macro]:
        async with self._get(
            f"v3/queues/{queue_id}/macros",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return MacroList.model_validate_json(await response.read()).root

    async def macro_get(
        self,
        queue_id: str,
        macro_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> Macro:
        async with self._get(
            f"v3/queues/{queue_id}/macros/{macro_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Macro.model_validate_json(await response.read())

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
        payload: dict[str, Any] = {"name": name}
        if body is not None:
            payload["body"] = body
        if field_changes is not None:
            payload["fieldChanges"] = field_changes
        if extra:
            for k, v in extra.items():
                payload.setdefault(k, v)
        async with self._session.post(
            f"v3/queues/{queue_id}/macros",
            headers=await self._build_headers(auth),
            json=payload,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Macro.model_validate_json(await response.read())

    async def macro_update(
        self,
        queue_id: str,
        macro_id: str | int,
        *,
        fields: dict[str, Any],
        auth: YandexAuth | None = None,
    ) -> Macro:
        async with self._session.patch(
            f"v3/queues/{queue_id}/macros/{macro_id}",
            headers=await self._build_headers(auth),
            json=fields,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return Macro.model_validate_json(await response.read())

    async def macro_delete(
        self,
        queue_id: str,
        macro_id: str | int,
        *,
        auth: YandexAuth | None = None,
    ) -> None:
        async with self._session.delete(
            f"v3/queues/{queue_id}/macros/{macro_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)

    async def workflows_list(self, *, auth: YandexAuth | None = None) -> list[Workflow]:
        async with self._get(
            "v3/workflows", headers=await self._build_headers(auth)
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return WorkflowList.model_validate_json(await response.read()).root

    async def queue_workflow_get(
        self, queue_id: str, *, auth: YandexAuth | None = None
    ) -> Workflow | None:
        # Tracker has no /v3/queues/<id>/workflow endpoint (404). Workflows are
        # top-level entities exposed via GET /v3/workflows; we filter client-side
        # by queue key/id.
        workflows = await self.workflows_list(auth=auth)
        for wf in workflows:
            q = wf.queue or {}
            if not isinstance(q, dict):
                continue
            if q.get("key") == queue_id or str(q.get("id") or "") == str(queue_id):
                return wf
        return None

    # --- bulk change ---
    async def bulk_update(
        self,
        *,
        issues: list[str],
        values: dict[str, Any],
        comment: str | None = None,
        notify: bool | None = None,
        auth: YandexAuth | None = None,
    ) -> BulkChangeResult:
        body: dict[str, Any] = {"issues": issues, "values": values}
        if comment is not None:
            body["comment"] = comment
        if notify is not None:
            body["notify"] = notify
        async with self._session.post(
            "v3/bulkchange/_update",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return BulkChangeResult.model_validate_json(await response.read())

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
        body: dict[str, Any] = {"issues": issues, "queue": queue}
        if move_all_fields is not None:
            body["moveAllFields"] = move_all_fields
        if initial_status is not None:
            body["initialStatus"] = initial_status
        if notify is not None:
            body["notify"] = notify
        if extra:
            for k, v in extra.items():
                body.setdefault(k, v)
        async with self._session.post(
            "v3/bulkchange/_move",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return BulkChangeResult.model_validate_json(await response.read())

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
        body: dict[str, Any] = {"issues": issues, "transition": transition}
        if comment is not None:
            body["comment"] = comment
        # Per the API, `resolution` (like any other field changed alongside the
        # transition) belongs inside `values`, not at the top level of the body.
        values: dict[str, Any] = dict(fields) if fields else {}
        if resolution is not None:
            values.setdefault("resolution", resolution)
        if values:
            body["values"] = values
        async with self._session.post(
            "v3/bulkchange/_transition",
            headers=await self._build_headers(auth),
            json=body,
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return BulkChangeResult.model_validate_json(await response.read())

    async def bulk_status_get(
        self, operation_id: str, *, auth: YandexAuth | None = None
    ) -> BulkChangeResult:
        async with self._get(
            f"v3/bulkchange/{operation_id}",
            headers=await self._build_headers(auth),
        ) as response:
            if response.status >= 400:
                await _raise_tracker_error(response)
            return BulkChangeResult.model_validate_json(await response.read())
