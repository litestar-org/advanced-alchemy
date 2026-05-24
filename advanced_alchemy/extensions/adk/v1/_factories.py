"""Factory helpers for ADK v1 schema customizations."""

from typing import Any, cast

from sqlalchemy import Column, MetaData

from advanced_alchemy.extensions.adk.v1._base import ADKv1DeclarativeBase
from advanced_alchemy.extensions.adk.v1.models import ADKSession


def _copy_column(column: Column[Any]) -> Column[Any]:
    """Return a detached copy of a user-provided column declaration."""
    foreign_keys = [foreign_key.copy() for foreign_key in column.foreign_keys]
    return Column(
        column.name,
        column.type,
        *foreign_keys,
        nullable=column.nullable,
        primary_key=column.primary_key,
        unique=column.unique,
        index=column.index,
        default=column.default,
        server_default=column.server_default,
        info=dict(column.info),
    )


def with_owner_column(model: type[ADKSession], column: Column[Any]) -> type[ADKSession]:
    """Return an ADK session model clone with an additional owner column."""
    if column.name is None:
        msg = "owner column must have a name"
        raise ValueError(msg)

    owner_metadata = MetaData()
    table = model.__table__.to_metadata(owner_metadata)
    if column.name in table.c:
        msg = f"owner column {column.name!r} conflicts with an existing ADK session column"
        raise ValueError(msg)
    table.append_column(_copy_column(column))

    mapped_class = type(
        f"{model.__name__}With{column.name.title().replace('_', '')}",
        (ADKv1DeclarativeBase,),
        {"__module__": __name__, "__table__": table},
    )
    return cast("type[ADKSession]", mapped_class)


__all__ = ("with_owner_column",)
