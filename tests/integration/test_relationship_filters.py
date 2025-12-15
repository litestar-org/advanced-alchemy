from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from advanced_alchemy.filters import CollectionFilter, ComparisonFilter, MultiFilter, RelationshipFilter

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("relationship-filters"),
]


# Skip unsupported engines at fixture setup time (before schema creation)
@pytest.fixture
def skip_unsupported_sync_engines(engine: Engine) -> None:
    """Skip tests for engines that don't support UNIQUE constraints or have schema issues."""
    dialect_name = getattr(engine.dialect, "name", "")

    # Skip Spanner - doesn't support direct UNIQUE constraints (used by Tag model)
    if dialect_name == "spanner":
        pytest.skip("Spanner doesn't support direct UNIQUE constraints")

    # Skip Oracle - has schema isolation issues with xdist groups
    if dialect_name.startswith("oracle"):
        pytest.skip("Oracle has schema isolation issues with relationship filter tests")


@pytest.fixture
def skip_unsupported_async_engines(async_engine: AsyncEngine) -> None:
    """Skip async tests for engines that don't support UNIQUE constraints."""
    dialect_name = getattr(async_engine.dialect, "name", "")

    # Skip Spanner - doesn't support direct UNIQUE constraints
    if dialect_name == "spanner":
        pytest.skip("Spanner doesn't support direct UNIQUE constraints")

    # Skip Oracle - has schema isolation issues with xdist groups
    if dialect_name.startswith("oracle"):
        pytest.skip("Oracle has schema isolation issues with relationship filter tests")


def _seed_item_tag_data_sync(session: Session, item_model: Any, tag_model: Any) -> tuple[Any, Any]:
    tag_python = tag_model(name="python")
    tag_sa = tag_model(name="sqlalchemy")

    item_1 = item_model(name="item-1")
    item_2 = item_model(name="item-2")
    item_3 = item_model(name="item-3")

    item_1.tags.append(tag_python)
    item_2.tags.extend([tag_python, tag_sa])
    item_3.tags.append(tag_sa)

    session.add_all([tag_python, tag_sa, item_1, item_2, item_3])
    session.commit()

    return tag_python, tag_sa


async def _seed_item_tag_data_async(session: AsyncSession, item_model: Any, tag_model: Any) -> tuple[Any, Any]:
    tag_python = tag_model(name="python")
    tag_sa = tag_model(name="sqlalchemy")

    item_1 = item_model(name="item-1")
    item_2 = item_model(name="item-2")
    item_3 = item_model(name="item-3")

    item_1.tags.append(tag_python)
    item_2.tags.extend([tag_python, tag_sa])
    item_3.tags.append(tag_sa)

    session.add_all([tag_python, tag_sa, item_1, item_2, item_3])
    await session.commit()

    return tag_python, tag_sa


