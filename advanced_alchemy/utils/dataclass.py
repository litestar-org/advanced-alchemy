from __future__ import annotations

from dataclasses import Field, fields, is_dataclass
from inspect import isclass
from typing import TYPE_CHECKING, AbstractSet, Any, ClassVar, Iterable, Protocol, Type, final, runtime_checkable

if TYPE_CHECKING:
    from typing_extensions import TypeAlias, TypeGuard

__all__ = (
    "DataclassProtocol",
    "Empty",
    "EmptyType",
    "extract_dataclass_fields",
    "extract_dataclass_items",
    "is_dataclass_class",
    "is_dataclass_instance",
    "simple_asdict",
)


@final
class Empty:
    """A sentinel class used as placeholder."""


EmptyType: TypeAlias = Type[Empty]
"""Type alias for the :class:`~advanced_alchemy.utils.dataclass.Empty` sentinel class."""


@runtime_checkable
class DataclassProtocol(Protocol):
    """Protocol for instance checking dataclasses"""

    __dataclass_fields__: ClassVar[dict[str, Any]]


def extract_dataclass_fields(
    dt: DataclassProtocol,
    exclude_none: bool = False,
    exclude_empty: bool = False,
    include: AbstractSet[str] | None = None,
    exclude: AbstractSet[str] | None = None,
) -> tuple[Field[Any], ...]:
    """Extract dataclass fields.

    Args:
        dt: :class:`DataclassProtocol` instance.
        exclude_none: Whether to exclude None values.
        exclude_empty: Whether to exclude Empty values.
        include: An iterable of fields to include.
        exclude: An iterable of fields to exclude.


    Returns:
        A tuple of dataclass fields.
    """
    include = include or set()
    exclude = exclude or set()

    if common := (include & exclude):
        msg = f"Fields {common} are both included and excluded."
        raise ValueError(msg)

    dataclass_fields: Iterable[Field[Any]] = fields(dt)
    if exclude_none:
        dataclass_fields = (field for field in dataclass_fields if getattr(dt, field.name) is not None)
    if exclude_empty:
        dataclass_fields = (field for field in dataclass_fields if getattr(dt, field.name) is not Empty)
    if include:
        dataclass_fields = (field for field in dataclass_fields if field.name in include)
    if exclude:
        dataclass_fields = (field for field in dataclass_fields if field.name not in exclude)

    return tuple(dataclass_fields)


def extract_dataclass_items(
    dt: DataclassProtocol,
    exclude_none: bool = False,
    exclude_empty: bool = False,
    include: AbstractSet[str] | None = None,
    exclude: AbstractSet[str] | None = None,
) -> tuple[tuple[str, Any], ...]:
    """Extract dataclass name, value pairs.

    Unlike the 'asdict' method exports by the stdlib, this function does not pickle values.

    Args:
        dt: :class:`DataclassProtocol` instance.
        exclude_none: Whether to exclude None values.
        exclude_empty: Whether to exclude Empty values.
        include: An iterable of fields to include.
        exclude: An iterable of fields to exclude.

    Returns:
        A tuple of key/value pairs.
    """
    dataclass_fields = extract_dataclass_fields(dt, exclude_none, exclude_empty, include, exclude)
    return tuple((field.name, getattr(dt, field.name)) for field in dataclass_fields)


def simple_asdict(
    obj: DataclassProtocol,
    exclude_none: bool = False,
    exclude_empty: bool = False,
    convert_nested: bool = True,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    """Convert a dataclass to a dictionary.

    This method has important differences to the standard library version:
    - it does not deepcopy values
    - it does not recurse into collections

    Args:
        obj: :class:`DataclassProtocol` instance.
        exclude_none: Whether to exclude None values.
        exclude_empty: Whether to exclude Empty values.
        convert_nested: Whether to recursively convert nested dataclasses.
        exclude: An iterable of fields to exclude.

    Returns:
        A dictionary of key/value pairs.
    """
    ret: dict[str, Any] = {}
    for field in extract_dataclass_fields(obj, exclude_none, exclude_empty, exclude=exclude):
        value = getattr(obj, field.name)
        if is_dataclass_instance(value) and convert_nested:
            ret[field.name] = simple_asdict(value, exclude_none, exclude_empty)
        else:
            ret[field.name] = getattr(obj, field.name)
    return ret


def is_dataclass_instance(obj: Any) -> TypeGuard[DataclassProtocol]:
    """Check if an object is a dataclass instance.

    Args:
        obj: An object to check.

    Returns:
        True if the object is a dataclass instance.
    """
    return hasattr(type(obj), "__dataclass_fields__")  # pyright: ignore[reportUnknownArgumentType]


def is_dataclass_class(annotation: Any) -> TypeGuard[type[DataclassProtocol]]:
    """Wrap :func:`is_dataclass <dataclasses.is_dataclass>` in a :data:`typing.TypeGuard`.

    Args:
        annotation: tested to determine if instance or type of :class:`dataclasses.dataclass`.

    Returns:
        ``True`` if instance or type of ``dataclass``.
    """
    try:
        return isclass(annotation) and is_dataclass(annotation)
    except TypeError:  # pragma: no cover
        return False
