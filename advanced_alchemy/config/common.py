from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, ClassVar, Generic, TypeVar, cast

from advanced_alchemy.base import orm_registry
from advanced_alchemy.config.engine import EngineConfig
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.utils.dataclass import Empty, simple_asdict

if TYPE_CHECKING:
    from typing import Any

    from sqlalchemy import Connection, Engine, MetaData
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker
    from sqlalchemy.orm import Mapper, Query, Session, sessionmaker
    from sqlalchemy.orm.session import JoinTransactionMode
    from sqlalchemy.sql import TableClause

    from advanced_alchemy.utils.dataclass import EmptyType

__all__ = (
    "GenericSQLAlchemyConfig",
    "GenericSessionConfig",
    "GenericAlembicConfig",
)

ALEMBIC_TEMPLATE_PATH = f"{Path(__file__).parent.parent}/alembic/templates"

"""Path to the Alembic templates."""
ConnectionT = TypeVar("ConnectionT", bound="Connection | AsyncConnection")
"""Type variable for a SQLAlchemy connection."""
EngineT = TypeVar("EngineT", bound="Engine | AsyncEngine")
"""Type variable for a SQLAlchemy engine."""
SessionT = TypeVar("SessionT", bound="Session | AsyncSession")
"""Type variable for a SQLAlchemy session."""
SessionMakerT = TypeVar("SessionMakerT", bound="sessionmaker[Session] | async_sessionmaker[AsyncSession]")
"""Type variable for a SQLAlchemy sessionmaker."""


@dataclass
class GenericSessionConfig(Generic[ConnectionT, EngineT, SessionT]):
    """SQLAlchemy async session config."""

    autobegin: bool | EmptyType = Empty
    """Automatically start transactions when database access is requested by an operation."""
    autoflush: bool | EmptyType = Empty
    """When ``True``, all query operations will issue a flush call to this :class:`Session <sqlalchemy.orm.Session>`
    before proceeding"""
    bind: EngineT | ConnectionT | None | EmptyType = Empty
    """The :class:`Engine <sqlalchemy.engine.Engine>` or :class:`Connection <sqlalchemy.engine.Connection>` that new
    :class:`Session <sqlalchemy.orm.Session>` objects will be bound to."""
    binds: dict[type[Any] | Mapper | TableClause | str, EngineT | ConnectionT] | None | EmptyType = Empty  # pyright: ignore[reportMissingTypeArgument]
    """A dictionary which may specify any number of :class:`Engine <sqlalchemy.engine.Engine>` or :class:`Connection
    <sqlalchemy.engine.Connection>` objects as the source of connectivity for SQL operations on a per-entity basis. The
    keys of the dictionary consist of any series of mapped classes, arbitrary Python classes that are bases for mapped
    classes, :class:`Table <sqlalchemy.schema.Table>` objects and :class:`Mapper <sqlalchemy.orm.Mapper>` objects. The
    values of the dictionary are then instances of :class:`Engine <sqlalchemy.engine.Engine>` or less commonly
    :class:`Connection <sqlalchemy.engine.Connection>` objects."""
    class_: type[SessionT] | EmptyType = Empty
    """Class to use in order to create new :class:`Session <sqlalchemy.orm.Session>` objects."""
    expire_on_commit: bool | EmptyType = Empty
    """If ``True``, all instances will be expired after each commit."""
    info: dict[str, Any] | None | EmptyType = Empty
    """Optional dictionary of information that will be available via the
    :attr:`Session.info <sqlalchemy.orm.Session.info>`"""
    join_transaction_mode: JoinTransactionMode | EmptyType = Empty
    """Describes the transactional behavior to take when a given bind is a Connection that has already begun a
    transaction outside the scope of this Session; in other words the
    :attr:`Connection.in_transaction() <sqlalchemy.Connection.in_transaction>` method returns True."""
    query_cls: type[Query] | None | EmptyType = Empty  # pyright: ignore[reportMissingTypeArgument]
    """Class which should be used to create new Query objects, as returned by the
    :attr:`Session.query() <sqlalchemy.orm.Session.query>` method."""
    twophase: bool | EmptyType = Empty
    """When ``True``, all transactions will be started as a “two phase” transaction, i.e. using the “two phase”
    semantics of the database in use along with an XID. During a :attr:`commit() <sqlalchemy.orm.Session.commit>`, after
    :attr:`flush() <sqlalchemy.orm.Session.flush>` has been issued for all attached databases, the
    :attr:`TwoPhaseTransaction.prepare() <sqlalchemy.engine.TwoPhaseTransaction.prepare>` method on each database`s
    :class:`TwoPhaseTransaction <sqlalchemy.engine.TwoPhaseTransaction>` will be called. This allows each database to
    roll back the entire transaction, before each transaction is committed."""


