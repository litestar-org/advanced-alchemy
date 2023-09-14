from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal, Mapping, Sequence, Type, final

if TYPE_CHECKING:
    from typing_extensions import TypeAlias


def filter_empty(obj: dict[Any, Any]) -> dict[Any, Any]:
    return {k: filter_empty(v) if isinstance(v, dict) else v for k, v in obj.items() if v is not Empty}


@final
class Empty:
    """A sentinel class used as placeholder."""


EmptyType: TypeAlias = Type[Empty]
TypeEncodersMap: TypeAlias = "Mapping[Any, Callable[[Any], Any]]"
TypeDecodersSequence: TypeAlias = "Sequence[tuple[Callable[[Any], bool], Callable[[Any, Any], Any]]]"

CommitStrategy = Literal["always", "match_status"]
