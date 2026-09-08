"""Regression test for GitHub issue #790.

``service.update()`` with an existing ``item_id`` copies the attributes
produced by ``to_model_on_update()`` onto the fetched, session-attached
instance. A common pattern for handling many-to-many relationships in that
hook is to build a transient model and assign already-persistent related
rows onto one of its relationships, e.g.::

    async def to_model_on_update(self, data):
        data = schema_dump(data)
        role_ids = data.pop("roles", None)
        model = await self.to_model(data)
        if role_ids is not None:
            model.roles = await RoleRepository(
                session=self.repository.session
            ).get_many(
                CollectionFilter(
                    field_name="id", values=role_ids
                )
            )
        return model

Because ``back_populates`` synchronization is a Python-side event that fires
regardless of session state, that assignment also appends the transient
``model`` into each related ``Role.users`` collection - even though ``model``
is discarded immediately after and never added to the session. The next
autoflush then tries to write that pairing, fails because the transient side
has no identity, and emits::

    SAWarning: Object of type <User> not in session, add operation along
    'Role.users' won't proceed

The secondary-table rows still end up correct (the real, session-attached
instance is what ultimately gets assigned), so the warning is spurious - but
it makes callers suspect the update silently failed.
"""

from __future__ import annotations

import warnings
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, attribute_keyed_dict, mapped_column, relationship, selectinload

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.filters import CollectionFilter
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from advanced_alchemy.utils.serialization import schema_dump

pytestmark = [pytest.mark.integration, pytest.mark.aiosqlite]


user_role_790 = Table(
    "user_role_790",
    UUIDBase.metadata,
    Column("user_id", ForeignKey("user_790.id"), primary_key=True),
    Column("role_id", ForeignKey("role_790.id"), primary_key=True),
)


class User790(UUIDBase):
    __tablename__ = "user_790"

    alias: Mapped[str] = mapped_column(String(50))
    roles: Mapped[list[Role790]] = relationship(secondary=user_role_790, back_populates="users", lazy="raise")


class Role790(UUIDBase):
    __tablename__ = "role_790"

    name: Mapped[str] = mapped_column(String(50))
    users: Mapped[list[User790]] = relationship(secondary=user_role_790, back_populates="roles", lazy="raise")


class RoleRepository790(SQLAlchemyAsyncRepository[Role790]):
    model_type = Role790


class UserRepository790(SQLAlchemyAsyncRepository[User790]):
    model_type = User790


class UserService790(SQLAlchemyAsyncRepositoryService[User790]):
    repository_type = UserRepository790

    async def to_model_on_update(self, data: Any) -> Any:
        data = schema_dump(data)
        role_ids = data.pop("roles", None)
        model = await self.to_model(data)
        if role_ids is not None:
            model.roles = await RoleRepository790(session=self.repository.session).get_many(
                CollectionFilter(field_name="id", values=role_ids)
            )
        return model


