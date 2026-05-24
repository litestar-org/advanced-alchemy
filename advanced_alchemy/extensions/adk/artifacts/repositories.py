"""Repository classes for Google ADK artifact persistence."""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from advanced_alchemy.extensions.adk.artifacts.models import ADKArtifact
from advanced_alchemy.repository import SQLAlchemyAsyncRepository


class ADKArtifactRepository(SQLAlchemyAsyncRepository[ADKArtifact]):
    """Repository for ADK artifacts."""

    model_type = ADKArtifact

    def __init__(self, *, session: AsyncSession) -> None:
        super().__init__(session=session)

    async def get_max_version(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
    ) -> Optional[int]:
        """Return the current max version for an artifact key."""
        statement = (
            select(func.max(ADKArtifact.version))
            .where(ADKArtifact.app_name == app_name)
            .where(ADKArtifact.user_id == user_id)
            .where(ADKArtifact.session_id == session_id)
            .where(ADKArtifact.filename == filename)
        )
        return await self.session.scalar(statement)


__all__ = ("ADKArtifactRepository",)
