"""Type aliases and constants used in the package config."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal, Mapping, Sequence, Tuple

if TYPE_CHECKING:
    from typing_extensions import TypeAlias


TypeEncodersMap: TypeAlias = "Mapping[Any, Callable[[Any], Any]]"
"""Type alias for a mapping of type encoders.

Maps types to their encoder functions.
"""

TypeDecodersSequence: TypeAlias = "Sequence[Tuple[Callable[[Any], bool], Callable[[Any, Any], Any]]]"
"""Type alias for a sequence of type decoders.

Each tuple contains a type check predicate and its corresponding decoder function.
"""

CommitStrategy = Literal["always", "match_status"]
"""Commit strategy for SQLAlchemy sessions.

Values:
    always: Always commit the session after operations
    match_status: Only commit if the HTTP status code indicates success
"""
