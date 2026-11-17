"""Declarative query filters with inferred relationship loading."""

from __future__ import annotations

import inspect as pyinspect
from collections.abc import Collection, Mapping
from functools import lru_cache
from typing import TYPE_CHECKING, Any, ClassVar, Generic, cast, get_type_hints

from sqlalchemy import ColumnElement, Select, inspect, or_
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.ext.associationproxy import AssociationProxyInstance
from sqlalchemy.orm import joinedload, selectinload, subqueryload
from typing_extensions import TypeVar

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.filters import (
    CursorFilter,
    CursorKey,
    FilterGroup,
    LimitOffsetFilter,
    OrderByFilter,
    PaginationFilter,
    RelationshipFilter,
    SearchFilter,
    StatementFilter,
    StatementTypeT,
)
from advanced_alchemy.repository._util import resolve_generic_type_args
from advanced_alchemy.utils.dependencies import (
    CursorDefaults,
    CursorSettings,
    FilterConfig,
    FilterFieldSpec,
    FilterFieldsSpec,
    build_field_filter,
    build_order_by_filters,
    normalize_sort_field,
    normalize_sort_fields,
    resolve_cursor_settings,
    resolve_filter_fields,
    resolve_pagination_bounds,
)

if TYPE_CHECKING:
    from sqlalchemy.sql.base import ExecutableOption

__all__ = ("FilterSet",)

ModelT = TypeVar("ModelT")
_HOOK_PARAMETER_COUNT = 2
_CONSTRUCTOR_OPTIONS = {"cursor_defaults", "require_cursor_secret"}
_STANDARD_PARAMETERS = {
    "cursor",
    "page",
    "pageSize",
    "page_size",
    "orderBy",
    "order_by",
    "sortOrder",
    "sort_order",
    "search",
    "searchString",
    "search_string",
}


