"""Multi-service acquisition and dependency injection grouping."""

from __future__ import annotations

import importlib
import inspect
import sys
from contextlib import AsyncExitStack, ExitStack
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, ForwardRef, Generic, Literal, NamedTuple, TypeVar, cast, get_type_hints
from weakref import WeakKeyDictionary

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio.scoping import async_scoped_session
from sqlalchemy.orm import Session
from sqlalchemy.orm.scoping import scoped_session
from typing_extensions import Annotated, Self, get_args, get_origin

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.repository import Empty, EmptyType, ErrorMessages
from advanced_alchemy.service._async import (
    SQLAlchemyAsyncQueryService,
    SQLAlchemyAsyncRepositoryReadService,
    SQLAlchemyAsyncRepositoryService,
)
from advanced_alchemy.service._sync import (
    SQLAlchemySyncQueryService,
    SQLAlchemySyncRepositoryReadService,
    SQLAlchemySyncRepositoryService,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from contextlib import AbstractAsyncContextManager, AbstractContextManager
    from types import FrameType, TracebackType

    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.sync import SQLAlchemySyncConfig

__all__ = ("ServiceGroup",)

ServiceGroupT = TypeVar("ServiceGroupT", bound="ServiceGroup")

_ASYNC_SERVICE_BASES: tuple[type[Any], ...] = (
    SQLAlchemyAsyncQueryService,
    SQLAlchemyAsyncRepositoryReadService,
    SQLAlchemyAsyncRepositoryService,
)
_SYNC_SERVICE_BASES: tuple[type[Any], ...] = (
    SQLAlchemySyncQueryService,
    SQLAlchemySyncRepositoryReadService,
    SQLAlchemySyncRepositoryService,
)
_BUILTIN_NEW_FUNCS: frozenset[Any] = frozenset(
    getattr(cls.__dict__["new"], "__func__", cls.__dict__["new"])
    for cls in (*_ASYNC_SERVICE_BASES, *_SYNC_SERVICE_BASES)
    if "new" in cls.__dict__
)
_IGNORED_ANNOTATION_NAMES: frozenset[str] = frozenset({"session", "_instances"})


class _FieldPlan(NamedTuple):
    service_class: type[Any]
    init: tuple[bool, frozenset[str] | None]
    factory: tuple[bool, frozenset[str] | None] | None


class _GroupMetadata(NamedTuple):
    fields: Mapping[str, type[Any]]
    plans: Mapping[str, _FieldPlan]
    mode: Literal["async", "sync"] | None


_GROUP_METADATA: WeakKeyDictionary[type[ServiceGroup], _GroupMetadata] = WeakKeyDictionary()
_ANNOTATIONLIB: Any = importlib.import_module("annotationlib") if sys.version_info >= (3, 14) else None


def _unwrap_annotated(annotation: Any) -> Any:
    """Extract the underlying type from an Annotated hint if present."""
    while get_origin(annotation) is Annotated:
        args = get_args(annotation)
        if not args:
            break
        annotation = args[0]
    return annotation


def _is_classvar_hint(annotation: Any) -> bool:
    """Return whether a raw or resolved annotation represents ClassVar."""
    hint = annotation.__forward_arg__ if isinstance(annotation, ForwardRef) else annotation
    if isinstance(hint, str):
        stripped = hint.strip()
        return stripped.startswith(("ClassVar[", "typing.ClassVar[", "typing_extensions.ClassVar["))
    return get_origin(hint) is ClassVar


def _resolve_annotation(raw_annotation: Any, globalns: dict[str, Any], localns: dict[str, Any]) -> Any:
    """Resolve a raw, ForwardRef, or stringified type annotation in module and caller scopes."""
    annotation = raw_annotation.__forward_arg__ if isinstance(raw_annotation, ForwardRef) else raw_annotation
    seen: set[str] = set()
    while isinstance(annotation, str) and annotation not in seen:
        seen.add(annotation)
        annotation = eval(annotation, globalns, localns)  # noqa: S307
    if get_origin(_unwrap_annotated(annotation)) is ClassVar:
        return _unwrap_annotated(annotation)

    def hint() -> None:
        pass

    hint.__annotations__ = {"return": annotation}
    return _unwrap_annotated(get_type_hints(hint, globalns, localns, include_extras=True)["return"])


def _get_own_raw_annotations(cls: type[Any]) -> dict[str, Any]:
    """Return annotations declared directly on ``cls`` across Python versions (including PEP 649).

    Reads ``cls.__dict__`` directly rather than calling ``typing_extensions.get_annotations`` to
    preserve compatibility with ``typing-extensions>=4.0.0`` and Python 3.9 inheritance semantics.
    """
    if "__annotations__" in cls.__dict__:
        return dict(cls.__dict__["__annotations__"])  # noqa: RUF063
    if _ANNOTATIONLIB is not None and ("__annotate__" in cls.__dict__ or "__annotate_func__" in cls.__dict__):
        try:
            return dict(_ANNOTATIONLIB.get_annotations(cls, format=_ANNOTATIONLIB.Format.FORWARDREF))
        except (NameError, AttributeError):
            return dict(_ANNOTATIONLIB.get_annotations(cls, format=_ANNOTATIONLIB.Format.STRING))
    return {}


def _collect_caller_locals() -> dict[str, Any]:
    """Collect local namespaces from enclosing stack frames to resolve local class annotations."""
    merged: dict[str, Any] = {}
    frame: FrameType | None = inspect.currentframe()
    frames: list[FrameType] = []
    try:
        current = frame.f_back if frame is not None else None
        while current is not None:
            frames.append(current)
            current = current.f_back
        for caller_frame in reversed(frames):
            merged.update(caller_frame.f_locals)
    finally:
        del frame
        del frames
    return merged


def _classify_session_annotation(ann: Any) -> Literal["async", "sync"] | None:
    """Classify a session parameter annotation as async, sync, or undetermined."""
    if isinstance(ann, str):
        if "AsyncSession" in ann or "async_scoped_session" in ann:
            return "async"
        if "Session" in ann or "scoped_session" in ann:
            return "sync"
        return None

    unwrapped = _unwrap_annotated(ann)
    origin = get_origin(unwrapped)
    candidates = get_args(unwrapped) if origin is not None else (unwrapped,)
    for candidate in candidates:
        if isinstance(candidate, type):
            if issubclass(candidate, (AsyncSession, async_scoped_session)):
                return "async"
            if issubclass(candidate, (Session, scoped_session)):
                return "sync"
    return None


def _classify_service_mode(service_cls: type[Any]) -> Literal["async", "sync"] | None:
    """Infer whether a service class operates asynchronously or synchronously."""
    if issubclass(service_cls, _ASYNC_SERVICE_BASES):
        return "async"
    if issubclass(service_cls, _SYNC_SERVICE_BASES):
        return "sync"
    if issubclass(service_cls, ServiceGroup):
        metadata = _GROUP_METADATA.get(service_cls)
        return metadata.mode if metadata is not None else None

    custom_new = _get_custom_new_method(service_cls)
    if custom_new is not None:
        wrapped = getattr(custom_new, "__wrapped__", None)
        if inspect.isasyncgenfunction(custom_new) or inspect.iscoroutinefunction(custom_new):
            return "async"
        if inspect.isasyncgenfunction(wrapped) or inspect.iscoroutinefunction(wrapped):
            return "async"

    try:
        sig = inspect.signature(service_cls.__init__)
    except (TypeError, ValueError):
        return None
    session_param = sig.parameters.get("session")
    if session_param is None:
        params = [p for name, p in sig.parameters.items() if name != "self"]
        session_param = params[0] if params else None
    if session_param is None or session_param.annotation is inspect.Parameter.empty:
        return None
    return _classify_session_annotation(session_param.annotation)


def _get_custom_new_method(service_cls: type[Any]) -> Any:
    """Return a user-defined .new factory when a class overrides built-in SQLAlchemy .new."""
    for base_cls in service_cls.__mro__:
        if "new" not in base_cls.__dict__:
            continue
        attr = base_cls.__dict__["new"]
        func = getattr(attr, "__func__", attr)
        if func in _BUILTIN_NEW_FUNCS or base_cls is ServiceGroup:
            return None
        return func
    return None


def _build_call_plan(call: Any) -> tuple[bool, frozenset[str] | None]:
    """Inspect a constructor or factory once to determine session passing style and accepted kwargs."""
    try:
        sig = inspect.signature(call)
    except (TypeError, ValueError):
        return False, None

    params = sig.parameters
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    session_param = params.get("session")
    requires_positional_session = any(
        name not in {"self", "cls"}
        and param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        and param.default is inspect.Parameter.empty
        for name, param in params.items()
    )
    accepts_session_kw = (session_param is not None and session_param.kind != inspect.Parameter.POSITIONAL_ONLY) or (
        session_param is None and has_var_kw and not requires_positional_session
    )
    accepted_kw = (
        None
        if has_var_kw
        else frozenset(
            name
            for name, p in params.items()
            if name != "self" and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        )
    )
    return accepts_session_kw, accepted_kw


def _filter_service_kwargs(
    accepted_kw: frozenset[str] | None,
    group_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """Filter group-level service options down to those accepted by an individual service."""
    filtered: dict[str, Any] = {}
    for key, value in group_kwargs.items():
        if key == "error_messages" and value is Empty:
            continue
        if key != "error_messages" and value is None:
            continue
        if accepted_kw is None or key in accepted_kw:
            filtered[key] = value
    return filtered


def _instantiate_service(
    group_cls: type[ServiceGroup],
    name: str,
    service_cls: type[Any],
    session: Any,
    group_kwargs: Mapping[str, Any],
) -> Any:
    """Instantiate one declared member service using its cached constructor plan."""
    accepts_session_kw, accepted_kw = _GROUP_METADATA[group_cls].plans[name].init
    extra_kwargs = _filter_service_kwargs(accepted_kw, group_kwargs)
    if accepts_session_kw:
        return service_cls(session=session, **extra_kwargs)
    return service_cls(session, **extra_kwargs)


def _create_group_from_instances(
    group_cls: type[Any],
    session: Any,
    instances: dict[str, Any],
) -> Any:
    """Construct a ServiceGroup subclass instance populated with initialized services."""
    obj: Any = object.__new__(group_cls)
    obj.session = session
    object.__setattr__(obj, "_instances", instances)
    return obj


class _ServiceFieldDescriptor:
    """Descriptor exposing an initialized service instance stored on a ServiceGroup."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __get__(self, instance: ServiceGroup | None, owner: type[ServiceGroup]) -> Any:
        if instance is None:
            return self
        instances: dict[str, Any] = object.__getattribute__(instance, "_instances")
        try:
            return instances[self.name]
        except KeyError as exc:
            msg = f"{owner.__name__!r} object has no initialized service {self.name!r}"
            raise AttributeError(msg) from exc


class _ServiceGroupContext(Generic[ServiceGroupT]):
    """Sync and async context manager resolving a shared session for a ServiceGroup subclass."""

    __slots__ = (
        "_async_stack",
        "_config",
        "_connection",
        "_group_cls",
        "_group_kwargs",
        "_session",
        "_sync_stack",
    )

    def __init__(
        self,
        group_cls: type[ServiceGroupT],
        *,
        session: AsyncSession | async_scoped_session[AsyncSession] | Session | scoped_session[Session] | None,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None,
        connection: Any | None,
        group_kwargs: dict[str, Any],
    ) -> None:
        self._group_cls = group_cls
        self._session = session
        self._config = config
        self._connection = connection
        self._group_kwargs = group_kwargs
        self._async_stack: AsyncExitStack | None = None
        self._sync_stack: ExitStack | None = None

    async def __aenter__(self) -> ServiceGroupT:
        """Resolve an async session, enter any custom service contexts, and return the group."""
        if _GROUP_METADATA[self._group_cls].mode == "sync":
            msg = "A synchronous ServiceGroup cannot be entered with 'async with'. Use 'with' instead."
            raise ImproperConfigurationError(msg)

        stack = AsyncExitStack()
        try:
            session = await self._resolve_async_session(stack)
            instances = await self._build_async_instances(session, stack)
            self._async_stack = stack
            return cast("ServiceGroupT", _create_group_from_instances(self._group_cls, session, instances))
        except BaseException:
            await stack.__aexit__(*sys.exc_info())
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        """Exit managed session and service contexts in reverse entry order."""
        if self._async_stack is not None:
            return await self._async_stack.__aexit__(exc_type, exc_val, exc_tb)
        return None

    def __enter__(self) -> ServiceGroupT:
        """Resolve a sync session, enter any custom service contexts, and return the group."""
        if _GROUP_METADATA[self._group_cls].mode == "async":
            msg = "An asynchronous ServiceGroup cannot be entered with 'with'. Use 'async with' instead."
            raise ImproperConfigurationError(msg)

        stack = ExitStack()
        try:
            session = self._resolve_sync_session(stack)
            instances = self._build_sync_instances(session, stack)
            self._sync_stack = stack
            return cast("ServiceGroupT", _create_group_from_instances(self._group_cls, session, instances))
        except BaseException:
            stack.__exit__(*sys.exc_info())
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        """Exit managed session and service contexts in reverse entry order."""
        if self._sync_stack is not None:
            return self._sync_stack.__exit__(exc_type, exc_val, exc_tb)
        return None

    async def _resolve_async_session(
        self,
        stack: AsyncExitStack,
    ) -> AsyncSession | async_scoped_session[AsyncSession]:
        if self._session is not None:
            if isinstance(self._session, (Session, scoped_session)):
                msg = (
                    "A synchronous Session cannot be used in an async context. Use a synchronous 'with' block instead."
                )
                raise ImproperConfigurationError(msg)
            return self._session
        if self._connection is not None:
            provide_session_fn = getattr(self._config, "provide_session", None)
            if not callable(provide_session_fn):
                msg = "A valid config with 'provide_session' must be provided alongside connection."
                raise ImproperConfigurationError(msg)
            resolved: Any = provide_session_fn(self._connection.app.state, self._connection.scope)
            if isinstance(resolved, (Session, scoped_session)):
                msg = (
                    "A synchronous Session cannot be used in an async context. Use a synchronous 'with' block instead."
                )
                raise ImproperConfigurationError(msg)
            return cast("AsyncSession | async_scoped_session[AsyncSession]", resolved)
        if self._config is not None and hasattr(self._config, "get_session"):
            session_ctx = self._config.get_session()
            if hasattr(session_ctx, "__aenter__"):
                return cast(
                    "AsyncSession | async_scoped_session[AsyncSession]",
                    await stack.enter_async_context(cast("AbstractAsyncContextManager[Any]", session_ctx)),
                )
            msg = "Config returned a synchronous session context in an async 'async with' block."
            raise ImproperConfigurationError(msg)
        msg = "One of session, config, or connection must be provided to acquire services."
        raise ImproperConfigurationError(msg)

    def _resolve_sync_session(self, stack: ExitStack) -> Session | scoped_session[Session]:
        if self._session is not None:
            if isinstance(self._session, (AsyncSession, async_scoped_session)):
                msg = "An asynchronous AsyncSession cannot be used in a sync context. Use 'async with' instead."
                raise ImproperConfigurationError(msg)
            return self._session
        if self._connection is not None:
            provide_session_fn = getattr(self._config, "provide_session", None)
            if not callable(provide_session_fn):
                msg = "A valid config with 'provide_session' must be provided alongside connection."
                raise ImproperConfigurationError(msg)
            resolved: Any = provide_session_fn(self._connection.app.state, self._connection.scope)
            if isinstance(resolved, (AsyncSession, async_scoped_session)):
                msg = "An asynchronous AsyncSession cannot be used in a sync context. Use 'async with' instead."
                raise ImproperConfigurationError(msg)
            return cast("Session | scoped_session[Session]", resolved)
        if self._config is not None and hasattr(self._config, "get_session"):
            session_ctx = self._config.get_session()
            if hasattr(session_ctx, "__enter__"):
                return cast(
                    "Session | scoped_session[Session]",
                    stack.enter_context(cast("AbstractContextManager[Any]", session_ctx)),
                )
            msg = "Config returned an asynchronous session context in a sync 'with' block."
            raise ImproperConfigurationError(msg)
        msg = "One of session, config, or connection must be provided to acquire services."
        raise ImproperConfigurationError(msg)

    async def _build_async_instances(
        self,
        session: AsyncSession | async_scoped_session[AsyncSession],
        stack: AsyncExitStack,
    ) -> dict[str, Any]:
        instances: dict[str, Any] = {}
        for name, plan in _GROUP_METADATA[self._group_cls].plans.items():
            service_cls = plan.service_class
            if plan.factory is None:
                instances[name] = _instantiate_service(self._group_cls, name, service_cls, session, self._group_kwargs)
                continue
            accepts_session_kw, accepted_kw = plan.factory
            kwargs = _filter_service_kwargs(accepted_kw, self._group_kwargs)
            ctx = (
                service_cls.new(session=session, **kwargs) if accepts_session_kw else service_cls.new(session, **kwargs)
            )
            if inspect.isawaitable(ctx):
                ctx = await ctx
            if hasattr(ctx, "__aenter__"):
                instances[name] = await stack.enter_async_context(ctx)
            elif hasattr(ctx, "__enter__"):
                instances[name] = stack.enter_context(ctx)
            else:
                instances[name] = ctx
        return instances

    def _build_sync_instances(
        self,
        session: Session | scoped_session[Session],
        stack: ExitStack,
    ) -> dict[str, Any]:
        instances: dict[str, Any] = {}
        for name, plan in _GROUP_METADATA[self._group_cls].plans.items():
            service_cls = plan.service_class
            if plan.factory is None:
                instances[name] = _instantiate_service(self._group_cls, name, service_cls, session, self._group_kwargs)
                continue
            accepts_session_kw, accepted_kw = plan.factory
            kwargs = _filter_service_kwargs(accepted_kw, self._group_kwargs)
            ctx = (
                service_cls.new(session=session, **kwargs) if accepts_session_kw else service_cls.new(session, **kwargs)
            )
            if inspect.isawaitable(ctx) or (hasattr(ctx, "__aenter__") and not hasattr(ctx, "__enter__")):
                if inspect.iscoroutine(ctx):
                    ctx.close()
                msg = f"Service {service_cls.__name__} defines an async factory and cannot run in a sync context."
                raise ImproperConfigurationError(msg)
            if hasattr(ctx, "__enter__"):
                instances[name] = stack.enter_context(ctx)
            else:
                instances[name] = ctx
        return instances


class ServiceGroup:
    """Base class for composing multiple repository services on one shared SQLAlchemy session.

    Declare each service as an annotated attribute on a ``ServiceGroup`` subclass:

    .. code-block:: python

        class AuthServices(ServiceGroup):
            users: UserService
            roles: RoleService
    """

    __slots__ = ("_instances", "session")

    _instances: dict[str, Any]
    session: Any

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Collect service annotations, validate mode homogeneity, and install descriptors."""
        super().__init_subclass__(**kwargs)

        inherited_fields: dict[str, type[Any]] = {}
        inherited_plans: dict[str, _FieldPlan] = {}
        for base_cls in reversed(cls.__mro__):
            if base_cls is not cls and issubclass(base_cls, ServiceGroup) and base_cls is not ServiceGroup:
                inherited_fields.update(_GROUP_METADATA[base_cls].fields)
                inherited_plans.update(_GROUP_METADATA[base_cls].plans)

        raw_annotations = _get_own_raw_annotations(cls)
        module = sys.modules.get(cls.__module__)
        globalns: dict[str, Any] = dict(vars(module)) if module is not None else {}
        localns = {**_collect_caller_locals(), **vars(cls)}

        new_fields: dict[str, type[Any]] = {}
        new_plans: dict[str, _FieldPlan] = {}
        for attr_name, raw_hint in raw_annotations.items():
            if attr_name in _IGNORED_ANNOTATION_NAMES or _is_classvar_hint(raw_hint):
                continue
            try:
                resolved = _resolve_annotation(raw_hint, globalns, localns)
            except Exception as exc:
                msg = f"Unable to resolve service annotation {attr_name!r} on {cls.__name__}: {exc}"
                raise ImproperConfigurationError(msg) from exc
            if get_origin(resolved) is ClassVar:
                continue
            if not isinstance(resolved, type):
                msg = f"ServiceGroup field {attr_name!r} on {cls.__name__} must resolve to a service class, got {resolved!r}."
                raise ImproperConfigurationError(msg)
            service_cls = cast("type[Any]", resolved)
            new_fields[attr_name] = service_cls
            new_plans[attr_name] = _FieldPlan(
                service_cls,
                _build_call_plan(service_cls.__init__),
                _build_call_plan(service_cls.new)
                if issubclass(service_cls, ServiceGroup) or _get_custom_new_method(service_cls) is not None
                else None,
            )

        merged_fields = {**inherited_fields, **new_fields}
        merged_plans = {**inherited_plans, **new_plans}

        modes: set[Literal["async", "sync"]] = {
            mode for svc in merged_fields.values() if (mode := _classify_service_mode(svc)) is not None
        }
        if len(modes) > 1:
            msg = f"ServiceGroup {cls.__name__} cannot mix async and sync service classes."
            raise ImproperConfigurationError(msg)

        _GROUP_METADATA[cls] = _GroupMetadata(
            MappingProxyType(merged_fields), MappingProxyType(merged_plans), next(iter(modes), None)
        )

        for attr_name in new_fields:
            setattr(cls, attr_name, _ServiceFieldDescriptor(attr_name))

    def __init__(
        self,
        session: AsyncSession | async_scoped_session[AsyncSession] | Session | scoped_session[Session],
        *,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
        auto_expunge: bool | None = None,
        auto_refresh: bool | None = None,
        auto_commit: bool | None = None,
        wrap_exceptions: bool | None = None,
    ) -> None:
        """Instantiate every declared service on the provided SQLAlchemy session."""
        cls = type(self)
        metadata = _GROUP_METADATA.get(cls)
        fields: Mapping[str, type[Any]] = metadata.fields if metadata is not None else {}
        if not fields:
            msg = f"ServiceGroup subclass {cls.__name__} declares no service attributes."
            raise ImproperConfigurationError(msg)
        if session is None:  # pyright: ignore[reportUnnecessaryComparison]
            msg = f"{cls.__name__} requires an active SQLAlchemy Session or AsyncSession."  # type: ignore[unreachable]
            raise ImproperConfigurationError(msg)
        group_mode = metadata.mode if metadata is not None else None
        if group_mode == "async" and isinstance(session, (Session, scoped_session)):
            msg = f"{cls.__name__} declares async services and cannot accept a synchronous Session."
            raise ImproperConfigurationError(msg)
        if group_mode == "sync" and isinstance(session, (AsyncSession, async_scoped_session)):
            msg = f"{cls.__name__} declares sync services and cannot accept an asynchronous AsyncSession."
            raise ImproperConfigurationError(msg)

        group_kwargs: dict[str, Any] = {
            "error_messages": error_messages,
            "execution_options": execution_options,
            "uniquify": uniquify,
            "count_with_window_function": count_with_window_function,
            "auto_expunge": auto_expunge,
            "auto_refresh": auto_refresh,
            "auto_commit": auto_commit,
            "wrap_exceptions": wrap_exceptions,
        }
        instances = {
            name: _instantiate_service(cls, name, svc_cls, session, group_kwargs) for name, svc_cls in fields.items()
        }
        self.session = session
        object.__setattr__(self, "_instances", instances)

    @classmethod
    def new(
        cls,
        *,
        session: AsyncSession | async_scoped_session[AsyncSession] | Session | scoped_session[Session] | None = None,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | None = None,
        connection: Any | None = None,
        error_messages: ErrorMessages | EmptyType | None = Empty,
        execution_options: dict[str, Any] | None = None,
        uniquify: bool | None = None,
        count_with_window_function: bool | None = None,
        auto_expunge: bool | None = None,
        auto_refresh: bool | None = None,
        auto_commit: bool | None = None,
        wrap_exceptions: bool | None = None,
    ) -> _ServiceGroupContext[Self]:
        """Acquire a session-managed or caller-bound context yielding an instance of this group."""
        if cls not in _GROUP_METADATA or not _GROUP_METADATA[cls].fields:
            msg = f"ServiceGroup subclass {cls.__name__} declares no service attributes."
            raise ImproperConfigurationError(msg)
        group_kwargs: dict[str, Any] = {
            "error_messages": error_messages,
            "execution_options": execution_options,
            "uniquify": uniquify,
            "count_with_window_function": count_with_window_function,
            "auto_expunge": auto_expunge,
            "auto_refresh": auto_refresh,
            "auto_commit": auto_commit,
            "wrap_exceptions": wrap_exceptions,
        }
        return _ServiceGroupContext(
            cls,
            session=session,
            config=config,
            connection=connection,
            group_kwargs=group_kwargs,
        )

    @classmethod
    def service_fields(cls) -> Mapping[str, type[Any]]:
        """Return a read-only mapping of declared service attribute names to service classes."""
        metadata = _GROUP_METADATA.get(cls)
        return metadata.fields if metadata is not None else MappingProxyType({})

    @classmethod
    def is_async_group(cls) -> bool | None:
        """Return ``True`` for async groups, ``False`` for sync groups, or ``None`` when undetermined."""
        metadata = _GROUP_METADATA.get(cls)
        mode = metadata.mode if metadata is not None else None
        if mode == "async":
            return True
        if mode == "sync":
            return False
        return None
