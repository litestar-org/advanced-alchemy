from __future__ import annotations

from abc import ABCMeta
from dataclasses import dataclass
from types import EllipsisType
from typing import TYPE_CHECKING, Generic, Tuple, TypeVar, Union

if TYPE_CHECKING:
    from typing import Any, TypeAlias


LoadT = TypeVar("LoadT", bound="Load[Any]")
StrategyT = TypeVar("StrategyT", bound=str)
AnyStrategy: TypeAlias = Union[bool, EllipsisType, str]
LoadPath: TypeAlias = Tuple[Tuple[str, ...], Union[bool, EllipsisType, StrategyT]]


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
    default_strategy: AnyStrategy | None = None

    def __hash__(self) -> int:
        return hash((self.sep, self.default_strategy))


class Load(Generic[StrategyT], metaclass=ABCMeta):
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

    def _load_paths(self, **kwargs: bool | EllipsisType | StrategyT) -> tuple[LoadPath[StrategyT], ...]:
        """Split loading paths into tuples."""
        # Resolve path conflicts: the last takes precedence
        # - {"a": False, "a__b": True} -> {"a__b": True}
        to_remove: set[str] = set()
        for key, strategy in kwargs.items():
            for other_key, other_strategy in kwargs.items():
                if (
                    other_key != key
                    and other_key.startswith(key)
                    and not self.strategy_will_load(strategy)
                    and other_strategy != strategy
                ):
                    to_remove.add(key)
        kwargs = {key: val for key, val in kwargs.items() if key not in to_remove}
        return tuple((tuple(key.split(self._config.sep)), kwargs[key]) for key in sorted(kwargs))

    def has_wildcards(self) -> bool:
        """Check if wildcard loading is used in any of loading path.

        Returns:
            True if there is at least one wildcard use, False otherwise
        """
        return self._config.default_strategy is not None or Ellipsis in self._kwargs.values()

    def strategy_will_load(self, strategy: bool | EllipsisType | StrategyT | None) -> bool:
        if strategy is False or strategy is None:
            return False
        return True
