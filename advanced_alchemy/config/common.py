import copy
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Generic, Optional, Union, cast

from typing_extensions import TypeVar

from advanced_alchemy.base import metadata_registry
from advanced_alchemy.config.engine import EngineConfig
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.utils.dataclass import Empty, is_dataclass_instance, simple_asdict

if TYPE_CHECKING:
    from sqlalchemy import Connection, Engine, MetaData
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker
    from sqlalchemy.orm import Mapper, Query, Session, sessionmaker
    from sqlalchemy.orm.session import JoinTransactionMode
    from sqlalchemy.sql import TableClause

    from advanced_alchemy.cache import CacheConfig, CacheManager
    from advanced_alchemy.utils.dataclass import EmptyType

__all__ = (
    "ALEMBIC_TEMPLATE_PATH",
    "AlembicMigrationConfig",
    "AlembicVersionTableConfig",
    "CacheOptions",
    "ConnectionConfig",
    "ConnectionT",
    "EngineT",
    "GenericAlembicConfig",
    "GenericSQLAlchemyConfig",
    "GenericSessionConfig",
    "ListenerConfig",
    "MetadataConfig",
    "SessionBindConfig",
    "SessionFactoryConfig",
    "SessionMakerT",
    "SessionT",
    "SessionTransactionConfig",
)


ALEMBIC_TEMPLATE_PATH = f"{Path(__file__).parent.parent}/alembic/templates"
"""Path to the Alembic templates."""
ConnectionT = TypeVar("ConnectionT", bound="Union[Connection, AsyncConnection]")
"""Type variable for SQLAlchemy connection types.

.. seealso::
    :class:`sqlalchemy.Connection`
    :class:`sqlalchemy.ext.asyncio.AsyncConnection`
"""
EngineT = TypeVar("EngineT", bound="Union[Engine, AsyncEngine]")
"""Type variable for a SQLAlchemy engine.

.. seealso::
    :class:`sqlalchemy.Engine`
    :class:`sqlalchemy.ext.asyncio.AsyncEngine`
"""
SessionT = TypeVar("SessionT", bound="Union[Session, AsyncSession]")
"""Type variable for a SQLAlchemy session.

.. seealso::
    :class:`sqlalchemy.Session`
    :class:`sqlalchemy.ext.asyncio.AsyncSession`
"""
SessionMakerT = TypeVar("SessionMakerT", bound="Union[sessionmaker[Session], async_sessionmaker[AsyncSession]]")
"""Type variable for a SQLAlchemy sessionmaker.

.. seealso::
    :class:`sqlalchemy.orm.sessionmaker`
    :class:`sqlalchemy.ext.asyncio.async_sessionmaker`
"""


@dataclass
class SessionTransactionConfig:
    """Configuration for session transaction behavior.

    Attributes:
        autobegin: Automatically start transactions when database access is requested by an operation.
        autoflush: When ``True``, all query operations will issue a flush call before proceeding.
        expire_on_commit: If ``True``, all instances will be expired after each commit.
        join_transaction_mode: Describes the transactional behavior when a bind is a Connection
            that has already begun a transaction outside the scope of this Session.
        twophase: When ``True``, all transactions will be started as a "two phase" transaction.
    """

    autobegin: "Union[bool, EmptyType]" = Empty
    """Automatically start transactions when database access is requested by an operation.

    Bool or :class:`Empty <advanced_alchemy.utils.dataclass.Empty>`
    """
    autoflush: "Union[bool, EmptyType]" = Empty
    """When ``True``, all query operations will issue a flush call to this :class:`Session <sqlalchemy.orm.Session>`
    before proceeding"""
    expire_on_commit: "Union[bool, EmptyType]" = Empty
    """If ``True``, all instances will be expired after each commit."""
    join_transaction_mode: "Union[JoinTransactionMode, EmptyType]" = Empty
    """Describes the transactional behavior to take when a given bind is a Connection that has already begun a
    transaction outside the scope of this Session; in other words the
    :attr:`Connection.in_transaction() <sqlalchemy.Connection.in_transaction>` method returns True."""
    twophase: "Union[bool, EmptyType]" = Empty
    """When ``True``, all transactions will be started as a "two phase" transaction, i.e. using the "two phase"
    semantics of the database in use along with an XID. During a :attr:`commit() <sqlalchemy.orm.Session.commit>`, after
    :attr:`flush() <sqlalchemy.orm.Session.flush>` has been issued for all attached databases, the
    :attr:`TwoPhaseTransaction.prepare() <sqlalchemy.engine.TwoPhaseTransaction.prepare>` method on each database`s
    :class:`TwoPhaseTransaction <sqlalchemy.engine.TwoPhaseTransaction>` will be called. This allows each database to
    roll back the entire transaction, before each transaction is committed."""


