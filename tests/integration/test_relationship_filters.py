from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.filters import CollectionFilter, ComparisonFilter, MultiFilter, RelationshipFilter

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("relationship-filters"),
]


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


def test_relationship_filter_many_to_many_sync(uuid_test_session_sync: tuple[Session, dict[str, type]]) -> None:
    session, uuid_models = uuid_test_session_sync
    item_model: Any = uuid_models["item"]
    tag_model: Any = uuid_models["tag"]

    _seed_item_tag_data_sync(session, item_model, tag_model)

    stmt = RelationshipFilter(
        relationship="tags",
        filters=[CollectionFilter(field_name="name", values=["python"])],
    ).append_to_statement(select(item_model), item_model)

    items = session.execute(stmt).scalars().all()
    assert {i.name for i in items} == {"item-1", "item-2"}


def test_relationship_filter_negate_many_to_many_sync(uuid_test_session_sync: tuple[Session, dict[str, type]]) -> None:
    session, uuid_models = uuid_test_session_sync
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
    uuid_test_session_sync: tuple[Session, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_sync
    item_model: Any = uuid_models["item"]
    tag_model: Any = uuid_models["tag"]

    tag_python, _tag_sa = _seed_item_tag_data_sync(session, item_model, tag_model)

    stmt = CollectionFilter(field_name="tags", values=[tag_python.id]).append_to_statement(
        select(item_model), item_model
    )
    items = session.execute(stmt).scalars().all()
    assert {i.name for i in items} == {"item-1", "item-2"}


def test_multifilter_relationship_filter_sync(uuid_test_session_sync: tuple[Session, dict[str, type]]) -> None:
    session, uuid_models = uuid_test_session_sync
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


def test_relationship_filter_many_to_one_sync(uuid_test_session_sync: tuple[Session, dict[str, type]]) -> None:
    session, uuid_models = uuid_test_session_sync
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


@pytest.mark.asyncio
async def test_relationship_filter_many_to_many_async(
    uuid_test_session_async: tuple[AsyncSession, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_async
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
    uuid_test_session_async: tuple[AsyncSession, dict[str, type]],
) -> None:
    session, uuid_models = uuid_test_session_async
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
