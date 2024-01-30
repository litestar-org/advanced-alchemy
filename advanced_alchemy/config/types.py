"""Type aliases and constants used in the package config."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal, Mapping, Sequence

if TYPE_CHECKING:
    from typing_extensions import TypeAlias


TypeEncodersMap: TypeAlias = "Mapping[Any, Callable[[Any], Any]]"
"""Type alias for a mapping of type encoders."""
TypeDecodersSequence: TypeAlias = "Sequence[tuple[Callable[[Any], bool], Callable[[Any, Any], Any]]]"
"""Type alias for a sequence of type decoders."""
CommitStrategy = Literal["always", "match_status"]
"""Commit strategy for SQLAlchemy sessions."""
