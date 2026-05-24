"""Async Google ADK memory service implementation."""

import datetime
import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal, Optional, Union
from typing import cast as type_cast

from google.adk.events.event import Event
from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions.session import Session as ADKSessionModel
from google.genai import types
from sqlalchemy import Select, cast, func, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import String

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.adk.models import ADKMemoryModelMixin

ADKMemoryEmbeddingProvider = Callable[[str], Union[Sequence[float], Awaitable[Sequence[float]]]]
ADKVectorDistanceMetric = Literal["cosine", "l2", "inner_product"]


class ADKAsyncMemoryService(BaseMemoryService):
    """Async SQLAlchemy-backed implementation of Google ADK's memory contract."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        memory_model: type[ADKMemoryModelMixin],
        max_results: int = 50,
        use_fts: Optional[bool] = None,
        embedding_provider: Optional[ADKMemoryEmbeddingProvider] = None,
        use_vector: Optional[bool] = None,
        vector_distance_metric: ADKVectorDistanceMetric = "cosine",
    ) -> None:
        self.session = session
        self.memory_model = memory_model
        self.max_results = max_results
        self.use_fts = use_fts
        self.embedding_provider = embedding_provider
        self.use_vector = use_vector
        self.vector_distance_metric = vector_distance_metric

    async def add_session_to_memory(self, session: ADKSessionModel) -> None:
        """Add all content-bearing events from a session to memory."""
        await self.add_events_to_memory(
            app_name=session.app_name,
            user_id=session.user_id,
            session_id=session.id,
            events=session.events,
        )

    async def add_events_to_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        events: Sequence[Event],
        session_id: Optional[str] = None,
        custom_metadata: Optional[Mapping[str, object]] = None,
    ) -> None:
        """Add an explicit event delta to memory, deduplicating by memory ID."""
        event_ids = [event.id for event in events if event.id]
        existing_ids = await self._existing_memory_ids(app_name=app_name, user_id=user_id, memory_ids=event_ids)
        metadata = dict(custom_metadata or {})
        for event in events:
            if not event.id or event.id in existing_ids or event.content is None or not event.content.parts:
                continue
            content_text = self._content_to_text(event.content)
            vector_embedding = await self._embedding_for_text(content_text)
            memory_data: dict[str, object] = {
                "memory_id": event.id,
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
                "event_id": event.id,
                "author": event.author,
                "timestamp": datetime.datetime.fromtimestamp(event.timestamp, tz=datetime.timezone.utc),
                "content_json": event.content.model_dump(exclude_none=True, mode="json"),
                "content_text": content_text,
                "metadata_json": metadata,
            }
            if vector_embedding is not None:
                memory_data["embedding"] = vector_embedding
            self.session.add(
                self.memory_model(**memory_data),
            )
            existing_ids.add(event.id)
        await self.session.flush()

    async def add_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        memories: Sequence[MemoryEntry],
        custom_metadata: Optional[Mapping[str, object]] = None,
    ) -> None:
        """Add explicit memory entries directly."""
        memory_ids = [memory.id for memory in memories if memory.id]
        existing_ids = await self._existing_memory_ids(app_name=app_name, user_id=user_id, memory_ids=memory_ids)
        shared_metadata = dict(custom_metadata or {})
        for memory in memories:
            memory_id = memory.id or self._new_memory_id()
            if memory_id in existing_ids:
                continue
            metadata = {**shared_metadata, **(memory.custom_metadata or {})}
            content_text = self._content_to_text(memory.content)
            vector_embedding = await self._embedding_for_text(content_text)
            memory_data: dict[str, object] = {
                "memory_id": memory_id,
                "app_name": app_name,
                "user_id": user_id,
                "session_id": None,
                "event_id": memory.id,
                "author": memory.author,
                "timestamp": self._parse_memory_timestamp(memory.timestamp),
                "content_json": memory.content.model_dump(exclude_none=True, mode="json"),
                "content_text": content_text,
                "metadata_json": metadata,
            }
            if vector_embedding is not None:
                memory_data["embedding"] = vector_embedding
            self.session.add(
                self.memory_model(**memory_data),
            )
            existing_ids.add(memory_id)
        await self.session.flush()

    async def search_memory(self, *, app_name: str, user_id: str, query: str) -> SearchMemoryResponse:
        """Search memory entries for an app/user scope."""
        statement = await self._search_statement(app_name=app_name, user_id=user_id, query=query)
        result = await self.session.scalars(statement)
        return SearchMemoryResponse(memories=[self._to_memory_entry(memory) for memory in result.all()])

    async def _existing_memory_ids(self, *, app_name: str, user_id: str, memory_ids: Sequence[str]) -> set[str]:
        if not memory_ids:
            return set()
        result = await self.session.scalars(
            select(self.memory_model.memory_id)
            .where(self.memory_model.app_name == app_name)
            .where(self.memory_model.user_id == user_id)
            .where(self.memory_model.memory_id.in_(memory_ids)),
        )
        return set(result.all())

    async def _search_statement(self, *, app_name: str, user_id: str, query: str) -> Select[tuple[ADKMemoryModelMixin]]:
        statement = (
            select(self.memory_model)
            .where(self.memory_model.app_name == app_name)
            .where(self.memory_model.user_id == user_id)
            .limit(self.max_results)
        )
        vector_embedding = await self._embedding_for_text(query)
        if vector_embedding is not None:
            return self._vector_search_statement(statement, vector_embedding)
        if self._should_use_fts():
            rank = func.ts_rank(
                func.to_tsvector(literal("english"), self.memory_model.content_text),
                func.plainto_tsquery(literal("english"), query),
            )
            return (
                statement.where(
                    text("to_tsvector('english', content_text) @@ plainto_tsquery('english', :query)").bindparams(
                        query=query,
                    ),
                )
                .order_by(rank.desc(), self.memory_model.timestamp.desc())
                .limit(self.max_results)
            )
        pattern = f"%{query}%"
        return statement.where(
            or_(
                self.memory_model.content_text.ilike(pattern),
                cast(self.memory_model.content_json, String).ilike(pattern),
            ),
        ).order_by(self.memory_model.timestamp.desc())

    def _vector_search_statement(
        self,
        statement: Select[tuple[ADKMemoryModelMixin]],
        embedding: Sequence[float],
    ) -> Select[tuple[ADKMemoryModelMixin]]:
        embedding_column = self._embedding_column()
        distance = self._vector_distance_expression(embedding_column, embedding)
        return statement.where(embedding_column.is_not(None)).order_by(distance, self.memory_model.timestamp.desc())

    def _vector_distance_expression(self, embedding_column: Any, embedding: Sequence[float]) -> Any:
        if self.vector_distance_metric == "l2":
            return embedding_column.l2_distance(embedding)
        if self.vector_distance_metric == "inner_product":
            return embedding_column.max_inner_product(embedding)
        return embedding_column.cosine_distance(embedding)

    async def _embedding_for_text(self, text_value: str) -> Optional[list[float]]:
        if not self._should_use_vector():
            return None
        if self.embedding_provider is None:
            return None
        embedding = self.embedding_provider(text_value)
        if inspect.isawaitable(embedding):
            embedding = await embedding
        return [float(value) for value in embedding]

    def _should_use_vector(self) -> bool:
        has_vector_model = self._has_embedding_column()
        has_provider = self.embedding_provider is not None
        is_postgresql = self._is_postgresql()
        can_use_vector = has_vector_model and has_provider and is_postgresql
        if self.use_vector is True and not can_use_vector:
            missing: list[str] = []
            if not has_vector_model:
                missing.append("memory model embedding column")
            if not has_provider:
                missing.append("embedding provider")
            if not is_postgresql:
                missing.append("PostgreSQL database bind")
            msg = f"Vector memory requires {', '.join(missing)}."
            raise ImproperConfigurationError(msg)
        if self.use_vector is False:
            return False
        return can_use_vector

    def _has_embedding_column(self) -> bool:
        return hasattr(self.memory_model, "embedding")

    def _embedding_column(self) -> Any:
        return type_cast("Any", self.memory_model).embedding

    def _is_postgresql(self) -> bool:
        bind = self.session.get_bind()
        return bool(bind and bind.dialect.name == "postgresql")

    def _should_use_fts(self) -> bool:
        if self.use_fts is not None:
            return self.use_fts
        return self._is_postgresql()

    @staticmethod
    def _to_memory_entry(memory: ADKMemoryModelMixin) -> MemoryEntry:
        return MemoryEntry(
            id=memory.memory_id,
            content=types.Content.model_validate(memory.content_json),
            author=memory.author,
            timestamp=memory.timestamp.isoformat(),
            custom_metadata=memory.metadata_json or {},
        )

    @staticmethod
    def _content_to_text(content: types.Content) -> str:
        parts = content.parts or []
        text_parts = [part.text for part in parts if part.text]
        if text_parts:
            return " ".join(text_parts)
        return content.model_dump_json(exclude_none=True)

    @staticmethod
    def _parse_memory_timestamp(timestamp: Optional[str]) -> datetime.datetime:
        if timestamp is None:
            return datetime.datetime.now(tz=datetime.timezone.utc)
        value = timestamp.removesuffix("Z")
        parsed = datetime.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed

    @staticmethod
    def _new_memory_id() -> str:
        from google.adk.platform import uuid as platform_uuid

        return platform_uuid.new_uuid()


__all__ = ("ADKAsyncMemoryService", "ADKMemoryEmbeddingProvider", "ADKVectorDistanceMetric")
