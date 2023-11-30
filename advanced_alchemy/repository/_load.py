from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Tuple, Union

from sqlalchemy import inspect
from sqlalchemy.orm import defaultload, joinedload, noload, raiseload, selectinload, subqueryload

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import EllipsisType

    from sqlalchemy.orm import Mapper, RelationshipProperty
    from sqlalchemy.orm.strategy_options import _AbstractLoad
    from typing_extensions import TypeAlias

    from advanced_alchemy import ModelT

    AnySQLAtrategy: TypeAlias = Union["SQLALoadStrategy", bool, EllipsisType]
    LoadPath: TypeAlias = Tuple[Tuple[str, ...], AnySQLAtrategy]

SQLALoadStrategy = Literal["defaultload", "noload", "joinedload", "selectinload", "subqueryload", "raiseload"]


@dataclass
class SQLAlchemyLoadConfig:
    sep: str = "__"
    default_strategy: AnySQLAtrategy | None = None


class SQLAlchemyLoad:
    _strategy_map: dict[SQLALoadStrategy, Callable[..., _AbstractLoad]] = {
        "defaultload": defaultload,
        "joinedload": joinedload,
        "noload": noload,
        "raiseload": raiseload,
        "selectinload": selectinload,
        "subqueryload": subqueryload,
    }

    def __init__(
        self,
        config: SQLAlchemyLoadConfig | None = None,
        /,
        **kwargs: AnySQLAtrategy,
    ) -> None:
        self._config = config if config is not None else SQLAlchemyLoadConfig()
        self._kwargs = kwargs
        self._paths = self._load_paths(**self._kwargs)
        self._identity = (self._config.default_strategy, self._paths)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SQLAlchemyLoad):
            return self._config.default_strategy == other._config.default_strategy and self._paths == other._paths
        return False

    def __bool__(self) -> bool:
        return bool(self._config.default_strategy or self._kwargs)

    def _load_paths(self, **kwargs: AnySQLAtrategy) -> tuple[LoadPath, ...]:
        """Split loading paths into tuples."""
        # Resolve path conflicts: the last takes precedence
        # - {"a": False, "a__b": True} -> {"a__b": True}
        to_remove: set[str] = set()
        for key, strategy in kwargs.items():
            for other_key, other_strategy in kwargs.items():
                if (
                    other_key != key
                    and other_key.startswith(key)
                    and not self._strategy_will_load(strategy)
                    and other_strategy != strategy
                ):
                    to_remove.add(key)
        kwargs = {key: val for key, val in kwargs.items() if key not in to_remove}
        return tuple((tuple(key.split(self._config.sep)), kwargs[key]) for key in sorted(kwargs))

    @classmethod
    def _strategy_to_load_fn(cls, strategy: AnySQLAtrategy, uselist: bool = False) -> Callable[..., _AbstractLoad]:
        if not strategy:
            return raiseload
        if isinstance(strategy, str):
            return cls._strategy_map[strategy]
        if uselist:
            return selectinload
        return joinedload

    def _default_load_strategy(self) -> _AbstractLoad | None:
        if self._config.default_strategy is not None:
            return self._strategy_to_load_fn(self._config.default_strategy)("*")
        return None

    def has_wildcards(self) -> bool:
        """Check if wildcard loading is used in any of loading path.

        Returns:
            True if there is at least one wildcard use, False otherwise
        """
        return self._config.default_strategy is not None or Ellipsis in self._kwargs.values()

    def loaders(self, model_type: type[ModelT]) -> list[_AbstractLoad]:
        loaders: list[_AbstractLoad] = []
        for path, strategy in self._paths:
            mapper: Mapper[ModelT] = inspect(model_type, raiseerr=True)
            loader_chain: list[_AbstractLoad] = []
            relationship: RelationshipProperty[Any] | None = None
            # Builder loaders
            for i, key in enumerate(path):
                key_strategy = strategy
                current_prefix_strategy = self._kwargs.get(self._config.sep.join(path[: i + 1]), None)
                if not self._strategy_will_load(strategy) and self._strategy_will_load(current_prefix_strategy):
                    key_strategy = True
                relationship = mapper.relationships[key]
                load_arg = "*" if strategy is Ellipsis else relationship.class_attribute
                key_loader = self._strategy_to_load_fn(key_strategy, bool(relationship.uselist))(load_arg)
                loader_chain.append(key_loader)
                if relationship is not None:
                    mapper = inspect(relationship.entity.class_, raiseerr=True)
            # Chain them together
            path_loader = loader_chain[-1]
            for loader in loader_chain[-2::-1]:
                path_loader = loader.options(path_loader)
            loaders.append(path_loader)
        if (default_load := self._default_load_strategy()) is not None:
            loaders.append(default_load)
        return loaders

    def _strategy_will_load(self, strategy: SQLALoadStrategy | bool | EllipsisType | None) -> bool:
        if strategy is False or strategy is None:
            return False
        if isinstance(strategy, str):
            return strategy not in ["noload", "raiseload"]
        return True