@dataclass
class SessionBindConfig(Generic[ConnectionT, EngineT]):
    """Configuration for session engine/connection binding.

    Attributes:
        bind: The :class:`Engine <sqlalchemy.engine.Engine>` or :class:`Connection <sqlalchemy.engine.Connection>`
            that new :class:`Session <sqlalchemy.orm.Session>` objects will be bound to.
        binds: A dictionary mapping entities to specific
            :class:`Engine <sqlalchemy.engine.Engine>` or :class:`Connection <sqlalchemy.engine.Connection>` objects.
    """

    bind: "Optional[Union[EngineT, ConnectionT, EmptyType]]" = Empty
    """The :class:`Engine <sqlalchemy.engine.Engine>` or :class:`Connection <sqlalchemy.engine.Connection>` that new
    :class:`Session <sqlalchemy.orm.Session>` objects will be bound to."""
    binds: "Optional[Union[dict[Union[type[Any], Mapper[Any], TableClause, str], Union[EngineT, ConnectionT]], EmptyType]]" = Empty
    """A dictionary which may specify any number of :class:`Engine <sqlalchemy.engine.Engine>` or :class:`Connection
    <sqlalchemy.engine.Connection>` objects as the source of connectivity for SQL operations on a per-entity basis. The
    keys of the dictionary consist of any series of mapped classes, arbitrary Python classes that are bases for mapped
    classes, :class:`Table <sqlalchemy.schema.Table>` objects and :class:`Mapper <sqlalchemy.orm.Mapper>` objects. The
    values of the dictionary are then instances of :class:`Engine <sqlalchemy.engine.Engine>` or less commonly
    :class:`Connection <sqlalchemy.engine.Connection>` objects."""


