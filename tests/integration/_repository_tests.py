"""Unit tests for the SQLAlchemy Repository implementation."""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Generator, cast
from uuid import UUID

import pytest
from sqlalchemy import and_
from sqlalchemy.orm import Session
from time_machine import travel

from advanced_alchemy.exceptions import NotFoundError, RepositoryError
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    NotInCollectionFilter,
    NotInSearchFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.repository.memory import (
    SQLAlchemyAsyncMockRepository,
    SQLAlchemySyncMockRepository,
)
from tests.fixtures.bigint import models as models_bigint
from tests.fixtures.types import (
    AnyAuthorRepository,
    AnyBook,
    AuthorModel,
    AuthorRepository,
    BookRepository,
    ItemModel,
    ItemRepository,
    ModelWithFetchedValue,
    ModelWithFetchedValueRepository,
    RawRecordData,
    RepositoryPKType,
    RuleModel,
    RuleRepository,
    RuleService,
    SecretModel,
    SecretRepository,
    TagModel,
    TagRepository,
)
from tests.fixtures.uuid import models as models_uuid
from tests.helpers import maybe_async

if TYPE_CHECKING:
    from pytest import FixtureRequest
    from time_machine import Coordinates


def test_filter_by_kwargs_with_incorrect_attribute_name(author_repo: AnyAuthorRepository) -> None:
    """Test SQLAlchemy filter by kwargs with invalid column name.

    Args:
        author_repo: The author mock repository
    """
    with pytest.raises(RepositoryError):
        if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
            author_repo.filter_collection_by_kwargs(author_repo.__collection__().list(), whoops="silly me")
        else:
            author_repo.filter_collection_by_kwargs(author_repo.statement, whoops="silly me")


async def test_repo_count_method(author_repo: AnyAuthorRepository) -> None:
    """Test SQLAlchemy count.

    Args:
        author_repo: The author mock repository
    """
    assert await maybe_async(author_repo.count()) == 2


async def test_repo_count_method_with_filters(raw_authors: RawRecordData, author_repo: AnyAuthorRepository) -> None:
    """Test SQLAlchemy count with filters.

    Args:
        author_repo: The author mock repository
    """
    if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        assert (
            await maybe_async(
                author_repo.count(
                    **{author_repo.model_type.name.key: raw_authors[0]["name"]},
                ),
            )
            == 1
        )
    else:
        assert (
            await maybe_async(
                author_repo.count(
                    author_repo.model_type.name == raw_authors[0]["name"],
                ),
            )
            == 1
        )


async def test_repo_list_and_count_method(raw_authors: RawRecordData, author_repo: AnyAuthorRepository) -> None:
    """Test SQLAlchemy list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_repo: The author mock repository
    """
    exp_count = len(raw_authors)
    collection, count = await maybe_async(author_repo.list_and_count())
    assert exp_count == count
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_repo_list_and_count_method_with_filters(
    raw_authors: RawRecordData,
    author_repo: AnyAuthorRepository,
) -> None:
    """Test SQLAlchemy list with count and filters in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_repo: The author mock repository
    """
    exp_name = raw_authors[0]["name"]
    exp_id = raw_authors[0]["id"]
    if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        collection, count = await maybe_async(
            author_repo.list_and_count(**{author_repo.model_type.name.key: exp_name}),
        )
    else:
        collection, count = await maybe_async(
            author_repo.list_and_count(author_repo.model_type.name == exp_name),
        )
    assert count == 1
    assert isinstance(collection, list)
    assert len(collection) == 1
    assert str(collection[0].id) == str(exp_id)
    assert collection[0].name == exp_name


async def test_repo_list_and_count_basic_method(raw_authors: RawRecordData, author_repo: AnyAuthorRepository) -> None:
    """Test SQLAlchemy basic list with count in asyncpg.

    Args:
        raw_authors: list of authors pre-seeded into the mock repository
        author_repo: The author mock repository
    """
    exp_count = len(raw_authors)
    collection, count = await maybe_async(author_repo.list_and_count(force_basic_query_mode=True))
    assert exp_count == count
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_repo_list_and_count_method_empty(book_repo: BookRepository) -> None:
    collection, count = await maybe_async(book_repo.list_and_count())
    assert count == 0
    assert isinstance(collection, list)
    assert len(collection) == 0


