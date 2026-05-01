"""Tier 2 declarative filter facade — bootstrap primitives.

Hosts the building blocks for the FilterSet facade:

* :data:`UNSET` — sentinel distinct from ``None`` for optional defaults.
* :class:`FieldSpec` — frozen description of a resolved declared field.
* :class:`BaseFieldFilter` — abstract base for typed field filters.

The concrete field filters (:class:`StringFilter`, :class:`NumberFilter`,
…) and the :class:`FilterSet` base class itself live alongside this
module and are layered on top of these primitives.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Final,
    Optional,
    cast,
)

from typing_extensions import Self

from advanced_alchemy.exceptions import ImproperConfigurationError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Union

    from sqlalchemy import Column

    from advanced_alchemy.filters._base import StatementFilter

__all__ = (
    "UNSET",
    "BaseFieldFilter",
    "FieldSpec",
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
            longer tuples encode relationship traversal.
        column: The terminal SQLAlchemy ``Column`` reached by ``path``.
        filter: The :class:`BaseFieldFilter` instance declared on the class.
    """

    path: tuple[str, ...]
    column: "Column[Any]"
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
