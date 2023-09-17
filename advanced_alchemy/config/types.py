"""Type aliases and constants used in the package config."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal, Mapping, Sequence, Type, final

if TYPE_CHECKING:
    from typing_extensions import TypeAlias


def filter_empty(obj: dict[Any, Any]) -> dict[Any, Any]:
    """Filter out empty values from a dictionary.

    Args:
        obj: The dictionary to filter.

    Returns:
        The filtered dictionary.
    """
    return {k: filter_empty(v) if isinstance(v, dict) else v for k, v in obj.items() if v is not Empty}


@final
class Empty:
    """A sentinel class used as placeholder."""


EmptyType: TypeAlias = Type[Empty]
"""Type alias for the :class:`Empty` sentinel class."""
TypeEncodersMap: TypeAlias = "Mapping[Any, Callable[[Any], Any]]"
"""Type alias for a mapping of type encoders."""
TypeDecodersSequence: TypeAlias = "Sequence[tuple[Callable[[Any], bool], Callable[[Any, Any], Any]]]"
"""Type alias for a sequence of type decoders."""
CommitStrategy = Literal["always", "match_status"]
"""Commit strategy for SQLAlchemy sessions."""
