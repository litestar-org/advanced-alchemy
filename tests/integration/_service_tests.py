"""Unit tests for the SQLAlchemy Repository implementation."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Union, cast
from uuid import uuid4

import pytest
from msgspec import Struct
from pydantic import BaseModel
from sqlalchemy import and_

from advanced_alchemy.exceptions import NotFoundError, RepositoryError
from advanced_alchemy.filters import (
    NotInSearchFilter,
    SearchFilter,
)
from advanced_alchemy.repository._util import get_instrumented_attr
from advanced_alchemy.repository.memory import (
    SQLAlchemyAsyncMockRepository,
    SQLAlchemyAsyncMockSlugRepository,
    SQLAlchemySyncMockRepository,
    SQLAlchemySyncMockSlugRepository,
)
from advanced_alchemy.service.pagination import OffsetPagination
from tests.fixtures.types import (
    AuthorModel,
    AuthorService,
    BookService,
    RawRecordData,
    SlugBookModel,
    SlugBookService,
)
from tests.helpers import maybe_async


# service tests
async def test_service_filter_search(author_service: AuthorService) -> None:
    existing_obj = await maybe_async(
        author_service.list(SearchFilter(field_name="name", value="gath", ignore_case=False)),
    )
    assert existing_obj[0].name == "Agatha Christie"
    existing_obj = await maybe_async(
        author_service.list(SearchFilter(field_name="name", value="GATH", ignore_case=False)),
    )
    # sqlite & mysql are case insensitive by default with a `LIKE`
    dialect = (
        author_service.repository.session.bind.dialect.name if author_service.repository.session.bind else "default"
    )
    expected_objs = 1 if dialect in {"sqlite", "mysql", "mssql"} else 0
    assert len(existing_obj) == expected_objs
    existing_obj = await maybe_async(
        author_service.list(SearchFilter(field_name="name", value="GATH", ignore_case=True)),
    )
    assert existing_obj[0].name == "Agatha Christie"


async def test_service_count_method(author_service: AuthorService) -> None:
    """Test SQLAlchemy count.

    Args:
        author_service: The author mock repository
    """
    assert await maybe_async(author_service.count()) == 2


async def test_service_count_method_with_filters(raw_authors: RawRecordData, author_service: AuthorService) -> None:
    """Test SQLAlchemy count with filters.

    Args:
        author_service: The author mock repository
    """
    if issubclass(author_service.repository_type, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        assert (
            await maybe_async(
                author_service.count(
                    **{author_service.repository.model_type.name.key: raw_authors[0]["name"]},
                ),
            )
            == 1
        )
    else:
        assert (
            await maybe_async(
                author_service.count(
                    author_service.repository.model_type.name == raw_authors[0]["name"],
                ),
            )
            == 1
        )


async def test_service_list_and_count_method(raw_authors: RawRecordData, author_service: AuthorService) -> None:
    """Test SQLAlchemy list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_service: The author mock repository
    """
    exp_count = len(raw_authors)
    collection, count = await maybe_async(author_service.list_and_count())
    assert exp_count == count
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_service_list_and_count_method_with_filters(
    raw_authors: RawRecordData,
    author_service: AuthorService,
) -> None:
    """Test SQLAlchemy list with count and filters in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_service: The author mock repository
    """
    exp_name = raw_authors[0]["name"]
    exp_id = raw_authors[0]["id"]
    if issubclass(author_service.repository_type, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        collection, count = await maybe_async(
            author_service.list_and_count(**{author_service.repository.model_type.name.key: exp_name}),
        )
    else:
        collection, count = await maybe_async(
            author_service.list_and_count(author_service.repository.model_type.name == exp_name),
        )
    assert count == 1
    assert isinstance(collection, list)
    assert len(collection) == 1
    assert str(collection[0].id) == str(exp_id)
    assert collection[0].name == exp_name


async def test_service_list_and_count_basic_method(raw_authors: RawRecordData, author_service: AuthorService) -> None:
    """Test SQLAlchemy basic list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_service: The author mock repository
    """
    exp_count = len(raw_authors)
    collection, count = await maybe_async(author_service.list_and_count(force_basic_query_mode=True))
    assert exp_count == count
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_service_list_and_count_method_empty(book_service: BookService) -> None:
    collection, count = await maybe_async(book_service.list_and_count())
    assert count == 0
    assert isinstance(collection, list)
    assert len(collection) == 0


async def test_service_list_method(
    raw_authors_uuid: RawRecordData,
    author_service: AuthorService,
) -> None:
    exp_count = len(raw_authors_uuid)
    collection = await maybe_async(author_service.list())
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_service_list_method_with_filters(raw_authors: RawRecordData, author_service: AuthorService) -> None:
    exp_name = raw_authors[0]["name"]
    exp_id = raw_authors[0]["id"]
    if issubclass(author_service.repository_type, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        collection = await maybe_async(
            author_service.list(
                **{
                    author_service.repository.model_type.id.key: exp_id,  # type: ignore[union-attr]
                    author_service.repository.model_type.name.key: exp_name,
                },
            ),
        )
    else:
        collection = await maybe_async(
            author_service.list(
                and_(
                    author_service.repository.model_type.id == exp_id,
                    author_service.repository.model_type.name == exp_name,
                ),
            ),
        )
    assert isinstance(collection, list)
    assert len(collection) == 1
    assert str(collection[0].id) == str(exp_id)
    assert collection[0].name == exp_name


async def test_service_create_method(
    raw_authors: RawRecordData,
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    exp_count = len(raw_authors) + 1
    new_author = author_model(name="Testing", dob=datetime.now().date())
    obj = await maybe_async(author_service.create(new_author))
    count = await maybe_async(author_service.count())
    assert exp_count == count
    assert isinstance(obj, author_model)
    assert new_author.name == obj.name
    assert obj.id is not None


async def test_service_create_many_method(
    raw_authors: RawRecordData,
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    exp_count = len(raw_authors) + 2
    objs = await maybe_async(
        author_service.create_many(
            [
                author_model(name="Testing 2", dob=datetime.now().date()),
                author_model(name="Cody", dob=datetime.now().date()),
            ],
        ),
    )
    count = await maybe_async(author_service.count())
    assert exp_count == count
    assert isinstance(objs, list)
    assert len(objs) == 2
    for obj in objs:
        assert obj.id is not None
        assert obj.name in {"Testing 2", "Cody"}


async def test_service_update_many_method(author_service: AuthorService) -> None:
    if author_service.repository._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage,reportUnknownMemberType,reportAttributeAccessIssue]
        pytest.skip("Skipped on emulator")

    objs = await maybe_async(author_service.list())
    for idx, obj in enumerate(objs):
        obj.name = f"Update {idx}"
    objs = await maybe_async(author_service.update_many(list(objs)))
    for obj in objs:
        assert obj.name.startswith("Update")


async def test_service_exists_method(author_service: AuthorService, first_author_id: Any) -> None:
    exists = await maybe_async(author_service.exists(id=first_author_id))
    assert exists


async def test_service_update_method_item_id(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.get(first_author_id))
    obj.name = "Updated Name2"
    updated_obj = await maybe_async(author_service.update(item_id=first_author_id, data=obj))
    assert updated_obj.name == obj.name


async def test_service_update_method_no_item_id(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.get(first_author_id))
    obj.name = "Updated Name2"
    updated_obj = await maybe_async(author_service.update(data=obj))
    assert str(updated_obj.id) == str(first_author_id)
    assert updated_obj.name == obj.name


async def test_service_update_method_data_is_dict(author_service: AuthorService, first_author_id: Any) -> None:
    new_date = datetime.date(datetime.now())
    updated_obj = await maybe_async(
        author_service.update(item_id=first_author_id, data={"dob": new_date}),
    )
    assert updated_obj.dob == new_date
    # ensure the other fields are not affected
    assert updated_obj.name == "Agatha Christie"


async def test_service_update_method_data_is_dict_with_none_value(
    author_service: AuthorService,
    first_author_id: Any,
) -> None:
    updated_obj = await maybe_async(author_service.update(item_id=first_author_id, data={"dob": None}))
    assert cast(Union[date, None], updated_obj.dob) is None
    # ensure the other fields are not affected
    assert updated_obj.name == "Agatha Christie"


async def test_service_update_method_instrumented_attribute(
    author_service: AuthorService,
    first_author_id: Any,
) -> None:
    obj = await maybe_async(author_service.get(first_author_id))
    id_attribute = get_instrumented_attr(author_service.repository.model_type, "id")
    obj.name = "Updated Name2"
    updated_obj = await maybe_async(author_service.update(data=obj, id_attribute=id_attribute))
    assert str(updated_obj.id) == str(first_author_id)
    assert updated_obj.name == obj.name


async def test_service_delete_method(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.delete(first_author_id))
    assert str(obj.id) == str(first_author_id)


async def test_service_delete_many_method(author_service: AuthorService, author_model: AuthorModel) -> None:
    data_to_insert = [author_model(name="author name %d" % chunk) for chunk in range(2000)]
    _ = await maybe_async(author_service.create_many(data_to_insert))
    all_objs = await maybe_async(author_service.list())
    ids_to_delete = [existing_obj.id for existing_obj in all_objs]
    objs = await maybe_async(author_service.delete_many(ids_to_delete))
    await maybe_async(author_service.repository.session.commit())  # pyright: ignore[reportUnknownArgumentType,reportUnknownMemberType,reportAttributeAccessIssue]
    assert len(objs) > 0
    data, count = await maybe_async(author_service.list_and_count())
    assert data == []
    assert count == 0


async def test_service_delete_where_method_empty(author_service: AuthorService, author_model: AuthorModel) -> None:
    data_to_insert = [author_model(name="author name %d" % chunk) for chunk in range(2000)]
    _ = await maybe_async(author_service.create_many(data_to_insert))
    total_count = await maybe_async(author_service.count())
    all_objs = await maybe_async(author_service.delete_where())
    assert len(all_objs) == total_count
    data, count = await maybe_async(author_service.list_and_count())
    assert data == []
    assert count == 0


async def test_service_delete_where_method_filter(author_service: AuthorService, author_model: AuthorModel) -> None:
    data_to_insert = [author_model(name="delete me") for _ in range(2000)]
    _ = await maybe_async(author_service.create_many(data_to_insert))
    all_objs = await maybe_async(author_service.delete_where(name="delete me"))
    assert len(all_objs) == len(data_to_insert)
    count = await maybe_async(author_service.count())
    assert count == 2


async def test_service_delete_where_method_search_filter(
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    data_to_insert = [author_model(name="delete me") for _ in range(2000)]
    _ = await maybe_async(author_service.create_many(data_to_insert))
    all_objs = await maybe_async(author_service.delete_where(NotInSearchFilter(field_name="name", value="delete me")))
    assert len(all_objs) == 2
    count = await maybe_async(author_service.count())
    assert count == len(data_to_insert)


async def test_service_get_method(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.get(first_author_id))
    assert obj.name == "Agatha Christie"


async def test_service_get_one_or_none_method(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.get_one_or_none(id=first_author_id))
    assert obj is not None
    assert obj.name == "Agatha Christie"
    none_obj = await maybe_async(author_service.get_one_or_none(name="I don't exist"))
    assert none_obj is None


async def test_service_get_one_method(author_service: AuthorService, first_author_id: Any) -> None:
    obj = await maybe_async(author_service.get_one(id=first_author_id))
    assert obj is not None
    assert obj.name == "Agatha Christie"
    with pytest.raises(RepositoryError):
        _ = await author_service.get_one(name="I don't exist")


async def test_service_get_or_upsert_method(author_service: AuthorService, first_author_id: Any) -> None:
    existing_obj, existing_created = await maybe_async(author_service.get_or_upsert(name="Agatha Christie"))
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_created is False
    new_obj, new_created = await maybe_async(author_service.get_or_upsert(name="New Author"))
    assert new_obj.id is not None
    assert new_obj.name == "New Author"
    assert new_created


async def test_service_get_and_update_method(author_service: AuthorService, first_author_id: Any) -> None:
    existing_obj, existing_created = await maybe_async(
        author_service.get_and_update(name="Agatha Christie", match_fields="name"),
    )
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_created is False
    with pytest.raises(NotFoundError):
        _ = await maybe_async(author_service.get_and_update(name="New Author"))


async def test_service_upsert_method(
    author_service: AuthorService,
    first_author_id: Any,
    author_model: AuthorModel,
    new_pk_id: Any,
) -> None:
    existing_obj = await maybe_async(author_service.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_obj = await maybe_async(author_service.upsert(item_id=first_author_id, data=existing_obj))
    assert str(upsert_update_obj.id) == str(first_author_id)
    assert upsert_update_obj.name == "Agatha C."

    upsert_insert_obj = await maybe_async(author_service.upsert(data=author_model(name="An Author")))
    assert upsert_insert_obj.id is not None
    assert upsert_insert_obj.name == "An Author"

    # ensures that it still works even if the ID is added before insert
    upsert2_insert_obj = await maybe_async(
        author_service.upsert(author_model(id=new_pk_id, name="Another Author")),
    )
    assert upsert2_insert_obj.id is not None
    assert upsert2_insert_obj.name == "Another Author"


async def test_service_upsert_method_match(
    author_service: AuthorService,
    first_author_id: Any,
    author_model: AuthorModel,
    new_pk_id: Any,
) -> None:
    if author_service.repository._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage,reportUnknownMemberType,reportAttributeAccessIssue]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_obj = await maybe_async(author_service.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_obj = await maybe_async(
        author_service.upsert(data=existing_obj.to_dict(exclude={"id"}), match_fields=["name"]),
    )
    if not isinstance(author_service.repository, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        assert str(upsert_update_obj.id) == str(first_author_id)
    assert upsert_update_obj.name == "Agatha C."

    upsert_insert_obj = await maybe_async(
        author_service.upsert(data=author_model(name="An Author"), match_fields=["name"]),
    )
    assert upsert_insert_obj.id is not None
    assert upsert_insert_obj.name == "An Author"

    # ensures that it still works even if the ID is added before insert
    upsert2_insert_obj = await maybe_async(
        author_service.upsert(author_model(id=new_pk_id, name="Another Author"), match_fields=["name"]),
    )
    assert upsert2_insert_obj.id is not None
    assert upsert2_insert_obj.name == "Another Author"


async def test_service_upsert_many_method(
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    if author_service.repository._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage,reportUnknownMemberType,reportAttributeAccessIssue]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_obj = await maybe_async(author_service.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_objs = await maybe_async(
        author_service.upsert_many(
            [
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
        ),
    )
    assert len(upsert_update_objs) == 3
    assert upsert_update_objs[0].id is not None
    assert upsert_update_objs[0].name in ("Agatha C.", "Inserted Author", "Custom Author")
    assert upsert_update_objs[1].id is not None
    assert upsert_update_objs[1].name in ("Agatha C.", "Inserted Author", "Custom Author")
    assert upsert_update_objs[2].id is not None
    assert upsert_update_objs[2].name in ("Agatha C.", "Inserted Author", "Custom Author")


async def test_service_upsert_many_method_match_fields_id(
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    if author_service.repository._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage,reportUnknownMemberType,reportAttributeAccessIssue]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_obj = await maybe_async(author_service.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_objs = await maybe_async(
        author_service.upsert_many(
            [
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
            match_fields=["id"],
        ),
    )
    assert len(upsert_update_objs) == 3
    assert upsert_update_objs[0].id is not None
    assert upsert_update_objs[0].name in ("Agatha C.", "Inserted Author", "Custom Author")
    assert upsert_update_objs[1].id is not None
    assert upsert_update_objs[1].name in ("Agatha C.", "Inserted Author", "Custom Author")
    assert upsert_update_objs[2].id is not None
    assert upsert_update_objs[2].name in ("Agatha C.", "Inserted Author", "Custom Author")


async def test_service_upsert_many_method_match_fields_non_id(
    author_service: AuthorService,
    author_model: AuthorModel,
) -> None:
    if author_service.repository._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage,reportUnknownMemberType,reportAttributeAccessIssue]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_count = await maybe_async(author_service.count())
    existing_obj = await maybe_async(author_service.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    _ = await maybe_async(
        author_service.upsert_many(
            data=[
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
            match_fields=["name"],
        ),
    )
    existing_count_now = await maybe_async(author_service.count())

    assert existing_count_now > existing_count


async def test_service_update_no_pk(author_service: AuthorService) -> None:
    with pytest.raises(RepositoryError):
        _existing_obj = await maybe_async(author_service.update(data={"name": "Agatha Christie"}))


async def test_service_create_method_slug(
    raw_slug_books: RawRecordData,
    slug_book_service: SlugBookService,
    slug_book_model: SlugBookModel,
) -> None:
    new_book = {"title": "a new book!!", "author_id": uuid4().hex}
    obj = await maybe_async(slug_book_service.create(new_book))
    assert isinstance(obj, slug_book_model)
    assert new_book["title"] == obj.title
    assert obj.slug == "a-new-book"
    assert obj.id is not None


async def test_service_create_method_slug_existing(
    raw_slug_books: RawRecordData,
    slug_book_service: SlugBookService,
    slug_book_model: SlugBookModel,
) -> None:
    if isinstance(
        slug_book_service.repository_type,
        (
            SQLAlchemySyncMockSlugRepository,
            SQLAlchemyAsyncMockSlugRepository,
            SQLAlchemyAsyncMockRepository,
            SQLAlchemySyncMockRepository,
        ),
    ):
        pytest.skip("Skipping additional bigint mock repository tests")
    current_count = await maybe_async(slug_book_service.count())
    if current_count == 0:
        _ = await maybe_async(slug_book_service.create_many(raw_slug_books))

    new_book = {"title": "Murder on the Orient Express", "author_id": uuid4().hex}
    obj = await maybe_async(slug_book_service.create(new_book))
    assert isinstance(obj, slug_book_model)
    assert new_book["title"] == obj.title
    assert obj.slug != "murder-on-the-orient-express"
    assert obj.id is not None


async def test_service_create_many_method_slug(
    raw_slug_books: RawRecordData,
    slug_book_service: SlugBookService,
    slug_book_model: SlugBookModel,
) -> None:
    objs = await maybe_async(
        slug_book_service.create_many(
            [
                {"title": " extra!! ", "author_id": uuid4().hex},
                {"title": "punctuated Book!!", "author_id": uuid4().hex},
            ],
        ),
    )
    assert isinstance(objs, list)
    for obj in objs:
        assert obj.id is not None
        assert obj.slug in {"extra", "punctuated-book"}
        assert obj.title in {" extra!! ", "punctuated Book!!"}


class AuthorStruct(Struct):
    name: str


class AuthorBaseModel(BaseModel):
    model_config = {"from_attributes": True}
    name: str


async def test_service_paginated_to_schema(raw_authors: RawRecordData, author_service: AuthorService) -> None:
    """Test SQLAlchemy list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_service: The author mock repository
    """
    exp_count = len(raw_authors)
    collection, count = await maybe_async(author_service.list_and_count())
    model_dto = author_service.to_schema(data=collection, total=count)
    pydantic_dto = author_service.to_schema(data=collection, total=count, schema_type=AuthorBaseModel)
    msgspec_dto = author_service.to_schema(data=collection, total=count, schema_type=AuthorStruct)
    assert exp_count == count
    assert isinstance(model_dto, OffsetPagination)
    assert isinstance(model_dto.items[0].name, str)
    assert model_dto.total == exp_count
    assert isinstance(pydantic_dto, OffsetPagination)
    assert isinstance(pydantic_dto.items[0].name, str)  # pyright: ignore
    assert pydantic_dto.total == exp_count
    assert isinstance(msgspec_dto, OffsetPagination)
    assert isinstance(msgspec_dto.items[0].name, str)  # pyright: ignore
    assert msgspec_dto.total == exp_count


async def test_service_to_schema(
    author_service: AuthorService,
    first_author_id: Any,
) -> None:
    """Test SQLAlchemy list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_service: The author mock repository
    """
    obj = await maybe_async(author_service.get(first_author_id))
    model_dto = author_service.to_schema(data=obj)
    pydantic_dto = author_service.to_schema(data=obj, schema_type=AuthorBaseModel)
    msgspec_dto = author_service.to_schema(data=obj, schema_type=AuthorStruct)
    assert issubclass(AuthorStruct, Struct)
    assert issubclass(AuthorBaseModel, BaseModel)
    assert isinstance(model_dto.name, str)
    assert isinstance(pydantic_dto, BaseModel)
    assert isinstance(msgspec_dto, Struct)
    assert isinstance(pydantic_dto.name, str)  # pyright: ignore
    assert isinstance(msgspec_dto.name, str)  # pyright: ignore
