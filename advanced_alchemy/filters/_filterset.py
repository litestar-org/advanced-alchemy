"""Tier 2 declarative filter facade — primitives plus :class:`FilterSet`.

Hosts the building blocks and the user-facing :class:`FilterSet` base
class:

* :data:`UNSET` — sentinel distinct from ``None`` for optional defaults.
* :class:`FieldSpec` — frozen description of a resolved declared field.
* :class:`BaseFieldFilter` — abstract base for typed field filters.
* :class:`FilterSet` — declarative facade with class-creation validation.

The concrete field filters (:class:`StringFilter`, :class:`NumberFilter`,
…) live in ``_fields`` and depend on the primitives here. ``FilterSet``
imports concrete filters lazily inside its auto-generation path so the
two modules stay in a strict dependency order.
"""

import keyword
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Final,
    Optional,
    cast,
)

from sqlalchemy.orm import class_mapper
from typing_extensions import Self

from advanced_alchemy.exceptions import (
    FilterValidationError,
    ImproperConfigurationError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Union

    from sqlalchemy import Column
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy.filters._base import StatementFilter

__all__ = (
    "UNSET",
    "BaseFieldFilter",
    "FieldSpec",
    "FilterSet",
)


class _UnsetSentinel:
    """Type for the :data:`UNSET` singleton.

    Defined as a class so :data:`UNSET` participates in identity checks
    (``value is UNSET``) without colliding with user-supplied values.
    """

    _instance: "Optional[_UnsetSentinel]" = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cast("Self", cls._instance)

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET: Final = _UnsetSentinel()


@dataclass(frozen=True)
class FieldSpec:
    """Resolved declaration for a FilterSet field.

    Built once per ``FilterSet`` subclass at class-creation time and
    frozen so subsequent reads are cheap and tamper-proof.

    Attributes:
        path: Tuple of attribute names from the FilterSet's ``Meta.model``
            to the leaf column. A single-element tuple for column fields;
            longer tuples encode relationship traversal. Empty for
            special filters that do not bind to a column path.
        column: The terminal SQLAlchemy ``Column`` reached by ``path``,
            or ``None`` for filters whose binding is not column-based
            (e.g. :class:`OrderingFilter`, which validates its own list).
        filter: The :class:`BaseFieldFilter` instance declared on the class.
    """

    path: tuple[str, ...]
    column: "Optional[Column[Any]]"
    filter: "BaseFieldFilter"


class BaseFieldFilter(ABC):
    """Abstract base for typed field filters.

    Subclasses describe which lookups they support, how to coerce raw
    string values into the right Python type, and how to compile a
    ``(path, lookup, value)`` triple into a Tier 1 leaf
    :class:`StatementFilter`. Wrapping into :class:`RelationshipFilter`
    for relationship traversal is the FilterSet's job, not the field
    filter's.

    Subclass contract:

    * Set :attr:`supported_lookups` to the full catalog of lookups the
      filter understands.
    * Optionally override :attr:`default_lookup` (defaults to ``"exact"``).
    * Implement :meth:`coerce` to parse raw values.
    * Implement :meth:`compile` to emit the leaf filter.
    """

    supported_lookups: ClassVar[frozenset[str]] = frozenset()
    default_lookup: ClassVar[str] = "exact"
    binds_to_column: ClassVar[bool] = True
    """Whether ``FilterSet`` should resolve a column path for this filter.

    Most field filters operate on a single column reachable from
    ``Meta.model`` via dotted attribute traversal. Special-case filters
    (e.g. :class:`OrderingFilter`) declare their own column allowlist
    and set this to ``False`` so the FilterSet machinery skips path
    resolution.
    """

    def __init__(
        self,
        *,
        lookups: "Optional[Sequence[str]]" = None,
        default: Any = UNSET,
    ) -> None:
        if lookups is None:
            self.lookups: frozenset[str] = frozenset(self.supported_lookups)
        else:
            requested = frozenset(lookups)
            if not requested:
                msg = f"{type(self).__name__} requires at least one lookup."
                raise ImproperConfigurationError(detail=msg)
            unsupported = requested - self.supported_lookups
            if unsupported:
                msg = (
                    f"{type(self).__name__} does not support lookups: "
                    f"{sorted(unsupported)}. Supported: "
                    f"{sorted(self.supported_lookups)}."
                )
                raise ImproperConfigurationError(detail=msg)
            self.lookups = requested
        self.default_value: Any = default

    @property
    def effective_default_lookup(self) -> str:
        """Lookup applied when a query key has no ``__lookup`` suffix.

        Falls back to the smallest enabled lookup if the class-level
        :attr:`default_lookup` was filtered out by ``lookups=…``.
        """
        if self.default_lookup in self.lookups:
            return self.default_lookup
        return next(iter(sorted(self.lookups)))

    @abstractmethod
    def coerce(self, raw: "Union[str, Sequence[str]]", lookup: str) -> Any:
        """Parse a raw query-string value into the right Python type.

        Args:
            raw: Single value or list of values from the query string.
            lookup: The lookup the value belongs to (e.g. ``"in"``,
                ``"between"``); allows lookup-aware coercion.

        Raises:
            ValueError: If ``raw`` cannot be coerced.
        """

    @abstractmethod
    def compile(
        self,
        path: tuple[str, ...],
        lookup: str,
        value: Any,
    ) -> "StatementFilter":
        """Compile a leaf filter for the column at ``path[-1]``.

        Args:
            path: Resolved field path (length 1 for column fields,
                longer for relationship traversal).
            lookup: The selected lookup.
            value: The coerced Python value.

        Returns:
            A Tier 1 :class:`StatementFilter` (e.g.
            :class:`SearchFilter`, :class:`ComparisonFilter`,
            :class:`CollectionFilter`, :class:`NullFilter`). Relationship
            wrapping is handled by the FilterSet's compilation pass.
        """


_DEFAULT_MAX_RELATIONSHIP_DEPTH = 2


class _FilterSetMeta:
    """Default ``FilterSet.Meta`` shape.

    Subclasses replace this with their own nested ``Meta`` class. The
    machinery only consults ``model``, ``allowed_relationships``,
    ``max_relationship_depth``, ``auto_fields``, ``auto_lookups``, and
    ``strict`` — anything else is ignored.
    """

    model: "Optional[type[DeclarativeBase]]" = None
    allowed_relationships: ClassVar["Sequence[str]"] = ()
    max_relationship_depth: ClassVar[int] = _DEFAULT_MAX_RELATIONSHIP_DEPTH
    auto_fields: ClassVar["Sequence[str]"] = ()
    auto_lookups: ClassVar["Mapping[str, Sequence[str]]"] = MappingProxyType({})
    strict: ClassVar[bool] = False


def _is_valid_field_name(name: str) -> bool:
    """A declared field name must look like a public Python identifier.

    Rejects dunder names (``__init__``, ``__class__``) and Python
    keywords; permits any other identifier the mapper might recognize.
    """
    if not name.isidentifier():
        return False
    if keyword.iskeyword(name):
        return False
    return not (name.startswith("__") and name.endswith("__"))


def _resolve_field_path(
    model: "type[DeclarativeBase]",
    raw_name: str,
    *,
    allowed_relationships: "frozenset[str]",
    max_depth: int,
    field_for_error: str,
) -> "tuple[tuple[str, ...], Column[Any]]":
    """Walk ``raw_name`` (split on ``__``) against the SQLAlchemy mapper.

    Returns ``(path_tuple, terminal_column)`` on success. Raises
    :class:`ImproperConfigurationError` with a human-friendly message on
    any invalid segment, including unknown columns, unknown or
    disallowed relationships, depth violations, or terminal segments
    that resolve to a relationship instead of a column.
    """
    segments = raw_name.split("__")
    if not segments or any(not seg for seg in segments):
        msg = f"Field {field_for_error!r}: empty path segment in {raw_name!r}."
        raise ImproperConfigurationError(detail=msg)

    *relationship_segments, terminal = segments
    if len(relationship_segments) > max_depth:
        msg = (
            f"Field {field_for_error!r}: relationship traversal depth "
            f"{len(relationship_segments)} exceeds Meta.max_relationship_depth={max_depth}."
        )
        raise ImproperConfigurationError(detail=msg)

    current = model
    for segment in relationship_segments:
        mapper = class_mapper(current)
        if segment not in mapper.relationships:
            msg = f"Field {field_for_error!r}: {segment!r} is not a relationship on {current.__name__}."
            raise ImproperConfigurationError(detail=msg)
        if segment not in allowed_relationships:
            msg = (
                f"Field {field_for_error!r}: relationship {segment!r} not in "
                f"Meta.allowed_relationships={sorted(allowed_relationships)}."
            )
            raise ImproperConfigurationError(detail=msg)
        current = mapper.relationships[segment].mapper.class_

    mapper = class_mapper(current)
    if terminal in mapper.relationships:
        msg = (
            f"Field {field_for_error!r}: terminal segment {terminal!r} is a relationship "
            f"on {current.__name__}, expected a column."
        )
        raise ImproperConfigurationError(detail=msg)
    columns = current.__table__.c
    if terminal not in columns:
        msg = f"Field {field_for_error!r}: column {terminal!r} not found on {current.__name__}."
        raise ImproperConfigurationError(detail=msg)
    return tuple(segments), cast("Column[Any]", columns[terminal])


def _filter_for_column(column: "Column[Any]") -> "BaseFieldFilter":
    """Map a SQLAlchemy column type to a sensible default field filter.

    Imports the concrete filter classes lazily to break the circular
    dependency with ``_fields``.
    """
    import enum as _enum
    from datetime import date as _date
    from datetime import datetime as _datetime
    from decimal import Decimal as _Decimal
    from uuid import UUID as _UUID

    from advanced_alchemy.filters._fields import (
        BooleanFilter,
        DateFilter,
        DateTimeFilter,
        EnumFilter,
        NumberFilter,
        StringFilter,
        UUIDFilter,
    )

    enum_class = getattr(column.type, "enum_class", None)
    if isinstance(enum_class, type) and issubclass(enum_class, _enum.Enum):
        return EnumFilter(enum=enum_class)
    try:
        py_type = column.type.python_type
    except (AttributeError, NotImplementedError):
        return StringFilter()

    factories: dict[type, Any] = {
        bool: BooleanFilter,
        int: lambda: NumberFilter(type_=int),
        float: lambda: NumberFilter(type_=float),
        _Decimal: lambda: NumberFilter(type_=_Decimal),
        _UUID: UUIDFilter,
        _datetime: DateTimeFilter,
        _date: DateFilter,
    }
    factory = factories.get(py_type)
    if factory is not None:
        return cast("BaseFieldFilter", factory())
    return StringFilter()


def _coerce_or_passthrough(
    field_filter: "BaseFieldFilter",
    raw_value: Any,
    lookup: str,
    *,
    allow_typed: bool,
) -> Any:
    """Run ``coerce()`` if the raw value looks like an HTTP token.

    When ``allow_typed`` is ``True`` (the :meth:`FilterSet.from_dict`
    path), values that are neither a string nor a list/tuple of strings
    are returned verbatim — the caller has already supplied typed input.
    """
    if allow_typed and not _looks_like_query_value(raw_value):
        return raw_value
    return field_filter.coerce(raw_value, lookup)


def _looks_like_query_value(value: Any) -> bool:
    """True if ``value`` should be passed through ``coerce()``."""
    if isinstance(value, str):
        return True
    if isinstance(value, (list, tuple)):
        return all(isinstance(item, str) for item in value)
    return False


def _validate_unbound_filter(
    model: "type[DeclarativeBase]",
    name: str,
    declaration: "BaseFieldFilter",
) -> None:
    """Validate a filter that declares its own model bindings.

    Currently used by :class:`OrderingFilter`, which carries an
    ``allowed`` list of column names. Each entry must resolve to a
    column on the FilterSet's ``Meta.model``.
    """
    allowed = getattr(declaration, "allowed", None)
    if allowed is None:
        return
    columns = model.__table__.c
    for column_name in allowed:
        if column_name not in columns:
            msg = (
                f"Field {name!r}: {type(declaration).__name__}.allowed entry "
                f"{column_name!r} is not a column on {model.__name__}."
            )
            raise ImproperConfigurationError(detail=msg)


def _restrict_lookups(filt: "BaseFieldFilter", lookups: "Sequence[str]") -> "BaseFieldFilter":
    """Return a new filter of the same class restricted to ``lookups``."""
    requested = frozenset(lookups)
    unsupported = requested - filt.supported_lookups
    if unsupported:
        msg = (
            f"auto_lookups: {type(filt).__name__} does not support lookups "
            f"{sorted(unsupported)}. Supported: {sorted(filt.supported_lookups)}."
        )
        raise ImproperConfigurationError(detail=msg)
    init_kwargs: dict[str, Any] = {"lookups": list(lookups)}
    enum_class = getattr(filt, "enum", None)
    if enum_class is not None:
        init_kwargs["enum"] = enum_class
    type_ = getattr(filt, "type_", None)
    if type_ is not None:
        init_kwargs["type_"] = type_
    return type(filt)(**init_kwargs)


class FilterSet:
    """Declarative filter container.

    Subclass and declare filterable fields as class attributes; each
    attribute is a :class:`BaseFieldFilter` mapped onto a column or a
    relationship-traversal path. ``__init_subclass__`` validates every
    declared path against ``Meta.model`` at import time and raises
    :class:`ImproperConfigurationError` on any inconsistency.

    The instance methods ``from_query_params`` / ``from_dict`` /
    ``to_filters`` / ``to_openapi_parameters`` are provided by later
    phases of the FilterSet roadmap; only the class-creation surface is
    implemented here.

    Example::

        class PostFilter(FilterSet):
            title = StringFilter(lookups=["exact", "icontains"])
            author__name = StringFilter(lookups=["iexact"])
            order_by = OrderingFilter(allowed=["created_at"])

            class Meta:
                model = Post
                allowed_relationships = ["author"]
    """

    Meta: ClassVar[type] = _FilterSetMeta
    _field_specs: ClassVar["Mapping[str, FieldSpec]"] = MappingProxyType({})
    _lookup_index: ClassVar["Mapping[tuple[str, str], FieldSpec]"] = MappingProxyType({})

    def __init__(self) -> None:
        self._invocations: list[tuple[str, str, Any]] = []

    @property
    def invocations(self) -> "list[tuple[str, str, Any]]":
        """Parsed ``(field_name, lookup, coerced_value)`` triples.

        Populated by :meth:`from_query_params` / :meth:`from_dict`. The
        Phase 5 compilation pass walks this list to emit Tier 1 filters.
        """
        return list(self._invocations)

    @classmethod
    def from_query_params(
        cls,
        params: "Mapping[str, Union[str, Sequence[str]]]",
    ) -> Self:
        """Build an instance from an HTTP query-parameter mapping.

        Each value is expected to be a string (single key) or a sequence
        of strings (repeated key); both shapes are passed through to the
        relevant field filter's :meth:`BaseFieldFilter.coerce`.

        Raises:
            FilterValidationError: If any value fails coercion or, when
                ``Meta.strict`` is ``True``, any key fails to match a
                declared field.
        """
        return cls._parse(params, allow_typed=False)

    @classmethod
    def from_dict(cls, data: "Mapping[str, Any]") -> Self:
        """Build an instance from a native Python mapping.

        Same key-resolution semantics as :meth:`from_query_params`. The
        difference is value handling: anything that is not a string or
        a sequence-of-strings is accepted verbatim, since callers
        passing native types (a ``date``, a list of ``int``) have
        already done the typing work the field filter would otherwise
        do.
        """
        return cls._parse(data, allow_typed=True)

    @classmethod
    def _resolve_query_key(
        cls,
        key: str,
    ) -> "Optional[tuple[str, FieldSpec, str]]":
        """Match a raw query key against the declared field surface.

        Returns ``(field_name, FieldSpec, lookup)`` or ``None`` when the
        key matches no declared field.
        """
        specs = cls._field_specs
        if key in specs:
            spec = specs[key]
            return key, spec, spec.filter.effective_default_lookup
        prefix, sep, last = key.rpartition("__")
        if not sep or prefix not in specs:
            return None
        spec = specs[prefix]
        if last not in spec.filter.lookups:
            return None
        return prefix, spec, last

    @classmethod
    def _parse(
        cls,
        params: "Mapping[str, Any]",
        *,
        allow_typed: bool,
    ) -> Self:
        instance = cls()
        errors: dict[str, str] = {}
        invocations: list[tuple[str, str, Any]] = []
        strict = bool(getattr(cls.Meta, "strict", False))

        for raw_key, raw_value in params.items():
            match = cls._resolve_query_key(raw_key)
            if match is None:
                if strict:
                    errors[raw_key] = f"Unknown filter key {raw_key!r}."
                continue
            name, spec, lookup = match
            try:
                value = _coerce_or_passthrough(spec.filter, raw_value, lookup, allow_typed=allow_typed)
            except ValueError as exc:
                errors[name] = str(exc)
                continue
            invocations.append((name, lookup, value))

        if errors:
            raise FilterValidationError(errors)

        instance._invocations = invocations
        return instance

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        meta = cls.__dict__.get("Meta") or getattr(cls, "Meta", _FilterSetMeta)
        declared_fields = _collect_declared_fields(cls)
        auto_fields: Sequence[str] = tuple(getattr(meta, "auto_fields", ()))

        if not declared_fields and not auto_fields:
            cls._field_specs = MappingProxyType({})
            cls._lookup_index = MappingProxyType({})
            return

        model = getattr(meta, "model", None)
        if model is None:
            msg = (
                f"FilterSet {cls.__name__!r} has declared fields but no "
                f"Meta.model. Set Meta.model to your SQLAlchemy declarative class."
            )
            raise ImproperConfigurationError(detail=msg)

        _validate_field_names(cls.__name__, declared_fields)

        allowed_relationships = frozenset(getattr(meta, "allowed_relationships", ()) or ())
        max_depth = int(getattr(meta, "max_relationship_depth", _DEFAULT_MAX_RELATIONSHIP_DEPTH))
        auto_lookups: Mapping[str, Sequence[str]] = getattr(meta, "auto_lookups", {}) or {}

        resolved = _build_auto_specs(
            model=model,
            auto_fields=auto_fields,
            declared_fields=declared_fields,
            auto_lookups=auto_lookups,
            allowed_relationships=allowed_relationships,
            max_depth=max_depth,
        )
        resolved.update(
            _build_declared_specs(
                model=model,
                declared_fields=declared_fields,
                allowed_relationships=allowed_relationships,
                max_depth=max_depth,
            ),
        )

        cls._field_specs = MappingProxyType(resolved)
        cls._lookup_index = MappingProxyType(_build_lookup_index(resolved))


def _collect_declared_fields(cls: type) -> dict[str, BaseFieldFilter]:
    """Collect ``BaseFieldFilter`` declarations from ``cls`` and its bases.

    Walks the MRO in reverse so subclass declarations win over inherited
    ones via natural dict overwrite.
    """
    return {
        name: value
        for klass in reversed(cls.__mro__)
        for name, value in vars(klass).items()
        if isinstance(value, BaseFieldFilter)
    }


def _validate_field_names(cls_name: str, declared: "Mapping[str, BaseFieldFilter]") -> None:
    """Reject reserved or non-identifier field names."""
    for name in declared:
        if not _is_valid_field_name(name):
            msg = (
                f"FilterSet {cls_name!r}: field name {name!r} is not a "
                f"valid filter declaration (dunders and keywords are reserved)."
            )
            raise ImproperConfigurationError(detail=msg)


def _build_auto_specs(
    *,
    model: "type[DeclarativeBase]",
    auto_fields: "Sequence[str]",
    declared_fields: "Mapping[str, BaseFieldFilter]",
    auto_lookups: "Mapping[str, Sequence[str]]",
    allowed_relationships: "frozenset[str]",
    max_depth: int,
) -> "dict[str, FieldSpec]":
    """Resolve ``Meta.auto_fields`` into ``FieldSpec`` entries."""
    resolved: dict[str, FieldSpec] = {}
    for name in auto_fields:
        if name in declared_fields:
            continue
        if not _is_valid_field_name(name):
            msg = f"auto_fields: {name!r} is not a valid field name."
            raise ImproperConfigurationError(detail=msg)
        path, column = _resolve_field_path(
            model,
            name,
            allowed_relationships=allowed_relationships,
            max_depth=max_depth,
            field_for_error=name,
        )
        generated = _filter_for_column(column)
        override = auto_lookups.get(name)
        if override is not None:
            generated = _restrict_lookups(generated, override)
        resolved[name] = FieldSpec(path=path, column=column, filter=generated)
    return resolved


def _build_declared_specs(
    *,
    model: "type[DeclarativeBase]",
    declared_fields: "Mapping[str, BaseFieldFilter]",
    allowed_relationships: "frozenset[str]",
    max_depth: int,
) -> "dict[str, FieldSpec]":
    """Resolve explicit class declarations into ``FieldSpec`` entries."""
    resolved: dict[str, FieldSpec] = {}
    for name, declaration in declared_fields.items():
        if not declaration.binds_to_column:
            _validate_unbound_filter(model, name, declaration)
            resolved[name] = FieldSpec(path=(name,), column=None, filter=declaration)
            continue
        path, column = _resolve_field_path(
            model,
            name,
            allowed_relationships=allowed_relationships,
            max_depth=max_depth,
            field_for_error=name,
        )
        resolved[name] = FieldSpec(path=path, column=column, filter=declaration)
    return resolved


def _build_lookup_index(
    specs: "Mapping[str, FieldSpec]",
) -> "dict[tuple[str, str], FieldSpec]":
    """Flatten ``{name: FieldSpec}`` into ``{(name, lookup): FieldSpec}``."""
    return {(name, lookup): spec for name, spec in specs.items() for lookup in spec.filter.lookups}
