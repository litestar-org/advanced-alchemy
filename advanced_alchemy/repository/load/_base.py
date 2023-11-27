from __future__ import annotations

from dataclasses import dataclass
from types import EllipsisType
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any


LoadT = TypeVar("LoadT", bound="Load[Any]")
StrategyT = TypeVar("StrategyT", bound=str)
LoadPath = tuple[tuple[str, ...], bool | EllipsisType | StrategyT]


@dataclass
class FieldLoadConfig:
    """DTO load field config.

    Control how to load DTO fields when using `.load_from_dto`
    """

    no_load: bool = False
    """Do not load this field"""


@dataclass
class LoadConfig:
    sep: str = "__"
    default_strategy: str | None = None

    def __hash__(self) -> int:
        return hash((self.sep, self.default_strategy))


class Load(Generic[StrategyT]):
    loading_strategies: Sequence[str] | None = None

    def __init__(
        self,
        config: LoadConfig | None = None,
        /,
        **kwargs: bool | EllipsisType | StrategyT,
    ) -> None:
        self._config = config if config is not None else LoadConfig()
        self._kwargs = kwargs
        self._paths = self._load_paths(**self._kwargs)
        self._identity = (self._config.default_strategy, self._paths)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Load):
            return self._config.default_strategy == other._config.default_strategy and self._paths == other._paths
        return False

    def __bool__(self) -> bool:
        return bool(self._config.default_strategy or self._kwargs)

    @property
    def _loading_strategies(self) -> tuple[object, ...]:
        if self.loading_strategies is None:
            return (True, Ellipsis)
        return (True, Ellipsis, *self.loading_strategies)

    def _load_paths(self, **kwargs: bool | EllipsisType | StrategyT) -> tuple[LoadPath[StrategyT], ...]:
        """Split loading paths into tuples."""
        # Resolve path conflicts
        # - {"a": False, "a__b": True} -> {"a": False}
        to_remove: set[str] = set()
        not_loaded: list[str] = [key for key, load in kwargs.items() if not load]
        for key in not_loaded:
            for kwarg, load in kwargs.items():
                if kwarg != key and kwarg.startswith(key) and load in self._loading_strategies:
                    to_remove.add(kwarg)
        kwargs = {key: val for key, val in kwargs.items() if key not in to_remove}
        return tuple((tuple(key.split(self._config.sep)), kwargs[key]) for key in sorted(kwargs))

    def has_wildcards(self) -> bool:
        """Check if wildcard loading is used in any of loading path.

        Returns:
            True if there is at least one wildcard use, False otherwise
        """
        return self._config.default_strategy is not None or Ellipsis in self._kwargs.values()
