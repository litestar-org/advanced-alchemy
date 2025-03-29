from typing import Any


class SingletonMeta(type):
    """Metaclass for singleton pattern."""

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:  # pyright: ignore[reportUnnecessaryContains]
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
