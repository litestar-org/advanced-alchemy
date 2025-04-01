from typing import Any, TypeVar

_T = TypeVar("_T")


class SingletonMeta(type):
    """Metaclass for singleton pattern."""

    # We store instances keyed by the class type
    _instances: dict[type, object] = {}

    def __call__(cls: type[_T], *args: Any, **kwargs: Any) -> _T:
        """Call method for the singleton metaclass.

        Args:
            cls: The class being instantiated.
            *args: Positional arguments for the class constructor.
            **kwargs: Keyword arguments for the class constructor.

        Returns:
            The singleton instance of the class.
        """
        # Use SingletonMeta._instances to access the class attribute
        if cls not in SingletonMeta._instances:  # pyright: ignore[reportUnnecessaryContains]
            # Create the instance using super().__call__ which calls the class's __new__ and __init__
            instance = super().__call__(*args, **kwargs)  # type: ignore
            SingletonMeta._instances[cls] = instance

        # Return the cached instance. We cast here because the dictionary stores `object`,
        # but we know it's of type _T for the given cls key.
        # Mypy might need an ignore here depending on configuration, but pyright should handle it.
        return SingletonMeta._instances[cls]  # type: ignore[return-value]