@pytest.fixture()
def frozen_datetime() -> Generator[Coordinates, None, None]:
    with travel(datetime.utcnow, tick=False) as frozen:  # pyright: ignore[reportDeprecated,reportCallIssue]
        yield frozen


async def test_repo_created_updated(
    frozen_datetime: Coordinates,
    author_repo: AnyAuthorRepository,
    book_model: type[AnyBook],
    repository_pk_type: RepositoryPKType,
) -> None:
    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.sync import SQLAlchemySyncConfig

    if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        pytest.skip(f"{SQLAlchemyAsyncMockRepository.__name__} does not update created/updated columns")
    if isinstance(author_repo, SQLAlchemyAsyncRepository):  # pyright: ignore[reportUnnecessaryIsInstance]
        config = SQLAlchemyAsyncConfig(
            engine_instance=author_repo.session.get_bind(),  # type: ignore[arg-type]
        )
    else:
        config = SQLAlchemySyncConfig(  # type: ignore[unreachable]
            engine_instance=author_repo.session.get_bind(),
        )
    config.__post_init__()
    author = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    original_update_dt = author.updated_at
    assert author.created_at is not None
    assert author.updated_at is not None
    frozen_datetime.shift(delta=timedelta(seconds=5))
    # looks odd, but we want to get correct type checking here
    if repository_pk_type == "uuid":
        author = cast(models_uuid.UUIDAuthor, author)
        book_model = cast("type[models_uuid.UUIDBook]", book_model)
    else:
        author = cast(models_bigint.BigIntAuthor, author)
        book_model = cast("type[models_bigint.BigIntBook]", book_model)
    author.name = "Altered"
    author = await maybe_async(author_repo.update(author))
    assert author.updated_at > original_update_dt
    # test nested
    author.books.append(book_model(title="Testing"))  # type: ignore[arg-type]
    author = await maybe_async(author_repo.update(author))
    assert author.updated_at > original_update_dt


async def test_repo_created_updated_no_listener(
    frozen_datetime: Coordinates,
    author_repo: AuthorRepository,
    book_model: type[AnyBook],
    repository_pk_type: RepositoryPKType,
) -> None:
    from sqlalchemy import event
    from sqlalchemy.exc import InvalidRequestError

    from advanced_alchemy._listeners import touch_updated_timestamp
    from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.sync import SQLAlchemySyncConfig

    with contextlib.suppress(InvalidRequestError):
        event.remove(Session, "before_flush", touch_updated_timestamp)

    if isinstance(author_repo, SQLAlchemyAsyncRepository):  # pyright: ignore[reportUnnecessaryIsInstance]
        config = SQLAlchemyAsyncConfig(
            enable_touch_updated_timestamp_listener=False,
            engine_instance=author_repo.session.get_bind(),  # type: ignore[arg-type]
        )
    else:
        config = SQLAlchemySyncConfig(  # type: ignore[unreachable]
            enable_touch_updated_timestamp_listener=False,
            engine_instance=author_repo.session.get_bind(),
        )
    config.__post_init__()
    author = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    original_update_dt = author.updated_at
    assert author.created_at is not None
    assert author.updated_at is not None
    frozen_datetime.shift(delta=timedelta(seconds=5))
    # looks odd, but we want to get correct type checking here
    if repository_pk_type == "uuid":
        author = cast(models_uuid.UUIDAuthor, author)
        book_model = cast("type[models_uuid.UUIDBook]", book_model)
    else:
        author = cast(models_bigint.BigIntAuthor, author)
        book_model = cast("type[models_bigint.BigIntBook]", book_model)
    author.books.append(book_model(title="Testing"))  # type: ignore[arg-type]
    author = await maybe_async(author_repo.update(author))
    assert author.updated_at == original_update_dt


async def test_repo_list_method(
    raw_authors_uuid: RawRecordData,
    author_repo: AnyAuthorRepository,
) -> None:
    exp_count = len(raw_authors_uuid)
    collection = await maybe_async(author_repo.list())
    assert isinstance(collection, list)
    assert len(collection) == exp_count


async def test_repo_list_method_with_filters(raw_authors: RawRecordData, author_repo: AnyAuthorRepository) -> None:
    exp_name = raw_authors[0]["name"]
    exp_id = raw_authors[0]["id"]
    if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        collection = await maybe_async(
            author_repo.list(**{author_repo.model_type.id.key: exp_id, author_repo.model_type.name.key: exp_name}),  # type: ignore[union-attr]
        )
    else:
        collection = await maybe_async(
            author_repo.list(
                and_(author_repo.model_type.id == exp_id, author_repo.model_type.name == exp_name),
            ),
        )
    assert isinstance(collection, list)
    assert len(collection) == 1
    assert str(collection[0].id) == str(exp_id)
    assert collection[0].name == exp_name


