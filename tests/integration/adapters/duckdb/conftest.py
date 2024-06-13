from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generator

import pytest
from sqlalchemy import Engine, NullPool, create_engine, insert
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy import base
from tests.fixtures import types

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


@pytest.fixture
def _patch_bases(monkeypatch: MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """Ensure new registry state for every test.

    This prevents errors such as "Table '...' is already defined for
    this MetaData instance...
    """
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy import base

    class NewUUIDBase(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDAuditBase(
        base.UUIDPrimaryKey,
        base.CommonTableAttributes,
        base.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewUUIDv6Base(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDv6AuditBase(
        base.UUIDPrimaryKey,
        base.CommonTableAttributes,
        base.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewUUIDv7Base(base.UUIDPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewUUIDv7AuditBase(
        base.UUIDPrimaryKey,
        base.CommonTableAttributes,
        base.AuditColumns,
        DeclarativeBase,
    ): ...

    class NewBigIntBase(base.BigIntPrimaryKey, base.CommonTableAttributes, DeclarativeBase): ...

    class NewBigIntAuditBase(base.BigIntPrimaryKey, base.CommonTableAttributes, base.AuditColumns, DeclarativeBase): ...

    monkeypatch.setattr(base, "UUIDBase", NewUUIDBase)
    monkeypatch.setattr(base, "UUIDAuditBase", NewUUIDAuditBase)
    monkeypatch.setattr(base, "UUIDv6Base", NewUUIDv6Base)
    monkeypatch.setattr(base, "UUIDv6AuditBase", NewUUIDv6AuditBase)
    monkeypatch.setattr(base, "UUIDv7Base", NewUUIDv7Base)
    monkeypatch.setattr(base, "UUIDv7AuditBase", NewUUIDv7AuditBase)
    monkeypatch.setattr(base, "BigIntBase", NewBigIntBase)
    monkeypatch.setattr(base, "BigIntAuditBase", NewBigIntAuditBase)


@pytest.fixture(name="engine", scope="session")
def duckdb_engine(tmp_path: Path, _patch_bases: Any) -> Generator[Engine, None, None]:
    """SQLite engine for end-to-end testing.

    Returns:
        Async SQLAlchemy engine instance.
    """
    engine = create_engine(f"duckdb:///{tmp_path}/test.duck.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def seed_db(
    engine: Engine,
    raw_authors: types.RawRecordData,
    raw_slug_books: types.RawRecordData,
    raw_rules: types.RawRecordData,
    raw_secrets: types.RawRecordData,
    author_model: types.AuthorModel,
    rule_model: types.RuleModel,
    secret_model: types.SecretModel,
    slug_book_model: types.SlugBookModel,
) -> None:
    with engine.begin() as conn:
        base.orm_registry.metadata.drop_all(conn)
        base.orm_registry.metadata.create_all(conn)
    with engine.begin() as conn:
        for author in raw_authors:
            conn.execute(insert(author_model).values(author))
        for rule in raw_rules:
            conn.execute(insert(rule_model).values(rule))
        for secret in raw_secrets:
            conn.execute(insert(secret_model).values(secret))
        for book in raw_slug_books:
            conn.execute(insert(slug_book_model).values(book))


@pytest.fixture(scope="session")
def session(engine: Engine) -> Generator[Session, None, None]:
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
