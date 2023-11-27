from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import inspect
from sqlalchemy.orm import defaultload, joinedload, noload, raiseload, selectinload, subqueryload

from ._base import Load, LoadConfig

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import EllipsisType

    from sqlalchemy.orm import Mapper, RelationshipProperty
    from sqlalchemy.orm.strategy_options import _AbstractLoad

    from advanced_alchemy import ModelT


SQLALoadStrategy = Literal["defaultload", "noload", "joinedload", "selectinload", "subqueryload", "raiseload"]


@dataclass
class SQLAlchemyLoadConfig(LoadConfig):
    default_strategy: SQLALoadStrategy | None = None


class SQLAlchemyLoad(Load[SQLALoadStrategy]):
    loading_strategies = ["defaultload", "joinedload", "noload", "raiseload", "selectinload", "subqueryload"]

    def __init__(
        self,
        config: LoadConfig | None = None,
        /,
        **kwargs: bool | EllipsisType | SQLALoadStrategy,
    ) -> None:
        config_ = config if config is not None else SQLAlchemyLoadConfig()
        super().__init__(config_, **kwargs)

    @classmethod
    def _strategy_to_load_fn(cls, strategy: SQLALoadStrategy) -> Callable[..., _AbstractLoad]:
        match strategy:
            case "defaultload":
                return defaultload
            case "noload":
                return noload
            case "joinedload":
                return joinedload
            case "selectinload":
                return selectinload
            case "subqueryload":
                return subqueryload
            case "raiseload":
                return raiseload

    def _loader_from_relationship(
        self,
        relationship: RelationshipProperty[Any],
        load: bool = True,
        wildcard: bool = False,
        strategy: SQLALoadStrategy | None = None,
    ) -> _AbstractLoad:  # sourcery skip: assign-if-exp, reintroduce-else
        arg = "*" if wildcard else relationship.class_attribute
        if not load:
            return raiseload(arg)
        if strategy is not None:
            return self._strategy_to_load_fn(strategy)(arg)
        if relationship.uselist:
            return selectinload(arg)
        return joinedload(arg)

    def _default_load_strategy(self) -> _AbstractLoad | None:
        match self._config:
            case SQLAlchemyLoadConfig():
                if self._config.default_strategy is not None:
                    return self._strategy_to_load_fn(self._config.default_strategy)("*")
                return None
            case LoadConfig(default_strategy="*"):
                return defaultload("*")
            case LoadConfig(default_strategy=None):
                return None
            case _:
                msg = f"Unknown load strategy: {self._config.default_strategy}"
                raise ValueError(msg)

    def loaders(self, model_type: type[ModelT]) -> list[_AbstractLoad]:
        loaders: list[_AbstractLoad] = []
        for path, load in self._paths:
            mapper: Mapper[ModelT] = inspect(model_type, raiseerr=True)
            if not path:
                continue
            loader_chain: list[_AbstractLoad] = []
            relationship: RelationshipProperty[Any] | None = None
            # Builder loaders
            for i, key in enumerate(path):
                should_load, wildcard, strategy = True, False, None
                if isinstance(load, str):
                    strategy = load
                elif load is Ellipsis:
                    wildcard = True
                elif not load and i == len(path) - 1:
                    should_load = False
                relationship = mapper.relationships[key]
                key_loader = self._loader_from_relationship(relationship, should_load, wildcard, strategy)
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
