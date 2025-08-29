import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column

from advanced_alchemy.mixins.sentinel import SentinelMixin
from advanced_alchemy.types import NANOID_INSTALLED

if NANOID_INSTALLED and not TYPE_CHECKING:
    from fastnanoid import (  # type: ignore[import-not-found,unused-ignore]  # pyright: ignore[reportMissingImports]
        generate as nanoid,
    )
else:
    from uuid import uuid4 as nanoid  # type: ignore[assignment,unused-ignore]

logger = logging.getLogger("advanced_alchemy")


@declarative_mixin
class NanoIDPrimaryKey(SentinelMixin):
    """Nano ID Primary Key Field Mixin."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not NANOID_INSTALLED and not cls.__module__.startswith("advanced_alchemy"):
            logger.warning("`fastnanoid` not installed, falling back to `uuid4` for NanoID generation.")

    id: Mapped[str] = mapped_column(default=nanoid, primary_key=True)
    """Nano ID Primary key column."""