@pytest.fixture
async def user_790_session() -> Any:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(UUIDBase.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


def _sa_warnings(caught: list[warnings.WarningMessage]) -> list[warnings.WarningMessage]:
    return [w for w in caught if "not in session" in str(w.message)]


async def test_service_update_m2m_relationship_no_sawarning_github_790(user_790_session: AsyncSession) -> None:
    """``service.update()`` must not emit a spurious SAWarning when
    ``to_model_on_update`` resolves many-to-many ids into related objects,
    and the association rows must be persisted correctly (GitHub #790)."""
    session = user_790_session
    role1 = Role790(name="admin")
    role2 = Role790(name="editor")
    user = User790(alias="orig")
    session.add_all([role1, role2, user])
    await session.commit()
    user_id: UUID = user.id
    role_ids = [role1.id, role2.id]

    service = UserService790(session=session)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        updated = await service.update(
            {"roles": role_ids, "alias": "x"},
            user_id,
            load=[selectinload(User790.roles)],
            auto_commit=True,
        )

    assert not _sa_warnings(caught), [str(w.message) for w in _sa_warnings(caught)]
    assert updated.alias == "x"

    # Re-fetch independently to confirm the association rows were actually written.
    # ``auto_refresh`` expires the lazy="raise" collection on ``updated``, so verify
    # through a fresh session rather than accessing ``updated.roles`` directly.
    async with AsyncSession(session.bind, expire_on_commit=False) as check_session:
        check = await check_session.get(User790, user_id)
        assert check is not None
        await check_session.refresh(check, attribute_names=["roles"])
        assert sorted(r.name for r in check.roles) == ["admin", "editor"]


async def test_service_update_m2m_relationship_clear_no_sawarning_github_790(
    user_790_session: AsyncSession,
) -> None:
    """Boundary case: clearing a many-to-many relationship to an empty list
    through the same hook must also be warning-free and persist correctly."""
    session = user_790_session
    role1 = Role790(name="admin")
    user = User790(alias="orig")
    session.add_all([role1, user])
    await session.commit()
    # Associate role1 with user directly through the secondary table, avoiding
    # any relationship access before commit (roles is ``lazy="raise"``).
    await session.execute(user_role_790.insert().values(user_id=user.id, role_id=role1.id))
    await session.commit()
    user_id: UUID = user.id

    service = UserService790(session=session)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        updated = await service.update(
            {"roles": [], "alias": "cleared"},
            user_id,
            load=[selectinload(User790.roles)],
            auto_commit=True,
        )

    assert not _sa_warnings(caught), [str(w.message) for w in _sa_warnings(caught)]
    assert updated.alias == "cleared"

    # Re-fetch independently: ``auto_refresh`` expires the lazy="raise" collection
    # on ``updated``, so check persistence through a fresh session instead of
    # accessing ``updated.roles`` directly.
    async with AsyncSession(session.bind, expire_on_commit=False) as check_session:
        check = await check_session.get(User790, user_id)
        assert check is not None
        await check_session.refresh(check, attribute_names=["roles"])
        assert list(check.roles) == []


team_member_790 = Table(
    "team_member_790",
    UUIDBase.metadata,
    Column("team_id", ForeignKey("team_790.id"), primary_key=True),
    Column("member_id", ForeignKey("member_790.id"), primary_key=True),
)


class Team790(UUIDBase):
    __tablename__ = "team_790"

    label: Mapped[str] = mapped_column(String(50))
    members: Mapped[dict[str, Member790]] = relationship(
        secondary=team_member_790,
        collection_class=attribute_keyed_dict("name"),
        back_populates="teams",
        lazy="raise",
    )


class Member790(UUIDBase):
    __tablename__ = "member_790"

    name: Mapped[str] = mapped_column(String(50))
    teams: Mapped[list[Team790]] = relationship(secondary=team_member_790, back_populates="members", lazy="raise")


class MemberRepository790(SQLAlchemyAsyncRepository[Member790]):
    model_type = Member790


class TeamRepository790(SQLAlchemyAsyncRepository[Team790]):
    model_type = Team790


class TeamService790(SQLAlchemyAsyncRepositoryService[Team790]):
    repository_type = TeamRepository790

    async def to_model_on_update(self, data: Any) -> Any:
        data = schema_dump(data)
        member_ids = data.pop("members", None)
        model = await self.to_model(data)
        if member_ids is not None:
            members = await MemberRepository790(session=self.repository.session).get_many(
                CollectionFilter(field_name="id", values=member_ids)
            )
            model.members = {member.name: member for member in members}
        return model


async def test_service_update_m2m_dict_collection_no_sawarning_github_790(user_790_session: AsyncSession) -> None:
    """A dict-keyed collection (``attribute_keyed_dict``) assigned by the hook is a
    mapping of related objects, not one related object; it must be detached per
    value and must not raise."""
    session = user_790_session
    alice = Member790(name="alice")
    bob = Member790(name="bob")
    team = Team790(label="orig")
    session.add_all([alice, bob, team])
    await session.commit()
    team_id: UUID = team.id

    service = TeamService790(session=session)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        updated = await service.update(
            {"members": [alice.id, bob.id], "label": "renamed"},
            team_id,
            load=[selectinload(Team790.members)],
            auto_commit=True,
        )

    assert not _sa_warnings(caught), [str(w.message) for w in _sa_warnings(caught)]
    assert updated.label == "renamed"

    async with AsyncSession(session.bind, expire_on_commit=False) as check_session:
        check = await check_session.get(Team790, team_id)
        assert check is not None
        await check_session.refresh(check, attribute_names=["members"])
        assert sorted(check.members) == ["alice", "bob"]
