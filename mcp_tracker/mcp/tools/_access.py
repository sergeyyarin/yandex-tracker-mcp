"""Access control helpers for MCP tools."""

from mcp_tracker.mcp.errors import TrackerError
from mcp_tracker.settings import Settings
from mcp_tracker.tracker.custom.errors import IssueNotFound


def check_issue_access(settings: Settings, issue_id: str) -> None:
    """Check if access to the issue is allowed based on queue restrictions."""
    queue = issue_id.split("-")[0]
    if settings.tracker_limit_queues and queue not in settings.tracker_limit_queues:
        raise IssueNotFound(issue_id)


def check_queue_access(settings: Settings, queue_id: str) -> None:
    """Check if access to the queue is allowed based on queue restrictions."""
    if settings.tracker_limit_queues and queue_id not in settings.tracker_limit_queues:
        raise TrackerError(f"Queue `{queue_id}` not found or not allowed.")


_DESTRUCTIVE_ACTIONS = frozenset({"delete", "clear", "close"})
_ADDITIVE_ACTIONS = frozenset({"create", "add", "upload"})


def require_write_mode(
    settings: Settings,
    action: str,
    *,
    confirmed: bool = False,
    destructive: bool | None = None,
) -> None:
    """Enforce read-only and optional controlled-write policies.

    Under the controlled profile, additive operations are allowed without a
    confirmation, ordinary mutations require ``confirmed=True``, and
    destructive operations are disabled unless explicitly enabled in settings.
    """
    if settings.tracker_read_only:
        raise TrackerError(
            f"Action `{action}` is not allowed — server is running in read-only mode."
        )

    if settings.tracker_write_policy != "controlled":
        return

    is_destructive = (
        action.lower() in _DESTRUCTIVE_ACTIONS if destructive is None else destructive
    )
    if is_destructive and not settings.tracker_allow_destructive:
        raise TrackerError(
            f"Action `{action}` is disabled by the controlled write policy. "
            "Set TRACKER_ALLOW_DESTRUCTIVE=true only for a controlled maintenance window."
        )

    if action.lower() not in _ADDITIVE_ACTIONS and not confirmed:
        raise TrackerError(
            f"Action `{action}` requires explicit human confirmation under the "
            "controlled write policy. Review the exact mutation and retry with "
            "`confirmed=true`."
        )
