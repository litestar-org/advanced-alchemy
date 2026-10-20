"""Multi-service acquisition and dependency injection grouping."""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import AsyncExitStack, ExitStack, asynccontextmanager, closing
from inspect import isclass
from typing import TYPE_CHECKING, Any, Generic, cast, overload

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from typing_extensions import TypeAlias, TypeVar, TypeVarTuple, Unpack

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.repository import Empty, EmptyType, ErrorMessages, LoadSpec

if TYPE_CHECKING:
    from types import TracebackType

    from sqlalchemy import Select

    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.sync import SQLAlchemySyncConfig
    from advanced_alchemy.repository.typing import ModelT

__all__ = (
    "AsyncServiceProvider",
    "ServiceGroup",
    "ServiceSpec",
    "SyncServiceProvider",
    "provide_services",
)

T = TypeVar("T")
T1 = TypeVar("T1")
T2 = TypeVar("T2")
T3 = TypeVar("T3")
T4 = TypeVar("T4")
T5 = TypeVar("T5")
T6 = TypeVar("T6")
Ts = TypeVarTuple("Ts")

AsyncServiceProvider: TypeAlias = Callable[..., AsyncGenerator[T, None]]
SyncServiceProvider: TypeAlias = Callable[..., Generator[T, None, None]]
ServiceSpec: TypeAlias = "type[T] | AsyncServiceProvider[T] | SyncServiceProvider[T]"


@asynccontextmanager
async def _aclosing(thing: Any) -> AsyncGenerator[Any, None]:
    """Helper for closing async generators cleanly."""
    try:
        yield thing
    finally:
        await thing.aclose()