@dataclass
class GenericSessionConfig(Generic[ConnectionT, EngineT, SessionT]):
    """SQLAlchemy async session config.

    Types:
        ConnectionT: :class:`sqlalchemy.Connection` | :class:`sqlalchemy.ext.asyncio.AsyncConnection`
        EngineT: :class:`sqlalchemy.Engine` | :class:`sqlalchemy.ext.asyncio.AsyncEngine`
        SessionT: :class:`sqlalchemy.Session` | :class:`sqlalchemy.ext.asyncio.AsyncSession`
    """

    bind_config: "SessionBindConfig[ConnectionT, EngineT]" = field(default_factory=SessionBindConfig)
    """Configuration for session engine/connection binding.

    .. seealso::
        :class:`SessionBindConfig`
    """
    transaction_config: SessionTransactionConfig = field(default_factory=SessionTransactionConfig)
    """Configuration for session transaction behavior.

    .. seealso::
        :class:`SessionTransactionConfig`
    """
    class_: "Union[type[SessionT], EmptyType]" = Empty
    """Class to use in order to create new :class:`Session <sqlalchemy.orm.Session>` objects."""
    info: "Optional[Union[dict[str, Any], EmptyType]]" = Empty
    """Optional dictionary of information that will be available via the
    :attr:`Session.info <sqlalchemy.orm.Session.info>`"""
    query_cls: "Optional[Union[type[Query], EmptyType]]" = Empty  # pyright: ignore[reportMissingTypeArgument]
    """Class which should be used to create new Query objects, as returned by the
    :attr:`Session.query() <sqlalchemy.orm.Session.query>` method."""

    @property
    def autobegin(self) -> "Union[bool, EmptyType]":
        return self.transaction_config.autobegin

    @autobegin.setter
    def autobegin(self, value: "Union[bool, EmptyType]") -> None:
        self.transaction_config.autobegin = value

    @property
    def autoflush(self) -> "Union[bool, EmptyType]":
        return self.transaction_config.autoflush

    @autoflush.setter
    def autoflush(self, value: "Union[bool, EmptyType]") -> None:
        self.transaction_config.autoflush = value

    @property
    def bind(self) -> "Optional[Union[EngineT, ConnectionT, EmptyType]]":
        return self.bind_config.bind

    @bind.setter
    def bind(self, value: "Optional[Union[EngineT, ConnectionT, EmptyType]]") -> None:
        self.bind_config.bind = value

    @property
    def binds(
        self,
    ) -> (
        "Optional[Union[dict[Union[type[Any], Mapper[Any], TableClause, str], Union[EngineT, ConnectionT]], EmptyType]]"
    ):
        return self.bind_config.binds

    @binds.setter
    def binds(
        self,
        value: "Optional[Union[dict[Union[type[Any], Mapper[Any], TableClause, str], Union[EngineT, ConnectionT]], EmptyType]]",
    ) -> None:
        self.bind_config.binds = value

    @property
    def expire_on_commit(self) -> "Union[bool, EmptyType]":
        return self.transaction_config.expire_on_commit

    @expire_on_commit.setter
    def expire_on_commit(self, value: "Union[bool, EmptyType]") -> None:
        self.transaction_config.expire_on_commit = value

    @property
    def join_transaction_mode(self) -> "Union[JoinTransactionMode, EmptyType]":
        return self.transaction_config.join_transaction_mode

    @join_transaction_mode.setter
    def join_transaction_mode(self, value: "Union[JoinTransactionMode, EmptyType]") -> None:
        self.transaction_config.join_transaction_mode = value

    @property
    def twophase(self) -> "Union[bool, EmptyType]":
        return self.transaction_config.twophase

    @twophase.setter
    def twophase(self, value: "Union[bool, EmptyType]") -> None:
        self.transaction_config.twophase = value


@dataclass
class ConnectionConfig:
    """Configuration for database engine connection and creation.

    Attributes:
        connection_string: Database connection string in one of the formats supported by SQLAlchemy.
        create_engine_callable: Callable that creates an :class:`Engine <sqlalchemy.engine.Engine>` instance.
        engine_instance: Optional pre-built engine instance to use instead of creating one.
    """

    connection_string: "Optional[str]" = None
    """Database connection string in one of the formats supported by SQLAlchemy.

    Notes:
        - For async connections, the connection string must include the correct async prefix.
          e.g. ``'postgresql+asyncpg://...'`` instead of ``'postgresql://'``, and for sync connections its the opposite.
    """
    create_engine_callable: "Optional[Callable[..., Any]]" = None
    """Callable that creates an :class:`Engine <sqlalchemy.engine.Engine>` instance or instance of its subclass."""
    engine_instance: "Optional[Any]" = None
    """Optional engine to use.

    If set, the plugin will use the provided instance rather than instantiate an engine.
    """


@dataclass
class SessionFactoryConfig:
    """Configuration for session maker creation.

    Attributes:
        session_maker_class: Sessionmaker class to use.
        session_maker: Optional pre-built callable that returns a session.
    """

    session_maker_class: "Optional[Any]" = None
    """Sessionmaker class to use.

    .. seealso::
        :class:`sqlalchemy.orm.sessionmaker`
        :class:`sqlalchemy.ext.asyncio.async_sessionmaker`
    """
    session_maker: "Optional[Callable[..., Any]]" = None
    """Callable that returns a session.

    If provided, the plugin will use this rather than instantiate a sessionmaker.
    """


@dataclass
class MetadataConfig:
    """Configuration for metadata and schema management.

    Attributes:
        metadata: Optional :class:`MetaData <sqlalchemy.schema.MetaData>` to use.
        bind_key: Bind key to register a metadata to a specific engine configuration.
        create_all: If true, all models are automatically created on engine creation.
    """

    metadata: "Optional[MetaData]" = None
    """Optional metadata to use.

      If set, the plugin will use the provided instance rather than the default metadata."""
    bind_key: "Optional[str]" = None
    """Bind key to register a metadata to a specific engine configuration."""
    create_all: bool = False
    """If true, all models are automatically created on engine creation."""


