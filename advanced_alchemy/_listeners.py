"""Application ORM configuration."""

import contextlib
import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from advanced_alchemy.types.file_object.registry import StorageRegistry


def touch_updated_timestamp(session: "Session", *_: Any) -> None:
    """Set timestamp on update.

    Called from SQLAlchemy's
    :meth:`before_flush <sqlalchemy.orm.SessionEvents.before_flush>` event to bump the ``updated``
    timestamp on modified instances.

    Args:
        session: The sync :class:`Session <sqlalchemy.orm.Session>` instance that underlies the async
            session.
    """
    for instance in session.dirty:
        if hasattr(instance, "updated_at"):
            instance.updated_at = datetime.datetime.now(datetime.timezone.utc)


def setup_file_object_listeners(registry: "StorageRegistry", handle_rollback: bool = False) -> None:
    """Attaches the necessary SQLAlchemy event listeners for FileObject operations.

    Args:
        registry: The configured StorageRegistry instance.
        handle_rollback: If True, automatically delete newly saved files on transaction rollback.
                         Defaults to False.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Mapper, Session

    from advanced_alchemy.types.file_object.tracker import FileObjectSessionTracker

    tracker = FileObjectSessionTracker
    tracker._set_registry(registry)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    # Store the rollback handling flag on the tracker class
    tracker._handle_rollback = handle_rollback  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

    # Check if already configured to avoid duplicate listeners
    if not event.contains(Mapper, "mapper_configured", tracker._mapper_configured):  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
        event.listen(Mapper, "mapper_configured", tracker._mapper_configured)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
        event.listen(Mapper, "after_configured", tracker._after_configured)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        # Sync listeners
        event.listen(Session, "before_flush", tracker._before_flush)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
        event.listen(Session, "after_commit", tracker._after_commit)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
        event.listen(Session, "after_soft_rollback", tracker._after_soft_rollback)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        # Async listeners
        with contextlib.suppress(AttributeError):
            # The `raw=True` argument might be needed depending on SQLAlchemy version specifics
            # for async listeners to receive the raw session object.
            event.listen(Session, "async_before_flush", tracker._before_flush_async, raw=True)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
        with contextlib.suppress(AttributeError):
            event.listen(Session, "async_after_commit", tracker._after_commit_async, raw=True)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
        with contextlib.suppress(AttributeError):
            event.listen(Session, "async_after_soft_rollback", tracker._after_soft_rollback_async, raw=True)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