class _ServiceGroupContext(Generic[Unpack[Ts]]):
    """Context manager for acquiring multiple services on a shared session."""

    __slots__ = (
        "_async_stack",
        "_config",
        "_connection",
        "_count_with_window_function",
        "_error_messages",
        "_execution_options",
        "_load",
        "_session",
        "_specs",
        "_statement",
        "_sync_stack",
        "_uniquify",
    )

    def __init__(
        self,
        specs: tuple[Any, ...],
        *,
        session: AsyncSession | Session | None = None,
        config: Any | None = None,
        connection: Any | None = None,
        statement: Any | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> None:
        """Initialize the multi-service acquisition context."""
        self._specs = specs
        self._session = session
        self._config = config
        self._connection = connection
        self._statement = statement
        self._error_messages = error_messages
        self._load = load
        self._execution_options = execution_options
        self._uniquify = uniquify
        self._count_with_window_function = count_with_window_function
        self._async_stack: AsyncExitStack | None = None
        self._sync_stack: ExitStack | None = None

    async def __aenter__(self) -> tuple[Unpack[Ts]]:
        """Enter the async context, resolving the session and entering each service provider."""
        stack = AsyncExitStack()
        try:
            session = await self._resolve_async_session(stack)
            services: list[Any] = []
            for spec in self._specs:
                service = await self._enter_spec_async(spec, session, stack)
                services.append(service)
            self._async_stack = stack
            return cast("tuple[Unpack[Ts]]", tuple(services))
        except Exception:
            await stack.aclose()
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        """Exit the async context and clean up entered service providers in reverse order."""
        if self._async_stack is not None:
            return await self._async_stack.__aexit__(exc_type, exc_val, exc_tb)
        return None

    def __enter__(self) -> tuple[Unpack[Ts]]:
        """Enter the sync context, resolving the session and entering each service provider."""
        stack = ExitStack()
        try:
            session = self._resolve_sync_session(stack)
            services: list[Any] = []
            for spec in self._specs:
                service = self._enter_spec_sync(spec, session, stack)
                services.append(service)
            self._sync_stack = stack
            return cast("tuple[Unpack[Ts]]", tuple(services))
        except Exception:
            stack.close()
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        """Exit the sync context and clean up entered service providers in reverse order."""
        if self._sync_stack is not None:
            return self._sync_stack.__exit__(exc_type, exc_val, exc_tb)
        return None

    async def _resolve_async_session(self, stack: AsyncExitStack) -> AsyncSession:
        """Resolve an active async session from session, connection + config, or config."""
        if self._session is not None:
            if isinstance(self._session, Session):
                msg = (
                    "A synchronous Session cannot be used in an async context. Use a synchronous 'with' block instead."
                )
                raise ImproperConfigurationError(msg)
            return self._session
        if self._connection is not None and self._config is not None and hasattr(self._config, "provide_session"):
            return cast(
                "AsyncSession",
                self._config.provide_session(self._connection.app.state, self._connection.scope),
            )
        if self._config is not None and hasattr(self._config, "get_session"):
            session_ctx = self._config.get_session()
            if hasattr(session_ctx, "__aenter__"):
                return cast("AsyncSession", await stack.enter_async_context(session_ctx))
            msg = "Config returned a synchronous session context in an async 'async with' block."
            raise ImproperConfigurationError(msg)
        msg = "One of session, config, or connection must be provided to acquire services."
        raise ImproperConfigurationError(msg)

    def _resolve_sync_session(self, stack: ExitStack) -> Session:
        """Resolve an active sync session from session, connection + config, or config."""
        if self._session is not None:
            if isinstance(self._session, AsyncSession):
                msg = "An asynchronous AsyncSession cannot be used in a sync context. Use 'async with' instead."
                raise ImproperConfigurationError(msg)
            return self._session
        if self._connection is not None and self._config is not None and hasattr(self._config, "provide_session"):
            return cast(
                "Session",
                self._config.provide_session(self._connection.app.state, self._connection.scope),
            )
        if self._config is not None and hasattr(self._config, "get_session"):
            session_ctx = self._config.get_session()
            if hasattr(session_ctx, "__enter__"):
                return cast("Session", stack.enter_context(session_ctx))
            msg = "Config returned an asynchronous session context in a sync 'with' block."
            raise ImproperConfigurationError(msg)
        msg = "One of session, config, or connection must be provided to acquire services."
        raise ImproperConfigurationError(msg)

    async def _enter_spec_async(self, spec: Any, session: AsyncSession, stack: AsyncExitStack) -> Any:
        """Instantiate or enter an individual service specification in an async context."""
        if isclass(spec):
            new_method = getattr(spec, "new", None)
            if callable(new_method):
                ctx = new_method(
                    session=session,
                    statement=self._statement,
                    config=self._config,
                    error_messages=self._error_messages,
                    load=self._load,
                    execution_options=self._execution_options,
                    uniquify=self._uniquify,
                    count_with_window_function=self._count_with_window_function,
                )
                if hasattr(ctx, "__aenter__"):
                    return await stack.enter_async_context(cast("Any", ctx))
                if hasattr(ctx, "__enter__"):
                    return stack.enter_context(cast("Any", ctx))
                return ctx
            spec_factory = cast("Callable[..., Any]", spec)
            try:
                return spec_factory(session=session)
            except TypeError:
                return spec_factory(session)

        try:
            result = spec(session)
        except TypeError:
            try:
                result = spec(session=session)
            except TypeError:
                result = spec()

        if hasattr(result, "__aenter__"):
            return await stack.enter_async_context(result)
        if hasattr(result, "__enter__"):
            return stack.enter_context(result)
        if hasattr(result, "__anext__"):
            gen_ctx = _aclosing(result)
            gen = await stack.enter_async_context(gen_ctx)
            return await gen.__anext__()
        if hasattr(result, "__next__"):
            sync_gen_ctx = closing(result)
            sync_gen = stack.enter_context(sync_gen_ctx)
            return next(sync_gen)
        return result

    def _enter_spec_sync(self, spec: Any, session: Session, stack: ExitStack) -> Any:
        """Instantiate or enter an individual service specification in a sync context."""
        if isclass(spec):
            new_method = getattr(spec, "new", None)
            if callable(new_method):
                ctx = new_method(
                    session=session,
                    statement=self._statement,
                    config=self._config,
                    error_messages=self._error_messages,
                    load=self._load,
                    execution_options=self._execution_options,
                    uniquify=self._uniquify,
                    count_with_window_function=self._count_with_window_function,
                )
                if hasattr(ctx, "__enter__"):
                    return stack.enter_context(cast("Any", ctx))
                return ctx
            spec_factory = cast("Callable[..., Any]", spec)
            try:
                return spec_factory(session=session)
            except TypeError:
                return spec_factory(session)

        try:
            result = spec(session)
        except TypeError:
            try:
                result = spec(session=session)
            except TypeError:
                result = spec()

        if hasattr(result, "__enter__"):
            return stack.enter_context(result)
        if hasattr(result, "__next__"):
            sync_gen_ctx = closing(result)
            sync_gen = stack.enter_context(sync_gen_ctx)
            return next(sync_gen)
        if hasattr(result, "__anext__") or hasattr(result, "__aenter__"):
            msg = "An asynchronous service provider cannot be used in a synchronous 'with' block."
            raise ImproperConfigurationError(msg)
        return result


class ServiceGroup(Generic[Unpack[Ts]]):
    """Reusable specification for acquiring multiple services on a shared session."""

    __slots__ = (
        "count_with_window_function",
        "error_messages",
        "execution_options",
        "load",
        "specs",
        "statement",
        "uniquify",
    )

    @overload
    def __init__(
        self: ServiceGroup[T1],
        s1: ServiceSpec[T1],
        /,
        *,
        statement: Any | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: ServiceGroup[T1, T2],
        s1: ServiceSpec[T1],
        s2: ServiceSpec[T2],
        /,
        *,
        statement: Any | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: ServiceGroup[T1, T2, T3],
        s1: ServiceSpec[T1],
        s2: ServiceSpec[T2],
        s3: ServiceSpec[T3],
        /,
        *,
        statement: Any | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: ServiceGroup[T1, T2, T3, T4],
        s1: ServiceSpec[T1],
        s2: ServiceSpec[T2],
        s3: ServiceSpec[T3],
        s4: ServiceSpec[T4],
        /,
        *,
        statement: Any | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: ServiceGroup[T1, T2, T3, T4, T5],
        s1: ServiceSpec[T1],
        s2: ServiceSpec[T2],
        s3: ServiceSpec[T3],
        s4: ServiceSpec[T4],
        s5: ServiceSpec[T5],
        /,
        *,
        statement: Any | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self: ServiceGroup[T1, T2, T3, T4, T5, T6],
        s1: ServiceSpec[T1],
        s2: ServiceSpec[T2],
        s3: ServiceSpec[T3],
        s4: ServiceSpec[T4],
        s5: ServiceSpec[T5],
        s6: ServiceSpec[T6],
        /,
        *,
        statement: Any | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *specs: Any,
        statement: Any | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> None: ...

    def __init__(
        self,
        *specs: Any,
        statement: Any | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> None:
        """Initialize a ServiceGroup with service specifications and default configuration."""
        self.specs = specs
        self.statement = statement
        self.error_messages = error_messages
        self.load = load
        self.execution_options = execution_options
        self.uniquify = uniquify
        self.count_with_window_function = count_with_window_function

    def new(
        self,
        *,
        session: AsyncSession | Session | None = None,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
        connection: Any | None = None,
        statement: Select[tuple[ModelT]] | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> _ServiceGroupContext[Unpack[Ts]]:
        """Instantiate an acquisition context for services in this group."""
        load_spec: Any = load if load is not None else self.load
        return cast(
            "_ServiceGroupContext[Unpack[Ts]]",
            _ServiceGroupContext(
                self.specs,
                session=session,
                config=config,
                connection=connection,
                statement=statement if statement is not None else self.statement,
                error_messages=error_messages if error_messages is not Empty else self.error_messages,
                load=load_spec,
                execution_options=execution_options if execution_options is not None else self.execution_options,
                uniquify=uniquify if uniquify is not None else self.uniquify,
                count_with_window_function=(
                    count_with_window_function
                    if count_with_window_function is not None
                    else self.count_with_window_function
                ),
            ),
        )

    @overload
    def provide(
        self,
        *,
        config: SQLAlchemySyncConfig,
        statement: Select[tuple[ModelT]] | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> Callable[..., Generator[tuple[Unpack[Ts]], None, None]]: ...

    @overload
    def provide(
        self,
        *,
        config: SQLAlchemyAsyncConfig | None = None,
        statement: Select[tuple[ModelT]] | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> Callable[..., AsyncGenerator[tuple[Unpack[Ts]], None]]: ...

    def provide(
        self,
        *,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
        statement: Select[tuple[ModelT]] | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
    ) -> Callable[..., AsyncGenerator[tuple[Unpack[Ts]], None] | Generator[tuple[Unpack[Ts]], None, None]]:
        """Create a dependency injection provider for this service group."""
        is_sync = config is not None and config.__class__.__name__.endswith("SyncConfig")
        session_dependency_key = getattr(config, "session_dependency_key", "db_session") if config else "db_session"

        if is_sync:

            def provide_service_group_sync(
                *args: Any,
                **kwargs: Any,
            ) -> Generator[tuple[Unpack[Ts]], None, None]:
                db_session = cast("Session | None", args[0] if args else kwargs.get(session_dependency_key))
                with self.new(
                    session=db_session,
                    config=config,
                    statement=statement,
                    error_messages=error_messages,
                    load=load,
                    execution_options=execution_options,
                    uniquify=uniquify,
                    count_with_window_function=count_with_window_function,
                ) as services:
                    yield services

            session_param = inspect.Parameter(
                name=session_dependency_key,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=inspect.Parameter.empty,
            )
            provide_service_group_sync.__name__ = "provide_service_group"
            setattr(
                provide_service_group_sync,
                "__signature__",
                inspect.Signature(
                    parameters=[session_param],
                    return_annotation=cast("Any", Generator[tuple[Unpack[Ts]], None, None]),
                ),
            )
            provide_service_group_sync.__annotations__ = {
                session_dependency_key: Any,
                "return": Generator[tuple[Unpack[Ts]], None, None],
            }
            return provide_service_group_sync

        async def provide_service_group_async(
            *args: Any,
            **kwargs: Any,
        ) -> AsyncGenerator[tuple[Unpack[Ts]], None]:
            db_session = cast("AsyncSession | None", args[0] if args else kwargs.get(session_dependency_key))
            async with self.new(
                session=db_session,
                config=config,
                statement=statement,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=uniquify,
                count_with_window_function=count_with_window_function,
            ) as services:
                yield services

        session_param = inspect.Parameter(
            name=session_dependency_key,
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=inspect.Parameter.empty,
        )
        provide_service_group_async.__name__ = "provide_service_group"
        setattr(
            provide_service_group_async,
            "__signature__",
            inspect.Signature(
                parameters=[session_param],
                return_annotation=cast("Any", AsyncGenerator[tuple[Unpack[Ts]], None]),
            ),
        )
        provide_service_group_async.__annotations__ = {
            session_dependency_key: Any,
            "return": AsyncGenerator[tuple[Unpack[Ts]], None],
        }
        return provide_service_group_async


@overload
def provide_services(
    s1: ServiceSpec[T1],
    /,
    *,
    session: AsyncSession | Session | None = None,
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
    connection: Any | None = None,
    statement: Select[tuple[ModelT]] | None = None,
    error_messages: ErrorMessages | EmptyType | None = Empty,
    load: LoadSpec | None = None,
    execution_options: dict[str, Any] | None = None,
    uniquify: bool | None = None,
    count_with_window_function: bool | None = None,
) -> _ServiceGroupContext[T1]: ...


@overload
def provide_services(
    s1: ServiceSpec[T1],
    s2: ServiceSpec[T2],
    /,
    *,
    session: AsyncSession | Session | None = None,
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
    connection: Any | None = None,
    statement: Select[tuple[ModelT]] | None = None,
    error_messages: ErrorMessages | EmptyType | None = Empty,
    load: LoadSpec | None = None,
    execution_options: dict[str, Any] | None = None,
    uniquify: bool | None = None,
    count_with_window_function: bool | None = None,
) -> _ServiceGroupContext[T1, T2]: ...


@overload
def provide_services(
    s1: ServiceSpec[T1],
    s2: ServiceSpec[T2],
    s3: ServiceSpec[T3],
    /,
    *,
    session: AsyncSession | Session | None = None,
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
    connection: Any | None = None,
    statement: Select[tuple[ModelT]] | None = None,
    error_messages: ErrorMessages | EmptyType | None = Empty,
    load: LoadSpec | None = None,
    execution_options: dict[str, Any] | None = None,
    uniquify: bool | None = None,
    count_with_window_function: bool | None = None,
) -> _ServiceGroupContext[T1, T2, T3]: ...


@overload
def provide_services(
    s1: ServiceSpec[T1],
    s2: ServiceSpec[T2],
    s3: ServiceSpec[T3],
    s4: ServiceSpec[T4],
    /,
    *,
    session: AsyncSession | Session | None = None,
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
    connection: Any | None = None,
    statement: Select[tuple[ModelT]] | None = None,
    error_messages: ErrorMessages | EmptyType | None = Empty,
    load: LoadSpec | None = None,
    execution_options: dict[str, Any] | None = None,
    uniquify: bool | None = None,
    count_with_window_function: bool | None = None,
) -> _ServiceGroupContext[T1, T2, T3, T4]: ...


@overload
def provide_services(
    s1: ServiceSpec[T1],
    s2: ServiceSpec[T2],
    s3: ServiceSpec[T3],
    s4: ServiceSpec[T4],
    s5: ServiceSpec[T5],
    /,
    *,
    session: AsyncSession | Session | None = None,
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
    connection: Any | None = None,
    statement: Select[tuple[ModelT]] | None = None,
    error_messages: ErrorMessages | EmptyType | None = Empty,
    load: LoadSpec | None = None,
    execution_options: dict[str, Any] | None = None,
    uniquify: bool | None = None,
    count_with_window_function: bool | None = None,
) -> _ServiceGroupContext[T1, T2, T3, T4, T5]: ...


@overload
def provide_services(
    s1: ServiceSpec[T1],
    s2: ServiceSpec[T2],
    s3: ServiceSpec[T3],
    s4: ServiceSpec[T4],
    s5: ServiceSpec[T5],
    s6: ServiceSpec[T6],
    /,
    *,
    session: AsyncSession | Session | None = None,
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
    connection: Any | None = None,
    statement: Select[tuple[ModelT]] | None = None,
    error_messages: ErrorMessages | EmptyType | None = Empty,
    load: LoadSpec | None = None,
    execution_options: dict[str, Any] | None = None,
    uniquify: bool | None = None,
    count_with_window_function: bool | None = None,
) -> _ServiceGroupContext[T1, T2, T3, T4, T5, T6]: ...


@overload
def provide_services(
    *specs: Any,
    session: AsyncSession | Session | None = None,
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
    connection: Any | None = None,
    statement: Select[tuple[ModelT]] | None = None,
    error_messages: ErrorMessages | EmptyType | None = Empty,
    load: LoadSpec | None = None,
    execution_options: dict[str, Any] | None = None,
    uniquify: bool | None = None,
    count_with_window_function: bool | None = None,
) -> Any: ...


def provide_services(
    *specs: Any,
    session: AsyncSession | Session | None = None,
    config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
    connection: Any | None = None,
    statement: Select[tuple[ModelT]] | None = None,
    error_messages: ErrorMessages | EmptyType | None = Empty,
    load: LoadSpec | None = None,
    execution_options: dict[str, Any] | None = None,
    uniquify: bool | None = None,
    count_with_window_function: bool | None = None,
) -> Any:
    """Acquire multiple services on a shared session.

    Args:
        *specs: Service classes or provider callables.
        session: An optional caller-owned database session.
        config: An optional SQLAlchemy config for auto-managing the session.
        connection: An optional ASGI connection for resolving request-scoped sessions.
        statement: An optional SQLAlchemy Select statement.
        error_messages: Optional custom error messages for services.
        load: Optional LoadSpec for eager loading relationships.
        execution_options: Optional execution options.
        uniquify: Optional flag to uniquify results.
        count_with_window_function: Optional flag to use window functions for counts.

    Returns:
        A context manager yielding a tuple of initialized services.
    """
    return cast("Any", ServiceGroup)(*specs).new(
        session=session,
        config=config,
        connection=connection,
        statement=statement,
        error_messages=error_messages,
        load=load,
        execution_options=execution_options,
        uniquify=uniquify,
        count_with_window_function=count_with_window_function,
    )
