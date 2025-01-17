# ruff: noqa: F401

import pytest


def test_repository_re_exports() -> None:
    with pytest.warns(DeprecationWarning):
        from litestar.contrib.sqlalchemy import types  # type: ignore
        from litestar.contrib.sqlalchemy.repository import (
            SQLAlchemyAsyncRepository,  # type: ignore
            SQLAlchemySyncRepository,  # type: ignore
            wrap_sqlalchemy_exception,  # type: ignore
        )