class FilterSet(StatementFilter, Generic[ModelT]):
    """Reusable typed filters for one mapped model.

    Declare ``filter_fields`` with dotted model paths and instantiate with typed
    double-underscore parameters, such as ``orders__price__ge=10``. Different
    fields match independently; operators on one field share a related row.
    Framework providers validate HTTP values before constructing this object.

    Args:
        cursor_defaults: Application-wide cursor token options, used where the configuration sets none.
        require_cursor_secret: Refuse to issue or accept unsigned cursor tokens.
        **values: Typed field values and configured pagination, ordering or search values.

    Raises:
        ValueError: An unknown query parameter is supplied.
        ImproperConfigurationError: The model, declared fields, or cursor options are invalid.
    """

    model_type: ClassVar[type[Any]]
    filter_fields: ClassVar[FilterFieldsSpec] = ()
    sort_fields: ClassVar[Collection[str]] = ()
    search_fields: ClassVar[Collection[str]] = ()
    config: ClassVar[FilterConfig] = {}
    auto_load: ClassVar[bool] = True

    def __init__(
        self, *, cursor_defaults: CursorDefaults | None = None, require_cursor_secret: bool = False, **values: Any
    ) -> None:
        specs = self.parameter_specs()
        accepted = {s.param_name for s in specs} | _STANDARD_PARAMETERS
        unknown = values.keys() - accepted
        if unknown:
            msg = f"Unknown filter parameters: {', '.join(sorted(unknown))}"
            raise ValueError(msg)
        self._values = dict(values)
        self._filters = tuple(self._compile_filters(cursor_defaults, require_cursor_secret))

    @classmethod
    def filter_config(cls) -> FilterConfig:
        """Return a copy of the declared framework filter configuration."""
        config = dict(cls.config)
        for name in FilterConfig.__annotations__:
            if name in {"filter_fields", "sort_fields", "search"}:
                continue
            if hasattr(cls, name):
                config[name] = getattr(cls, name)
        if cls.filter_fields:
            config["filter_fields"] = cls.filter_fields
        if cls.sort_fields:
            config["sort_fields"] = cls.sort_fields
        if cls.search_fields:
            config["search"] = cls.search_fields
        return cast("FilterConfig", config)

    @classmethod
    @lru_cache(maxsize=128)
    def parameter_specs(cls) -> tuple[FilterFieldSpec, ...]:
        """Return query parameter metadata shared by framework adapters."""
        model = cls._model()
        config = cls.filter_config()
        resolve_pagination_bounds(config)
        fields = config.get("filter_fields", ())
        entries = fields.items() if isinstance(fields, Mapping) else ((f, None) for f in fields)
        specs: list[FilterFieldSpec] = []
        for path, operators in entries:
            normalized = _resolved_path(model, path)
            declaration = {normalized: operators} if operators is not None else (normalized,)
            specs.extend(
                FilterFieldSpec(
                    field_path=spec.field_path,
                    rel_path=spec.rel_path,
                    leaf_field=spec.leaf_field,
                    operator=spec.operator,
                    param_name=path.replace(".", "__") + "__" + spec.operator,
                    value_type=spec.value_type,
                )
                for spec in resolve_filter_fields(cast("Any", declaration), model)
            )
        for name, hint in cls._custom_hooks().items():
            specs.append(
                FilterFieldSpec(
                    field_path=name, rel_path=(), leaf_field=name, operator="eq", param_name=name, value_type=hint
                )
            )
        names = [s.param_name for s in specs]
        if len(names) != len(set(names)) or set(names) & (_STANDARD_PARAMETERS | _CONSTRUCTOR_OPTIONS):
            msg = "FilterSet query parameter names must be distinct"
            raise ImproperConfigurationError(msg)
        for path in cls._search_paths(config):
            _resolved_path(model, path)
        if sort_fields := config.get("sort_fields"):
            normalize_sort_fields([_resolved_path(model, path) for path in sort_fields], model)
        if config.get("pagination_type") == "cursor":
            cls._cursor_settings()
        return tuple(specs)

    def to_statement_filters(self) -> list[StatementFilter | ColumnElement[bool]]:
        """Return the compiled primitive filters for explicit query integration.

        Returns:
            A fresh list of native filters and custom SQL expressions.
        """
        return list(self._filters)

    def inferred_load(self, dialect: Any = None) -> list[ExecutableOption]:
        """Infer loading options for active relationship paths.

        Args:
            dialect: Optional SQLAlchemy dialect, used for composite-key SQL Server loading.

        Returns:
            Joined to-one, select-in collection, or composite SQL Server subquery options.
        """
        options: list[ExecutableOption] = []
        for path in self._active_relationship_paths():
            current: Any = self._model()
            option = None
            for segment in path:
                prop: Any = inspect(current).mapper.relationships[segment]
                if prop.lazy in {"write_only", "dynamic"}:
                    break
                attr = getattr(current, segment)
                composite_mssql = (
                    getattr(dialect, "name", dialect) == "mssql" and len(inspect(current).mapper.primary_key) > 1
                )
                strategy = (
                    subqueryload if prop.uselist and composite_mssql else selectinload if prop.uselist else joinedload
                )
                option = strategy(attr) if option is None else getattr(option, strategy.__name__)(attr)
                current = prop.mapper.class_
            if option is not None:
                options.append(option)
        return options

    @property
    def load(self) -> list[ExecutableOption]:
        """Inferred loading options for explicit statement-filter expansion."""
        return self.inferred_load()

    def append_to_statement(
        self, statement: StatementTypeT, model: type[Any], *args: Any, **kwargs: Any
    ) -> StatementTypeT:
        """Apply native filters to a statement.

        Args:
            statement: Statement being filtered.
            model: Expected mapped root model.
            *args: Reserved for the StatementFilter protocol.
            **kwargs: Reserved for the StatementFilter protocol.

        Returns:
            Filtered statement with inferred loaders for entity selects.
        """
        if model is not self._model():
            msg = "FilterSet model does not match the query model"
            raise ValueError(msg)
        for filter_ in self.to_statement_filters():
            statement = (
                filter_.append_to_statement(statement, model)
                if isinstance(filter_, StatementFilter)
                else cast("StatementTypeT", statement.where(filter_))
            )
        if isinstance(statement, Select):
            from advanced_alchemy.repository._util import (
                _filterset_loader_options,  # pyright: ignore[reportPrivateUsage]
            )

            statement = cast(
                "StatementTypeT",
                _filterset_loader_options(
                    statement,
                    [self],
                    kwargs.get("dialect") or DefaultDialect(),
                    paginated=any(isinstance(filter_, PaginationFilter) for filter_ in self._filters)
                    or getattr(statement, "_limit_clause", None) is not None
                    or getattr(statement, "_offset_clause", None) is not None,
                ),
            )
        return statement

    @classmethod
    def _model(cls) -> type[Any]:
        model = getattr(cls, "model_type", None)
        if not isinstance(model, type) or inspect(model, raiseerr=False) is None:
            msg = "FilterSet requires a mapped model_type or FilterSet[Model]"
            raise ImproperConfigurationError(msg)
        return model

    @classmethod
    def _custom_hooks(cls) -> dict[str, Any]:
        hooks: dict[str, Any] = {}
        for attr in dir(cls):
            if not attr.startswith("filter_") or attr in {"filter_config", "filter_fields"}:
                continue
            method = getattr(cls, attr)
            if not callable(method):
                continue
            parameters = list(pyinspect.signature(method).parameters.values())
            if len(parameters) != _HOOK_PARAMETER_COUNT:
                msg = f"{attr} must accept self and one typed value"
                raise ImproperConfigurationError(msg)
            hints = get_type_hints(method)
            hint = hints.get(parameters[1].name)
            if hint is None:
                msg = f"{attr} must annotate its value parameter"
                raise ImproperConfigurationError(msg)
            hooks[attr[len("filter_") :]] = hint
        return hooks

    def _compile_filters(
        self, cursor_defaults: CursorDefaults | None, require_cursor_secret: bool
    ) -> list[StatementFilter | ColumnElement[bool]]:
        """Build flat native filters, retaining explicit false and zero values.

        Returns:
            Primitive statement filters and custom SQL expressions.

        Raises:
            ValueError: Pagination or ordering values are invalid.
        """
        result: list[StatementFilter | ColumnElement[bool]] = []
        config = self.filter_config()
        model = self._model()
        groups: dict[str, tuple[tuple[str, ...], list[StatementFilter]]] = {}
        hooks = self._custom_hooks()
        for spec in self.parameter_specs():
            value = self._values.get(spec.param_name)
            if value is None:
                continue
            if spec.param_name in hooks:
                condition = getattr(self, "filter_" + spec.param_name)(value)
                if condition is not None:
                    if not isinstance(condition, (StatementFilter, ColumnElement)):
                        msg = f"Custom filter {spec.param_name!r} must return a filter or SQL expression"
                        raise ValueError(msg)
                    result.append(cast("StatementFilter | ColumnElement[bool]", condition))
                continue
            built = build_field_filter(
                spec,
                value,
                ignore_case=config.get("search_ignore_case", True),
                escape_wildcards=config.get("search_escape_wildcards", False),
            )
            if built is not None:
                groups.setdefault(spec.field_path, (spec.rel_path, []))[1].append(built)
        for group_path, filters in groups.values():
            if group_path:
                result.append(RelationshipFilter(group_path, filters))
            else:
                result.extend(filters)
        search = self._value("search", "searchString", "search_string")
        if search is not None and config.get("search"):
            branches: list[StatementFilter] = []
            for path in self._search_paths(config):
                normalized = _resolved_path(model, path)
                *rels, leaf = normalized.split(".")
                branch: StatementFilter = SearchFilter(
                    field_name=leaf,
                    value=search,
                    ignore_case=config.get("search_ignore_case", True),
                    escape_wildcards=config.get("search_escape_wildcards", False),
                )
                branches.append(RelationshipFilter(tuple(rels), [branch]) if rels else branch)
            result.append(FilterGroup(logical_operator=or_, filters=branches))
        ordering = self._ordering_filters(config)
        pagination_type = config.get("pagination_type")
        if pagination_type == "cursor":
            result.append(self._cursor_filter(ordering, config, cursor_defaults, require_cursor_secret))
        else:
            result.extend(ordering)
        if pagination_type == "limit_offset":
            page = self._value("page", default=1)
            size = self._page_size(config)
            if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                msg = "Pagination page and page size must be positive integers"
                raise ValueError(msg)
            result.append(LimitOffsetFilter(limit=size, offset=(page - 1) * size))
        return result

    def _value(self, *names: str, default: Any = None) -> Any:
        for name in names:
            if name in self._values and self._values[name] is not None:
                return self._values[name]
        return default

    @staticmethod
    def _search_paths(config: FilterConfig) -> Collection[str]:
        paths = config.get("search", ())
        return (paths,) if isinstance(paths, str) else paths

    def _ordering_filters(self, config: FilterConfig) -> list[StatementFilter]:
        result: list[StatementFilter] = []
        model = self._model()
        ordering = self._value("orderBy", "order_by")
        default_sort = config.get("sort_field")
        default_field = _resolved_path(model, normalize_sort_field(default_sort)) if default_sort else None
        allowed = config.get("sort_fields", ())
        if not allowed and default_sort:
            allowed = (normalize_sort_field(default_sort),)

        if ordering is not None:
            tokens: list[str] = ordering.split(",") if isinstance(ordering, str) else list(ordering)
            token_values: list[str] = []
            for token in tokens:
                sign = token[:1] if token[:1] in {"-", "+"} else ""
                raw = token[1:] if sign else token
                path = raw.replace("__", ".")
                if path not in allowed:
                    msg = f"Invalid sort field {path!r}"
                    raise ValueError(msg)
                token_values.append(sign + _resolved_path(model, path))
            normalized_tokens = token_values
        else:
            normalized_tokens = None
        if allowed:
            result.extend(
                build_order_by_filters(
                    normalized_tokens,
                    self._value("sortOrder", "sort_order"),
                    allowed_fields={_resolved_path(model, path) for path in allowed},
                    default_field=default_field,
                    default_order=config.get("sort_order", "desc"),
                    nulls=config.get("sort_nulls"),
                )
            )
        elif ordering is not None:
            msg = "No sort fields are configured"
            raise ValueError(msg)
        return result

    def _cursor_filter(
        self,
        ordering: list[StatementFilter],
        config: FilterConfig,
        cursor_defaults: CursorDefaults | None,
        require_cursor_secret: bool,
    ) -> CursorFilter:
        """Build the cursor filter from the validated ordering, page size, and cursor values."""
        secret, ttl, encrypted = self._cursor_settings().token_options(
            cursor_defaults, require_secret=require_cursor_secret
        )
        keys: list[CursorKey] = []
        for order in cast("list[OrderByFilter]", ordering):
            if isinstance(order.field_name, str) and "." in order.field_name:
                msg = f"Cursor pagination cannot order by relationship path {order.field_name!r}"
                raise ValueError(msg)
            keys.append(CursorKey(order.field_name, order.sort_order, order.nulls))
        return CursorFilter(
            keys,
            self._page_size(config),
            self._value("cursor"),
            secret,
            ttl=ttl,
            encrypted=encrypted,
        )

    @classmethod
    @lru_cache(maxsize=128)
    def _cursor_settings(cls) -> CursorSettings:
        return resolve_cursor_settings(cls.filter_config(), cls._model())

    def _page_size(self, config: FilterConfig) -> int:
        default_size, max_size = resolve_pagination_bounds(config)
        size = self._value("pageSize", "page_size", default=default_size)
        if not isinstance(size, int) or isinstance(size, bool) or size < 1:
            msg = "Pagination page and page size must be positive integers"
            raise ValueError(msg)
        if max_size is not None and size > max_size:
            msg = f"Pagination page size {size} exceeds maximum allowed size {max_size}"
            raise ValueError(msg)
        return size

    def _active_relationship_paths(self) -> tuple[tuple[str, ...], ...]:
        if not self.auto_load:
            return ()
        paths = {
            spec.rel_path
            for spec in self.parameter_specs()
            if spec.rel_path and self._values.get(spec.param_name) is not None
        }
        config = self.filter_config()
        if self._value("search", "searchString", "search_string") is not None:
            for path in self._search_paths(config):
                rels = tuple(_resolved_path(self._model(), path).split(".")[:-1])
                if rels:
                    paths.add(rels)
        for filter_ in self._filters:
            if isinstance(filter_, OrderByFilter) and isinstance(filter_.field_name, str) and "." in filter_.field_name:
                paths.add(tuple(filter_.field_name.split(".")[:-1]))
        return tuple(sorted(paths))

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        args = resolve_generic_type_args(cls, FilterSet)
        if (
            "model_type" not in cls.__dict__
            and args
            and isinstance(args[0], type)
            and inspect(args[0], raiseerr=False) is not None
        ):
            cls.model_type = args[0]


