from __future__ import annotations

from dataclasses import dataclass
from types import EllipsisType
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, Union

from sqlalchemy import inspect
from sqlalchemy.orm import defaultload, joinedload, noload, raiseload, selectinload, subqueryload

from ._base import Load, LoadConfig

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Mapper, RelationshipProperty
    from sqlalchemy.orm.strategy_options import _AbstractLoad

    from advanced_alchemy import ModelT


SQLALoadStrategy = Literal["defaultload", "noload", "joinedload", "selectinload", "subqueryload", "raiseload"]
AnySQLAtrategy: TypeAlias = Union[SQLALoadStrategy, bool, EllipsisType]


@dataclass
class SQLAlchemyLoadConfig(LoadConfig):
    default_strategy: AnySQLAtrategy | None = None


class SQLAlchemyLoad(Load[SQLALoadStrategy]):
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
        config: LoadConfig | None = None,
        /,
        **kwargs: AnySQLAtrategy,
    ) -> None:
        config_ = config if config is not None else SQLAlchemyLoadConfig()
        super().__init__(config_, **kwargs)

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
        if isinstance(self._config, SQLAlchemyLoadConfig):
            if self._config.default_strategy is not None:
                return self._strategy_to_load_fn(self._config.default_strategy)("*")
            return None
        if self._config.default_strategy == "*":
            return defaultload("*")
        if self._config.default_strategy is None:
            return None
        msg = f"Unknown load strategy: {self._config.default_strategy}"
        raise ValueError(msg)

    def loaders(self, model_type: type[ModelT]) -> list[_AbstractLoad]:
        loaders: list[_AbstractLoad] = []
        for path, strategy in self._paths:
            mapper: Mapper[ModelT] = inspect(model_type, raiseerr=True)
            if not path:
                continue
            loader_chain: list[_AbstractLoad] = []
            relationship: RelationshipProperty[Any] | None = None
            # Builder loaders
            for i, key in enumerate(path):
                key_strategy = strategy
                current_prefix_strategy = self._kwargs.get(self._config.sep.join(path[: i + 1]), None)
                if not self.strategy_will_load(strategy) and self.strategy_will_load(current_prefix_strategy):
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

    def strategy_will_load(self, strategy: SQLALoadStrategy | bool | EllipsisType | None) -> bool:
        if strategy is False or strategy is None:
            return False
        if isinstance(strategy, str):
            return strategy not in ["noload", "raiseload"]
        return True
