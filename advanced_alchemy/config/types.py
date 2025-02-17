"""Type aliases and constants used in the package config."""

from collections.abc import Mapping, Sequence
from typing import Any, Callable, Literal

from typing_extensions import TypeAlias

TypeEncodersMap: TypeAlias = Mapping[Any, Callable[[Any], Any]]
"""Type alias for a mapping of type encoders.

Maps types to their encoder functions.
"""

TypeDecodersSequence: TypeAlias = Sequence[tuple[Callable[[Any], bool], Callable[[Any, Any], Any]]]
"""Type alias for a sequence of type decoders.

Each tuple contains a type check predicate and its corresponding decoder function.
"""

CommitStrategy: TypeAlias = Literal["always", "match_status"]
"""Commit strategy for SQLAlchemy sessions.

Values:
    always: Always commit the session after operations
    match_status: Only commit if the HTTP status code indicates success
"""