def _resolved_path(model: type[Any], path: str) -> str:
    """Expand association proxies into mapped relationship and column paths."""
    parts = path.split(".")
    if not parts or any(not p or not p.isidentifier() for p in parts):
        msg = f"Invalid field path {path!r}"
        raise ImproperConfigurationError(msg)
    current: Any = model
    resolved: list[str] = []
    for index, part in enumerate(parts):
        mapper: Any = inspect(current).mapper
        attr = getattr(current, part, None)
        if isinstance(attr, AssociationProxyInstance):
            proxy = cast("Any", attr)
            local: Any = proxy.local_attr
            resolved.append(local.key)
            current = local.property.mapper.class_
            remote: Any = proxy.remote_attr
            resolved.append(remote.key)
            if hasattr(remote.property, "mapper"):
                current = remote.property.mapper.class_
            elif index != len(parts) - 1:
                msg = f"Column in {path!r} cannot contain another field"
                raise ImproperConfigurationError(msg)
        elif part in mapper.relationships:
            resolved.append(part)
            current = mapper.relationships[part].mapper.class_
        elif index == len(parts) - 1 and (part in mapper.column_attrs or hasattr(attr, "expression")):
            resolved.append(part)
        else:
            msg = f"Unknown field {part!r} in {path!r}"
            raise ImproperConfigurationError(msg)
    return ".".join(resolved)