def test_relationship_filter_many_to_many_sync(
    skip_unsupported_sync_engines: None,
    uuid_test_session_sync: tuple[Session, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    item_model: Any = uuid_models["item"]
    tag_model: Any = uuid_models["tag"]

    _seed_item_tag_data_sync(session, item_model, tag_model)

    stmt = RelationshipFilter(
        relationship="tags",
        filters=[CollectionFilter(field_name="name", values=["python"])],
    ).append_to_statement(select(item_model), item_model)

    items = session.execute(stmt).scalars().all()
    assert {i.name for i in items} == {"item-1", "item-2"}


def test_relationship_filter_negate_many_to_many_sync(
    skip_unsupported_sync_engines: None,
    uuid_test_session_sync: tuple[Session, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    item_model: Any = uuid_models["item"]
    tag_model: Any = uuid_models["tag"]

    _seed_item_tag_data_sync(session, item_model, tag_model)

    stmt = RelationshipFilter(
        relationship="tags",
        filters=[CollectionFilter(field_name="name", values=["python"])],
        negate=True,
    ).append_to_statement(select(item_model), item_model)

    items = session.execute(stmt).scalars().all()
    assert {i.name for i in items} == {"item-3"}


def test_collection_filter_relationship_delegates_to_relationship_filter_sync(
    skip_unsupported_sync_engines: None,
    uuid_test_session_sync: tuple[Session, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    item_model: Any = uuid_models["item"]
    tag_model: Any = uuid_models["tag"]

    tag_python, _tag_sa = _seed_item_tag_data_sync(session, item_model, tag_model)

    stmt = CollectionFilter(field_name="tags", values=[tag_python.id]).append_to_statement(
        select(item_model), item_model
    )
    items = session.execute(stmt).scalars().all()
    assert {i.name for i in items} == {"item-1", "item-2"}


def test_multifilter_relationship_filter_sync(
    skip_unsupported_sync_engines: None,
    uuid_test_session_sync: tuple[Session, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    item_model: Any = uuid_models["item"]
    tag_model: Any = uuid_models["tag"]

    _seed_item_tag_data_sync(session, item_model, tag_model)

    multi = MultiFilter(
        filters={
            "and_": [
                {
                    "type": "relationship",
                    "relationship": "tags",
                    "filters": [{"type": "collection", "field_name": "name", "values": ["python"]}],
                }
            ]
        }
    )
    stmt = multi.append_to_statement(select(item_model), item_model)
    items = session.execute(stmt).scalars().all()
    assert {i.name for i in items} == {"item-1", "item-2"}


def test_relationship_filter_many_to_one_sync(
    skip_unsupported_sync_engines: None,
    uuid_test_session_sync: tuple[Session, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_sync

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    author_model: Any = uuid_models["author"]
    book_model: Any = uuid_models["book"]

    author = author_model(name="Agatha Christie")
    book_1 = book_model(title="The Mysterious Affair at Styles", author=author)
    book_2 = book_model(title="Murder on the Orient Express", author=author)
    session.add_all([author, book_1, book_2])
    session.commit()

    stmt = RelationshipFilter(
        relationship="author",
        filters=[ComparisonFilter(field_name="name", operator="eq", value="Agatha Christie")],
    ).append_to_statement(select(book_model), book_model)

    books = session.execute(stmt).scalars().all()
    assert {b.title for b in books} == {"The Mysterious Affair at Styles", "Murder on the Orient Express"}


def test_relationship_filter_invalid_relationship_raises(
    skip_unsupported_sync_engines: None,
    uuid_test_session_sync: tuple[Session, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_sync

    item_model: Any = uuid_models["item"]

    stmt = select(item_model)
    filter_ = RelationshipFilter(relationship="does_not_exist", filters=[])

    with pytest.raises(ValueError, match="Relationship 'does_not_exist' not found on model"):
        filter_.append_to_statement(stmt, item_model)


def test_relationship_filter_join_negate_raises(
    skip_unsupported_sync_engines: None,
    uuid_test_session_sync: tuple[Session, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_sync

    book_model: Any = uuid_models["book"]

    stmt = select(book_model)
    filter_ = RelationshipFilter(relationship="author", filters=[], use_exists=False, negate=True)

    with pytest.raises(ValueError, match="JOIN-based relationship filters do not support negate=True"):
        filter_.append_to_statement(stmt, book_model)


def test_collection_filter_relationship_composite_pk_raises() -> None:
    class Base(DeclarativeBase):
        pass

    class Parent(Base):
        __tablename__ = "rel_filter_parent"

        id: Mapped[int] = mapped_column(primary_key=True)
        children: Mapped[list[Child]] = relationship(back_populates="parent")

    class Child(Base):
        __tablename__ = "rel_filter_child"

        parent_id: Mapped[int] = mapped_column(ForeignKey("rel_filter_parent.id"), primary_key=True)
        seq: Mapped[int] = mapped_column(primary_key=True)
        parent: Mapped[Parent] = relationship(back_populates="children")

    with pytest.raises(ValueError, match="composite primary keys"):
        CollectionFilter(field_name="children", values=[1]).append_to_statement(select(Parent), Parent)


@pytest.mark.asyncio
async def test_relationship_filter_many_to_many_async(
    skip_unsupported_async_engines: None,
    uuid_test_session_async: tuple[AsyncSession, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_async

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    item_model: Any = uuid_models["item"]
    tag_model: Any = uuid_models["tag"]

    await _seed_item_tag_data_async(session, item_model, tag_model)

    stmt = RelationshipFilter(
        relationship="tags",
        filters=[CollectionFilter(field_name="name", values=["python"])],
    ).append_to_statement(select(item_model), item_model)

    items = (await session.execute(stmt)).scalars().all()
    assert {i.name for i in items} == {"item-1", "item-2"}


@pytest.mark.asyncio
async def test_multifilter_relationship_filter_async(
    skip_unsupported_async_engines: None,
    uuid_test_session_async: tuple[AsyncSession, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_async

    # Skip mock engines
    if getattr(session.bind.dialect, "name", "") == "mock":
        pytest.skip("Mock engines not supported for filter tests")

    item_model: Any = uuid_models["item"]
    tag_model: Any = uuid_models["tag"]

    await _seed_item_tag_data_async(session, item_model, tag_model)

    multi = MultiFilter(
        filters={
            "and_": [
                {
                    "type": "relationship",
                    "relationship": "tags",
                    "filters": [{"type": "collection", "field_name": "name", "values": ["python"]}],
                }
            ]
        }
    )
    stmt = multi.append_to_statement(select(item_model), item_model)
    items = (await session.execute(stmt)).scalars().all()
    assert {i.name for i in items} == {"item-1", "item-2"}
