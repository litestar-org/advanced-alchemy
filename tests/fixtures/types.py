from __future__ import annotations

from typing import Any, Dict, List, Literal, Type, Union

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemyAsyncSlugRepository
from advanced_alchemy.repository.memory import (
    SQLAlchemyAsyncMockRepository,
)
from advanced_alchemy.service import (
    SQLAlchemyAsyncRepositoryService,
)
from tests.fixtures.bigint import models as models_bigint
from tests.fixtures.uuid import models as models_uuid

AnySession = Type[Union[AsyncSession, Session]]
RepositoryPKType = Literal["uuid", "bigint"]
SessionType = Literal["sync", "async"]
SecretModel = Type[Union[models_uuid.UUIDSecret, models_bigint.BigIntSecret]]
AuthorModel = Type[Union[models_uuid.UUIDAuthor, models_bigint.BigIntAuthor]]
RuleModel = Type[Union[models_uuid.UUIDRule, models_bigint.BigIntRule]]
ModelWithFetchedValue = Type[Union[models_uuid.UUIDModelWithFetchedValue, models_bigint.BigIntModelWithFetchedValue]]
ItemModel = Type[Union[models_uuid.UUIDItem, models_bigint.BigIntItem]]
TagModel = Type[Union[models_uuid.UUIDTag, models_bigint.BigIntTag]]
SlugBookModel = Type[Union[models_uuid.UUIDSlugBook, models_bigint.BigIntSlugBook]]
BookModel = Type[Union[models_uuid.UUIDBook, models_bigint.BigIntBook]]


AnySecret = Union[models_uuid.UUIDSecret, models_bigint.BigIntSecret]
SecretRepository = SQLAlchemyAsyncRepository[AnySecret]
SecretService = SQLAlchemyAsyncRepositoryService[AnySecret]
SecretMockRepository = SQLAlchemyAsyncMockRepository[AnySecret]
AnySecretRepository = Union[SecretRepository, SecretMockRepository]

AnyAuthor = Union[models_uuid.UUIDAuthor, models_bigint.BigIntAuthor]
AuthorRepository = SQLAlchemyAsyncRepository[AnyAuthor]
AuthorMockRepository = SQLAlchemyAsyncMockRepository[AnyAuthor]
AnyAuthorRepository = Union[AuthorRepository, AuthorMockRepository]
AuthorService = SQLAlchemyAsyncRepositoryService[AnyAuthor]

AnyRule = Union[models_uuid.UUIDRule, models_bigint.BigIntRule]
RuleRepository = SQLAlchemyAsyncRepository[AnyRule]
RuleService = SQLAlchemyAsyncRepositoryService[AnyRule]

AnySlugBook = Union[models_uuid.UUIDSlugBook, models_bigint.BigIntSlugBook]
SlugBookRepository = SQLAlchemyAsyncSlugRepository[AnySlugBook]
SlugBookService = SQLAlchemyAsyncRepositoryService[AnySlugBook]


AnyBook = Union[models_uuid.UUIDBook, models_bigint.BigIntBook]
BookRepository = SQLAlchemyAsyncRepository[AnyBook]
BookService = SQLAlchemyAsyncRepositoryService[AnyBook]

AnyTag = Union[models_uuid.UUIDTag, models_bigint.BigIntTag]
TagRepository = SQLAlchemyAsyncRepository[AnyTag]
TagService = SQLAlchemyAsyncRepositoryService[AnyTag]

AnyItem = Union[models_uuid.UUIDItem, models_bigint.BigIntItem]
ItemRepository = SQLAlchemyAsyncRepository[AnyItem]
ItemService = SQLAlchemyAsyncRepositoryService[AnyItem]

AnyModelWithFetchedValue = Union[models_uuid.UUIDModelWithFetchedValue, models_bigint.BigIntModelWithFetchedValue]
ModelWithFetchedValueRepository = SQLAlchemyAsyncRepository[AnyModelWithFetchedValue]
ModelWithFetchedValueService = SQLAlchemyAsyncRepositoryService[AnyModelWithFetchedValue]
RawRecordData = List[Dict[str, Any]]