@dataclass
class ListenerConfig:
    """Configuration for event listeners.

    Attributes:
        enable_touch_updated_timestamp_listener: Enable Created/Updated Timestamp event listener.
        enable_file_object_listener: Enable FileObject listener.
        file_object_raise_on_error: Control FileObject error handling behavior.
    """

    enable_touch_updated_timestamp_listener: bool = True
    """Enable Created/Updated Timestamp event listener.

    This is a listener that will update ``created_at`` and ``updated_at`` columns on record modification.
    Disable if you plan to bring your own update mechanism for these columns"""
    enable_file_object_listener: bool = True
    """Enable FileObject listener.

    This is a listener that will automatically save and delete :class:`FileObject <advanced_alchemy.types.file_object.FileObject>` instances when they are saved or deleted.

    Disable if you plan to bring your own save/delete mechanism for these columns"""
    file_object_raise_on_error: bool = True
    """Control FileObject error handling behavior.

    - ``False``: Log warnings on file operation failures, don't raise exceptions
    - ``True`` (default): Raise exceptions on file operation failures
    """


@dataclass
class CacheOptions:
    """Configuration for caching.

    Attributes:
        config: Optional :class:`CacheConfig <advanced_alchemy.cache.CacheConfig>` for dogpile.cache integration.
        manager: Optional pre-built :class:`CacheManager <advanced_alchemy.cache.CacheManager>` instance.
    """

    config: "Optional[CacheConfig]" = None
    """Optional :class:`CacheConfig <advanced_alchemy.cache.CacheConfig>` for dogpile.cache integration.

    When set, a :class:`CacheManager <advanced_alchemy.cache.CacheManager>` is instantiated during
    :meth:`__post_init__` and stored in ``session_config.info["cache_manager"]``. Repositories
    created against sessions produced by this config will pick the manager up automatically.

    Requires the optional ``dogpile.cache`` dependency (``pip install advanced-alchemy[dogpile]``);
    without it the manager falls back to a no-op :class:`NullRegion`.

    .. seealso::
        :doc:`/usage/caching`
    """
    manager: "Optional[CacheManager]" = None
    """Optional pre-built :class:`CacheManager <advanced_alchemy.cache.CacheManager>` instance.

    Takes precedence over :attr:`config`. Useful when sharing a single cache manager across
    multiple configs.
    """


@dataclass
class AlembicVersionTableConfig:
    """Configuration for the Alembic version table.

    Attributes:
        version_table_name: Configure the name of the table used to hold the applied alembic revisions.
        version_table_schema: Configure the schema to use for the alembic revisions.
    """

    version_table_name: str = "alembic_versions"
    """Configure the name of the table used to hold the applied alembic revisions.
    Defaults to ``alembic_versions``.
    """
    version_table_schema: "Optional[str]" = None
    """Configure the schema to use for the alembic revisions revisions.
    If unset, it defaults to connection's default schema."""


@dataclass
class AlembicMigrationConfig:
    """Configuration for Alembic migration behavior.

    Attributes:
        user_module_prefix: User module prefix.
        render_as_batch: Render as batch.
        compare_type: Compare type.
    """

    user_module_prefix: "Optional[str]" = "sa."
    """User module prefix."""
    render_as_batch: bool = True
    """Render as batch."""
    compare_type: bool = False
    """Compare type."""


