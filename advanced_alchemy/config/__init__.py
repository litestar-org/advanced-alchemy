from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Mapping,
    Type,
    final,
)

if TYPE_CHECKING:
    from typing_extensions import TypeAlias


@final
class Empty:
    """A sentinel class used as placeholder."""


EmptyType: TypeAlias = Type[Empty]
TypeEncodersMap: TypeAlias = "Mapping[Any, Callable[[Any], Any]]"
