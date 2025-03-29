from collections import UserList
from typing import Any, TypeVar, no_type_check

from sqlalchemy.ext.mutable import Mutable, MutableDict
from typing_extensions import Self

T = TypeVar("T", bound=Any)


class MutableList(Mutable, list[T]):
    """A list type that implements :class:`Mutable`.

    The :class:`MutableList` object implements a list that will
    emit change events to the underlying mapping when the contents of
    the list are altered, including when values are added or removed.

    This is a replication of default MutableList provide by SQLAlchemy.
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
            if isinstance(value, (list, UserList)):
                return MutableList(value)  # pyright: ignore[reportUnknownVariableType]
            # this call will raise ValueError
            return Mutable.coerce(key, value)
        return value  # pyright: ignore[reportUnknownVariableType]

    @no_type_check
    def __reduce_ex__(self, proto: Any) -> "tuple[type[MutableList[T]], tuple[list[T]]]":
        return self.__class__, (list(self),)

    # needed for backwards compatibility with
    # older pickles
    def __getstate__(self) -> "tuple[list[T], list[T]]":
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
        old_value = self[index]
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


class FreezableFileBase(MutableDict[str, Any]):
    """Base class for storing file metadata.

    Acts as a dictionary holding metadata related to a file (e.g., path, size,
    modification time, custom tags) potentially stored elsewhere.

    Provides attribute-style access for dictionary keys (e.g., obj.key).
    Instances can be 'frozen' (made immutable) using the _freeze() method,
    typically after being saved or persisted.

    Inherits from collections.UserDict, allowing easy JSON serialization.

    Attributes:
        data (Dict[str, Any]): The underlying dictionary storing the metadata.
        # _frozen is managed internally, not listed as a public attribute
    """

    __slots__ = ("_frozen",)

    # Use a tuple for faster "in" checks if performance matters,
    # otherwise a set is fine. Define attributes that are NOT dict keys.
    _INSTANCE_ATTRS = ("_frozen",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize FileBase.

        Accepts arguments like a standard dict to populate initial metadata.
        Initializes the instance as mutable (_frozen = False).

        Args:
            *args: Positional arguments passed to the dict constructor.
            **kwargs: Keyword arguments passed to the dict constructor.
        """
        super().__init__(*args, **kwargs)
        # Use object.__setattr__ to initialize internal state,
        # bypassing our custom __setattr__.
        object.__setattr__(self, "_frozen", False)

    def _is_frozen(self) -> bool:
        """Check if the instance is frozen.

        Returns:
            bool: True if the instance is frozen, False otherwise.
        """
        # Use getattr for safe access before fully initialized? Or rely on __init__?
        # Relying on __init__ setting it is usually fine.
        return getattr(self, "_frozen", False)

    def __getitem__(self, key: str) -> Any:
        """Retrieve item by key. Read access is always allowed, even if frozen.

        Returns:
            The item associated with the key.
        """
        # No freeze check needed for read access.
        # Delegate to UserDict's implementation which accesses self.data.
        return super().__getitem__(key)

    def __getattr__(self, name: str) -> Any:
        """Retrieve item as an attribute (e.g., obj.key).

        Args:
            name: The attribute/key name.

        Returns:
            The value associated with the key.

        Raises:
            AttributeError: If 'name' is not found as a key in the dictionary.
        """
        # __getattr__ is only called if the attribute wasn't found normally.
        # So, no need to check _INSTANCE_ATTRS here.
        try:
            # Access via __getitem__ to leverage its logic (if any complex logic existed)
            # or access self.data directly: return self.data[name]
            return self[name]
        except KeyError as err:
            # More informative error message
            msg = f"'{type(self).__name__}' object has no attribute or key '{name}'"
            raise AttributeError(msg) from err

    def __setitem__(self, key: str, value: Any) -> None:
        """Set item by key (e.g., obj['key'] = value).

        Args:
            key: The key to set.
            value: The value to associate with the key.

        Raises:
            TypeError: If the instance is frozen.
        """
        if self._is_frozen():
            msg = f"Cannot set item '{key}': instance is frozen."
            raise TypeError(msg)
        super().__setitem__(key, value)  # Delegates to self.data[key] = value

    def __setattr__(self, name: str, value: Any) -> None:
        """Set item as an attribute (e.g., obj.key = value) or set internal state.

        If 'name' starts with '_' or is in _INSTANCE_ATTRS, it's treated as
        an internal instance attribute. Otherwise, it's treated as a
        dictionary key/value pair.

        Args:
            name: The attribute/key name.
            value: The value to set.

        Raises:
            TypeError: If setting a dictionary key/value and the instance is frozen.
        """
        # Check if it's an internal attribute
        # Also handle 'data' which is UserDict's internal dict attribute
        if name.startswith("_") or name in self._INSTANCE_ATTRS or name == "data":
            # Use object.__setattr__ to bypass checks and __setitem__ delegation
            # This allows setting internal state like _frozen even when frozen.
            object.__setattr__(self, name, value)
        else:
            # It's a dictionary key, delegate to __setitem__ (which includes freeze check)
            try:
                self[name] = value
            except TypeError as e:
                # Re-raise with a slightly more specific context if desired
                msg = f"Cannot set attribute '{name}': instance is frozen."
                raise TypeError(msg) from e

    def __delitem__(self, key: str) -> None:
        """Delete item by key (e.g., del obj['key']).

        Args:
            key: The key to delete.

        Raises:
            TypeError: If the instance is frozen.
        """
        if self._is_frozen():
            msg = f"Cannot delete item '{key}': instance is frozen."
            raise TypeError(msg)
        super().__delitem__(key)  # Delegates to del self.data[key]

    def __delattr__(self, name: str) -> None:
        """Delete item as an attribute (e.g., del obj.key).

        Args:
            name: The attribute/key name to delete.

        Raises:
            AttributeError: If 'name' refers to an internal attribute or
                            if the key does not exist.
            TypeError: If deleting a dictionary key/value and the instance is frozen.
        """
        # Prevent deleting internal attributes
        if name.startswith("_") or name in self._INSTANCE_ATTRS or name == "data":
            msg = f"Cannot delete internal attribute '{name}'"
            raise AttributeError(msg)
        # It's potentially a dictionary key, delegate to __delitem__
        try:
            del self[name]
        except KeyError as e:
            msg = f"'{type(self).__name__}' object has no attribute or key '{name}'"
            raise AttributeError(msg) from e
        except TypeError as e:
            # Re-raise with a slightly more specific context if desired
            msg = f"Cannot delete attribute '{name}': instance is frozen."
            raise TypeError(msg) from e

    def _freeze(self) -> None:
        """Make the instance immutable (dictionary items cannot be changed)."""
        # Use object.__setattr__ to bypass our custom __setattr__
        object.__setattr__(self, "_frozen", True)  # noqa: PLC2801

    def _thaw(self) -> None:
        """Make the instance mutable again."""
        # Use object.__setattr__ to bypass our custom __setattr__
        object.__setattr__(self, "_frozen", False)  # noqa: PLC2801

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        status = " (frozen)" if self._is_frozen() else ""
        # Use super().__repr__() which relies on self.data
        return f"{type(self).__name__}({self.data!r}){status}"