async def test_repo_add_method(
    raw_authors: RawRecordData,
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    exp_count = len(raw_authors) + 1
    new_author = author_model(name="Testing", dob=datetime.now().date())
    obj = await maybe_async(author_repo.add(new_author))
    count = await maybe_async(author_repo.count())
    assert exp_count == count
    assert isinstance(obj, author_model)
    assert new_author.name == obj.name
    assert obj.id is not None


async def test_repo_add_many_method(
    raw_authors: RawRecordData,
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    exp_count = len(raw_authors) + 2
    objs = await maybe_async(
        author_repo.add_many(
            [
                author_model(name="Testing 2", dob=datetime.now().date()),
                author_model(name="Cody", dob=datetime.now().date()),
            ],
        ),
    )
    count = await maybe_async(author_repo.count())
    assert exp_count == count
    assert isinstance(objs, list)
    assert len(objs) == 2
    for obj in objs:
        assert obj.id is not None
        assert obj.name in {"Testing 2", "Cody"}


async def test_repo_update_many_method(author_repo: AnyAuthorRepository) -> None:
    if author_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip("Skipped on emulator")

    objs = await maybe_async(author_repo.list())
    for idx, obj in enumerate(objs):
        obj.name = f"Update {idx}"
    objs = await maybe_async(author_repo.update_many(objs))
    for obj in objs:
        assert obj.name.startswith("Update")


async def test_repo_exists_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    exists = await maybe_async(author_repo.exists(id=first_author_id))
    assert exists


async def test_repo_exists_method_with_filters(
    raw_authors: RawRecordData,
    author_repo: AnyAuthorRepository,
    first_author_id: Any,
) -> None:
    if isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        exists = await maybe_async(
            author_repo.exists(
                **{author_repo.model_type.name.key: raw_authors[0]["name"]},
                id=first_author_id,
            ),
        )
    else:
        exists = await maybe_async(
            author_repo.exists(
                author_repo.model_type.name == raw_authors[0]["name"],
                id=first_author_id,
            ),
        )
    assert exists


async def test_repo_update_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    obj = await maybe_async(author_repo.get(first_author_id))
    obj.name = "Updated Name"
    updated_obj = await maybe_async(author_repo.update(obj))
    assert updated_obj.name == obj.name


async def test_repo_delete_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    obj = await maybe_async(author_repo.delete(first_author_id))
    assert str(obj.id) == str(first_author_id)


async def test_repo_delete_many_method(author_repo: AnyAuthorRepository, author_model: AuthorModel) -> None:
    data_to_insert = [author_model(name="author name %d" % chunk) for chunk in range(2000)]
    _ = await maybe_async(author_repo.add_many(data_to_insert))
    all_objs = await maybe_async(author_repo.list())
    ids_to_delete = [existing_obj.id for existing_obj in all_objs]
    objs = await maybe_async(author_repo.delete_many(ids_to_delete))
    await maybe_async(author_repo.session.commit())
    assert len(objs) > 0
    data, count = await maybe_async(author_repo.list_and_count())
    assert data == []
    assert count == 0


async def test_repo_get_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    obj = await maybe_async(author_repo.get(first_author_id))
    assert obj.name == "Agatha Christie"


async def test_repo_get_one_or_none_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    obj = await maybe_async(author_repo.get_one_or_none(id=first_author_id))
    assert obj is not None
    assert obj.name == "Agatha Christie"
    none_obj = await maybe_async(author_repo.get_one_or_none(name="I don't exist"))
    assert none_obj is None


async def test_repo_get_one_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    obj = await maybe_async(author_repo.get_one(id=first_author_id))
    assert obj is not None
    assert obj.name == "Agatha Christie"
    with pytest.raises(RepositoryError):
        _ = await author_repo.get_one(name="I don't exist")


async def test_repo_get_or_upsert_method(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    existing_obj, existing_created = await maybe_async(author_repo.get_or_upsert(name="Agatha Christie"))
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_created is False
    new_obj, new_created = await maybe_async(author_repo.get_or_upsert(name="New Author"))
    assert new_obj.id is not None
    assert new_obj.name == "New Author"
    assert new_created


async def test_repo_get_or_upsert_match_filter(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    now = datetime.now()
    existing_obj, existing_created = await maybe_async(
        author_repo.get_or_upsert(match_fields="name", name="Agatha Christie", dob=now.date()),
    )
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_obj.dob == now.date()
    assert existing_created is False


async def test_repo_get_or_upsert_match_filter_no_upsert(
    author_repo: AnyAuthorRepository,
    first_author_id: Any,
) -> None:
    now = datetime.now()
    existing_obj, existing_created = await maybe_async(
        author_repo.get_or_upsert(match_fields="name", upsert=False, name="Agatha Christie", dob=now.date()),
    )
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_obj.dob != now.date()
    assert existing_created is False


async def test_repo_get_and_update(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    existing_obj, existing_updated = await maybe_async(
        author_repo.get_and_update(name="Agatha Christie"),
    )
    assert str(existing_obj.id) == str(first_author_id)
    assert existing_updated is False


async def test_repo_get_and_upsert_match_filter(author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
    now = datetime.now()
    with pytest.raises(NotFoundError):
        _ = await maybe_async(
            author_repo.get_and_update(match_fields="name", name="Agatha Christie123", dob=now.date()),
        )
    with pytest.raises(NotFoundError):
        _ = await maybe_async(
            author_repo.get_and_update(name="Agatha Christie123"),
        )


async def test_repo_upsert_method(
    author_repo: AnyAuthorRepository,
    first_author_id: Any,
    author_model: AuthorModel,
    new_pk_id: Any,
) -> None:
    existing_obj = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_obj = await maybe_async(author_repo.upsert(existing_obj))
    assert str(upsert_update_obj.id) == str(first_author_id)
    assert upsert_update_obj.name == "Agatha C."

    upsert_insert_obj = await maybe_async(author_repo.upsert(author_model(name="An Author")))
    assert upsert_insert_obj.id is not None
    assert upsert_insert_obj.name == "An Author"

    # ensures that it still works even if the ID is added before insert
    upsert2_insert_obj = await maybe_async(author_repo.upsert(author_model(id=new_pk_id, name="Another Author")))
    assert upsert2_insert_obj.id is not None
    assert upsert2_insert_obj.name == "Another Author"
    _ = await maybe_async(author_repo.get_one(name="Leo Tolstoy"))
    # ensures that it still works even if the ID isn't set on an existing key
    new_dob = datetime.strptime("2028-09-09", "%Y-%m-%d").date()
    upsert3_update_obj = await maybe_async(
        author_repo.upsert(
            author_model(name="Leo Tolstoy", dob=new_dob),
            match_fields=["name"],
        ),
    )
    if not isinstance(author_repo, (SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository)):
        assert upsert3_update_obj.id in {UUID("5ef29f3c-3560-4d15-ba6b-a2e5c721e4d2"), 2024}
    assert upsert3_update_obj.name == "Leo Tolstoy"
    assert upsert3_update_obj.dob == new_dob


async def test_repo_upsert_many_method(
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    if author_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_obj = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_objs = await maybe_async(
        author_repo.upsert_many(
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


async def test_repo_upsert_many_method_match(
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    if author_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_obj = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    upsert_update_objs = await maybe_async(
        author_repo.upsert_many(
            data=[
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
            match_fields=["id"],
        ),
    )
    assert len(upsert_update_objs) == 3


async def test_repo_upsert_many_method_match_non_id(
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    if author_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_count = await maybe_async(author_repo.count())
    existing_obj = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    _ = await maybe_async(
        author_repo.upsert_many(
            data=[
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
            match_fields=["name"],
        ),
    )
    existing_count_now = await maybe_async(author_repo.count())

    assert existing_count_now > existing_count


async def test_repo_upsert_many_method_match_not_on_input(
    author_repo: AnyAuthorRepository,
    author_model: AuthorModel,
) -> None:
    if author_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip(
            "Skipped on emulator. See the following:  https://github.com/GoogleCloudPlatform/cloud-spanner-emulator/issues/73",
        )
    existing_count = await maybe_async(author_repo.count())
    existing_obj = await maybe_async(author_repo.get_one(name="Agatha Christie"))
    existing_obj.name = "Agatha C."
    _ = await maybe_async(
        author_repo.upsert_many(
            data=[
                existing_obj,
                author_model(name="Inserted Author"),
                author_model(name="Custom Author"),
            ],
            match_fields=["id"],
        ),
    )
    existing_count_now = await maybe_async(author_repo.count())

    assert existing_count_now > existing_count


async def test_repo_filter_before_after(author_repo: AnyAuthorRepository) -> None:
    before_filter = BeforeAfter(
        field_name="created_at",
        before=datetime.strptime("2023-05-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(timezone.utc),
        after=None,
    )
    existing_obj = await maybe_async(author_repo.list(before_filter))
    assert existing_obj[0].name == "Leo Tolstoy"

    after_filter = BeforeAfter(
        field_name="created_at",
        after=datetime.strptime("2023-03-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(timezone.utc),
        before=None,
    )
    existing_obj = await maybe_async(author_repo.list(after_filter))
    assert existing_obj[0].name == "Agatha Christie"


async def test_repo_filter_on_before_after(author_repo: AnyAuthorRepository) -> None:
    before_filter = OnBeforeAfter(
        field_name="created_at",
        on_or_before=datetime.strptime("2023-05-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(timezone.utc),
        on_or_after=None,
    )
    existing_obj = await maybe_async(
        author_repo.list(*[before_filter, OrderBy(field_name="created_at", sort_order="desc")]),  # type: ignore
    )
    assert existing_obj[0].name == "Agatha Christie"

    after_filter = OnBeforeAfter(
        field_name="created_at",
        on_or_after=datetime.strptime("2023-03-01T00:00:00", "%Y-%m-%dT%H:%M:%S").astimezone(timezone.utc),
        on_or_before=None,
    )
    existing_obj = await maybe_async(
        author_repo.list(*[after_filter, OrderBy(field_name="created_at", sort_order="desc")]),  # type: ignore
    )
    assert existing_obj[0].name == "Agatha Christie"


async def test_repo_filter_search(author_repo: AnyAuthorRepository) -> None:
    existing_obj = await maybe_async(author_repo.list(SearchFilter(field_name="name", value="gath", ignore_case=False)))
    assert existing_obj[0].name == "Agatha Christie"
    existing_obj = await maybe_async(author_repo.list(SearchFilter(field_name="name", value="GATH", ignore_case=False)))
    # sqlite & mysql are case insensitive by default with a `LIKE`
    dialect = author_repo.session.bind.dialect.name if author_repo.session.bind else "default"
    expected_objs = 1 if dialect in {"sqlite", "mysql", "mssql"} else 0
    assert len(existing_obj) == expected_objs
    existing_obj = await maybe_async(author_repo.list(SearchFilter(field_name="name", value="GATH", ignore_case=True)))
    assert existing_obj[0].name == "Agatha Christie"


async def test_repo_filter_search_multi_field(author_repo: AnyAuthorRepository) -> None:
    existing_obj = await maybe_async(
        author_repo.list(SearchFilter(field_name={"name", "string_field"}, value="gath", ignore_case=False)),
    )
    assert existing_obj[0].name == "Agatha Christie"
    existing_obj = await maybe_async(
        author_repo.list(SearchFilter(field_name={"name", "string_field"}, value="GATH", ignore_case=False)),
    )
    # sqlite & mysql are case insensitive by default with a `LIKE`
    dialect = author_repo.session.bind.dialect.name if author_repo.session.bind else "default"
    expected_objs = 1 if dialect in {"sqlite", "mysql", "mssql"} else 0
    assert len(existing_obj) == expected_objs
    existing_obj = await maybe_async(
        author_repo.list(SearchFilter(field_name={"name", "string_field"}, value="GATH", ignore_case=True)),
    )
    assert existing_obj[0].name == "Agatha Christie"


async def test_repo_filter_not_in_search(author_repo: AnyAuthorRepository) -> None:
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name="name", value="gath", ignore_case=False)),
    )
    assert existing_obj[0].name == "Leo Tolstoy"
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name="name", value="GATH", ignore_case=False)),
    )
    # sqlite & mysql are case insensitive by default with a `LIKE`
    dialect = author_repo.session.bind.dialect.name if author_repo.session.bind else "default"
    expected_objs = 1 if dialect in {"sqlite", "mysql", "mssql"} else 2
    assert len(existing_obj) == expected_objs
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name={"name", "string_field"}, value="GATH", ignore_case=True)),
    )
    assert existing_obj[0].name == "Leo Tolstoy"


async def test_repo_filter_not_in_search_multi_field(author_repo: AnyAuthorRepository) -> None:
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name={"name", "string_field"}, value="gath", ignore_case=False)),
    )
    assert existing_obj[0].name == "Leo Tolstoy"
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name={"name", "string_field"}, value="GATH", ignore_case=False)),
    )
    # sqlite & mysql are case insensitive by default with a `LIKE`
    dialect = author_repo.session.bind.dialect.name if author_repo.session.bind else "default"
    expected_objs = 1 if dialect in {"sqlite", "mysql", "mssql"} else 2
    assert len(existing_obj) == expected_objs
    existing_obj = await maybe_async(
        author_repo.list(NotInSearchFilter(field_name={"name", "string_field"}, value="GATH", ignore_case=True)),
    )
    assert existing_obj[0].name == "Leo Tolstoy"


async def test_repo_filter_order_by(author_repo: AnyAuthorRepository) -> None:
    existing_obj = await maybe_async(author_repo.list(OrderBy(field_name="created_at", sort_order="desc")))
    assert existing_obj[0].name == "Agatha Christie"
    existing_obj = await maybe_async(author_repo.list(OrderBy(field_name="created_at", sort_order="asc")))
    assert existing_obj[0].name == "Leo Tolstoy"


async def test_repo_filter_collection(
    author_repo: AnyAuthorRepository,
    existing_author_ids: Generator[Any, None, None],
) -> None:
    first_author_id = next(existing_author_ids)
    second_author_id = next(existing_author_ids)
    existing_obj = await maybe_async(author_repo.list(CollectionFilter(field_name="id", values=[first_author_id])))
    assert existing_obj[0].name == "Agatha Christie"

    existing_obj = await maybe_async(author_repo.list(CollectionFilter(field_name="id", values=[second_author_id])))
    assert existing_obj[0].name == "Leo Tolstoy"


async def test_repo_filter_no_obj_collection(
    author_repo: AnyAuthorRepository,
) -> None:
    no_obj = await maybe_async(author_repo.list(CollectionFilter[str](field_name="id", values=[])))
    assert no_obj == []


async def test_repo_filter_null_collection(
    author_repo: AnyAuthorRepository,
) -> None:
    no_obj = await maybe_async(author_repo.list(CollectionFilter[str](field_name="id", values=None)))
    assert len(no_obj) > 0


async def test_repo_filter_not_in_collection(
    author_repo: AnyAuthorRepository,
    existing_author_ids: Generator[Any, None, None],
) -> None:
    first_author_id = next(existing_author_ids)
    second_author_id = next(existing_author_ids)
    existing_obj = await maybe_async(author_repo.list(NotInCollectionFilter(field_name="id", values=[first_author_id])))
    assert existing_obj[0].name == "Leo Tolstoy"

    existing_obj = await maybe_async(
        author_repo.list(NotInCollectionFilter(field_name="id", values=[second_author_id])),
    )
    assert existing_obj[0].name == "Agatha Christie"


async def test_repo_filter_not_in_no_obj_collection(
    author_repo: AnyAuthorRepository,
) -> None:
    existing_obj = await maybe_async(author_repo.list(NotInCollectionFilter[str](field_name="id", values=[])))
    assert len(existing_obj) > 0


async def test_repo_filter_not_in_null_collection(
    author_repo: AnyAuthorRepository,
) -> None:
    existing_obj = await maybe_async(author_repo.list(NotInCollectionFilter[str](field_name="id", values=None)))
    assert len(existing_obj) > 0


async def test_repo_json_methods(
    raw_rules_uuid: RawRecordData,
    rule_repo: RuleRepository,
    rule_service: RuleService,
    rule_model: RuleModel,
) -> None:
    if rule_repo._dialect.name.startswith("spanner") and os.environ.get("SPANNER_EMULATOR_HOST"):  # pyright: ignore[reportPrivateUsage]
        pytest.skip("Skipped on emulator")

    exp_count = len(raw_rules_uuid) + 1
    new_rule = rule_model(name="Testing", config={"an": "object"})
    obj = await maybe_async(rule_repo.add(new_rule))
    count = await maybe_async(rule_repo.count())
    assert exp_count == count
    assert isinstance(obj, rule_model)
    assert new_rule.name == obj.name
    assert new_rule.config == obj.config  # pyright: ignore
    assert obj.id is not None
    obj.config = {"the": "update"}
    updated = await maybe_async(rule_repo.update(obj))
    assert obj.config == updated.config  # pyright: ignore

    get_obj, get_created = await maybe_async(
        rule_repo.get_or_upsert(match_fields=["name"], name="Secondary loading rule.", config={"another": "object"}),
    )
    assert get_created is False
    assert get_obj.id is not None
    assert get_obj.config == {"another": "object"}  # pyright: ignore

    new_obj, new_created = await maybe_async(
        rule_repo.get_or_upsert(match_fields=["name"], name="New rule.", config={"new": "object"}),
    )
    assert new_created is True
    assert new_obj.id is not None
    assert new_obj.config == {"new": "object"}  # pyright: ignore


async def test_repo_fetched_value(
    model_with_fetched_value_repo: ModelWithFetchedValueRepository,
    model_with_fetched_value: ModelWithFetchedValue,
    request: FixtureRequest,
) -> None:
    if any(fixture in request.fixturenames for fixture in ["mock_async_engine", "mock_sync_engine"]):
        pytest.skip(f"{SQLAlchemyAsyncMockRepository.__name__} does not works with fetched values")
    obj = await maybe_async(model_with_fetched_value_repo.add(model_with_fetched_value(val=1)))
    first_time = obj.updated
    assert first_time is not None
    assert obj.val == 1
    await maybe_async(model_with_fetched_value_repo.session.commit())
    await maybe_async(asyncio.sleep(2))
    obj.val = 2
    obj = await maybe_async(model_with_fetched_value_repo.update(obj))
    assert obj.updated is not None
    assert obj.val == 2
    assert obj.updated != first_time


async def test_lazy_load(
    item_repo: ItemRepository,
    tag_repo: TagRepository,
    item_model: ItemModel,
    tag_model: TagModel,
) -> None:
    if getattr(tag_repo, "__collection__", None) is not None:
        pytest.skip("Skipping lazy load testing on Mock repositories.")
    tag_obj = await maybe_async(tag_repo.add(tag_model(name="A new tag")))
    assert tag_obj
    new_items = await maybe_async(
        item_repo.add_many([item_model(name="The first item"), item_model(name="The second item")]),
    )
    await maybe_async(item_repo.session.commit())
    await maybe_async(tag_repo.session.commit())
    assert len(new_items) > 0
    first_item_id = new_items[0].id
    new_items[1].id
    update_data = {
        "name": "A modified Name",
        "tag_names": ["A new tag"],
        "id": first_item_id,
    }
    tags_to_add = await maybe_async(tag_repo.list(CollectionFilter("name", update_data.pop("tag_names", []))))  # type: ignore
    assert len(tags_to_add) > 0  # pyright: ignore
    assert tags_to_add[0].id is not None  # pyright: ignore
    update_data["tags"] = tags_to_add  # type: ignore[assignment]
    updated_obj = await maybe_async(item_repo.update(item_model(**update_data), auto_refresh=False))
    await maybe_async(item_repo.session.commit())
    assert len(updated_obj.tags) > 0
    assert updated_obj.tags[0].name == "A new tag"


async def test_repo_health_check(author_repo: AnyAuthorRepository) -> None:
    healthy = await maybe_async(author_repo.check_health(author_repo.session))
    assert healthy


async def test_repo_encrypted_methods(
    raw_secrets_uuid: RawRecordData,
    secret_repo: SecretRepository,
    raw_secrets: RawRecordData,
    first_secret_id: Any,
    secret_model: SecretModel,
) -> None:
    existing_obj = await maybe_async(secret_repo.get(first_secret_id))
    assert existing_obj.secret == raw_secrets[0]["secret"]
    assert existing_obj.long_secret == raw_secrets[0]["long_secret"]

    exp_count = len(raw_secrets_uuid) + 1
    new_secret = secret_model(secret="hidden data", long_secret="another longer secret")
    obj = await maybe_async(secret_repo.add(new_secret))
    count = await maybe_async(secret_repo.count())
    assert exp_count == count
    assert isinstance(obj, secret_model)
    assert new_secret.secret == obj.secret
    assert new_secret.long_secret == obj.long_secret
    assert obj.id is not None
    obj.secret = "new secret value"
    obj.long_secret = "new long secret value"
    updated = await maybe_async(secret_repo.update(obj))
    assert obj.secret == updated.secret
    assert obj.long_secret == updated.long_secret
