from typing import Any, TypeVar, no_type_check

from sqlalchemy.ext.mutable import MutableList as SQLMutableList
from typing_extensions import Self

T = TypeVar("T", bound=Any)


class MutableList(SQLMutableList[T]):  # pragma: no cover
    """A list type that implements :class:`Mutable`.

    The :class:`MutableList` object implements a list that will
    emit change events to the underlying mapping when the contents of
    the list are altered, including when values are added or removed.

    This is a replication of default Mutablelist provide by SQLAlchemy.
    The difference here is the properties _removed which keep every element
    removed from the list in order to be able to delete them after commit
    and keep them when session rolled back.

    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._removed: list[T] = []

    @no_type_check
    def __reduce_ex__(self, proto: int) -> "tuple[type[MutableList[T]], tuple[list[T]]]":  # pragma: no cover
        return self.__class__, (list(self),)

    # needed for backwards compatibility with
    # older pickles
    def __getstate__(self) -> "tuple[list[T], list[T]]":  # pragma: no cover
        return list(self), self._removed

    def __setstate__(self, state: "Any") -> None:  # pragma: no cover
        self[:] = state[0]
        self._removed = state[1]

    def __setitem__(self, index: "Any", value: "Any") -> None:
        """Detect list set events and emit change events."""
        old_value = self[index] if isinstance(index, slice) else [self[index]]
        list.__setitem__(self, index, value)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        self.changed()
        self._removed.extend(old_value)  # pyright: ignore[reportArgumentType]

    def __delitem__(self, index: "Any") -> None:
        """Detect list del events and emit change events."""
        old_value = self[index] if isinstance(index, slice) else [self[index]]
        list.__delitem__(self, index)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        self.changed()
        self._removed.extend(old_value)  # pyright: ignore[reportArgumentType]

    def pop(self, *arg: "Any") -> "T":
        result = list.pop(self, *arg)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        self.changed()
        self._removed.append(result)  # pyright: ignore[reportArgumentType,reportUnknownArgumentType]
        return result  # pyright: ignore[reportUnknownVariableType]

    def append(self, x: "Any") -> None:
        list.append(self, x)  # pyright: ignore[reportUnknownMemberType]
        self.changed()

    def extend(self, x: "Any") -> None:
        list.extend(self, x)  # pyright: ignore[reportUnknownMemberType]
        self.changed()

    @no_type_check
    def __iadd__(self, x: "Any") -> "Self":
        self.extend(x)
        return self

    def insert(self, i: "Any", x: "Any") -> None:
        list.insert(self, i, x)  # pyright: ignore[reportUnknownMemberType]
        self.changed()

    def remove(self, i: "T") -> None:
        list.remove(self, i)  # pyright: ignore[reportUnknownMemberType]
        self._removed.append(i)
        self.changed()

    def clear(self) -> None:
        self._removed.extend(self)
        list.clear(self)  # type: ignore[arg-type] # pyright: ignore[reportUnknownMemberType]
        self.changed()

    def sort(self, **kw: "Any") -> None:
        list.sort(self, **kw)  # pyright: ignore[reportUnknownMemberType]
        self.changed()

    def reverse(self) -> None:
        list.reverse(self)  # type: ignore[arg-type]  # pyright: ignore[reportUnknownMemberType]
        self.changed()
