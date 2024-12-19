from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, TypeVar, no_type_check

from sqlalchemy.ext.mutable import Mutable

if TYPE_CHECKING:
    from typing_extensions import Self  # noqa: F401

T = TypeVar("T", bound=Any)


class MutableDict(Mutable, Dict[str, Any]):
    @classmethod
    def coerce(cls, key: Any, value: Any) -> Any:
        """Convert plain dictionaries to MutableDict."""

        if not isinstance(value, MutableDict):
            if isinstance(value, dict):
                return MutableDict(value)  # pyright: ignore[reportUnknownArgumentType]

            # this call will raise ValueError
            return Mutable.coerce(key, value)
        return value

    def __setitem__(self, key: Any, value: Any) -> None:
        """Detect dictionary set events and emit change events."""

        dict.__setitem__(self, key, value)  # pyright: ignore[reportUnknownMemberType]
        self.changed()

    def __delitem__(self, key: Any) -> None:
        """Detect dictionary del events and emit change events."""

        dict.__delitem__(self, key)  # pyright: ignore[reportUnknownMemberType]
        self.changed()


class MutableList(Mutable, List[T]):
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

    @classmethod
    def coerce(cls, key: Any, value: Any) -> Any:
        if not isinstance(value, MutableList):
            if isinstance(value, list):
                return MutableList(value)  # pyright: ignore[reportUnknownVariableType]
            # this call will raise ValueError
            return Mutable.coerce(key, value)
        return value  # pyright: ignore[reportUnknownVariableType]

    @no_type_check
    def __reduce_ex__(self, proto: Any) -> tuple[type[MutableList[T]], tuple[list[T]]]:
        return self.__class__, (list(self),)

    # needed for backwards compatibility with
    # older pickles
    def __getstate__(self) -> tuple[list[T], list[T]]:
        return list(self), self._removed

    def __setstate__(self, state: Any) -> None:
        self[:] = state[0]
        self._removed = state[1]

    def __setitem__(self, index: Any, value: Any) -> None:
        """Detect list set events and emit change events."""
        old_value = self[index]
        super().__setitem__(index, value)
        self.changed()
        self._removed.extend(old_value)

    def __delitem__(self, index: Any) -> None:
        """Detect list del events and emit change events."""
        old_value = self[index] if isinstance(index, slice) else self[index]
        super().__delitem__(index)  # pyright: ignore[reportUnknownArgumentType]
        self.changed()
        self._removed.extend(old_value)

    def pop(self, *arg: Any) -> T:
        result = super().pop(*arg)
        self.changed()
        self._removed.append(result)
        return result

    def append(self, x: Any) -> None:
        super().append(x)
        self.changed()

    def extend(self, x: Any) -> None:
        super().extend(x)
        self.changed()

    @no_type_check
    def __iadd__(self, x: Any) -> Self:
        self.extend(x)
        return self

    def insert(self, i: Any, x: Any) -> None:
        super().insert(i, x)
        self.changed()

    def remove(self, i: T) -> None:
        super().remove(i)
        self._removed.append(i)
        self.changed()

    def clear(self) -> None:
        self._removed.extend(self)
        super().clear()
        self.changed()

    def sort(self, **kw: Any) -> None:
        super().sort(**kw)
        self.changed()

    def reverse(self) -> None:
        super().reverse()
        self.changed()