@dataclass
class GenericSQLAlchemyConfig(Generic[EngineT, SessionT, SessionMakerT]):
    """Common SQLAlchemy Configuration."""

    create_engine_callable: Callable[[str], EngineT]
    """Callable that creates an :class:`AsyncEngine <sqlalchemy.ext.asyncio.AsyncEngine>` instance or instance of its
    subclass.
    """
    session_config: GenericSessionConfig[Any, Any, Any]
    """Configuration options for either the :class:`async_sessionmaker <sqlalchemy.ext.asyncio.async_sessionmaker>`
    or :class:`sessionmaker <sqlalchemy.orm.sessionmaker>`.
    """
    session_maker_class: type[sessionmaker[Session] | async_sessionmaker[AsyncSession]]
    """Sessionmaker class to use."""
    connection_string: str | None = field(default=None)
    """Database connection string in one of the formats supported by SQLAlchemy.

    Notes:
        - For async connections, the connection string must include the correct async prefix.
          e.g. ``'postgresql+asyncpg://...'`` instead of ``'postgresql://'``, and for sync connections its the opposite.

    """
    engine_config: EngineConfig = field(default_factory=EngineConfig)
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """
    session_maker: Callable[[], SessionT] | None = None
    """Callable that returns a session.

    If provided, the plugin will use this rather than instantiate a sessionmaker.
    """
    engine_instance: EngineT | None = None
    """Optional engine to use.

    If set, the plugin will use the provided instance rather than instantiate an engine.
    """
    create_all: bool = False
    """If true, all models are automatically created on engine creation."""

    metadata: MetaData | None = None
    """Optional metadata to use.

      If set, the plugin will use the provided instance rather than the default metadata."""
    enable_touch_updated_timestamp_listener: bool = True
    """Enable Created/Updated Timestamp event listener.

    This is a listener that will update ``created_at`` and ``updated_at`` columns on record modification.
    Disable if you plan to bring your own update mechanism for these columns"""
    _SESSION_SCOPE_KEY_REGISTRY: ClassVar[set[str]] = field(init=False, default=cast("set[str]", set()))
    """Internal counter for ensuring unique identification of session scope keys in the class."""
    _ENGINE_APP_STATE_KEY_REGISTRY: ClassVar[set[str]] = field(init=False, default=cast("set[str]", set()))
    """Internal counter for ensuring unique identification of engine app state keys in the class."""
    _SESSIONMAKER_APP_STATE_KEY_REGISTRY: ClassVar[set[str]] = field(init=False, default=cast("set[str]", set()))
    """Internal counter for ensuring unique identification of sessionmaker state keys in the class."""

    def __post_init__(self) -> None:
        if self.connection_string is not None and self.engine_instance is not None:
            msg = "Only one of 'connection_string' or 'engine_instance' can be provided."
            raise ImproperConfigurationError(msg)
        if self.enable_touch_updated_timestamp_listener:
            from sqlalchemy import event
            from sqlalchemy.orm import Session

            from advanced_alchemy._listeners import touch_updated_timestamp

            event.listen(Session, "before_flush", touch_updated_timestamp)

    @property
    def engine_config_dict(self) -> dict[str, Any]:
        """Return the engine configuration as a dict.

        Returns:
            A string keyed dict of config kwargs for the SQLAlchemy :func:`get_engine <sqlalchemy.get_engine>`
            function.
        """
        return simple_asdict(self.engine_config, exclude_empty=True)

    @property
    def session_config_dict(self) -> dict[str, Any]:
        """Return the session configuration as a dict.

        Returns:
            A string keyed dict of config kwargs for the SQLAlchemy :class:`sessionmaker <sqlalchemy.orm.sessionmaker>`
            class.
        """
        return simple_asdict(self.session_config, exclude_empty=True)

    def get_engine(self) -> EngineT:
        """Return an engine. If none exists yet, create one.

        Returns:
            Getter that returns the engine instance used by the plugin.
        """
        if self.engine_instance:
            return self.engine_instance

        if self.connection_string is None:
            msg = "One of 'connection_string' or 'engine_instance' must be provided."
            raise ImproperConfigurationError(msg)

        engine_config = self.engine_config_dict
        try:
            return self.create_engine_callable(self.connection_string, **engine_config)
        except TypeError:
            # likely due to a dialect that doesn't support json type
            del engine_config["json_deserializer"]
            del engine_config["json_serializer"]
            return self.create_engine_callable(self.connection_string, **engine_config)

    def create_session_maker(self) -> Callable[[], SessionT]:
        """Get a session maker. If none exists yet, create one.

        Returns:
            Session factory used by the plugin.
        """
        if self.session_maker:
            return self.session_maker

        session_kws = self.session_config_dict
        if session_kws.get("bind") is None:
            session_kws["bind"] = self.get_engine()
        return cast("Callable[[], SessionT]", self.session_maker_class(**session_kws))


@dataclass
class GenericAlembicConfig:
    """Configuration for Alembic's :class:`Config <alembic.config.Config>`.

    For details see: https://alembic.sqlalchemy.org/en/latest/api/config.html
    """

    script_config: str = "alembic.ini"
    """A path to the Alembic configuration file such as ``alembic.ini``.  If left unset, the default configuration
    will be used.
    """
    version_table_name: str = "alembic_versions"
    """Configure the name of the table used to hold the applied alembic revisions.
    Defaults to ``alembic_versions``.
    """
    version_table_schema: str | None = None
    """Configure the schema to use for the alembic revisions revisions.
    If unset, it defaults to connection's default schema."""
    script_location: str = "migrations"
    """A path to save generated migrations.
    """
    target_metadata: MetaData = orm_registry.metadata
    """Metadata to use."""
    user_module_prefix: str | None = "sa."
    """User module prefix."""
    render_as_batch: bool = True
    """Render as batch."""
    compare_type: bool = False
    """Compare type."""
    template_path: str = ALEMBIC_TEMPLATE_PATH
    """Template path."""
