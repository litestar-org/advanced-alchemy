"""Declarative base for ADK v1 schema models."""

from sqlalchemy.orm import DeclarativeBase

from advanced_alchemy.extensions.adk.v1.metadata import metadata


class ADKv1DeclarativeBase(DeclarativeBase):
    """Base class for ADK v1 schema models."""

    metadata = metadata


__all__ = ("ADKv1DeclarativeBase",)
