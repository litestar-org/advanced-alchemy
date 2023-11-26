from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from advanced_alchemy import SQLAlchemyAsyncMockRepository
from advanced_alchemy.repository.typing import ModelT


def update_raw_records(raw_authors: list[dict[str, Any]], raw_rules: list[dict[str, Any]]) -> None:
    for raw_author in raw_authors:
        raw_author["dob"] = datetime.strptime(raw_author["dob"], "%Y-%m-%d").date()
        raw_author["created_at"] = datetime.strptime(raw_author["created_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            timezone.utc,
        )
        raw_author["updated_at"] = datetime.strptime(raw_author["updated_at"], "%Y-%m-%dT%H:%M:%S").astimezone(
            timezone.utc,
        )
    for raw_rule in raw_rules:
        raw_rule["created_at"] = datetime.strptime(raw_rule["created_at"], "%Y-%m-%dT%H:%M:%S").astimezone(timezone.utc)
        raw_rule["updated_at"] = datetime.strptime(raw_rule["updated_at"], "%Y-%m-%dT%H:%M:%S").astimezone(timezone.utc)


def get_mock_repo_type(model: type[ModelT]) -> type[SQLAlchemyAsyncMockRepository[ModelT]]:
    class _MockRepository(SQLAlchemyAsyncMockRepository[Any]):
        model_type = model

    _MockRepository.__name__ = f"{model}AsyncMockRepository"
    return _MockRepository


def get_mock_repo(model_type: type[ModelT]) -> SQLAlchemyAsyncMockRepository[ModelT]:
    return get_mock_repo_type(model_type)()