@dataclass
class GenericSQLAlchemyConfig(Generic[EngineT, SessionT, SessionMakerT]):
    """Common SQLAlchemy Configuration.

    Types:
        EngineT: :class:`sqlalchemy.Engine` or :class:`sqlalchemy.ext.asyncio.AsyncEngine`
        SessionT: :class:`sqlalchemy.Session` or :class:`sqlalchemy.ext.asyncio.AsyncSession`
        SessionMakerT: :class:`sqlalchemy.orm.sessionmaker` or :class:`sqlalchemy.ext.asyncio.async_sessionmaker`
    """

    session_config: "GenericSessionConfig[Any, Any, Any]"
    """Configuration options for either the :class:`async_sessionmaker <sqlalchemy.ext.asyncio.async_sessionmaker>`
    or :class:`sessionmaker <sqlalchemy.orm.sessionmaker>`.
    """
    engine_config: "EngineConfig" = field(default_factory=EngineConfig)
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """
    connection_config: ConnectionConfig = field(default_factory=ConnectionConfig)
    """Configuration for database engine connection and creation.

    .. seealso::
        :class:`ConnectionConfig`
    """
    session_factory_config: SessionFactoryConfig = field(default_factory=SessionFactoryConfig)
    """Configuration for session maker creation.

    .. seealso::
        :class:`SessionFactoryConfig`
    """
    metadata_config: MetadataConfig = field(default_factory=MetadataConfig)
    """Configuration for metadata and schema management.

    .. seealso::
        :class:`MetadataConfig`
    """
    listener_config: ListenerConfig = field(default_factory=ListenerConfig)
    """Configuration for event listeners.

    .. seealso::
        :class:`ListenerConfig`
    """
    cache_options: CacheOptions = field(default_factory=CacheOptions)
    """Configuration for caching.

    .. seealso::
        :class:`CacheOptions`
    """
    connection_string: "Optional[str]" = field(default=None, repr=False)
    create_engine_callable: "Optional[Callable[..., Any]]" = field(default=None, repr=False)
    engine_instance: "Optional[Any]" = field(default=None, repr=False)
    session_maker_class: "Optional[Any]" = field(default=None, repr=False)
    session_maker: "Optional[Callable[..., Any]]" = field(default=None, repr=False)
    metadata: "Optional[MetaData]" = field(default=None, repr=False)
    bind_key: "Optional[str]" = field(default=None, repr=False)
    create_all: Optional[bool] = field(default=None, repr=False)
    enable_touch_updated_timestamp_listener: Optional[bool] = field(default=None, repr=False)
    enable_file_object_listener: Optional[bool] = field(default=None, repr=False)
    file_object_raise_on_error: Optional[bool] = field(default=None, repr=False)
    cache_config: "Optional[CacheConfig]" = field(default=None, repr=False)
    cache_manager: "Optional[CacheManager]" = field(default=None, repr=False)
    _SESSION_SCOPE_KEY_REGISTRY: "ClassVar[set[str]]" = field(init=False, default=cast("set[str]", set()))
    """Internal counter for ensuring unique identification of session scope keys in the class."""
    _ENGINE_APP_STATE_KEY_REGISTRY: "ClassVar[set[str]]" = field(init=False, default=cast("set[str]", set()))
    """Internal counter for ensuring unique identification of engine app state keys in the class."""
    _SESSIONMAKER_APP_STATE_KEY_REGISTRY: "ClassVar[set[str]]" = field(init=False, default=cast("set[str]", set()))
    """Internal counter for ensuring unique identification of sessionmaker state keys in the class."""

    def __post_init__(self) -> None:
        if self.connection_config.connection_string is not None and self.connection_config.engine_instance is not None:
            msg = "Only one of 'connection_string' or 'engine_instance' can be provided."
            raise ImproperConfigurationError(msg)
        if self.metadata_config.metadata is None:
            self.metadata_config.metadata = metadata_registry.get(self.metadata_config.bind_key)
        else:
            metadata_registry.set(self.metadata_config.bind_key, self.metadata_config.metadata)

        # Detach session_config and normalize info to a private dict so config writes
        # don't bleed between configs that share the same session_config object.
        self.session_config = copy.copy(self.session_config)
        configured_info = self.session_config.info
        session_info: dict[str, Any] = (
            {} if configured_info is Empty or configured_info is None else dict(configured_info)
        )
        session_info["file_object_raise_on_error"] = self.listener_config.file_object_raise_on_error
        self.session_config.info = session_info

        # Build a CacheManager from cache_config if one wasn't supplied explicitly,
        # then propagate it to sessions via session_config.info["cache_manager"].
        if self.cache_options.manager is None and self.cache_options.config is not None:
            from advanced_alchemy.cache import CacheManager

            self.cache_options.manager = CacheManager(self.cache_options.config)
        if self.cache_options.manager is not None:
            session_info["cache_manager"] = self.cache_options.manager

    def __hash__(self) -> int:  # pragma: no cover
        return hash(
            (
                self.__class__.__qualname__,
                self.connection_config.connection_string,
                self.engine_config.__class__.__qualname__,
                self.metadata_config.bind_key,
                id(self.cache_options.manager) if self.cache_options.manager is not None else None,
            )
        )

    def __eq__(self, other: object) -> bool:
        return self.__hash__() == other.__hash__()

    # --- Backward-compatible property accessors ---
    _LEGACY_ATTRS: ClassVar[set[str]] = {
        "connection_string",
        "create_engine_callable",
        "engine_instance",
        "session_maker_class",
        "session_maker",
        "metadata",
        "bind_key",
        "create_all",
        "enable_touch_updated_timestamp_listener",
        "enable_file_object_listener",
        "file_object_raise_on_error",
        "cache_config",
        "cache_manager",
    }

    def __setattr__(self, name: str, value: Any) -> None:
        try:
            legacy_attrs = object.__getattribute__(self, "__class__")._LEGACY_ATTRS  # noqa: SLF001
        except AttributeError:
            legacy_attrs = None

        if legacy_attrs and name in legacy_attrs:
            try:
                if name in {"connection_string", "create_engine_callable", "engine_instance"}:
                    setattr(object.__getattribute__(self, "connection_config"), name, value)
                elif name in {"session_maker_class", "session_maker"}:
                    setattr(object.__getattribute__(self, "session_factory_config"), name, value)
                elif name in {"metadata", "bind_key", "create_all"}:
                    setattr(object.__getattribute__(self, "metadata_config"), name, value)
                elif name in {
                    "enable_touch_updated_timestamp_listener",
                    "enable_file_object_listener",
                    "file_object_raise_on_error",
                }:
                    setattr(object.__getattribute__(self, "listener_config"), name, value)
                elif name == "cache_config":
                    self.cache_options.config = value
                elif name == "cache_manager":
                    self.cache_options.manager = value
            except AttributeError:
                pass
        super().__setattr__(name, value)

    def __getattribute__(self, name: str) -> Any:
        try:
            legacy_attrs = object.__getattribute__(self, "__class__")._LEGACY_ATTRS  # noqa: SLF001
        except AttributeError:
            legacy_attrs = None

        if legacy_attrs and name in legacy_attrs:
            try:
                if name in {"connection_string", "create_engine_callable", "engine_instance"}:
                    sub_cfg = object.__getattribute__(self, "connection_config")
                elif name in {"session_maker_class", "session_maker"}:
                    sub_cfg = object.__getattribute__(self, "session_factory_config")
                elif name in {"metadata", "bind_key", "create_all"}:
                    sub_cfg = object.__getattribute__(self, "metadata_config")
                elif name in {
                    "enable_touch_updated_timestamp_listener",
                    "enable_file_object_listener",
                    "file_object_raise_on_error",
                }:
                    sub_cfg = object.__getattribute__(self, "listener_config")
                elif name == "cache_config":
                    return object.__getattribute__(self, "cache_options").config
                elif name == "cache_manager":
                    return object.__getattribute__(self, "cache_options").manager
                else:
                    sub_cfg = None

                if sub_cfg is not None:
                    return getattr(sub_cfg, name)
            except AttributeError:
                pass

        return object.__getattribute__(self, name)

    # --- Public methods ---

    @property
    def engine_config_dict(self) -> dict[str, Any]:
        """Return the engine configuration as a dict.

        Returns:
            A string keyed dict of config kwargs for the SQLAlchemy :func:`sqlalchemy.get_engine`
            function.
        """
        return self.engine_config.to_dict(exclude_empty=True)

    @property
    def session_config_dict(self) -> dict[str, Any]:
        """Return the session configuration as a flat dict.

        Flattens nested sub-configs (bind_config, transaction_config) so the
        result can be passed directly to :class:`sqlalchemy.orm.sessionmaker`.

        Returns:
            A string keyed dict of config kwargs for the SQLAlchemy :class:`sqlalchemy.orm.sessionmaker`
            class.
        """
        kwargs: dict[str, Any] = {}
        for sc_field in fields(self.session_config):
            sc_value = getattr(self.session_config, sc_field.name)
            if sc_value is Empty:
                continue
            if is_dataclass_instance(sc_value):
                kwargs.update(simple_asdict(sc_value, exclude_empty=True))
            else:
                kwargs[sc_field.name] = sc_value
        return kwargs

    def get_engine(self) -> EngineT:
        """Return an engine. If none exists yet, create one.

        Raises:
            ImproperConfigurationError: if neither `connection_string` nor `engine_instance` are provided.

        Returns:
            :class:`sqlalchemy.Engine` or :class:`sqlalchemy.ext.asyncio.AsyncEngine` instance used by the plugin.
        """
        if self.connection_config.engine_instance:
            return cast("EngineT", self.connection_config.engine_instance)

        if self.connection_config.connection_string is None:
            msg = "One of 'connection_string' or 'engine_instance' must be provided."
            raise ImproperConfigurationError(msg)

        if self.connection_config.create_engine_callable is None:
            msg = "'create_engine_callable' must be provided in connection_config to create an engine."
            raise ImproperConfigurationError(msg)

        engine_config = self.engine_config_dict
        try:
            self.connection_config.engine_instance = self.connection_config.create_engine_callable(
                self.connection_config.connection_string,
                **engine_config,
            )
        except TypeError:
            # likely due to a dialect that doesn't support json type
            del engine_config["json_deserializer"]
            del engine_config["json_serializer"]
            self.connection_config.engine_instance = self.connection_config.create_engine_callable(
                self.connection_config.connection_string,
                **engine_config,
            )
        return cast("EngineT", self.connection_config.engine_instance)

    def create_session_maker(self) -> "Callable[[], SessionT]":  # pragma: no cover
        """Get a session maker. If none exists yet, create one.

        Returns:
            :class:`sqlalchemy.orm.sessionmaker` or :class:`sqlalchemy.ext.asyncio.async_sessionmaker` factory used by the plugin.
        """
        if self.session_factory_config.session_maker:
            return cast("Callable[[], SessionT]", self.session_factory_config.session_maker)

        session_kws = self.session_config_dict
        if session_kws.get("bind") is None:
            session_kws["bind"] = self.get_engine()
        if self.session_factory_config.session_maker_class is None:
            msg = "session_maker_class must be provided."
            raise ImproperConfigurationError(msg)
        self.session_factory_config.session_maker = cast(
            "Callable[[], SessionT]",
            self.session_factory_config.session_maker_class(**session_kws),
        )
        return self.session_factory_config.session_maker


@dataclass
class GenericAlembicConfig:
    """Configuration for Alembic's :class:`Config <alembic.config.Config>`.

    For details see: https://alembic.sqlalchemy.org/en/latest/api/config.html
    """

    script_config: str = "alembic.ini"
    """A path to the Alembic configuration file such as ``alembic.ini``.  If left unset, the default configuration
    will be used.
    """
    script_location: str = "migrations"
    """A path to save generated migrations."""
    toml_file: "Optional[str]" = None
    """A path to the Alembic pyproject.toml configuration file.
    If left unset, the default configuration will be used.
    """
    template_path: str = ALEMBIC_TEMPLATE_PATH
    """Path to the Alembic template directory."""
    version_table_config: AlembicVersionTableConfig = field(default_factory=AlembicVersionTableConfig)
    """Configuration for the Alembic version table.

    .. seealso::
        :class:`AlembicVersionTableConfig`
    """
    migration_config: AlembicMigrationConfig = field(default_factory=AlembicMigrationConfig)
    """Configuration for Alembic migration behavior.

    .. seealso::
        :class:`AlembicMigrationConfig`
    """
